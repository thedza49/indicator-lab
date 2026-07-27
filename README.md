# Sovson Indicator Lab

**Sovson Analytics** — a system that watches a basket of stocks every day, calculates technical indicators (like MACD and RSI), and stores the results so both Daniel and AI assistants can look them up.

## How it works, in plain terms

There are two parts:

1. **The brain (on a cloud server)** — a small computer running 24/7 that pulls each stock's price every weekday after the market closes, does the math for each indicator, and saves it all to a local database. This database holds years of history for every ticker.

2. **The public snapshot (on GitHub, this repo)** — every day, the brain also writes out a small, easy-to-read file for each stock (like `AAPL.json`) and pushes it here. This is what AI assistants read when asked to analyze a stock — a lightweight "today's numbers" file, not the full multi-year database.

Think of it like a weather station: the full sensor logs live on the machine, but every day it prints out today's forecast card and pins it somewhere anyone can grab.

## Looking up data

**If you're on the server**, you can ask the full database directly, e.g. to see how many days of price history it's storing:
```bash
python3 -c "import sqlite3; conn = sqlite3.connect('data/indicators.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM daily_prices'); print(cursor.fetchone()[0]); conn.close()"
```

**If you just want today's numbers for a stock**, grab the snapshot file for it, e.g.:
`https://raw.githubusercontent.com/thedza49/indicator-lab/main/data/{TICKER}.json`

## Keeping it running automatically

Every weekday at 9pm UTC (after the US market closes), the server automatically does two things, one after the other:
1. Fetches the latest prices and re-runs the indicator math
2. Publishes the updated snapshot files here to GitHub

These two steps used to run separately and could occasionally step on each other. They're now chained together so the second step always waits for the first to finish properly.

**If a day gets missed** (say the server was rebooting or briefly down), nothing extra needs to be done — the very next time it runs, it automatically fills in every missing day since the last successful update, not just "yesterday." This has always been how the system checks for new data: it looks at the last date it has saved for each stock and fetches everything from there up to today, however big that gap is. So a missed day heals itself the next time the job runs, with no special command needed.

---

## 🗺️ Roadmap

Three things planned next, roughly in order of how developed the idea is:

### 1. Chart Pattern Recognition

Right now, the system reports **indicators** — numbers like RSI and MACD that describe momentum after the fact. This stage teaches it to also recognize **shapes** in the price chart that often signal what happens next — patterns traders have used for decades, like a stock forming a "wedge" before a reversal.

**The end goal:** once a pattern is confidently detected on a stock, it gets added right into that stock's daily snapshot file — the same file AI assistants already read — so an assistant can say "heads up, AAPL is forming a Rising Wedge" without anyone having to ask a separate question. It becomes just another piece of information sitting alongside the existing indicators.

**The patterns being planned:**

| Pattern | What it usually means | Reference |
|---|---|---|
| **Bullish Flag** | A brief pause after a strong climb, usually followed by the climb continuing | [TradingView guide](https://www.tradingview.com/support/solutions/43000653209/) |
| **Head and Shoulders** | Three peaks with the middle one tallest — often signals an uptrend running out of steam | [TradingView guide](https://www.tradingview.com/support/solutions/43000653213/) |
| **Rising Wedge** | Price still climbing, but the swings are narrowing — a warning that momentum is fading | [TradingView guide](https://www.tradingview.com/support/solutions/43000653219/) |
| **Elliott Wave** | A more complex, cyclical theory about crowd psychology playing out in repeating wave patterns | [TradingView guide](https://www.tradingview.com/support/solutions/43000653212/) |

**How they'll be rolled out** — safest and easiest first, hardest and most subjective last:
1. Build a proper testing setup first, so any new pattern gets checked against years of historical data before it's trusted
2. Start with basic candlestick shapes using a well-tested existing tool, rather than inventing detection from scratch
3. Move on to the geometric patterns above (flags, wedges, head & shoulders)
4. Elliott Wave last, if at all — it's the most subjective of the group and hardest to automate reliably

**The bar for going live:** same rule as everything else in this system — a pattern only gets trusted and shown once it's proven, in testing, to correctly predict the next 10 days' movement at least 60% of the time. Nothing goes live just because it looks promising.

### 2. Fibonacci Levels

**What it is, in plain terms:** Fibonacci retracement is a way of guessing where a stock might pause or reverse during a pullback, based on math from an old numerical sequence. After a stock moves from a low to a high (or vice versa), traders watch specific percentage levels of that move — commonly 23.6%, 38.2%, 50%, 61.8%, and 78.6% — as likely spots where the price might find support or resistance on the way back.

**The goal:** calculate these levels for each stock and add them into that stock's daily snapshot file, the same way patterns will be added — so an AI assistant could say "AAPL just pulled back to its 61.8% Fibonacci level" as part of an analysis, without anyone having to ask separately.

**Status:** not yet started — needs a proper design pass on exactly how the "recent high" and "recent low" get chosen (e.g. over what time window), since that choice changes where the levels land.

### 3. Daily Auto-Generated Chart

**The goal:** each day, alongside the JSON snapshot, generate an actual image of the stock's chart and publish it to GitHub too — so instead of just numbers, there's a visual anyone (or any AI) can pull up directly.

**Status:** design not yet started. Open questions to figure out before building this:
- What should the chart actually show — plain price candles, or price with indicators overlaid (like MACD, Bollinger Bands, moving averages)?
- Should it show a fixed lookback window (e.g. last 30/90 days), or be zoomable/interactive?
- Once patterns and Fibonacci levels exist, should they be drawn directly on this chart too?
- What file format and naming (e.g. `data/charts/{TICKER}.png`), so it's easy for both people and AI assistants to find?

---

*Developed for Daniel — Sovson Analytics*
