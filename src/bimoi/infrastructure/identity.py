"""Identity layer: resolve channel + external_id to a stable user_id (Account).

Account and ChannelLink nodes live in Neo4j. Used by Telegram (and later
WhatsApp, web) to get a single user_id per person across channels.
Profile (name, bio) is stored on the Account node and exposed via AccountProfile.
"""

import uuid
from datetime import datetime, timezone

from bimoi.domain import AccountProfile
from bimoi.domain.entities import BIO_MAX_LENGTH, NAME_MAX_LENGTH

# Channel name constants for extensibility (whatsapp, web, etc. later).
CHANNEL_TELEGRAM = "telegram"

_CONSTRAINT_QUERY = """
CREATE CONSTRAINT channel_link_unique IF NOT EXISTS
FOR (c:ChannelLink) REQUIRE (c.channel, c.external_id) IS NODE UNIQUE
"""

_LOOKUP_QUERY = """
MERGE (c:ChannelLink { channel: $channel, external_id: $external_id })
ON CREATE SET c.created_at = $created_at
WITH c
OPTIONAL MATCH (c)-[:BELONGS_TO]->(a:Account)
RETURN a.id AS user_id
"""

_CREATE_ACCOUNT_QUERY = """
MATCH (c:ChannelLink { channel: $channel, external_id: $external_id })
WHERE NOT (c)-[:BELONGS_TO]->()
WITH c
CREATE (a:Account { id: $user_id, created_at: $created_at })
CREATE (c)-[:BELONGS_TO]->(a)
RETURN a.id AS user_id
"""

_SET_ACCOUNT_NAME_QUERY = """
MATCH (a:Account { id: $user_id })
SET a.name = $name
RETURN a.id AS user_id
"""

_UPDATE_PROFILE_QUERY = """
MATCH (a:Account { id: $user_id })
WITH a
SET a.name = CASE WHEN $name IS NOT NULL THEN $name ELSE a.name END,
    a.bio = CASE WHEN $bio IS NOT NULL THEN $bio ELSE a.bio END
RETURN a.id AS user_id
"""

_GET_PROFILE_QUERY = """
MATCH (a:Account { id: $user_id })
RETURN a.name AS name, a.bio AS bio
"""


def ensure_channel_link_constraint(driver) -> None:
    """Create unique constraint on ChannelLink(channel, external_id) if missing."""
    with driver.session() as session:
        session.run(_CONSTRAINT_QUERY)


def get_or_create_user_id(
    driver,
    channel: str,
    external_id: str,
    *,
    initial_name: str | None = None,
) -> tuple[str, bool]:
    """Resolve (channel, external_id) to a stable user_id (Account id).

    Returns (user_id, is_new_account). is_new_account is True when the Account
    was created in this call; False when an existing Account was found.
    If a link exists, returns the linked Account id. Otherwise creates an
    Account (UUID), a ChannelLink, and BELONGS_TO, then returns the new id.
    When creating, optional initial_name is stored on the Account.
    Call ensure_channel_link_constraint at startup so MERGE is unique.
    """
    external_id = (external_id or "").strip()
    if not external_id:
        raise ValueError("external_id must be non-empty")
    channel = (channel or "").strip()
    if not channel:
        raise ValueError("channel must be non-empty")

    user_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    name = (initial_name or "").strip() or None

    with driver.session() as session:
        result = session.run(
            _LOOKUP_QUERY,
            channel=channel,
            external_id=external_id,
            created_at=created_at,
        )
        record = result.single()
        if record and record["user_id"] is not None:
            return (record["user_id"], False)
        result = session.run(
            _CREATE_ACCOUNT_QUERY,
            channel=channel,
            external_id=external_id,
            user_id=user_id,
            created_at=created_at,
        )
        record = result.single()
        if record and name:
            session.run(_SET_ACCOUNT_NAME_QUERY, user_id=record["user_id"], name=name)
    if not record:
        raise RuntimeError("get_or_create_user_id: expected one result")
    return (record["user_id"], True)


def update_account_profile(
    driver,
    user_id: str,
    *,
    name: str | None = None,
    bio: str | None = None,
) -> None:
    """Update Account profile fields. Only provided (non-None) fields are set.
    Validates name/bio length using domain constants (NAME_MAX_LENGTH, BIO_MAX_LENGTH).
    """
    if name is None and bio is None:
        return
    if name is not None:
        name = name.strip() or None
        if name and len(name) > NAME_MAX_LENGTH:
            raise ValueError(f"Account profile name must be at most {NAME_MAX_LENGTH} characters.")
    if bio is not None:
        bio = bio.strip() or None
        if bio and len(bio) > BIO_MAX_LENGTH:
            raise ValueError(f"Account profile bio must be at most {BIO_MAX_LENGTH} characters.")
    with driver.session() as session:
        session.run(
            _UPDATE_PROFILE_QUERY,
            user_id=user_id,
            name=name,
            bio=bio,
        )


def get_account_profile(driver, user_id: str) -> AccountProfile | None:
    """Return Account profile (name, bio) as domain type, or None if not found."""
    with driver.session() as session:
        result = session.run(_GET_PROFILE_QUERY, user_id=user_id)
        record = result.single()
    if not record:
        return None
    return AccountProfile(
        name=record["name"],
        bio=record["bio"],
    )
