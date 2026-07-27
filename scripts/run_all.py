"""
run_all.py — Sovson Indicator Lab
One command to run the full pipeline:
  1. Fetch latest prices from Yahoo Finance
  2. Calculate all indicators

Run:  python3 scripts/run_all.py
"""

import subprocess
import sys
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = BASE_DIR / "logs" / "run_all.log"

sys.path.append(str(BASE_DIR / "scripts"))
from utils import send_telegram_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def run(script_name):
    script_path = BASE_DIR / "scripts" / script_name
    log.info(f"--- Running {script_name} ---")
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=False
        )
        if result.returncode != 0:
            err_msg = f"{script_name} failed with exit code {result.returncode}"
            log.error(err_msg)
            send_telegram_alert(f"❌ [run_all.py] {err_msg}")
            sys.exit(result.returncode)
    except Exception as e:
        err_msg = f"Exception running {script_name}: {e}"
        log.error(err_msg)
        send_telegram_alert(f"❌ [run_all.py] {err_msg}")
        sys.exit(1)
    log.info(f"--- {script_name} completed successfully ---")


if __name__ == "__main__":
    log.info("=== run_all.py: starting full pipeline ===")
    try:
        run("fetch_prices.py")
        run("calculate_indicators.py")
        log.info("=== run_all.py: pipeline complete ===")
    except Exception as e:
        log.critical(f"Unhandled exception in run_all.py: {e}")
        send_telegram_alert(f"🚨 [run_all.py] Unhandled pipeline exception: {e}")
        sys.exit(1)
