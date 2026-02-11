"""
FastAPI backend: REST API and Telegram webhook.
Run with uvicorn: uvicorn api.main:app --reload
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root (when run from repo root or from Docker)
for path in (
    Path(__file__).resolve().parent.parent.parent / ".env",
    Path.cwd() / ".env",
):
    if path.exists():
        load_dotenv(path)
        break

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from neo4j import GraphDatabase
from pydantic import BaseModel

from bimoi.application import (
    ContactCardData,
    ContactCreated,
    ContactService,
    ContactSummary,
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

# Optional: multi-user placeholder (REST)
USER_ID_HEADER = "X-User-Id"
DEFAULT_USER_ID = "default"


def _get_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687").strip()
    user = os.environ.get("NEO4J_USER", "neo4j").strip()
    password = os.environ.get("NEO4J_PASSWORD", "password").strip()
    return GraphDatabase.driver(uri, auth=(user, password))


# Per-user ContactService cache (for webhook: same user keeps same pending state)
_service_cache: dict[str, ContactService] = {}
_pending_by_chat: dict[int, str] = {}  # chat_id -> pending_id for webhook


def _format_contact_card(s: ContactSummary) -> str:
    """Format one contact as card (name, phone) + description."""
    parts = [s.name]
    if s.phone_number:
        parts.append(f"Phone: {s.phone_number}")
    parts.append(f"— {s.context}")
    return "\n".join(parts)


def get_service(user_id: str, app: FastAPI) -> ContactService:
    driver = _get_cached_driver(app)
    if user_id not in _service_cache:
        repo = Neo4jContactRepository(driver, user_id=user_id)
        _service_cache[user_id] = ContactService(repo)
    return _service_cache[user_id]


def _get_cached_driver(app: FastAPI):
    if getattr(app.state, "driver", None) is None:
        app.state.driver = _get_driver()
    return app.state.driver


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.driver = None
    logger.info(
        "Telegram webhook: POST /webhook/telegram. "
        "To receive messages, set webhook to a public HTTPS URL (e.g. ngrok). "
        "Localhost is not reachable by Telegram. "
        "Local testing without tunnel: USE_POLLING=1 python -m bot"
    )
    try:
        yield
    finally:
        if getattr(app.state, "driver", None) is not None:
            app.state.driver.close()


app = FastAPI(title="Bimoi API", lifespan=lifespan)


# --- REST: health ---


@app.get("/health")
def health():
    return {"status": "ok"}


# --- REST: contacts ---


class CreateContactBody(BaseModel):
    name: str
    phone_number: str | None = None
    telegram_user_id: int | str | None = None
    context: str


class ContactListItem(BaseModel):
    name: str
    context: str
    created_at: str
    person_id: str = ""
    phone_number: str | None = None


@app.post("/contacts")
def create_contact(
    body: CreateContactBody,
    request: Request,
    x_user_id: str | None = Header(None, alias=USER_ID_HEADER),
):
    user_id = (x_user_id or "").strip() or DEFAULT_USER_ID
    service = get_service(user_id, request.app)
    card = ContactCardData(
        name=body.name,
        phone_number=body.phone_number,
        telegram_user_id=body.telegram_user_id,
    )
    result = service.receive_contact_card(card)
    if isinstance(result, Invalid):
        raise HTTPException(status_code=400, detail=result.reason)
    if isinstance(result, Duplicate):
        raise HTTPException(status_code=409, detail="Contact already exists")
    if not isinstance(result, PendingContact):
        raise HTTPException(status_code=400, detail="Invalid contact")
    context_clean = (body.context or "").strip()
    if not context_clean:
        raise HTTPException(status_code=400, detail="Context is required")
    created = service.submit_context(result.pending_id, context_clean)
    if not isinstance(created, ContactCreated):
        raise HTTPException(status_code=400, detail="Failed to create contact")
    return JSONResponse(
        content={"person_id": created.person_id, "name": created.name},
        status_code=201,
    )


@app.get("/contacts")
def list_contacts(
    request: Request,
    x_user_id: str | None = Header(None, alias=USER_ID_HEADER),
):
    user_id = (x_user_id or "").strip() or DEFAULT_USER_ID
    service = get_service(user_id, request.app)
    summaries = service.list_contacts()
    return [
        ContactListItem(
            name=s.name,
            context=s.context,
            created_at=s.created_at.isoformat(),
            person_id=s.person_id,
            phone_number=s.phone_number,
        )
        for s in summaries
    ]


@app.get("/contacts/search")
def search_contacts(
    q: str,
    request: Request,
    x_user_id: str | None = Header(None, alias=USER_ID_HEADER),
):
    user_id = (x_user_id or "").strip() or DEFAULT_USER_ID
    service = get_service(user_id, request.app)
    summaries = service.search_contacts(q)
    return [
        ContactListItem(
            name=s.name,
            context=s.context,
            created_at=s.created_at.isoformat(),
            person_id=s.person_id,
            phone_number=s.phone_number,
        )
        for s in summaries
    ]


# --- Telegram webhook ---


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request):
    """Handle Telegram updates. Set Telegram webhook URL to https://<your-domain>/webhook/telegram"""
    from telegram import Bot, Update

    try:
        body = await request.json()
    except Exception as e:
        logger.warning("Telegram webhook body error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON") from e
    try:
        update = Update.de_json(body, None)
    except Exception as e:
        logger.warning("Telegram webhook parse error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid update") from e
    if not update or not update.effective_user:
        return {}
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        return {}
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return {}
    bot = Bot(token=token)
    service = get_service(user_id, app)

    async def send(text: str) -> None:
        await bot.send_message(chat_id=chat_id, text=text)

    # Contact shared (Contact object from python-telegram-bot)
    if update.message and update.message.contact:
        c = update.message.contact
        name = (getattr(c, "first_name", None) or "").strip()
        if getattr(c, "last_name", None):
            name = f"{name} {c.last_name}".strip()
        name = name or "Unknown"
        card = ContactCardData(
            name=name,
            phone_number=getattr(c, "phone_number", None),
            telegram_user_id=getattr(c, "user_id", None),
        )
        result = service.receive_contact_card(card)
        if isinstance(result, PendingContact):
            _pending_by_chat[chat_id] = result.pending_id
            await send(
                f"Got it. Send me a short description of why {result.name} matters to you."
            )
        elif isinstance(result, Duplicate):
            await send("This contact already exists.")
        elif isinstance(result, Invalid):
            await send(result.reason)
        return {}

    # Text message
    if update.message and update.message.text:
        text = (update.message.text or "").strip()
        if text == "/start":
            await send(
                "Send or share a contact card to add a contact. "
                "I'll ask for a short description of why this person matters. "
                "Commands: /list — list all contacts; /search <keyword> — search by context."
            )
            return {}
        if text == "/list":
            summaries = service.list_contacts()
            if not summaries:
                await send("No contacts yet. Share a contact card to add one.")
            else:
                lines = [_format_contact_card(s) for s in summaries]
                await send("\n\n".join(lines))
            return {}
        if text.startswith("/search "):
            keyword = text[8:].strip()
            if not keyword:
                await send("Usage: /search <keyword>")
            else:
                summaries = service.search_contacts(keyword)
                if not summaries:
                    await send("No contacts match that keyword.")
                else:
                    lines = [_format_contact_card(s) for s in summaries]
                    await send("\n\n".join(lines))
            return {}
        # Treat as context for pending
        pending_id = _pending_by_chat.get(chat_id)
        if not pending_id:
            await send(
                "Send a contact card first, then I'll ask for a description."
            )
            return {}
        result = service.submit_context(pending_id, text)
        _pending_by_chat.pop(chat_id, None)
        if isinstance(result, ContactCreated):
            await send(f"Contact {result.name} added.")
        else:
            await send(
                "That contact wasn't pending anymore. Send a contact card again to add one."
            )
        return {}

    return {}
