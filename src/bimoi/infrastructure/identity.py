"""Identity layer: resolve channel + external_id to a stable user_id (Account).

Account and ChannelLink nodes live in Neo4j. Used by Telegram (and later
WhatsApp, web) to get a single user_id per person across channels.
"""

import uuid
from datetime import datetime, timezone

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


def ensure_channel_link_constraint(driver) -> None:
    """Create unique constraint on ChannelLink(channel, external_id) if missing."""
    with driver.session() as session:
        session.run(_CONSTRAINT_QUERY)


def get_or_create_user_id(driver, channel: str, external_id: str) -> str:
    """Resolve (channel, external_id) to a stable user_id (Account id).

    If a link exists, returns the linked Account id. Otherwise creates an
    Account (UUID), a ChannelLink, and BELONGS_TO, then returns the new id.
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

    with driver.session() as session:
        result = session.run(
            _LOOKUP_QUERY,
            channel=channel,
            external_id=external_id,
            created_at=created_at,
        )
        record = result.single()
        if record and record["user_id"] is not None:
            return record["user_id"]
        result = session.run(
            _CREATE_ACCOUNT_QUERY,
            channel=channel,
            external_id=external_id,
            user_id=user_id,
            created_at=created_at,
        )
        record = result.single()
    if not record:
        raise RuntimeError("get_or_create_user_id: expected one result")
    return record["user_id"]
