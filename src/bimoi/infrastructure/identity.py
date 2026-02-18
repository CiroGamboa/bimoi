"""Identity layer: resolve Telegram user id to a stable user_id (Person).

The user is represented by a single Person node (owner) with account-like properties
(id, telegram_id, name, bio, created_at, registered: true). Telegram id is stored
on the Person node; no separate ChannelLink. Same shape as contact Person nodes.
"""

import uuid
from datetime import datetime, timezone

from bimoi.domain import AccountProfile
from bimoi.domain.entities import BIO_MAX_LENGTH, NAME_MAX_LENGTH
from bimoi.infrastructure.phone import normalize_phone

# Channel name constants for extensibility (whatsapp, web, etc. later).
CHANNEL_TELEGRAM = "telegram"

_CONSTRAINT_QUERY = """
CREATE CONSTRAINT person_telegram_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.telegram_id IS UNIQUE
"""

_LOOKUP_QUERY = """
MATCH (p:Person { telegram_id: $telegram_id })
RETURN p.id AS user_id
"""

_SET_REGISTERED_QUERY = """
MATCH (p:Person { id: $user_id })
SET p.registered = true
RETURN p.id AS user_id
"""

_CREATE_OWNER_QUERY = """
CREATE (p:Person {
  id: $user_id,
  telegram_id: $telegram_id,
  created_at: $created_at,
  registered: true
})
RETURN p.id AS user_id
"""

_SET_OWNER_NAME_QUERY = """
MATCH (p:Person { id: $user_id, registered: true })
SET p.name = $name
RETURN p.id AS user_id
"""

_UPDATE_PROFILE_QUERY = """
MATCH (p:Person { id: $user_id, registered: true })
WITH p
SET p.name = CASE WHEN $name IS NOT NULL THEN $name ELSE p.name END,
    p.bio = CASE WHEN $bio IS NOT NULL THEN $bio ELSE p.bio END,
    p.phone_number = CASE WHEN $phone_number IS NOT NULL THEN $phone_number ELSE p.phone_number END
RETURN p.id AS user_id
"""

_GET_PROFILE_QUERY = """
MATCH (p:Person { id: $user_id, registered: true })
RETURN p.name AS name, p.bio AS bio, p.phone_number AS phone_number
"""

_GET_PERSON_ID_BY_TELEGRAM_ID_QUERY = """
MATCH (p:Person { telegram_id: $telegram_id })
RETURN p.id AS person_id
"""


def ensure_identity_constraint(driver) -> None:
    """Create unique constraint on Person.telegram_id if missing."""
    with driver.session() as session:
        session.run(_CONSTRAINT_QUERY)


# Backward compatibility: tests and docs may still reference this name.
ensure_channel_link_constraint = ensure_identity_constraint


def get_or_create_user_id(
    driver,
    channel: str,
    external_id: str,
    *,
    initial_name: str | None = None,
) -> tuple[str, bool]:
    """Resolve (channel, external_id) to a stable user_id (owner Person id).

    For Telegram, external_id is stored as Person.telegram_id. Returns (user_id, is_new_account).
    If a Person with this telegram_id exists, sets registered = true and returns its id.
    Otherwise creates a Person (id, telegram_id, created_at, registered: true).
    Call ensure_identity_constraint at startup.
    """
    external_id = (external_id or "").strip()
    if not external_id:
        raise ValueError("external_id must be non-empty")
    channel = (channel or "").strip()
    if not channel:
        raise ValueError("channel must be non-empty")
    if channel != CHANNEL_TELEGRAM:
        raise ValueError(f"Unsupported channel: {channel}")

    telegram_id = external_id
    user_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    name = (initial_name or "").strip() or None

    with driver.session() as session:
        result = session.run(_LOOKUP_QUERY, telegram_id=telegram_id)
        record = result.single()
        if record and record["user_id"] is not None:
            session.run(_SET_REGISTERED_QUERY, user_id=record["user_id"])
            return (record["user_id"], False)
        result = session.run(
            _CREATE_OWNER_QUERY,
            user_id=user_id,
            telegram_id=telegram_id,
            created_at=created_at,
        )
        record = result.single()
        if record and name:
            session.run(_SET_OWNER_NAME_QUERY, user_id=record["user_id"], name=name)
    if not record:
        raise RuntimeError("get_or_create_user_id: expected one result")
    return (record["user_id"], True)


def update_account_profile(
    driver,
    user_id: str,
    *,
    name: str | None = None,
    bio: str | None = None,
    phone_number: str | None = None,
) -> None:
    """Update owner Person profile fields (name, bio, phone_number). Only provided (non-None) fields are set."""
    if name is None and bio is None and phone_number is None:
        return
    if name is not None:
        name = name.strip() or None
        if name and len(name) > NAME_MAX_LENGTH:
            raise ValueError(f"Account profile name must be at most {NAME_MAX_LENGTH} characters.")
    if bio is not None:
        bio = bio.strip() or None
        if bio and len(bio) > BIO_MAX_LENGTH:
            raise ValueError(f"Account profile bio must be at most {BIO_MAX_LENGTH} characters.")
    if phone_number is not None:
        phone_number = normalize_phone(phone_number.strip() or "", default_region=None) or None
    with driver.session() as session:
        session.run(
            _UPDATE_PROFILE_QUERY,
            user_id=user_id,
            name=name,
            bio=bio,
            phone_number=phone_number,
        )


def get_person_id_by_channel_external_id(
    driver,
    channel: str,
    external_id: str,
) -> str | None:
    """Return the Person id for this Telegram user id if one exists, else None.
    Read-only. Used to detect if a contact is already on the app (reuse their node).
    """
    channel = (channel or "").strip()
    external_id = (external_id or "").strip()
    if not external_id or channel != CHANNEL_TELEGRAM:
        return None
    with driver.session() as session:
        result = session.run(_GET_PERSON_ID_BY_TELEGRAM_ID_QUERY, telegram_id=external_id)
        record = result.single()
    if not record or record["person_id"] is None:
        return None
    return record["person_id"]


def get_account_profile(driver, user_id: str) -> AccountProfile | None:
    """Return owner Person profile (name, bio, phone_number) as domain type, or None if not found."""
    with driver.session() as session:
        result = session.run(_GET_PROFILE_QUERY, user_id=user_id)
        record = result.single()
    if not record:
        return None
    return AccountProfile(
        name=record["name"],
        bio=record["bio"],
        phone_number=record.get("phone_number"),
    )
