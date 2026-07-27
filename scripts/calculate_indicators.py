"""
calculate_indicators.py — Sovson Indicator Lab
Reads daily_prices from SQLite, calculates all four indicators,
and writes results to the indicators table.

Indicators calculated:
  - MACD (12/26/9)         — momentum / trend direction
  - RSI (14)               — overbought / oversold exhaustion
  - Bollinger Bands (20/2) — volatility envelope + price position
  - SMA 200                — long-term trend context

Run manually:  python3 scripts/calculate_indicators.py
"""

import sqlite3
import logging
import json
from pathlib import Path
import pandas as pd
import numpy as np

# ── Setup ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "indicators.db"
CFG_PATH = BASE_DIR / "config" / "tickers.json"
LOG_PATH = BASE_DIR / "logs" / "calculate_indicators.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ── Database ───────────────────────────────────────────────────────────────────
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def setup_indicators_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indicators (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker              TEXT    NOT NULL,
            date                TEXT    NOT NULL,

            -- MACD (12/26/9)
            macd_line           REAL,
            macd_signal         REAL,
            macd_histogram      REAL,
            macd_crossover      INTEGER,   -- 1 = bullish cross today
            macd_crossunder     INTEGER,   -- 1 = bearish cross today

            -- RSI (14)
            rsi                 REAL,
            rsi_overbought      INTEGER,   -- 1 = crossed above 70 today
            rsi_oversold        INTEGER,   -- 1 = crossed below 30 today

            -- Bollinger Bands (20/2)
            bb_upper            REAL,
            bb_middle           REAL,
            bb_lower            REAL,
            bb_position         REAL,      -- 0.0 = at lower band, 1.0 = at upper band

            -- SMA 200
            sma200              REAL,
            price_above_sma200  INTEGER,   -- 1 = price is above SMA200

            -- Close price (convenience)
            close               REAL,

            calculated_at       TEXT DEFAULT (datetime('now')),
            UNIQUE(ticker, date)
        )
    """)
    conn.commit()


# ── Indicator calculations ─────────────────────────────────────────────────────

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast   = calc_ema(close, fast)
    ema_slow   = calc_ema(close, slow)
    macd_line  = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_rsi(close, period=14):
    delta  = close.diff()
    gain   = delta.clip(lower=0)
    loss   = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_bollinger_bands(close, period=20, multiplier=2.0):
    middle = close.rolling(window=period).mean()
    std    = close.rolling(window=period).std()
    upper  = middle + multiplier * std
    lower  = middle - multiplier * std
    # Position: where is price within the bands? 0 = lower, 1 = upper
    band_width = upper - lower
    position = ((close - lower) / band_width).clip(0, 1)
    return upper, middle, lower, position


def calc_sma200(close, period=200):
    return close.rolling(window=period).mean()


def detect_crossover(series_a, series_b):
    """
    Returns a boolean series that is True on bars where series_a
    crossed above series_b (was below yesterday, is above today).
    """
    above_today     = series_a > series_b
    above_yesterday = above_today.shift(1).fillna(False).astype(bool)
    return (above_today & ~above_yesterday).fillna(False)


def detect_crossunder(series_a, series_b):
    """
    Returns a boolean series that is True on bars where series_a
    crossed below series_b.
    """
    below_today     = series_a < series_b
    below_yesterday = below_today.shift(1).fillna(False).astype(bool)
    return (below_today & ~below_yesterday).fillna(False)


# ── Per-ticker processing ──────────────────────────────────────────────────────

def load_prices(conn, ticker):
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume FROM daily_prices "
        "WHERE ticker = ? ORDER BY date ASC",
        (ticker,)
    ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"]  = pd.to_datetime(df["date"])
    df["close"] = df["close"].astype(float)
    return df


def calculate_for_ticker(conn, ticker):
    df = load_prices(conn, ticker)
    if df is None or len(df) < 30:
        log.warning(f"{ticker}: not enough data to calculate (need at least 30 rows).")
        return 0

    close = df["close"]

    # Calculate all indicators
    macd_line, signal_line, histogram = calc_macd(close)
    rsi                               = calc_rsi(close)
    bb_upper, bb_middle, bb_lower, bb_pos = calc_bollinger_bands(close)
    sma200                            = calc_sma200(close)

    # Detect crossover events
    macd_cross_up   = detect_crossover(macd_line, signal_line)
    macd_cross_down = detect_crossunder(macd_line, signal_line)

    rsi_threshold_70 = pd.Series(70, index=rsi.index)
    rsi_threshold_30 = pd.Series(30, index=rsi.index)
    rsi_overbought   = detect_crossover(rsi, rsi_threshold_70)
    rsi_oversold     = detect_crossunder(rsi, rsi_threshold_30)

    price_above_200  = (close > sma200).astype(int)

    # Build rows to insert
    inserted = 0
    for i in range(len(df)):
        row = df.iloc[i]
        date_str = row["date"].strftime("%Y-%m-%d")

        def v(series):
            val = series.iloc[i]
            if pd.isna(val):
                return None
            return round(float(val), 6)

        def b(series):
            val = series.iloc[i]
            if pd.isna(val):
                return None
            return int(bool(val))

        try:
            conn.execute("""
                INSERT OR REPLACE INTO indicators (
                    ticker, date,
                    macd_line, macd_signal, macd_histogram,
                    macd_crossover, macd_crossunder,
                    rsi, rsi_overbought, rsi_oversold,
                    bb_upper, bb_middle, bb_lower, bb_position,
                    sma200, price_above_sma200,
                    close
                ) VALUES (
                    ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?
                )
            """, (
                ticker, date_str,
                v(macd_line), v(signal_line), v(histogram),
                b(macd_cross_up), b(macd_cross_down),
                v(rsi), b(rsi_overbought), b(rsi_oversold),
                v(bb_upper), v(bb_middle), v(bb_lower), v(bb_pos),
                v(sma200), b(price_above_200),
                v(close)
            ))
            inserted += 1
        except Exception as e:
            log.error(f"{ticker} {date_str}: insert error — {e}")

    conn.commit()
    log.info(f"{ticker}: calculated and saved {inserted} rows.")
    return inserted


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log.info("=== calculate_indicators.py starting ===")
    try:
        conn = get_connection()
        setup_indicators_table(conn)

        with open(CFG_PATH) as f:
            tickers = [t.upper() for t in json.load(f)["tickers"]]

        log.info(f"Tickers: {tickers}")
        total = 0
        for ticker in tickers:
            try:
                total += calculate_for_ticker(conn, ticker)
            except Exception as ticker_err:
                log.error(f"Error calculating indicators for {ticker}: {ticker_err}")

        conn.close()
        log.info(f"=== Done. Total rows written: {total} ===")
    except Exception as fatal_err:
        log.critical(f"Fatal error in calculate_indicators: {fatal_err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
