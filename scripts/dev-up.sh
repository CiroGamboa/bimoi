#!/usr/bin/env bash
# Start the whole app for local dev: Neo4j + backend + ngrok, then set Telegram webhook.
# Run from repo root. To stop: ./scripts/dev-down.sh

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
PID_FILE="$REPO_ROOT/.dev-ngrok.pid"

echo "Starting Neo4j + backend..."
docker compose up -d

echo "Waiting for backend to be healthy..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/health 2>/dev/null | grep -q 200; then
    break
  fi
  if [ "$i" -eq 10 ]; then
    echo "Backend did not become healthy. Check: docker compose logs backend" >&2
    exit 1
  fi
  sleep 2
done
echo "Backend is up."

if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Stopping existing ngrok (PID $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

echo "Starting ngrok (tunnel to port 8010)..."
ngrok http 8010 --log=stdout > "$REPO_ROOT/.dev-ngrok.log" 2>&1 &
NGROK_PID=$!
echo $NGROK_PID > "$PID_FILE"
echo "Waiting for ngrok tunnel..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -s -o /dev/null http://127.0.0.1:4040/api/tunnels 2>/dev/null; then
    break
  fi
  if [ "$i" -eq 10 ]; then
    echo "ngrok did not start. Check .dev-ngrok.log" >&2
    kill $NGROK_PID 2>/dev/null || true
    rm -f "$PID_FILE"
    exit 1
  fi
  sleep 1
done

echo "Setting Telegram webhook..."
python scripts/set_webhook_ngrok.py

echo ""
echo "App is running."
echo "  Backend:  http://localhost:8010"
echo "  ngrok:    see URL above or http://127.0.0.1:4040"
echo "  Telegram: use your bot; webhook is set."
echo ""
echo "To stop everything:  ./scripts/dev-down.sh"
