#!/usr/bin/env python3
"""One-off migration: register existing Telegram owners as Account + ChannelLink.

Finds every Person with registered: true whose id looks like a numeric Telegram ID,
creates an Account with that id and ChannelLink(telegram, id). After this,
get_or_create_user_id("telegram", id) returns the same id so contact data is
unchanged. Run from repo root with .env (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD).
Idempotent.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from bimoi.infrastructure.identity import (  # noqa: E402
    CHANNEL_TELEGRAM,
    ensure_channel_link_constraint,
)

load_dotenv(REPO_ROOT / ".env")

_FIND_OWNERS = """
MATCH (owner:Person { registered: true })
RETURN owner.id AS owner_id
"""

_MERGE_ACCOUNT_AND_LINK = """
MERGE (c:ChannelLink { channel: $channel, external_id: $owner_id })
WITH c
MERGE (a:Account { id: $owner_id })
ON CREATE SET a.created_at = $created_at
MERGE (c)-[:BELONGS_TO]->(a)
"""


def _looks_like_telegram_id(owner_id: str) -> bool:
    """Treat numeric string as Telegram user id."""
    return bool(owner_id and owner_id.strip().isdigit())


def main() -> int:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687").strip()
    user = os.environ.get("NEO4J_USER", "neo4j").strip()
    password = os.environ.get("NEO4J_PASSWORD", "password").strip()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        ensure_channel_link_constraint(driver)
        with driver.session() as session:
            result = session.run(_FIND_OWNERS)
            owner_ids = [r["owner_id"] for r in result if r["owner_id"]]
        to_migrate = [oid for oid in owner_ids if _looks_like_telegram_id(oid)]
        if not to_migrate:
            print("No owner ids that look like Telegram IDs to migrate.")
            return 0
        created_at = datetime.now(timezone.utc).isoformat()
        with driver.session() as session:
            for owner_id in to_migrate:
                session.run(
                    _MERGE_ACCOUNT_AND_LINK,
                    channel=CHANNEL_TELEGRAM,
                    owner_id=owner_id,
                    created_at=created_at,
                )
        msg = f"Migrated {len(to_migrate)} owner(s) to Account + ChannelLink: {to_migrate}"
        print(msg)
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
