#!/bin/bash

API="http://localhost:5001"
KEY="sovson2026"
REPO="$HOME/indicator-lab"

# If we are in the repository, use current directory instead of hardcoded $HOME if it doesn't exist
if [ -d "$REPO" ]; then
  cd "$REPO"
else
  REPO=$(pwd)
  cd "$REPO"
fi

# Ensure data directory exists
mkdir -p data

# Read tickers from config/tickers.json
TICKERS=($(python3 -c "import json; data=json.load(open('config/tickers.json')); print(' '.join(data['tickers']))"))

if [ ${#TICKERS[@]} -eq 0 ]; then
  echo "Error: No tickers found in config/tickers.json"
  exit 1
fi

log_error() {
  local msg="$1"
  echo "ERROR: $msg"
}

for TICKER in "${TICKERS[@]}"; do
  echo "Exporting $TICKER ..."

  TMP_IND="data/${TICKER}_ind.json.tmp"
  TMP_SNAP="data/${TICKER}_snap.json.tmp"

  # 1. Fetch and validate Indicators
  curl -s -f -H "X-API-Key: $KEY" "$API/indicators/$TICKER?days=30" > "$TMP_IND"
  if [ $? -ne 0 ] || [ ! -s "$TMP_IND" ]; then
    log_error "Failed to fetch indicators for $TICKER (API/Network error)."
    rm -f "$TMP_IND" "$TMP_SNAP"
    exit 1
  fi

  python3 -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    if 'indicators' not in data or 'ticker' not in data:
        sys.exit(1)
except Exception:
    sys.exit(1)
" "$TMP_IND"
  if [ $? -ne 0 ]; then
    log_error "Invalid indicators JSON structure for $TICKER."
    rm -f "$TMP_IND" "$TMP_SNAP"
    exit 1
  fi

  # 2. Fetch and validate Snapshot
  curl -s -f -H "X-API-Key: $KEY" "$API/snapshot/$TICKER" > "$TMP_SNAP"
  if [ $? -ne 0 ] || [ ! -s "$TMP_SNAP" ]; then
    log_error "Failed to fetch snapshot for $TICKER (API/Network error)."
    rm -f "$TMP_IND" "$TMP_SNAP"
    exit 1
  fi

  python3 -c "
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    if 'snapshot' not in data or 'ticker' not in data:
        sys.exit(1)
except Exception:
    sys.exit(1)
" "$TMP_SNAP"
  if [ $? -ne 0 ]; then
    log_error "Invalid snapshot JSON structure for $TICKER."
    rm -f "$TMP_IND" "$TMP_SNAP"
    exit 1
  fi

  # 3. Combine and clean up
  cat "$TMP_IND" "$TMP_SNAP" > "data/${TICKER}.json"
  rm -f "$TMP_IND" "$TMP_SNAP"
  echo "Exported $TICKER successfully"
done

# Git steps
git pull || { log_error "Git pull failed."; exit 1; }
git add data/ config/
git commit -m "Daily indicator update $(date '+%Y-%m-%d')" || echo "Nothing to commit"
git push || { log_error "Git push failed."; exit 1; }

echo "Done: $(date)"
