# Context for AI coding assistants

This file gives LLMs and other agents the main pointers to understand and work on this project. Read it first, then follow the references below as needed.

## What this project is

**Bimoi** — Externalize real relationships: who you know and why they matter. MVP is a multi-user Telegram bot: each user has their own isolated contact graph. Users add contacts by sharing a contact card, then add free-text context. Authentication is handled by Telegram.

## Where to find what

| Need | Location |
|------|----------|
| **Full product scope, requirements, user stories, domain model** | [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) — canonical source of truth |
| **Domain types (Person, RelationshipContext)** | [src/bimoi/domain/](src/bimoi/domain/) — use these types when implementing features |
| **Core business logic (contact flow, list, search)** | [src/bimoi/application/](src/bimoi/application/) — ContactService, ContactRepository, ContactCardData |
| **Neo4j persistence** | [src/bimoi/infrastructure/persistence/](src/bimoi/infrastructure/persistence/) — Neo4jContactRepository |
| **Production Telegram bot** | [src/bot/](src/bot/) — run with `python -m bot` (Neo4j + ContactService) |
| **Conversation flow (XState)** | [flows/telegram_machine.json](flows/telegram_machine.json) — standard state machine (xstate-python); [src/api/flow_adapter.py](src/api/flow_adapter.py) — effects; messages in [flows/telegram.yaml](flows/telegram.yaml). See [docs/CONVERSATION_ARCHITECTURE.md](docs/CONVERSATION_ARCHITECTURE.md) for fixed workflows vs semantic layer. |
| **Human-facing overview and POC instructions** | [README.md](README.md) |
| **Telegram POC (connect + read contact card)** | [poc/](poc/) — [poc/README.md](poc/README.md) for setup and run |

## Setup and run (for agents)

- **Python:** 3.10+
- **Venv:** From repo root: `python3 -m venv .venv`, then `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`).
- **POC deps:** `pip install -r poc/requirements.txt`
- **POC token:** Set `TELEGRAM_BOT_TOKEN` (e.g. in `poc/.env`; see `poc/.env.example`). Get token from @BotFather.
- **Run POC:** `python poc/bot.py`
- **Production bot:** Start Neo4j with `docker compose up -d`, set `.env` (see [.env.example](.env.example)), then `pip install -e ".[bot]"` and `python -m bot`.
- **Tests:** `pip install -e ".[dev,api]"` then `pytest tests/ -v`. Package uses src layout; tests run against the installed package. API tests need the `api` extra (FastAPI, xstate-python). If your index doesn't have Js2Py 0.71 (e.g. private Azure index), use `pip install --extra-index-url https://pypi.org/simple -e ".[dev,api]"`. CI runs tests on every push.
- **Code quality (pre-commit):** `pre-commit install`. Hooks run on commit (isort, ruff, trailing whitespace, etc.). Run manually: `pre-commit run --all-files`.

## Tasks and status (Notion)

Project tasks and user stories live in **Notion**. Branch naming convention: `feature/US-<id>-<slug>` (e.g. `feature/US-1-add-contact`). When the user asks for project status or the user story for the current branch, use **Notion MCP** to query the tasks database and summarize (search or filter by Branch or ID). Configure Notion MCP in Cursor (Settings → MCP) if not already connected.

## Conventions

- Keep behavior and scope aligned with [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md). Do not add features that are explicitly out of scope (e.g. multi-user, auth, tagging, context editing).
- Use or extend types from [bimoi.domain](src/bimoi/domain/) for contact/context modeling rather than inventing new structures.
