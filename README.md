# Bimoi

Bimoi helps you externalize your real relationships: who you know and why they matter. Instead of that knowledge living only in memory or chat history, you capture it at the moment it’s freshest—by sharing a contact and adding context—with minimal friction.

**Current status:** A **FastAPI backend** exposes a REST API and the **Telegram webhook**; one service handles all clients. Contacts are stored in **Neo4j**. In production the bot receives updates via webhook; for local development you expose the backend with ngrok and set the webhook to the ngrok URL. [poc/](poc/README.md) remains a standalone POC.

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

One backend serves the **REST API** and the **Telegram bot** (via webhook). Telegram sends updates to your server.

1. **Docker:** `docker compose up -d` — starts Neo4j and the backend (e.g. http://localhost:8010 for health and API).
2. **Env:** Copy [.env.example](.env.example) to `.env` and set `NEO4J_*`, `TELEGRAM_BOT_TOKEN`.
3. **Webhook:** In production, point the Telegram webhook to `https://<your-domain>/webhook/telegram`. For local development, use ngrok (see below).

Commands in Telegram: share a contact to add (then send context text), `/list`, `/search <keyword>`.

---

## Architecture Overview

**Technology Stack**:
- Backend: FastAPI (REST API + Telegram webhook)
- Database: Neo4j (graph for contacts and identity)
- Conversation Flow: XState state machine (flow-as-data, see [docs/CONVERSATION_ARCHITECTURE.md](docs/CONVERSATION_ARCHITECTURE.md))
- Deployment: Docker Compose (Neo4j + backend)

**Data Model**:
Graph structure optimized for "who you know and why":
- Person nodes (owner with registered: true, contacts with registered: false)
- KNOWS relationships with context properties (description, timestamps)
- Account/ChannelLink nodes for multi-channel identity (Telegram, future WhatsApp/web)

**Key Design Decisions**:
1. Context lives on relationships, not separate nodes (describes the connection, not the person)
2. Single-user MVP: one Account per user, contacts scoped by KNOWS edge from owner
3. Flow-as-data: conversation logic in JSON/YAML (flows/telegram_machine.json), not hardcoded
4. Clean architecture: domain entities agnostic to storage, repository pattern for persistence

See [AGENTS.md](AGENTS.md) for AI agent context and [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) for full product spec.

---

## Development with ngrok

Telegram cannot reach `localhost`, so to test the bot locally you expose your backend with a tunnel and set the webhook to that URL.

**Prerequisites:** [ngrok](https://ngrok.com/) installed, `TELEGRAM_BOT_TOKEN` in `.env`.

### One-command start / stop

From the repo root:

```bash
./scripts/dev-up.sh    # Start Neo4j + backend + ngrok, set webhook
./scripts/dev-down.sh  # Stop ngrok and Docker
```

`dev-up.sh` brings up Docker (Neo4j + backend), starts ngrok in the background, waits for the tunnel, then runs `set_webhook_ngrok.py`. Use your bot in Telegram. Optionally run `python scripts/set_telegram_commands.py` so the "/" menu shows start, list, and search. When you're done, run `dev-down.sh` to stop everything.

### Manual steps (alternative)

1. **Start the backend** (choose one):
   - **Docker:** `docker compose up -d` — backend on **port 8010**.
   - **Local:** `pip install -e ".[bot,api]"`, `docker compose up -d neo4j`, then `uvicorn api.main:app --reload --port 8000` — backend on **port 8000**.

2. **Start ngrok** against the same port as the backend:
   - Docker: `ngrok http 8010`
   - Local uvicorn: `ngrok http 8000`
   Leave this terminal open; ngrok will show a public HTTPS URL (e.g. `https://abc123.ngrok-free.app`).

3. **Set the Telegram webhook** to the ngrok URL:
   ```bash
   python scripts/set_webhook_ngrok.py
   ```
   The script reads the current ngrok tunnel from `http://127.0.0.1:4040` and sets the webhook to `https://<ngrok-url>/webhook/telegram`. Use the same port in step 2 as your backend (8010 for Docker, 8000 for uvicorn).

4. **Use the bot** in Telegram: open your bot, send `/start`, share a contact, etc. Updates go to ngrok → your backend.

The backend runs with **auto-reload** (`--reload`), so code changes under `src/` should apply without restarting. If changes don't appear (e.g. Docker on some hosts), run `docker compose restart backend`.

**To stop:** Run `./scripts/dev-down.sh`.

**No response in Telegram?** Run `./scripts/dev-check-telegram.sh` from the repo root. It checks: webhook URL, whether the backend container has the token, backend health, and recent logs. Ensure `.env` contains a line `TELEGRAM_BOT_TOKEN=<your_bot_token>` (from @BotFather). If you changed `.env` after starting, run `./scripts/dev-down.sh` then `./scripts/dev-up.sh` so the backend picks up the token.

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
  - **`src/bot/`** — Bot runs via FastAPI webhook only; `python -m bot` prints instructions
- **`docs/PROJECT_CONTEXT.md`** — Full product and domain spec for the MVP
- **`tests/`** — Unit and integration tests (integration tests require Docker)
- **`poc/`** — Standalone Telegram contact-card POC (unchanged)
- **`Dockerfile`** — Backend image (FastAPI + uvicorn)
- **`docker-compose.yml`** — Neo4j + backend services
- **`.env.example`** — NEO4J_*, TELEGRAM_BOT_TOKEN
- **`.github/workflows/test.yml`** — Run tests on every push
