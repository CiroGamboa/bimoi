"""
Production bot: Telegram + ContactService + Neo4j.
Run: python -m bot (from repo root, with .env or env vars set).
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root: from src/bot/__main__.py go up to repo root (parent.parent.parent when in src layout)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# Load .env from repo root or current dir
for path in (_REPO_ROOT / ".env", Path.cwd() / ".env"):
    if path.exists():
        load_dotenv(path)
        break

from neo4j import GraphDatabase
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bimoi.application import (
    ContactCardData,
    ContactCreated,
    ContactService,
    Duplicate,
    Invalid,
    PendingContact,
)
from bimoi.infrastructure import Neo4jContactRepository

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SERVICE_KEY = "contact_service"


def _get_service(context: ContextTypes.DEFAULT_TYPE) -> ContactService:
    return context.bot_data[SERVICE_KEY]


def _contact_from_telegram(contact) -> ContactCardData:
    name = (contact.first_name or "").strip()
    if contact.last_name:
        name = f"{name} {contact.last_name}".strip()
    return ContactCardData(
        name=name or "Unknown",
        phone_number=contact.phone_number or None,
        telegram_user_id=contact.user_id,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send or share a contact card to add a contact. "
        "I'll ask for a short description of why this person matters. "
        "Commands: /list — list all contacts; /search <keyword> — search by context."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    service = _get_service(context)
    # If we have a pending, treat text as context (unless it's a command)
    if text.startswith("/"):
        if text == "/list":
            summaries = service.list_contacts()
            if not summaries:
                await update.message.reply_text("No contacts yet. Share a contact card to add one.")
                return
            lines = [f"{s.name} — {s.context}" for s in summaries]
            await update.message.reply_text("\n\n".join(lines))
            return
        if text.startswith("/search "):
            keyword = text[8:].strip()
            if not keyword:
                await update.message.reply_text("Usage: /search <keyword>")
                return
            summaries = service.search_contacts(keyword)
            if not summaries:
                await update.message.reply_text("No contacts match that keyword.")
                return
            lines = [f"{s.name} — {s.context}" for s in summaries]
            await update.message.reply_text("\n\n".join(lines))
            return
        await update.message.reply_text(
            "Send a contact card to add a contact, or use /list and /search <keyword>."
        )
        return
    # Treat as context for pending contact
    # We need to submit with the current pending_id; the service holds one pending per process
    # We don't have the pending_id in context - the service has it internally. So we need to
    # either store pending_id in bot_data when we get PendingContact, or change the service
    # to accept "submit context for current pending" without id. The service API is
    # submit_context(pending_id, text). So we must store the last pending_id when we return
    # PendingContact. Store in bot_data: bot_data["pending_id"] = result.pending_id
    pending_id = context.bot_data.get("pending_id")
    if not pending_id:
        await update.message.reply_text(
            "Send a contact card first, then I'll ask for a description."
        )
        return
    result = service.submit_context(pending_id, text)
    if isinstance(result, ContactCreated):
        context.bot_data.pop("pending_id", None)
        await update.message.reply_text(f"Contact {result.name} added.")
    else:
        context.bot_data.pop("pending_id", None)
        await update.message.reply_text(
            "That contact wasn't pending anymore. Send a contact card again to add one."
        )


async def handle_contact_then_save_pending(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle contact and store pending_id in bot_data for the next text message."""
    contact = update.message.contact
    if not contact:
        return
    card = _contact_from_telegram(contact)
    service = _get_service(context)
    result = service.receive_contact_card(card)
    if isinstance(result, PendingContact):
        context.bot_data["pending_id"] = result.pending_id
        await update.message.reply_text(
            f"Got it. Send me a short description of why {result.name} matters to you."
        )
    elif isinstance(result, Duplicate):
        await update.message.reply_text("This contact already exists.")
    elif isinstance(result, Invalid):
        await update.message.reply_text(result.reason)


async def other_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "I only accept contact cards and text. Share a contact to add someone, or use /list and /search."
    )


def main() -> None:
    use_polling = os.environ.get("USE_POLLING", "").strip().lower() in ("1", "true", "yes")
    if not use_polling:
        raise SystemExit(
            "For production use the FastAPI backend: uvicorn api.main:app "
            "and set the Telegram webhook to https://<your-domain>/webhook/telegram. "
            "For local dev with polling set USE_POLLING=1 and run python -m bot again."
        )
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687").strip()
    user = os.environ.get("NEO4J_USER", "neo4j").strip()
    password = os.environ.get("NEO4J_PASSWORD", "password").strip()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Set TELEGRAM_BOT_TOKEN (e.g. in .env). Get a token from @BotFather."
        )
    driver = GraphDatabase.driver(uri, auth=(user, password))
    repo = Neo4jContactRepository(driver, user_id="default")
    service = ContactService(repo)
    app = Application.builder().token(token).build()
    app.bot_data[SERVICE_KEY] = service
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact_then_save_pending))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND & ~filters.CONTACT & ~filters.TEXT,
            other_message,
        )
    )
    logger.info("Bot running (polling, dev). Commands: /list, /search")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
