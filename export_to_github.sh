#!/bin/bash

API="http://localhost:5001"
KEY="sovson2026"
REPO="$HOME/indicator-lab"

cd $REPO

# Read tickers from config/tickers.json
TICKERS=($(python3 -c "import json; data=json.load(open('config/tickers.json')); print(' '.join(data['tickers']))"))

for TICKER in "${TICKERS[@]}"; do
  curl -s -H "X-API-Key: $KEY" "$API/indicators/$TICKER?days=30" > data/${TICKER}.json
  curl -s -H "X-API-Key: $KEY" "$API/snapshot/$TICKER" >> data/${TICKER}.json
  echo "Exported $TICKER"
done

git pull
git add data/ config/
git commit -m "Daily indicator update $(date '+%Y-%m-%d')" || echo "Nothing to commit"
git push

echo "Done: $(date)"
