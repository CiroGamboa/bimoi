# Backend: FastAPI + Telegram webhook. Run with docker compose or:
#   docker build -t bimoi-backend . && docker run --env-file .env -p 8000:8000 bimoi-backend
FROM python:3.11-slim

WORKDIR /app

# Copy project files needed for editable install (setuptools needs src/ and README)
COPY pyproject.toml README.md ./
COPY src ./src

# Install deps (bot + api extras: neo4j, telegram, fastapi, uvicorn)
RUN pip install --no-cache-dir -e ".[bot,api]"

# Default: run FastAPI. Override with command to run polling bot (USE_POLLING=1 python -m bot)
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
