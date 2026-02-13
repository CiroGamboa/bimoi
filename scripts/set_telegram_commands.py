#!/usr/bin/env python3
"""Set the bot command menu shown when the user taps '/' in Telegram.
Run once after creating the bot (or when changing commands).
Requires TELEGRAM_BOT_TOKEN in .env.
"""
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

commands = [
    {"command": "start", "description": "Start or help"},
    {"command": "list", "description": "List my contacts"},
    {"command": "search", "description": "Search by keyword"},
]
url = f"https://api.telegram.org/bot{token}/setMyCommands"
data = json.dumps({"commands": commands}).encode()
req = urllib.request.Request(
    url,
    data=data,
    method="POST",
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        out = json.loads(r.read().decode())
    if out.get("ok"):
        print("Command menu set: start, list, search")
    else:
        print(f"Telegram error: {out}", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"Failed to set commands: {e}", file=sys.stderr)
    sys.exit(1)
