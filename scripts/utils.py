import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

def send_telegram_alert(message):
    """
    Sends a Telegram message if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in the environment.
    Fails gracefully if they are not set or if the request fails.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log.debug("Telegram alert skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            log.info("Telegram alert sent successfully.")
            return True
        else:
            log.error(f"Failed to send Telegram alert. Status code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        log.error(f"Exception raised while sending Telegram alert: {e}")

    return False
