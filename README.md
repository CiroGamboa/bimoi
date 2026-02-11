# Bimoi

Bimoi helps you externalize your real relationships: who you know and why they matter. Instead of that knowledge living only in memory or chat history, you capture it at the moment it’s freshest—by sharing a contact and adding context—with minimal friction.

**Current status:** Production bot in `bot/` wires Telegram to the core (`bimoi/`) and persists contacts in **Neo4j** (Docker for dev). Core logic is tested with an in-memory repo; [poc/](poc/README.md) remains a standalone POC.

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

## Production bot (Neo4j + Telegram)

The **bot** package runs the full flow: Telegram → ContactService → Neo4j.

1. **Neo4j (Docker):** `docker compose up -d` — Neo4j on ports 7474 (HTTP) and 7687 (Bolt).
2. **Env:** Copy [.env.example](.env.example) to `.env` and set `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `TELEGRAM_BOT_TOKEN`.
3. **Run:** `pip install -e ".[bot]"` (or install neo4j, python-telegram-bot, python-dotenv), then `python -m bot`.

Commands in Telegram: share a contact to add (then send context text), `/list`, `/search <keyword>`.

## Core logic and tests

The `bimoi/` package implements the contact creation flow (receive contact card → pending → submit context → stored), duplicate detection, list, and search. It uses [domain.py](domain.py) (Person, RelationshipContext). Persistence is via [bimoi.persistence](bimoi/persistence/) (Neo4j adapter); tests use the in-memory repo.

- **Run tests:** From repo root with venv activated: `pip install -r requirements-dev.txt` then `pytest tests/ -v`
- **CI:** Tests run on every push via [.github/workflows/test.yml](.github/workflows/test.yml)

## Tasks and status (Notion)

Project tasks, user stories, and status are tracked in **Notion**. Branches are associated with tasks by naming: use `feature/US-1-add-contact`, `feature/US-4-list-contacts`, etc., and set the **Branch** field in your Notion tasks database to the branch name when you start work. If you connect the **Notion MCP** server in Cursor (Settings → MCP; remote OAuth at `https://mcp.notion.com/mcp` or local with `@notionhq/notion-mcp-server`), you can ask in chat for project status or the user story for the current branch and the AI will fetch and summarize from Notion.

## Repo layout

- **`docs/PROJECT_CONTEXT.md`** — Full product and domain spec for the MVP
- **`domain.py`** — Core domain types (Person, RelationshipContext)
- **`bimoi/`** — Core business logic (ContactService, repository, contact card DTOs) and **`bimoi.persistence`** — Neo4j adapter
- **`bot/`** — Production Telegram bot (ContactService + Neo4j); run with `python -m bot`
- **`tests/`** — Unit tests for the core logic
- **`poc/`** — Standalone Telegram contact-card POC (unchanged)
- **`docker-compose.yml`** — Neo4j for local development
- **`.env.example`** — NEO4J_*, TELEGRAM_BOT_TOKEN for the production bot
- **`.github/workflows/test.yml`** — Run tests on every push
