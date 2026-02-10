"""Input DTO and result types for contact creation flow."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ContactSummary:
    """One contact as returned by list_contacts and search_contacts."""

    name: str
    context: str
    created_at: datetime


@dataclass(frozen=True)
class ContactCardData:
    """Data from a Telegram contact card (or mock). Core has no Telegram dependency."""

    name: str
    phone_number: str | None = None
    telegram_user_id: int | str | None = None


# --- receive_contact_card results ---


@dataclass(frozen=True)
class PendingContact:
    """Contact card accepted; waiting for context. Submit context with this id."""

    pending_id: str
    name: str


@dataclass(frozen=True)
class Duplicate:
    """A contact with this phone or Telegram user id already exists."""

    pass


@dataclass(frozen=True)
class Invalid:
    """Contact card is invalid (e.g. missing or empty name)."""

    reason: str


# --- submit_context results ---


@dataclass(frozen=True)
class ContactCreated:
    """Contact aggregate was created and stored."""

    person_id: str
    name: str


@dataclass(frozen=True)
class PendingNotFound:
    """No pending contact for the given id (wrong id or already consumed)."""

    pending_id: str
