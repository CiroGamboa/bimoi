# Bimoi

Bimoi helps you externalize your real relationships: who you know and why they matter. Instead of that knowledge living only in memory or chat history, you capture it at the moment it’s freshest—by sharing a contact and adding context—with minimal friction.

**Current status:** Early stage. A [proof-of-concept](poc/README.md) validates that we can connect to Telegram and read contact cards. The full MVP (contact creation with context, persistence, search) is defined in the project context below.

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

## Repo layout

- **`docs/PROJECT_CONTEXT.md`** — Full product and domain spec for the MVP
- **`domain.py`** — Core domain types (Person, RelationshipContext) for future use
- **`poc/`** — Telegram contact-card POC (bot, README, requirements)
