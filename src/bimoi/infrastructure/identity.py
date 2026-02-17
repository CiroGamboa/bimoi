"""Identity layer: resolve channel + external_id to a stable user_id (Person).

The user is represented by a single Person node (owner) with account-like properties
(id, name, bio, created_at, registered: true). ChannelLink links to that Person.
Same shape as contact Person nodes; profile fields (name, bio) may later move to a relational DB.
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
OPTIONAL MATCH (c)-[:BELONGS_TO]->(p:Person)
WHERE p.registered = true
RETURN p.id AS user_id
"""

_CREATE_OWNER_QUERY = """
MATCH (c:ChannelLink { channel: $channel, external_id: $external_id })
WHERE NOT (c)-[:BELONGS_TO]->()
WITH c
CREATE (p:Person { id: $user_id, created_at: $created_at, registered: true })
CREATE (c)-[:BELONGS_TO]->(p)
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
    p.bio = CASE WHEN $bio IS NOT NULL THEN $bio ELSE p.bio END
RETURN p.id AS user_id
"""

_GET_PROFILE_QUERY = """
MATCH (p:Person { id: $user_id, registered: true })
RETURN p.name AS name, p.bio AS bio
"""

_GET_PERSON_ID_BY_CHANNEL_EXTERNAL_ID_QUERY = """
MATCH (c:ChannelLink { channel: $channel, external_id: $external_id })-[:BELONGS_TO]->(p:Person)
WHERE p.registered = true
RETURN p.id AS person_id
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
    """Resolve (channel, external_id) to a stable user_id (owner Person id).

    Returns (user_id, is_new_account). is_new_account is True when the owner
    Person was created in this call; False when an existing one was found.
    If a link exists, returns the linked Person (owner) id. Otherwise creates a
    Person (id, created_at, registered: true), links ChannelLink -[:BELONGS_TO]-> Person,
    and returns the new id. When creating, optional initial_name is stored on the Person.
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
            _CREATE_OWNER_QUERY,
            channel=channel,
            external_id=external_id,
            user_id=user_id,
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
) -> None:
    """Update owner Person profile fields (name, bio). Only provided (non-None) fields are set.
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


def get_person_id_by_channel_external_id(
    driver,
    channel: str,
    external_id: str,
) -> str | None:
    """Return the owner Person id for (channel, external_id) if already linked, else None.

    Read-only: does not create ChannelLink or Person. Use to detect if a contact
    (e.g. Telegram user id) is already a Bimoi user so we can reuse their Person node.
    """
    channel = (channel or "").strip()
    external_id = (external_id or "").strip()
    if not channel or not external_id:
        return None
    with driver.session() as session:
        result = session.run(
            _GET_PERSON_ID_BY_CHANNEL_EXTERNAL_ID_QUERY,
            channel=channel,
            external_id=external_id,
        )
        record = result.single()
    if not record or record["person_id"] is None:
        return None
    return record["person_id"]


def get_account_profile(driver, user_id: str) -> AccountProfile | None:
    """Return owner Person profile (name, bio) as domain type, or None if not found."""
    with driver.session() as session:
        result = session.run(_GET_PROFILE_QUERY, user_id=user_id)
        record = result.single()
    if not record:
        return None
    return AccountProfile(
        name=record["name"],
        bio=record["bio"],
    )
