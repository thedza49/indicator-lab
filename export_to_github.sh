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

log_error() {
  local msg="$1"
  echo "ERROR: $msg"
}

# ── Step 0: Recover from any previous failed run ───────────────────────────────
# If a prior run committed data locally but failed to push (e.g. rejected due
# to a non-fast-forward), that commit is still sitting on this machine ahead
# of origin. Try to push it before doing anything else, so we never pile a
# new day's commit on top of an unresolved old one.
git fetch origin main --quiet
AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
if [ "$AHEAD" -gt 0 ]; then
  echo "Found $AHEAD unpushed local commit(s) from a previous run. Attempting to push first..."
  if git push; then
    echo "Recovered: previous local commit(s) pushed successfully."
  else
    log_error "Could not push previous local commit(s). Resolve manually before continuing (git log, git status)."
    exit 1
  fi
fi

# ── Step 1: Sync with GitHub BEFORE touching any data files ────────────────────
# This is the fix for the conflict we hit: pulling AFTER overwriting data/*.json
# caused "local changes would be overwritten by merge". Pulling first, while the
# working tree is clean, means there's nothing to conflict with.
if ! git pull --ff-only; then
  log_error "Git pull failed (working tree not clean or history diverged.) Not safe to proceed — resolve manually with 'git status' / 'git fetch' before re-running."
  exit 1
fi

# Ensure data directory exists
mkdir -p data

# Read tickers from config/tickers.json
TICKERS=($(python3 -c "import json; data=json.load(open('config/tickers.json')); print(' '.join(data['tickers']))"))

if [ ${#TICKERS[@]} -eq 0 ]; then
  echo "Error: No tickers found in config/tickers.json"
  exit 1
fi

# ── Step 2: Fetch + validate + write each ticker's data ────────────────────────
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

# ── Step 3: Commit and push, with one retry on a rejected push ─────────────────
git add data/ config/
git commit -m "Daily indicator update $(date '+%Y-%m-%d')" || echo "Nothing to commit"

if git push; then
  echo "Done: $(date)"
  exit 0
fi

# Push was rejected — most likely because something else pushed to origin/main
# in between our pull and our push. Try exactly once to reconcile automatically
# using --autostash so any in-progress state isn't lost, then push again.
echo "Push rejected, attempting to reconcile with origin/main..."
if git pull --rebase --autostash && git push; then
  echo "Done after reconciling with origin: $(date)"
  exit 0
fi

log_error "Push failed even after reconciliation attempt. The day's data is committed LOCALLY on this machine but NOT on GitHub. Run 'git status' and 'git log --oneline -5' to inspect, resolve manually, then push."
exit 1
