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

# Flow state: (user_id, chat_id) -> { current_node_id, slots }
_flow_state: dict[tuple[str, int], dict] = {}


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


# --- Telegram webhook (flow-driven) ---


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


def _welcome_inline_keyboard(has_contacts: bool = True):
    """Inline keyboard for welcome/help. If has_contacts is False, only 'Add contact'; otherwise List, Search, Add contact."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if has_contacts:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("List contacts", callback_data="cmd:list"),
                    InlineKeyboardButton("Search", callback_data="cmd:search"),
                ],
                [InlineKeyboardButton("Add contact", callback_data="cmd:add")],
            ]
        )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Add contact", callback_data="cmd:add")]]
    )


async def _send_contact_results_impl(bot, chat_id: int, summaries: list) -> None:
    """Send each contact as card + context with 'Add relationship context' inline button."""
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
                await bot.send_message(
                    chat_id=chat_id, text=f"— {s.context}", reply_markup=add_ctx_kb(s.person_id)
                )
            except Exception:
                await bot.send_message(
                    chat_id=chat_id,
                    text=_format_contact_card(s),
                    reply_markup=add_ctx_kb(s.person_id),
                )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=_format_contact_card(s),
                reply_markup=add_ctx_kb(s.person_id),
            )


def _get_flow_state(user_id: str, chat_id: int, initial_state: str = "idle") -> dict:
    """Get flow state for (user_id, chat_id). Merge file-backed add_context into slots."""
    key = (user_id, chat_id)
    state = _flow_state.get(key)
    if not state:
        state = {
            "current_node_id": initial_state,
            "slots": {},
        }
    slots = dict(state.get("slots") or {})
    # Merge file-backed add_context so it survives restarts (read-only)
    from_file = _load_pending_add_context(user_id).get(chat_id)
    if from_file:
        person_id, name = from_file
        slots["person_id"] = person_id
        slots["contact_name"] = name
        state = {**state, "slots": slots}
    return state


def _set_flow_state(user_id: str, chat_id: int, state: dict) -> None:
    """Save flow state. Persist person_id/contact_name to file when set."""
    key = (user_id, chat_id)
    _flow_state[key] = state
    slots = state.get("slots") or {}
    person_id = slots.get("person_id")
    contact_name = slots.get("contact_name")
    if person_id and contact_name:
        _save_pending_add_context(user_id, chat_id, person_id, contact_name)
    else:
        _clear_pending_add_context_from_file(user_id, chat_id)


def _update_to_event(update, slots: dict) -> dict | None:
    """Build flow event from Telegram Update. Returns None if no relevant event."""
    from telegram import Update

    if not update or not isinstance(update, Update):
        return None
    # Callback
    if update.callback_query:
        cq = update.callback_query
        data = (cq.data or "").strip()
        payload = {"data": data}
        if data == "cmd:list":
            subtype = "cmd_list"
        elif data == "cmd:search":
            subtype = "cmd_search"
        elif data == "cmd:add":
            subtype = "cmd_add"
        elif data.startswith("addmore:"):
            subtype = "addmore"
            payload["person_id"] = data[8:].strip()
        elif data == "addctx_done":
            subtype = "addctx_done"
        else:
            subtype = "person_id"
            payload["person_id"] = data
        return {"type": "callback", "subtype": subtype, "payload": payload}
    # Contact shared
    if update.message and update.message.contact:
        c = update.message.contact
        name = (getattr(c, "first_name", None) or "").strip()
        if getattr(c, "last_name", None):
            name = f"{name} {c.last_name}".strip()
        name = name or "Unknown"
        return {
            "type": "contact_shared",
            "subtype": None,
            "payload": {
                "name": name,
                "phone_number": getattr(c, "phone_number", None),
                "telegram_user_id": getattr(c, "user_id", None),
            },
        }
    # Text
    if update.message and update.message.text:
        text = (update.message.text or "").strip()
        t = text.lower()
        payload = {"text": text}
        if text == "/start":
            subtype = "command_start"
        elif text == "/help":
            subtype = "command_help"
        elif text in ("/list", "List contacts") or t == "list":
            subtype = "command_list"
        elif text == "Search" or t == "search":
            subtype = "command_search"
        elif text == "Add contact" or t == "add contact":
            subtype = "command_add_contact"
        elif text.startswith("/search "):
            if not text[8:].strip():
                subtype = "unsupported"
            else:
                subtype = "search_keyword"
        elif slots.get("search_pending"):
            subtype = "search_keyword"
        elif slots.get("person_id") or slots.get("contact_name"):
            subtype = "add_context_text"
        elif slots.get("pending_id"):
            subtype = "pending_context_text"
        else:
            subtype = "unsupported"
        return {"type": "text", "subtype": subtype, "payload": payload}
    # Other message (photo, voice, etc.)
    if update.message:
        return {"type": "text", "subtype": "unsupported", "payload": {"text": ""}}
    return None


def _keyboard_by_name(name: str | None, slots: dict) -> object:
    """Return Telegram reply_markup for the given keyboard name. Requires person_id in slots for add_context/add_more_or_done."""
    if not name:
        return None
    person_id = (slots or {}).get("person_id") or ""
    if name == "main":
        return _main_keyboard()
    if name == "welcome":
        return _welcome_inline_keyboard(has_contacts=True)
    if name == "welcome_no_contacts":
        return _welcome_inline_keyboard(has_contacts=False)
    if name == "add_context" and person_id:
        return _add_context_inline_keyboard(person_id)
    if name == "add_more_or_done" and person_id:
        return _add_more_or_done_keyboard(person_id)
    return None


_ONBOARDING_MSG = (
    "Hi! Bimoi helps you remember who people are and why they matter—so that lives with you, "
    "not just in your head or in old chats. Share a contact card and add a short note; "
    "later you can search and list everyone. Let's get started."
)


def _telegram_display_name(effective_user) -> str | None:
    """Build a display name from Telegram effective_user (first_name, last_name, username)."""
    if not effective_user:
        return None
    first = (getattr(effective_user, "first_name", None) or "").strip()
    last = (getattr(effective_user, "last_name", None) or "").strip()
    if first or last:
        return f"{first} {last}".strip()
    username = getattr(effective_user, "username", None)
    if username and str(username).strip():
        return str(username).strip()
    return None


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request):
    """Handle Telegram updates. Set Telegram webhook URL to https://<your-domain>/webhook/telegram"""
    from telegram import Bot, Update

    from api.flow_adapter import SendContactList, SendMessage, run_xstate_flow

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
    initial_name = _telegram_display_name(update.effective_user)
    user_id, is_new_user = get_or_create_user_id(
        driver,
        CHANNEL_TELEGRAM,
        str(update.effective_user.id),
        initial_name=initial_name,
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

    if is_new_user:
        await bot.send_message(chat_id=chat_id, text=_ONBOARDING_MSG)

    state = _get_flow_state(user_id, chat_id)
    event = _update_to_event(update, state.get("slots") or {})
    if event is None:
        return {}

    actions, new_state_value, new_slots = run_xstate_flow(
        state.get("current_node_id"),
        event,
        state.get("slots") or {},
        service,
    )
    new_state = {"current_node_id": new_state_value, "slots": new_slots}

    # Answer callback so Telegram stops showing loading state
    if update.callback_query:
        await bot.answer_callback_query(callback_query_id=update.callback_query.id)

    reply_chat_id = chat_id
    if update.callback_query and update.callback_query.message and update.callback_query.message.chat:
        reply_chat_id = int(update.callback_query.message.chat.id)

    for action in actions:
        if isinstance(action, SendMessage):
            reply_markup = _keyboard_by_name(
                action.keyboard, new_state.get("slots") or {}
            )
            await bot.send_message(
                chat_id=reply_chat_id,
                text=action.text,
                reply_markup=reply_markup,
            )
        elif isinstance(action, SendContactList):
            await _send_contact_results_impl(bot, reply_chat_id, action.summaries)

    # When back at idle, clear slots so we don't carry stale pending state (after sending so keyboards can use slots)
    if new_state_value == "idle":
        new_state["slots"] = {}

    _set_flow_state(user_id, chat_id, new_state)
    return {}
