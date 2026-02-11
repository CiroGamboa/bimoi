# Bimoi

Bimoi helps you externalize your real relationships: who you know and why they matter. Instead of that knowledge living only in memory or chat history, you capture it at the moment it’s freshest—by sharing a contact and adding context—with minimal friction.

**Current status:** A **FastAPI backend** exposes a REST API and the **Telegram webhook**; one service handles all clients. Contacts are stored in **Neo4j**. Run the backend in Docker or with uvicorn; for local dev without a public URL you can use polling (`USE_POLLING=1 python -m bot`). [poc/](poc/README.md) remains a standalone POC.

## Project context

Detailed scope, requirements, user stories, and domain model are in **[docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md)**. Summary:

- **MVP:** Single-user system, Telegram bot only. Contacts are added by forwarding/sharing a Telegram contact card; the user then adds free-text context. No auth, no automation, no multi-user features.
- **Domain:** A relationship exists when a person is known and meaningful context is explicitly captured. The system stores a personal graph of contacts plus human-authored context.

## Running the POC

The POC in `poc/` checks that we can connect to Telegram and read a contact card when the user shares one with the bot.

1. **Setup:** See [poc/README.md](poc/README.md) for:
   - Getting a bot token from @BotFather
   - Using a virtual environment and installing dependencies
   - Setting `TELEGRAM_BOT_TOKEN` (e.g. in `poc/.env`)
2. **Run:** From the project root with the venv activated: `python poc/bot.py`
3. **Test:** In Telegram, open your bot, send `/start`, then share a contact; the bot echoes the contact data it read.

## Production backend (FastAPI + Neo4j + Telegram webhook)

One backend serves the **REST API** and the **Telegram bot** (via webhook). Telegram sends updates to your server; no long-polling in production.

1. **Docker (recommended):** `docker compose up -d` — starts Neo4j and the backend. Backend: http://localhost:8000 (health: `GET /health`, API: `GET/POST /contacts`, `GET /contacts/search?q=...`, Telegram: `POST /webhook/telegram`).
2. **Env:** Copy [.env.example](.env.example) to `.env` and set `NEO4J_*`, `TELEGRAM_BOT_TOKEN`.
3. **Set Telegram webhook:** In production, your backend must be reachable over HTTPS. Set the webhook URL to `https://<your-domain>/webhook/telegram` (e.g. via Telegram Bot API or a one-off script). Then Telegram will POST updates to that URL; no need to run a separate bot process.
4. **Run without Docker:** `pip install -e ".[bot,api]"`, start Neo4j (e.g. `docker compose up -d neo4j`), then `uvicorn api.main:app --reload --port 8000`. Again, set the webhook URL to your public HTTPS endpoint for Telegram to work.

**Local dev without a public URL:** Use polling so Telegram doesn’t need to reach your machine: set `USE_POLLING=1`, then run `python -m bot` (same contact flow; Neo4j must be running). Alternatively use a tunnel (e.g. ngrok) and point the webhook at it.

Commands in Telegram: share a contact to add (then send context text), `/list`, `/search <keyword>`.

## Core logic and tests

The `bimoi/` package uses a clean-architecture layout: **domain** (Person, RelationshipContext), **application** (ContactService, ports, DTOs), **infrastructure** (Neo4j and in-memory adapters). Tests use the in-memory repo; integration tests use testcontainers Neo4j.

- **Run tests:** From repo root with venv activated: `pip install -e ".[dev]"` then `pytest tests/ -v` (src layout: tests run against the installed package)
- **CI:** Tests run on every push via [.github/workflows/test.yml](.github/workflows/test.yml)

## Tasks and status (Notion)

Project tasks, user stories, and status are tracked in **Notion**. Branches are associated with tasks by naming: use `feature/US-1-add-contact`, `feature/US-4-list-contacts`, etc., and set the **Branch** field in your Notion tasks database to the branch name when you start work. If you connect the **Notion MCP** server in Cursor (Settings → MCP; remote OAuth at `https://mcp.notion.com/mcp` or local with `@notionhq/notion-mcp-server`), you can ask in chat for project status or the user story for the current branch and the AI will fetch and summarize from Notion.

## Repo layout

- **`src/`** — Installable packages (src layout: tests run against installed package)
  - **`src/bimoi/`** — Core (domain, application, infrastructure)
  - **`src/api/`** — FastAPI backend (REST + Telegram webhook); run with `uvicorn api.main:app`
  - **`src/bot/`** — Telegram polling entry point for local dev (`USE_POLLING=1 python -m bot`)
- **`docs/PROJECT_CONTEXT.md`** — Full product and domain spec for the MVP
- **`tests/`** — Unit and integration tests (integration tests require Docker)
- **`poc/`** — Standalone Telegram contact-card POC (unchanged)
- **`Dockerfile`** — Backend image (FastAPI + uvicorn)
- **`docker-compose.yml`** — Neo4j + backend services
- **`.env.example`** — NEO4J_*, TELEGRAM_BOT_TOKEN
- **`.github/workflows/test.yml`** — Run tests on every push
