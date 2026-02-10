"""
POC: Connect to Telegram and read contact cards.
Run with TELEGRAM_BOT_TOKEN set (e.g. from .env in poc/ or environment).
"""
import os
import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env from poc/ so it works when run from project root or from poc/
_env = Path(__file__).resolve().parent / ".env"
load_dotenv(_env)

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Set TELEGRAM_BOT_TOKEN (e.g. in poc/.env or export). "
            "Get a token from @BotFather on Telegram."
        )
    return token


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send or share a contact card to test. I'll echo back what I read."
    )


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    contact = update.message.contact
    if not contact:
        return
    name = contact.first_name or ""
    if contact.last_name:
        name = f"{name} {contact.last_name}".strip()
    parts = [
        f"Contact received:",
        f"  Name: {name or '(none)'}",
        f"  Phone: {contact.phone_number or '(none)'}",
        f"  Telegram user_id: {contact.user_id or '(none)'}",
    ]
    if contact.vcard:
        parts.append(f"  vCard: (present, {len(contact.vcard)} chars)")
    await update.message.reply_text("\n".join(parts))
    logger.info("Contact read: %s", name or contact.phone_number)


async def other_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send a contact card (share a contact) to test the POC."
    )


def main() -> None:
    token = get_token()
    app = (
        Application.builder()
        .token(token)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, other_message))

    logger.info("POC bot running (polling). Send a contact card to the bot to test.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
