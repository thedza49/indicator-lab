# Sovson Indicator Lab

**Sovson Analytics** — A specialized stock indicator analysis engine running on Oracle Cloud.

This project employs a hybrid architecture: it maintains a **local historical database** on an Oracle Cloud VM for deep historical analysis, while publishing **lightweight daily snapshots** to this repository for easy, on-demand access by AI assistants.

---

## 🏗️ System Architecture

### 1. The Engine (Local Oracle VM)
* **Storage:** 3+ years of raw historical OHLCV data is housed locally in a **SQLite database** (`data/indicators.db`).
* **Processing:** Python scripts (`scripts/`) fetch daily data from Yahoo Finance, compute technical indicators, and update the local database.

### 2. The Dashboard (GitHub Repository)
* **Export:** An automated script (`export_to_github.sh`) generates JSON snapshots of market data.
* **Accessibility:** These JSON files serve as a public data source, allowing AI assistants to read current market data instantly.

---

## 🛠️ Accessing Data

### View Raw Archive (On the VM)
Query the historical archive directly:
```bash
python3 -c "import sqlite3; conn = sqlite3.connect('data/indicators.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM daily_prices'); print(cursor.fetchone()[0]); conn.close()"
```

### View Daily Snapshots (Via GitHub)
`https://raw.githubusercontent.com/thedza49/indicator-lab/main/data/{TICKER}.json`

---

## ⚙️ Maintenance

### Automated Tasks
Two cron jobs run weekdays at 9pm UTC:
```cron
0 21 * * 1-5 cd /home/ubuntu/indicator-lab && python3 scripts/run_all.py >> logs/cron.log 2>&1
0 21 * * 1-5 /home/ubuntu/indicator-lab/export_to_github.sh >> logs/export.log 2>&1
```

*Developed for Daniel — Sovson Analytics*