# Context for AI coding assistants

This file gives LLMs and other agents the main pointers to understand and work on this project. Read it first, then follow the references below as needed.

## What this project is

**Bimoi** — Externalize real relationships: who you know and why they matter. MVP is a single-user Telegram bot: users add contacts by sharing a contact card, then add free-text context. No auth, no multi-user.

## Where to find what

| Need | Location |
|------|----------|
| **Full product scope, requirements, user stories, domain model** | [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) — canonical source of truth |
| **Domain types (Person, RelationshipContext)** | [domain.py](domain.py) — use these types when implementing features |
| **Human-facing overview and POC instructions** | [README.md](README.md) |
| **Telegram POC (connect + read contact card)** | [poc/](poc/) — [poc/README.md](poc/README.md) for setup and run |

## Setup and run (for agents)

- **Python:** 3.10+
- **Venv:** From repo root: `python3 -m venv .venv`, then `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`).
- **POC deps:** `pip install -r poc/requirements.txt`
- **POC token:** Set `TELEGRAM_BOT_TOKEN` (e.g. in `poc/.env`; see `poc/.env.example`). Get token from @BotFather.
- **Run POC:** `python poc/bot.py`
- **Code quality (pre-commit):** `pip install -r requirements-dev.txt`, then `pre-commit install`. Hooks run on commit (isort, ruff, trailing whitespace, etc.). Run manually: `pre-commit run --all-files`.

## Conventions

- Keep behavior and scope aligned with [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md). Do not add features that are explicitly out of scope (e.g. multi-user, auth, tagging, context editing).
- Use or extend types from [domain.py](domain.py) for contact/context modeling rather than inventing new structures.
