# infra/discord_notify.py

import requests
import os

def send_discord_message(content: str):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("❗ DISCORD_WEBHOOK_URL not set")
        return

    data = {
        "content": content
    }

    try:
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print("❌ Discord 전송 실패:", e)
