"""
api/app.py — Sovson Indicator Lab
Flask API that exposes indicator data from SQLite.
This is what gets queried during Claude chat sessions.

Also includes a small password-protected admin page at /admin for adding
and removing tickers from a browser, without needing to SSH into the VM.

Run:  python3 api/app.py
      Listens on http://0.0.0.0:5001 by default
"""

import os
import re
import sqlite3
import json
import subprocess
from functools import wraps
from pathlib import Path
from datetime import datetime

from flask import Flask, jsonify, request, abort, Response
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "indicators.db"
CFG_PATH = BASE_DIR / "config" / "tickers.json"

app = Flask(__name__)

FLASK_PORT = int(os.getenv("FLASK_PORT", 5001))
API_KEY    = os.getenv("API_KEY", "")  # Optional: set in .env to require a key

# Admin page credentials — set ADMIN_PASSWORD in .env before relying on this.
# Username is fixed ("admin"); only the password is configurable.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Tickers must look like a normal stock symbol: 1-6 letters, optionally with
# a dot or dash (e.g. BRK.B). Keeps the admin form from writing junk into
# config/tickers.json.
TICKER_PATTERN = re.compile(r"^[A-Z]{1,6}([.\-][A-Z]{1,3})?$")


# ── Auth middleware (existing API key check, for the /prices /indicators etc endpoints) ──
@app.before_request
def check_api_key():
    """If API_KEY is set in .env, all requests must include it as a header.
    Admin routes use their own separate Basic Auth check instead (see
    require_admin_auth below), so they're excluded here."""
    if request.path.startswith("/admin"):
        return
    if API_KEY:
        provided = request.headers.get("X-API-Key", "")
        if provided != API_KEY:
            abort(401)


# ── Admin auth (separate from the API key, since a browser can't easily send
#    a custom header — HTTP Basic Auth works natively in every browser) ──────
def require_admin_auth(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not ADMIN_PASSWORD:
            return Response(
                "Admin page is disabled: set ADMIN_PASSWORD in .env to enable it.",
                401
            )
        auth = request.authorization
        if not auth or auth.username != "admin" or auth.password != ADMIN_PASSWORD:
            return Response(
                "Login required.", 401,
                {"WWW-Authenticate": 'Basic realm="Indicator Lab Admin"'}
            )
        return f(*args, **kwargs)
    return wrapped


# ── DB helper ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_tickers():
    with open(CFG_PATH) as f:
        return [t.upper() for t in json.load(f)["tickers"]]


def save_tickers(tickers):
    """Writes the ticker list back to config/tickers.json, sorted and de-duped."""
    unique_sorted = sorted(set(t.upper() for t in tickers))
    with open(CFG_PATH, "w") as f:
        json.dump({"tickers": unique_sorted}, f, indent=2)
        f.write("\n")
    return unique_sorted


def run_pipeline_command(cmd, timeout=600):
    """Runs a command from the project root, capturing combined output.
    Used by the catch-up button — every step of the pipeline goes through
    this so failures show up in the on-page log instead of disappearing."""
    try:
        result = subprocess.run(
            cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=timeout
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode, output
    except subprocess.TimeoutExpired as e:
        partial = (e.stdout or "") + (e.stderr or "")
        return -1, f"[Timed out after {timeout}s]\n{partial}"
    except Exception as e:
        return -1, f"[Error running command: {e}]"


def render_admin_page(message="", log_text=None):
    tickers = load_tickers()
    rows = "".join(
        f"""<tr>
              <td>{t}</td>
              <td>
                <form method="POST" action="/admin/tickers/remove" style="margin:0;">
                  <input type="hidden" name="ticker" value="{t}">
                  <button type="submit" onclick="return confirm('Remove {t}?')">Remove</button>
                </form>
              </td>
            </tr>"""
        for t in tickers
    )
    banner = f'<p style="color:#2a7;font-weight:bold;">{message}</p>' if message else ""

    log_block = ""
    if log_text is not None:
        # Basic HTML-escaping so log output (which may include quotes, angle
        # brackets from error messages, etc.) doesn't break the page layout.
        escaped = (
            log_text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
        )
        log_block = f"""
          <h3>Catch-up log</h3>
          <pre style="background:#111;color:#0f0;padding:12px;border-radius:6px;
                       max-height:400px;overflow:auto;font-size:12px;white-space:pre-wrap;">{escaped}</pre>
        """

    return f"""
    <html>
    <head>
      <title>Indicator Lab — Tickers</title>
      <style>
        body {{ font-family: -apple-system, Arial, sans-serif; max-width: 560px; margin: 40px auto; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
        input[type=text] {{ padding: 6px; font-size: 16px; text-transform: uppercase; }}
        button {{ padding: 6px 12px; cursor: pointer; }}
        .tools a {{ margin-right: 14px; }}
        .catchup-btn {{ background:#2a6; color:white; border:none; padding:10px 16px;
                        border-radius:6px; font-size:15px; cursor:pointer; }}
      </style>
    </head>
    <body>
      <h2>Sovson Indicator Lab — Tickers</h2>

      <p class="tools">
        <a href="https://claude.ai" target="_blank">Claude</a>
        <a href="https://gemini.google.com" target="_blank">Gemini</a>
      </p>

      {banner}
      <form method="POST" action="/admin/tickers/add">
        <input type="text" name="ticker" placeholder="e.g. AAPL" maxlength="10" required>
        <button type="submit">Add</button>
      </form>
      <br>
      <table>{rows}</table>
      <p style="color:#888;font-size:13px;">
        Adding a ticker registers it for the next scheduled fetch — it'll show up
        with data after the next weekday 9pm UTC run, or right away if you hit
        "Run Catch-Up Now" below.
      </p>

      <hr>
      <h3>Catch-up</h3>
      <p style="color:#888;font-size:13px;">
        Runs the full pipeline right now — fetches price history for any new
        tickers, recalculates indicators, exports everything to GitHub, and
        removes GitHub data files for any ticker no longer in your list above.
        Takes a couple of minutes. Don't close this tab while it runs.
      </p>
      <form method="POST" action="/admin/catchup">
        <button type="submit" class="catchup-btn" onclick="this.innerText='Running... please wait';">
          Run Catch-Up Now
        </button>
      </form>

      {log_block}
    </body>
    </html>
    """


# ── Admin routes ──────────────────────────────────────────────────────────────
@app.route("/admin", methods=["GET"])
@require_admin_auth
def admin_page():
    return render_admin_page()


@app.route("/admin/tickers/add", methods=["POST"])
@require_admin_auth
def admin_add_ticker():
    ticker = request.form.get("ticker", "").strip().upper()
    if not ticker or not TICKER_PATTERN.match(ticker):
        return render_admin_page(f'"{ticker}" doesn\'t look like a valid ticker — not added.')
    tickers = load_tickers()
    if ticker in tickers:
        return render_admin_page(f"{ticker} is already tracked.")
    tickers.append(ticker)
    save_tickers(tickers)
    return render_admin_page(f"Added {ticker}.")


@app.route("/admin/tickers/remove", methods=["POST"])
@require_admin_auth
def admin_remove_ticker():
    ticker = request.form.get("ticker", "").strip().upper()
    tickers = load_tickers()
    if ticker not in tickers:
        return render_admin_page(f"{ticker} wasn't in the list.")
    tickers.remove(ticker)
    save_tickers(tickers)
    return render_admin_page(f"Removed {ticker}.")


@app.route("/admin/catchup", methods=["POST"])
@require_admin_auth
def admin_catchup():
    """
    Runs the full pipeline on demand:
      1. fetch_prices.py       — pull any missing price history (new tickers
                                  get up to a year of backfill automatically)
      2. calculate_indicators.py — recompute MACD/RSI/Bollinger/SMA200
      3. export_to_github.sh   — push updated data/*.json for current tickers
      4. Remove data/<ticker>.json from GitHub for any ticker that's been
         removed from config/tickers.json (export_to_github.sh only writes
         files for tickers it's told about — it never deletes old ones on
         its own, so a separate small commit handles that here).
    """
    log_parts = []

    log_parts.append("=== Step 1/4: fetch_prices.py ===")
    rc, out = run_pipeline_command(["python3", "scripts/fetch_prices.py"])
    log_parts.append(out)
    if rc != 0:
        log_parts.append(f"[fetch_prices.py exited with code {rc} — continuing anyway]")

    log_parts.append("\n=== Step 2/4: calculate_indicators.py ===")
    rc, out = run_pipeline_command(["python3", "scripts/calculate_indicators.py"])
    log_parts.append(out)
    if rc != 0:
        log_parts.append(f"[calculate_indicators.py exited with code {rc} — continuing anyway]")

    log_parts.append("\n=== Step 3/4: export_to_github.sh ===")
    rc, out = run_pipeline_command(["bash", "export_to_github.sh"])
    log_parts.append(out)
    if rc != 0:
        log_parts.append(f"[export_to_github.sh exited with code {rc} — stopping before cleanup step]")
        return render_admin_page("Catch-up finished with errors — see log below.", "\n".join(log_parts))

    log_parts.append("\n=== Step 4/4: removing stale ticker files from GitHub ===")
    current = set(load_tickers())
    data_dir = BASE_DIR / "data"
    stale = [f.name for f in data_dir.glob("*.json") if f.stem not in current]

    if not stale:
        log_parts.append("No stale ticker files to remove.")
    else:
        rc, out = run_pipeline_command(["git", "rm", "-f"] + [f"data/{name}" for name in stale])
        log_parts.append(out)
        rc, out = run_pipeline_command(
            ["git", "commit", "-m", f"Remove data for untracked tickers: {', '.join(stale)}"]
        )
        log_parts.append(out)
        rc, out = run_pipeline_command(["git", "push"])
        log_parts.append(out)
        if rc == 0:
            log_parts.append(f"Removed from GitHub: {', '.join(stale)}")

    return render_admin_page("Catch-up complete.", "\n".join(log_parts))


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
    app.run(host=host, port=FLASK_PORT, debug=debug, threaded=True)
