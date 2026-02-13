#!/usr/bin/env bash
# Quick checks when the bot doesn't respond. Run from repo root.

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f "$REPO_ROOT/.env" ]; then
  echo ".env not found. Create it from .env.example and set TELEGRAM_BOT_TOKEN."
  exit 1
fi

TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$REPO_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' || true)
if [ -z "$TOKEN" ]; then
  echo "TELEGRAM_BOT_TOKEN not found in .env (expected a line: TELEGRAM_BOT_TOKEN=your_token)"
  exit 1
fi

echo "1. Webhook URL (from Telegram):"
curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if not d.get('ok'):
    print('  Error:', d)
    sys.exit(1)
info = d.get('result', {})
url = info.get('url') or '(not set)'
print('  ', url)
if url == '(not set)':
    print('  -> Run: python scripts/set_webhook_ngrok.py (after ngrok is running)')
" 2>/dev/null || echo "  (could not parse response)"

echo ""
echo "2. Backend has token?"
if docker compose exec -T backend env 2>/dev/null | grep -q "TELEGRAM_BOT_TOKEN=."; then
  echo "  Yes (TELEGRAM_BOT_TOKEN is set in container)"
else
  echo "  No or empty -> Restart stack: ./scripts/dev-down.sh && ./scripts/dev-up.sh"
fi

echo ""
echo "3. Backend health:"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/health 2>/dev/null || echo "000")
if [ "$HTTP" = "200" ]; then
  echo "  OK (http://localhost:8010/health)"
else
  echo "  Failed (HTTP $HTTP). Is the backend running? docker compose ps"
fi

echo ""
echo "4. Recent backend logs (last 15 lines):"
docker compose logs backend --tail 15 2>/dev/null || echo "  (could not get logs)"

echo ""
echo "If you see 'Telegram webhook received' in the logs when you message the bot,"
echo "the request reaches the backend; check for errors after that line."
