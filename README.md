## 🗺️ Roadmap — Geometric Pattern Recognition

### 🎯 Goal
Move the Sovson Indicator Lab from **reactive** indicator reporting (RSI, MACD, Bollinger Bands, SMA 200) toward **proactive** geometric pattern recognition — spotting the *shape* of price action (flags, wedges, head & shoulders, wave cycles) to anticipate moves rather than just react to them.

### 📚 Pattern Library

| Pattern | Type | Core Concept | Reference |
|---|---|---|---|
| **Bullish Flag** | Continuation | Brief consolidation after a strong upward move, followed by a resumption of the trend | [TradingView guide](https://www.tradingview.com/support/solutions/43000653209/) |
| **Head and Shoulders** | Reversal | Three peaks (higher-lower-higher... wait, middle peak highest) signaling a top forming at the end of an uptrend | [TradingView guide](https://www.tradingview.com/support/solutions/43000653213/) |
| **Rising Wedge** | Bearish Reversal | Two converging upward-sloping trendlines — narrowing price action signals fading momentum despite still-rising price | [TradingView guide](https://www.tradingview.com/support/solutions/43000653219/) |
| **Elliott Wave** | Cycle Analysis | Fractal 5-wave impulse / 3-wave correction cycle rooted in crowd psychology | [TradingView guide](https://www.tradingview.com/support/solutions/43000653212/) |

### 🔨 Planned Build Sequence

Patterns will be introduced in order of reliability and ease of automated detection — not the order listed above:

1. **Backtest harness first** — before any pattern goes live, build the infrastructure to test it against historical OHLCV data and confirm it clears the same win-rate bar (≥60% at the 10-day forward window) used for the existing indicator tournament.
2. **Pilot candlestick patterns via `pandas-ta`** — lowest-risk starting point since it's a well-supported library rather than custom geometry detection.
3. **Geometric patterns (Bullish Flag, Rising Wedge, Head & Shoulders)** — detected using `scipy.signal.argrelextrema` to find local highs/lows, tested against historical SQLite OHLCV data before promotion to a live signal.
4. **Elliott Wave** — last in line, if pursued at all. Wave-counting is inherently subjective and harder to automate reliably; it only gets built once the simpler geometric patterns have proven out.

### ✅ Promotion Criteria

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
To prevent race conditions, the data refresh and GitHub export are chained together to run on weekdays at 9pm UTC:
```cron
0 21 * * 1-5 cd /home/ubuntu/indicator-lab && python3 scripts/run_all.py >> logs/cron.log 2>&1 && ./export_to_github.sh >> logs/export.log 2>&1
```

*Developed for Daniel — Sovson Analytics*
Same bar as every other contestant in the Indicator Lab: a pattern only becomes a live signal candidate once it demonstrates a **≥60% win rate at the 10-day forward window** in backtesting. No pattern goes live on vibes alone — human review of the backtest results decides if/when it graduates.
