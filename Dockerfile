# Backend: FastAPI + Telegram webhook. Run with docker compose or:
#   docker build -t bimoi-backend . && docker run --env-file .env -p 8000:8000 bimoi-backend
FROM python:3.12.7-slim-bookworm

WORKDIR /app

# git required for pip to install xstate from git URL (api extra)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files needed for editable install and runtime (flows/ for XState machine)
COPY pyproject.toml README.md ./
COPY src ./src
COPY flows ./flows

# Install deps (bot + api extras: neo4j, telegram, fastapi, uvicorn, xstate)
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -e ".[bot,api]"

# Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Default: run FastAPI (Telegram bot via webhook at /webhook/telegram)
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
