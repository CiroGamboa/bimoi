#!/usr/bin/env python3
"""Set Telegram webhook to the current ngrok tunnel URL. Run after: ngrok http 8010"""
import json
import os
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")
token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
if not token:
    print("TELEGRAM_BOT_TOKEN not set in .env", file=sys.stderr)
    sys.exit(1)

# Get ngrok public URL from local API
try:
    req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
    with urllib.request.urlopen(req, timeout=2) as r:
        data = json.loads(r.read().decode())
except Exception as e:
    print(f"Ngrok not running or API unreachable: {e}", file=sys.stderr)
    print("Start ngrok first: ngrok http 8010", file=sys.stderr)
    sys.exit(1)

tunnels = data.get("tunnels", [])
public_url = None
for t in tunnels:
    if t.get("proto") == "https" and "public_url" in t:
        public_url = t["public_url"].rstrip("/")
        break
if not public_url:
    print("No HTTPS tunnel found in ngrok", file=sys.stderr)
    sys.exit(1)

webhook_url = f"{public_url}/webhook/telegram"
set_url = f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}"
try:
    with urllib.request.urlopen(set_url, timeout=10) as r:
        out = json.loads(r.read().decode())
    if out.get("ok"):
        print(f"Webhook set to {webhook_url}")
    else:
        print(f"Telegram error: {out}", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"Failed to set webhook: {e}", file=sys.stderr)
    sys.exit(1)
