"""
fetch_prices.py — Sovson Indicator Lab
Pulls daily OHLCV price data for all tickers in config/tickers.json
using yahooquery and stores it in the SQLite database.

Run manually:  python3 scripts/fetch_prices.py
Or via cron:   0 21 * * 1-5 cd /path/to/project && python3 scripts/fetch_prices.py
               (runs at 9pm UTC / 1pm PST, Monday–Friday, after market close)
"""

import os
import sys
import json
import time
import random
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from yahooquery import Ticker

# ── Setup ──────────────────────────────────────────────────────────────────────
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "indicators.db"
CFG_PATH = BASE_DIR / "config" / "tickers.json"
LOG_PATH = BASE_DIR / "logs" / "fetch_prices.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

INITIAL_HISTORY_DAYS = int(os.getenv("INITIAL_HISTORY_DAYS", 365))

# Retry settings for Yahoo Finance rate limiting (HTTP 429 / "Failed to obtain crumb")
MAX_RETRIES         = 3
BASE_BACKOFF_SECS   = 10      # first retry waits ~10s, then ~20s, then ~40s (+ jitter)
DELAY_BETWEEN_TICKERS_SECS = 2   # small gap between tickers so we don't hammer Yahoo in a burst


# ── Database setup ─────────────────────────────────────────────────────────────
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def setup_database(conn):
    """Create tables if they don't exist yet."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            open        REAL,
            high        REAL,
            low         REAL,
            close       REAL,
            volume      INTEGER,
            fetched_at  TEXT    DEFAULT (datetime('now')),
            UNIQUE(ticker, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            ticker      TEXT PRIMARY KEY,
            active      INTEGER DEFAULT 1,
            added_at    TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    log.info("Database tables verified.")


# ── Ticker management ──────────────────────────────────────────────────────────
def load_tickers():
    with open(CFG_PATH) as f:
        data = json.load(f)
    return [t.upper() for t in data["tickers"]]


def register_tickers(conn, tickers):
    """Make sure every ticker in config exists in the tickers table."""
    for ticker in tickers:
        conn.execute(
            "INSERT OR IGNORE INTO tickers (ticker) VALUES (?)", (ticker,)
        )
    conn.commit()


# ── Last stored date helper ────────────────────────────────────────────────────
def get_last_stored_date(conn, ticker):
    """Returns the most recent date we have data for, or None if no data."""
    row = conn.execute(
        "SELECT MAX(date) as last_date FROM daily_prices WHERE ticker = ?",
        (ticker,)
    ).fetchone()
    return row["last_date"] if row and row["last_date"] else None


def _is_rate_limit_error(err) -> bool:
    """Detect Yahoo Finance rate limiting / crumb failures from the exception text."""
    msg = str(err).lower()
    return "429" in msg or "crumb" in msg or "too many" in msg


# ── Price fetching ─────────────────────────────────────────────────────────────
def fetch_prices_for_ticker(ticker, start_date, end_date):
    """
    Fetch OHLCV data from Yahoo Finance via yahooquery.
    Returns a list of dicts, one per trading day.
    Retries with exponential backoff if Yahoo rate-limits us (HTTP 429 /
    "Failed to obtain crumb"), since that's a transient, not permanent, failure.
    """
    log.info(f"  Fetching {ticker} from {start_date} to {end_date} ...")

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            t = Ticker(ticker)
            df = t.history(start=start_date, end=end_date)

            if df is None or df.empty:
                # An empty result isn't necessarily "no new data" — Yahoo
                # sometimes hasn't finished publishing the day's EOD candle
                # yet right after market close, or silently rate-limits us
                # without raising an exception we can detect by message.
                # Treat it as transient and retry, same as a rate-limit hit,
                # instead of accepting it as final and moving on with stale
                # data.
                if attempt < MAX_RETRIES:
                    backoff = BASE_BACKOFF_SECS * (2 ** (attempt - 1)) + random.uniform(0, 3)
                    log.warning(
                        f"  {ticker}: empty result on attempt {attempt}/{MAX_RETRIES} "
                        f"(data may not be published yet, or a silent rate limit). "
                        f"Retrying in {backoff:.1f}s ..."
                    )
                    time.sleep(backoff)
                    continue
                log.error(
                    f"  {ticker}: still empty after {MAX_RETRIES} attempts. "
                    f"Giving up for this run — will retry next scheduled run."
                )
                return []

            # yahooquery returns a MultiIndex dataframe (symbol, date)
            if hasattr(df.index, 'levels'):
                df = df.xs(ticker, level=0)

            df = df.reset_index()
            df = df.rename(columns={"date": "date"})

            rows = []
            for _, row in df.iterrows():
                rows.append({
                    "ticker": ticker,
                    "date":   str(row["date"])[:10],  # YYYY-MM-DD
                    "open":   round(float(row["open"]),  4),
                    "high":   round(float(row["high"]),  4),
                    "low":    round(float(row["low"]),   4),
                    "close":  round(float(row["close"]), 4),
                    "volume": int(row["volume"]),
                })
            log.info(f"  Got {len(rows)} rows for {ticker}.")
            return rows

        except Exception as e:
            last_err = e
            if _is_rate_limit_error(e) and attempt < MAX_RETRIES:
                backoff = BASE_BACKOFF_SECS * (2 ** (attempt - 1)) + random.uniform(0, 3)
                log.warning(
                    f"  {ticker}: rate-limited by Yahoo (attempt {attempt}/{MAX_RETRIES}). "
                    f"Retrying in {backoff:.1f}s ..."
                )
                time.sleep(backoff)
                continue
            else:
                log.error(f"  Error fetching {ticker}: {e}")
                return []

    log.error(f"  Giving up on {ticker} after {MAX_RETRIES} attempts: {last_err}")
    return []


def save_prices(conn, rows):
    """Insert rows, skipping any date we already have (UNIQUE constraint)."""
    inserted = 0
    for row in rows:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO daily_prices
                    (ticker, date, open, high, low, close, volume)
                VALUES
                    (:ticker, :date, :open, :high, :low, :close, :volume)
            """, row)
            if conn.total_changes > 0:
                inserted += 1
        except Exception as e:
            log.error(f"  DB insert error for {row}: {e}")
    conn.commit()
    return inserted


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log.info("=== fetch_prices.py starting ===")
    try:
        conn = get_connection()
        setup_database(conn)

        tickers = load_tickers()
        log.info(f"Tickers: {tickers}")
        register_tickers(conn, tickers)

        today     = datetime.today().date()
        total_new = 0
        failed_tickers = []

        for i, ticker in enumerate(tickers):
            try:
                last_date = get_last_stored_date(conn, ticker)

                if last_date:
                    # Start from the day after last stored date
                    start = (datetime.strptime(last_date, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
                    log.info(f"{ticker}: last stored date is {last_date}, fetching from {start}")
                else:
                    # First run — go back INITIAL_HISTORY_DAYS
                    start = (today - timedelta(days=INITIAL_HISTORY_DAYS)).isoformat()
                    log.info(f"{ticker}: no data yet, fetching {INITIAL_HISTORY_DAYS} days of history from {start}")

                # yahooquery/Yahoo's `end` boundary is exclusive, so a request
                # window of [start, today) never actually includes today's own
                # close — every run was landing one full trading day behind.
                # Push the boundary out by one day so today is included.
                end = (today + timedelta(days=1)).isoformat()

                if start > today.isoformat():
                    log.info(f"{ticker}: already up to date, skipping.")
                    continue

                rows = fetch_prices_for_ticker(ticker, start, end)
                if not rows:
                    log.warning(f"{ticker}: no price rows retrieved.")
                    failed_tickers.append(ticker)
                new = save_prices(conn, rows)
                total_new += new
                log.info(f"{ticker}: saved {new} new rows.")
            except Exception as ticker_err:
                log.error(f"Error processing ticker {ticker}: {ticker_err}")
                failed_tickers.append(ticker)

            # Small pause between tickers so we don't fire requests at Yahoo in
            # a tight burst — this is what triggered the 429s in the first place.
            if i < len(tickers) - 1:
                time.sleep(DELAY_BETWEEN_TICKERS_SECS)

        conn.close()
        log.info(f"=== Done. Total new rows inserted: {total_new} ===")
        if failed_tickers:
            log.warning(f"=== Tickers with no new data this run: {failed_tickers} ===")
    except Exception as fatal_err:
        log.critical(f"Fatal error in fetch_prices: {fatal_err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
