"""
fetch_prices.py — Sovson Indicator Lab
Pulls daily OHLCV price data for all tickers in config/tickers.json
using yahooquery and stores it in the SQLite database.

Run manually:  python3 scripts/fetch_prices.py
Or via cron:   0 21 * * 1-5 cd /path/to/project && python3 scripts/fetch_prices.py
               (runs at 9pm UTC / 1pm PST, Monday–Friday, after market close)
"""

import os
import json
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


# ── Price fetching ─────────────────────────────────────────────────────────────
def fetch_prices_for_ticker(ticker, start_date, end_date):
    """
    Fetch OHLCV data from Yahoo Finance via yahooquery.
    Returns a list of dicts, one per trading day.
    """
    log.info(f"  Fetching {ticker} from {start_date} to {end_date} ...")
    try:
        t = Ticker(ticker)
        df = t.history(start=start_date, end=end_date)

        if df is None or df.empty:
            log.warning(f"  No data returned for {ticker}.")
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
        log.error(f"  Error fetching {ticker}: {e}")
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
    conn = get_connection()
    setup_database(conn)

    tickers = load_tickers()
    log.info(f"Tickers: {tickers}")
    register_tickers(conn, tickers)

    today     = datetime.today().date()
    total_new = 0

    for ticker in tickers:
        last_date = get_last_stored_date(conn, ticker)

        if last_date:
            # Start from the day after last stored date
            start = (datetime.strptime(last_date, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
            log.info(f"{ticker}: last stored date is {last_date}, fetching from {start}")
        else:
            # First run — go back INITIAL_HISTORY_DAYS
            start = (today - timedelta(days=INITIAL_HISTORY_DAYS)).isoformat()
            log.info(f"{ticker}: no data yet, fetching {INITIAL_HISTORY_DAYS} days of history from {start}")

        end = today.isoformat()

        if start >= end:
            log.info(f"{ticker}: already up to date, skipping.")
            continue

        rows    = fetch_prices_for_ticker(ticker, start, end)
        new     = save_prices(conn, rows)
        total_new += new
        log.info(f"{ticker}: saved {new} new rows.")

    conn.close()
    log.info(f"=== Done. Total new rows inserted: {total_new} ===")


if __name__ == "__main__":
    main()
