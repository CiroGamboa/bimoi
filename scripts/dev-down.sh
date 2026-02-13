#!/usr/bin/env bash
# Stop the dev stack: ngrok and Docker (Neo4j + backend). Run from repo root.

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
PID_FILE="$REPO_ROOT/.dev-ngrok.pid"

if [ -f "$PID_FILE" ]; then
  NGROK_PID=$(cat "$PID_FILE")
  if kill -0 "$NGROK_PID" 2>/dev/null; then
    echo "Stopping ngrok (PID $NGROK_PID)..."
    kill "$NGROK_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

echo "Stopping Docker stack..."
docker compose down

echo "Done. App is stopped."
