# Sovson Indicator Lab

**Sovson Analytics** — Stock indicator analysis engine running on Oracle Cloud.

Collects daily OHLCV price data and calculates four technical indicators for a configurable basket of tickers. Exposes a lightweight Flask API so Claude can query live data during chat sessions and deliver plain-English analysis.

---

## What This Does

1. **Fetches** daily price data (Open, High, Low, Close, Volume) from Yahoo Finance
2. **Calculates** four indicators on every ticker, every day:
   - MACD (12/26/9) — momentum and trend direction
   - RSI (14) — overbought / oversold exhaustion meter
   - Bollinger Bands (20/2) — volatility envelope and price position
   - SMA 200 — long-term trend context
3. **Stores** everything in a local SQLite database
4. **Serves** the data via a Flask API that Claude can query on demand

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/YOUR_USERNAME/Sovson-Indicator-Lab.git
cd Sovson-Indicator-Lab
pip3 install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
nano .env   # Fill in your FMP_API_KEY and set API_KEY for auth
```

### 3. Add your tickers

Edit `config/tickers.json` — add or remove ticker symbols as needed.

### 4. Run the pipeline for the first time

```bash
python3 scripts/run_all.py
```

This fetches 365 days of history (configurable via `INITIAL_HISTORY_DAYS` in `.env`) and calculates all indicators.

### 5. Start the API

```bash
python3 api/app.py
```

The API runs on port `5001` by default.

---

## Running Daily (Cron)

To keep data fresh, add a cron job that runs after market close:

```bash
crontab -e
```

Add this line (runs at 9pm UTC = 1pm PST, Monday–Friday):

```
0 21 * * 1-5 cd /home/ubuntu/Sovson-Indicator-Lab && python3 scripts/run_all.py >> logs/cron.log 2>&1
```

---

## API Endpoints

All endpoints return JSON.

| Endpoint | Description |
|---|---|
| `GET /` | Health check |
| `GET /tickers` | List all configured tickers |
| `GET /snapshot/{ticker}` | Latest indicator snapshot for one ticker |
| `GET /summary` | Latest snapshot for all tickers |
| `GET /indicators/{ticker}?days=30` | Last N days of indicator data |
| `GET /prices/{ticker}?days=60` | Last N days of raw price data |
| `GET /signals/{ticker}?days=90` | Days where a signal event fired |

If `API_KEY` is set in `.env`, include it as a request header:
```
X-API-Key: your_key_here
```

---

## Adding or Removing Tickers

Edit `config/tickers.json`:

```json
{
  "tickers": ["AAPL", "NVDA", "MSFT", "META", "GOOG", "SNDK", "TSLA"]
}
```

Then run `python3 scripts/run_all.py` to backfill history for any new tickers.

---

## Project Structure

```
Sovson-Indicator-Lab/
├── config/
│   └── tickers.json          # Ticker list — edit to add/remove
├── data/
│   └── indicators.db         # SQLite database (auto-created)
├── scripts/
│   ├── fetch_prices.py       # Pulls OHLCV from Yahoo Finance
│   ├── calculate_indicators.py  # Computes all four indicators
│   └── run_all.py            # Runs fetch + calculate in sequence
├── api/
│   └── app.py                # Flask API
├── logs/                     # Log files (auto-created)
├── .env.example              # Environment variable template
├── requirements.txt
└── README.md
```

---

*Developed for Daniel — Sovson Analytics*
