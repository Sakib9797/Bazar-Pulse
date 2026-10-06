"""Alerts: always logged to data/monitoring/alerts.jsonl; also sent to Telegram when
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set."""
import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime

ALERTS = os.path.join("data", "monitoring", "alerts.jsonl")
ICON = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}


def send(message, level="warning"):
    entry = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "level": level, "message": message}
    print(f"[alert:{level}] {message}", flush=True)
    os.makedirs(os.path.dirname(ALERTS), exist_ok=True)
    with open(ALERTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": f"{ICON.get(level, '')} Bazar Pulse: {message}"})
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage",
                               data=data.encode(), timeout=20).read()
        return True
    except Exception as e:
        print(f"[alert] Telegram delivery failed: {type(e).__name__}", flush=True)
        return False
