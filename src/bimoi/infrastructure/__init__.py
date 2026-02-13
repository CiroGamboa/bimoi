"""Infrastructure layer: concrete implementations of application ports."""

from bimoi.infrastructure.identity import (
    CHANNEL_TELEGRAM,
    ensure_channel_link_constraint,
    get_or_create_user_id,
)
from bimoi.infrastructure.memory_repository import InMemoryContactRepository
from bimoi.infrastructure.persistence.neo4j_repository import Neo4jContactRepository

__all__ = [
    "CHANNEL_TELEGRAM",
    "InMemoryContactRepository",
    "Neo4jContactRepository",
    "ensure_channel_link_constraint",
    "get_or_create_user_id",
]
