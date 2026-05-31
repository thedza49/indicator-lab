# Sovson Indicator Lab

**Sovson Analytics** — Stock indicator analysis engine running on Oracle Cloud.

Collects daily OHLCV price data, calculates four technical indicators for a configurable basket of tickers, and exports the results to GitHub so Claude can fetch and analyze them on demand from any device.

---

## What This Does

1. **Fetches** daily price data (Open, High, Low, Close, Volume) from Yahoo Finance
2. **Calculates** four indicators on every ticker, every day:
   - MACD (12/26/9) — momentum and trend direction
   - RSI (14) — overbought / oversold exhaustion meter
   - Bollinger Bands (20/2) — volatility envelope and price position
   - SMA 200 — long-term trend context
3. **Stores** everything in a local SQLite database on the Oracle VM
4. **Exports** daily JSON snapshots to this GitHub repo so Claude can read them without any direct connection to the VM

---

## How Claude Accesses the Data

Claude reads indicator data directly from this repo via raw GitHub URLs:

```
https://raw.githubusercontent.com/thedza49/indicator-lab/main/data/{TICKER}.json
```

Available tickers: `AAPL`, `META`, `MSFT`, `NVDA`, `GOOG`, `SNDK`

No API keys or tunnels required — files are public. To trigger a full analysis, type `/stock_analysis` in Claude chat.

---

## Data Flow

```
Yahoo Finance
     ↓
Oracle Cloud VM (scripts/run_all.py)
     ↓
SQLite Database
     ↓
Flask API (localhost:5001)
     ↓
export_to_github.sh
     ↓
GitHub repo (data/*.json)
     ↓
Claude (via raw GitHub URL)
```

---

## Running Daily (Cron)

Two cron jobs run automatically on the Oracle VM every weekday at 9pm UTC (2pm Pacific):

```
0 21 * * 1-5 cd /home/ubuntu/indicator-lab && python3 scripts/run_all.py >> logs/cron.log 2>&1
0 21 * * 1-5 /home/ubuntu/indicator-lab/export_to_github.sh >> logs/export.log 2>&1
```

The first job fetches prices and recalculates indicators. The second exports the results to GitHub.

---

## Manual Export

To push fresh data to GitHub outside of the scheduled cron:

```bash
ssh into Oracle VM
~/indicator-lab/export_to_github.sh
```

---

## Setup (Oracle VM)

### 1. Clone and install dependencies

```bash
git clone https://github.com/thedza49/indicator-lab.git
cd indicator-lab
pip3 install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
nano .env   # Fill in your API keys
```

### 3. Run the pipeline for the first time

```bash
python3 scripts/run_all.py
```

### 4. Start the Flask API (used by the export script)

```bash
cd ~/indicator-lab && nohup python3 api/app.py > logs/api.log 2>&1 &
```

### 5. Configure git credentials for GitHub push

```bash
git config --global user.email "your@email.com"
git config --global user.name "your-github-username"
git remote set-url origin https://YOUR_USERNAME:YOUR_GITHUB_TOKEN@github.com/thedza49/indicator-lab.git
```

---

## Project Structure

```
indicator-lab/
├── api/
│   └── app.py                   # Flask API (localhost:5001)
├── config/
│   └── tickers.json             # Ticker list — edit to add/remove
├── data/
│   ├── AAPL.json                # Daily export — read by Claude
│   ├── GOOG.json
│   ├── META.json
│   ├── MSFT.json
│   ├── NVDA.json
│   └── SNDK.json
├── scripts/
│   ├── fetch_prices.py          # Pulls OHLCV from Yahoo Finance
│   ├── calculate_indicators.py  # Computes all four indicators
│   └── run_all.py               # Runs fetch + calculate in sequence
├── logs/                        # Log files (auto-created)
├── export_to_github.sh          # Exports data/ JSON files and pushes to GitHub
├── .env.example
├── requirements.txt
└── README.md
```

---

## Adding or Removing Tickers

Edit `config/tickers.json`:

```json
{
  "tickers": ["AAPL", "META", "MSFT", "NVDA", "GOOG", "SNDK"]
}
```

Then run `python3 scripts/run_all.py` to backfill history for any new tickers, and update `export_to_github.sh` to include the new ticker in the loop.

---

*Developed for Daniel — Sovson Analytics*
