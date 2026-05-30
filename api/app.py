"""
api/app.py — Sovson Indicator Lab
Flask API that exposes indicator data from SQLite.
This is what gets queried during Claude chat sessions.

Run:  python3 api/app.py
      Listens on http://0.0.0.0:5001 by default
"""

import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime

from flask import Flask, jsonify, request, abort
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "indicators.db"
CFG_PATH = BASE_DIR / "config" / "tickers.json"

app = Flask(__name__)

FLASK_PORT = int(os.getenv("FLASK_PORT", 5001))
API_KEY    = os.getenv("API_KEY", "")  # Optional: set in .env to require a key


# ── Auth middleware ────────────────────────────────────────────────────────────
@app.before_request
def check_api_key():
    """If API_KEY is set in .env, all requests must include it as a header."""
    if API_KEY:
        provided = request.headers.get("X-API-Key", "")
        if provided != API_KEY:
            abort(401)


# ── DB helper ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_tickers():
    with open(CFG_PATH) as f:
        return [t.upper() for t in json.load(f)["tickers"]]


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def health():
    """Quick health check — confirms the API is alive."""
    return jsonify({
        "status": "ok",
        "project": "Sovson Indicator Lab",
        "time": datetime.utcnow().isoformat() + "Z"
    })


@app.route("/tickers", methods=["GET"])
def list_tickers():
    """Returns all tickers currently in the config."""
    return jsonify({"tickers": load_tickers()})


@app.route("/prices/<ticker>", methods=["GET"])
def get_prices(ticker):
    """
    Returns recent OHLCV price data for a ticker.
    Query params:
      days=N  — how many recent trading days to return (default 60)
    """
    ticker = ticker.upper()
    days   = int(request.args.get("days", 60))

    conn = get_db()
    rows = conn.execute("""
        SELECT date, open, high, low, close, volume
        FROM daily_prices
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT ?
    """, (ticker, days)).fetchall()
    conn.close()

    if not rows:
        return jsonify({"error": f"No price data found for {ticker}"}), 404

    data = [dict(r) for r in rows]
    data.reverse()  # Return oldest first
    return jsonify({"ticker": ticker, "count": len(data), "prices": data})


@app.route("/indicators/<ticker>", methods=["GET"])
def get_indicators(ticker):
    """
    Returns the most recent indicator snapshot for a ticker.
    This is the primary endpoint for analysis.
    Query params:
      days=N  — how many recent days to return (default 30)
    """
    ticker = ticker.upper()
    days   = int(request.args.get("days", 30))

    conn = get_db()
    rows = conn.execute("""
        SELECT
            date, close,
            macd_line, macd_signal, macd_histogram,
            macd_crossover, macd_crossunder,
            rsi, rsi_overbought, rsi_oversold,
            bb_upper, bb_middle, bb_lower, bb_position,
            sma200, price_above_sma200
        FROM indicators
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT ?
    """, (ticker, days)).fetchall()
    conn.close()

    if not rows:
        return jsonify({"error": f"No indicator data found for {ticker}"}), 404

    data = [dict(r) for r in rows]
    data.reverse()  # Return oldest first
    return jsonify({"ticker": ticker, "count": len(data), "indicators": data})


@app.route("/snapshot/<ticker>", methods=["GET"])
def get_snapshot(ticker):
    """
    Returns the single most recent indicator row for a ticker.
    Most useful for a quick 'what is the setup right now' analysis.
    """
    ticker = ticker.upper()

    conn = get_db()
    row = conn.execute("""
        SELECT
            date, close,
            macd_line, macd_signal, macd_histogram,
            macd_crossover, macd_crossunder,
            rsi, rsi_overbought, rsi_oversold,
            bb_upper, bb_middle, bb_lower, bb_position,
            sma200, price_above_sma200
        FROM indicators
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT 1
    """, (ticker,)).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": f"No data found for {ticker}"}), 404

    return jsonify({"ticker": ticker, "snapshot": dict(row)})


@app.route("/signals/<ticker>", methods=["GET"])
def get_recent_signals(ticker):
    """
    Returns any days in the last N days where a signal event fired.
    Signal events: MACD crossover/crossunder, RSI overbought/oversold.
    Query params:
      days=N  — lookback window (default 90)
    """
    ticker = ticker.upper()
    days   = int(request.args.get("days", 90))

    conn = get_db()
    rows = conn.execute("""
        SELECT
            date, close,
            macd_crossover, macd_crossunder,
            rsi, rsi_overbought, rsi_oversold,
            bb_position, sma200, price_above_sma200
        FROM indicators
        WHERE ticker = ?
          AND (macd_crossover = 1 OR macd_crossunder = 1
               OR rsi_overbought = 1 OR rsi_oversold = 1)
        ORDER BY date DESC
        LIMIT ?
    """, (ticker, days)).fetchall()
    conn.close()

    data = [dict(r) for r in rows]
    return jsonify({
        "ticker":  ticker,
        "count":   len(data),
        "signals": data
    })


@app.route("/summary", methods=["GET"])
def summary_all():
    """
    Returns the latest snapshot for ALL tickers in one call.
    Useful for a quick portfolio-wide overview.
    """
    tickers = load_tickers()
    conn    = get_db()
    results = {}

    for ticker in tickers:
        row = conn.execute("""
            SELECT date, close,
                   macd_line, macd_signal, macd_histogram,
                   macd_crossover, macd_crossunder,
                   rsi, bb_position, sma200, price_above_sma200
            FROM indicators
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT 1
        """, (ticker,)).fetchone()

        if row:
            results[ticker] = dict(row)
        else:
            results[ticker] = None

    conn.close()
    return jsonify({"snapshots": results})


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    debug = os.getenv("DEBUG", "false").lower() == "true"
    print(f"Starting Sovson Indicator Lab API on {host}:{FLASK_PORT}")
    app.run(host=host, port=FLASK_PORT, debug=debug)
