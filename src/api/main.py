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
    AddContextNotFound,
    AddContextSuccess,
    ContactCardData,
    ContactCreated,
    ContactService,
    ContactSummary,
    Duplicate,
    Invalid,
    PendingContact,
)
from bimoi.infrastructure import (
    Neo4jContactRepository,
    ensure_channel_link_constraint,
    get_or_create_user_id,
)
from bimoi.infrastructure.identity import CHANNEL_TELEGRAM

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


def _first_last(name: str) -> tuple[str, str | None]:
    """Split name into first_name and optional last_name (first word vs rest)."""
    parts = (name or "").strip().split(None, 1)
    if not parts:
        return "Unknown", None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


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
        "Set webhook to a public HTTPS URL (e.g. ngrok). See README: Development with ngrok."
    )
    try:
        app.state.driver = _get_driver()
        ensure_channel_link_constraint(app.state.driver)
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

# Centralized copy for /start, /help, and all bot replies
_WELCOME_LINE = "Add contacts by sharing a card; I'll ask why they matter."
_HOW_TO_ADD_CONTACT = "To add someone: tap the attachment icon, choose Contact, then send their card here."
_COMMAND_LIST = (
    "You can:\n"
    "• /list — see all your contacts\n"
    "• /search <word> — search by description (e.g. /search work)"
)
_EMPTY_LIST_MSG = (
    "No contacts yet. To add one: share a contact card (attachment → Contact)."
)
_PENDING_CONTEXT_EXAMPLE = "e.g. 'Colleague from Project X, great at reviews'."
_SEARCH_PROMPT = "Type a keyword to search in your contact descriptions (e.g. work)."
_SEARCH_USAGE = "Use /search <word> to search in your descriptions (e.g. /search work)."
_CONTACT_ADDED_EXTRA = (
    "You can find them later with Search using a word from their description."
)
_DUPLICATE_EXTRA = "Use List contacts or Search to find them."
_PENDING_LOST_EXTRA = "Share their card again to add them."
_UNSUPPORTED_INPUT_MSG = (
    "I only accept contact cards and text. Use the buttons below: "
    "List contacts, Search, or Add contact."
)
_ADD_CONTACT_HOWTO = "To add a contact, share their card: tap the attachment icon, choose Contact, then send it here."
_CONTEXT_HINTS = "E.g. We met at… • We work together in… • Who introduced us: …"
_DUPLICATE_OFFER_ADD_CONTEXT = (
    "They're already in your contacts. Send a message to add more context about {name}.\n"
    + _CONTEXT_HINTS
)
_ADD_CONTEXT_BUTTON_PROMPT = (
    "Send a message to add more context about {name}.\n" + _CONTEXT_HINTS
)
_ADD_CONTEXT_SUCCESS = "Added. " + _CONTACT_ADDED_EXTRA
_ADD_MORE_OR_DONE_MSG = "Added. Add more or done?"
_ADD_MORE_CONTEXT_AGAIN_MSG = (
    "Send another message to add more context about {name}.\n" + _CONTEXT_HINTS
)
_ADD_CONTEXT_DONE_MSG = "Done. You can find them with Search."
_ADD_CONTEXT_NOT_FOUND = "That contact couldn't be found."
_ADD_CONTEXT_EMPTY = "Please send some text to add."

# Chat id -> True when we are waiting for the next message as search keyword
_search_pending_by_chat: dict[int, bool] = {}
# Chat id -> (person_id, name) when we are waiting for text to append to an existing contact
_pending_add_context_by_chat: dict[int, tuple[str, str]] = {}


def _pending_add_context_file() -> Path:
    """Path for file-backed pending add-context state (survives process/request boundaries)."""
    root = Path(__file__).resolve().parent.parent.parent
    return root / ".cursor" / "pending_add_context.json"


def _load_pending_add_context(user_id: str) -> dict[int, tuple[str, str]]:
    """Load pending add-context for a user from file. Returns dict chat_id -> (person_id, name)."""
    path = _pending_add_context_file()
    out: dict[int, tuple[str, str]] = {}
    try:
        if path.exists():
            data = path.read_text(encoding="utf-8")
            obj = __import__("json").loads(data)
            per_user = obj.get(user_id) or {}
            for k, v in per_user.items():
                if isinstance(v, list | tuple) and len(v) >= 2:
                    out[int(k)] = (str(v[0]), str(v[1]))
    except Exception:  # noqa: S110
        pass
    return out


def _save_pending_add_context(
    user_id: str, chat_id: int, person_id: str, name: str
) -> None:
    """Append one pending add-context entry for (user_id, chat_id)."""
    path = _pending_add_context_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        obj = {}
        if path.exists():
            obj = __import__("json").loads(path.read_text(encoding="utf-8"))
        if user_id not in obj:
            obj[user_id] = {}
        obj[user_id][str(chat_id)] = [person_id, name]
        path.write_text(__import__("json").dumps(obj), encoding="utf-8")
    except Exception:  # noqa: S110
        pass


def _pop_pending_add_context_from_file(
    user_id: str, chat_id: int
) -> tuple[str, str] | None:
    """Remove and return pending add-context for (user_id, chat_id) from file, or None."""
    path = _pending_add_context_file()
    try:
        if not path.exists():
            return None
        obj = __import__("json").loads(path.read_text(encoding="utf-8"))
        per_user = obj.get(user_id)
        if not per_user:
            return None
        val = per_user.pop(str(chat_id), None)
        if val and isinstance(val, list | tuple) and len(val) >= 2:
            # Write back without this entry
            path.write_text(__import__("json").dumps(obj), encoding="utf-8")
            return (str(val[0]), str(val[1]))
    except Exception:  # noqa: S110
        pass
    return None


def _clear_pending_add_context_from_file(user_id: str, chat_id: int) -> None:
    """Remove pending add-context for (user_id, chat_id) from file."""
    _pop_pending_add_context_from_file(user_id, chat_id)


def _main_keyboard():
    """Reply keyboard with List contacts, Search, and Add contact buttons."""
    from telegram import KeyboardButton, ReplyKeyboardMarkup

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("List contacts"),
                KeyboardButton("Search"),
            ],
            [KeyboardButton("Add contact")],
        ],
        resize_keyboard=True,
    )


def _add_context_inline_keyboard(person_id: str):
    """Inline keyboard with one button: Add relationship context (callback_data = person_id)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Add relationship context", callback_data=person_id)],
        ]
    )


def _add_more_or_done_keyboard(person_id: str):
    """Inline keyboard after adding context: Add more context | I'm done."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Add more context", callback_data="addmore:" + person_id
                ),
                InlineKeyboardButton("I'm done", callback_data="addctx_done"),
            ],
        ]
    )


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request):
    """Handle Telegram updates. Set Telegram webhook URL to https://<your-domain>/webhook/telegram"""
    from telegram import Bot, Update

    logger.info("Telegram webhook received")
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
        logger.warning("Telegram webhook: no update or effective_user")
        return {}
    driver = _get_cached_driver(app)
    user_id = get_or_create_user_id(
        driver, CHANNEL_TELEGRAM, str(update.effective_user.id)
    )
    _raw_chat_id = update.effective_chat.id if update.effective_chat else None
    chat_id = int(_raw_chat_id) if _raw_chat_id is not None else None
    if chat_id is None:
        logger.warning("Telegram webhook: no chat_id")
        return {}
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set in backend environment")
        return {}
    bot = Bot(token=token)
    service = get_service(user_id, app)

    # Inline button callbacks: Add more context / I'm done (after adding context), or Add context (from list/search)
    if update.callback_query:
        cq = update.callback_query
        cq_chat_id = cq.message.chat.id if cq.message and cq.message.chat else chat_id
        cq_chat_id = int(cq_chat_id) if cq_chat_id is not None else None
        data = (cq.data or "").strip()

        if data.startswith("addmore:") and cq_chat_id is not None:
            person_id = data[8:].strip()
            contact = service.get_contact(person_id) if person_id else None
            if contact:
                _pending_add_context_by_chat[cq_chat_id] = (person_id, contact.name)
                _save_pending_add_context(user_id, cq_chat_id, person_id, contact.name)
                await bot.answer_callback_query(callback_query_id=cq.id)
                await bot.send_message(
                    chat_id=cq_chat_id,
                    text=_ADD_MORE_CONTEXT_AGAIN_MSG.format(name=contact.name),
                )
            else:
                await bot.answer_callback_query(
                    callback_query_id=cq.id,
                    text=_ADD_CONTEXT_NOT_FOUND,
                )
            return {}
        if data == "addctx_done":
            await bot.answer_callback_query(callback_query_id=cq.id)
            await bot.send_message(chat_id=cq_chat_id, text=_ADD_CONTEXT_DONE_MSG)
            return {}

        person_id = data
        contact = service.get_contact(person_id) if person_id else None
        if person_id and cq_chat_id is not None:
            if contact:
                _pending_add_context_by_chat[cq_chat_id] = (person_id, contact.name)
                _save_pending_add_context(user_id, cq_chat_id, person_id, contact.name)
                await bot.answer_callback_query(callback_query_id=cq.id)
                await bot.send_message(
                    chat_id=cq_chat_id,
                    text=_ADD_CONTEXT_BUTTON_PROMPT.format(name=contact.name),
                )
            else:
                await bot.answer_callback_query(
                    callback_query_id=cq.id,
                    text=_ADD_CONTEXT_NOT_FOUND,
                )
        else:
            await bot.answer_callback_query(callback_query_id=cq.id)
        return {}

    async def send(text: str, reply_markup=None) -> None:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

    async def send_contact_results(summaries: list[ContactSummary]) -> None:
        """Send each contact as a Telegram contact card (if phone) + context, or as text. Each with 'Add relationship context' button."""
        add_ctx_kb = _add_context_inline_keyboard
        for s in summaries:
            if s.phone_number and s.phone_number.strip():
                first_name, last_name = _first_last(s.name)
                try:
                    await bot.send_contact(
                        chat_id=chat_id,
                        phone_number=s.phone_number.strip(),
                        first_name=first_name,
                        last_name=last_name,
                    )
                    await send(f"— {s.context}", reply_markup=add_ctx_kb(s.person_id))
                except Exception:
                    await send(
                        _format_contact_card(s), reply_markup=add_ctx_kb(s.person_id)
                    )
            else:
                await send(
                    _format_contact_card(s), reply_markup=add_ctx_kb(s.person_id)
                )

    # Contact shared (Contact object from python-telegram-bot)
    if update.message and update.message.contact:
        _search_pending_by_chat.pop(chat_id, None)
        _pending_add_context_by_chat.pop(chat_id, None)
        _clear_pending_add_context_from_file(user_id, chat_id)
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
                f"Got it. Send me a short description of why {result.name} matters to you. "
                f"{_PENDING_CONTEXT_EXAMPLE}"
            )
        elif isinstance(result, Duplicate):
            _pending_add_context_by_chat[chat_id] = (result.person_id, result.name)
            _save_pending_add_context(user_id, chat_id, result.person_id, result.name)
            await send(_DUPLICATE_OFFER_ADD_CONTEXT.format(name=result.name))
        elif isinstance(result, Invalid):
            await send(result.reason)
        return {}

    # Text message
    if update.message and update.message.text:
        text = (update.message.text or "").strip()
        t = text.lower()
        # Clear search-pending and add-context pending when user runs another command or list/search
        if text in (
            "/start",
            "/help",
            "/list",
            "List contacts",
            "Add contact",
        ) or t in ("list", "search", "add contact"):
            _search_pending_by_chat.pop(chat_id, None)
            _pending_add_context_by_chat.pop(chat_id, None)
            _clear_pending_add_context_from_file(user_id, chat_id)

        if text == "/start":
            welcome = f"{_WELCOME_LINE}\n{_HOW_TO_ADD_CONTACT}\n\n{_COMMAND_LIST}"
            await send(welcome, reply_markup=_main_keyboard())
            return {}
        if text == "/help":
            help_text = f"{_WELCOME_LINE}\n{_HOW_TO_ADD_CONTACT}\n\n{_COMMAND_LIST}"
            await send(help_text, reply_markup=_main_keyboard())
            return {}
        if text == "/list" or text == "List contacts" or t == "list":
            summaries = service.list_contacts()
            if not summaries:
                await send(_EMPTY_LIST_MSG)
            else:
                await send_contact_results(summaries)
            return {}
        if text == "Search" or t == "search":
            _search_pending_by_chat[chat_id] = True
            await send(_SEARCH_PROMPT)
            return {}
        if text == "Add contact" or t == "add contact":
            await send(_ADD_CONTACT_HOWTO, reply_markup=_main_keyboard())
            return {}
        if text.startswith("/search "):
            keyword = text[8:].strip()
            if not keyword:
                await send(_SEARCH_USAGE)
            else:
                summaries = service.search_contacts(keyword)
                if not summaries:
                    await send("No contacts match that keyword.")
                else:
                    await send_contact_results(summaries)
            return {}
        if _search_pending_by_chat.get(chat_id):
            _search_pending_by_chat.pop(chat_id, None)
            keyword = text
            summaries = service.search_contacts(keyword)
            if not summaries:
                await send("No contacts match that keyword.")
            else:
                await send_contact_results(summaries)
            return {}
        # Add more context to an existing contact (from re-share or "Add context" button)
        add_ctx = _pending_add_context_by_chat.pop(chat_id, None)
        if add_ctx is None:
            add_ctx = _pop_pending_add_context_from_file(user_id, chat_id)
        if add_ctx:
            person_id, name = add_ctx
            result = service.add_context(person_id, text)
            if isinstance(result, AddContextSuccess):
                await send(
                    _ADD_MORE_OR_DONE_MSG,
                    reply_markup=_add_more_or_done_keyboard(person_id),
                )
            elif isinstance(result, AddContextNotFound):
                await send(_ADD_CONTEXT_NOT_FOUND)
            else:
                await send(_ADD_CONTEXT_EMPTY)
            return {}
        # Treat as context for pending (new contact)
        pending_id = _pending_by_chat.get(chat_id)
        if not pending_id:
            await send(
                "Send a contact card first, then I'll ask for a description.",
                reply_markup=_main_keyboard(),
            )
            return {}
        result = service.submit_context(pending_id, text)
        _pending_by_chat.pop(chat_id, None)
        if isinstance(result, ContactCreated):
            await send(f"Contact {result.name} added. {_CONTACT_ADDED_EXTRA}")
        else:
            await send(f"That contact wasn't pending anymore. {_PENDING_LOST_EXTRA}")
        return {}

    # Message present but not contact and not text (e.g. photo, voice, sticker)
    if update.message:
        await send(_UNSUPPORTED_INPUT_MSG, reply_markup=_main_keyboard())
        return {}

    return {}
