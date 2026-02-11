"""
Bimoi core: clean-architecture layout.

- domain: entities (Person, RelationshipContext). No outer dependencies.
- application: use cases (ContactService), ports (ContactRepository), DTOs.
- infrastructure: adapters (InMemoryContactRepository, Neo4jContactRepository).
"""

from bimoi.application import (
    ContactCardData,
    ContactCreated,
    ContactRepository,
    ContactService,
    ContactSummary,
    Duplicate,
    Invalid,
    PendingContact,
    PendingNotFound,
)
from bimoi.domain import Person, RelationshipContext
from bimoi.infrastructure import InMemoryContactRepository, Neo4jContactRepository

__all__ = [
    "ContactCardData",
    "ContactCreated",
    "ContactRepository",
    "ContactService",
    "ContactSummary",
    "Duplicate",
    "InMemoryContactRepository",
    "Invalid",
    "Neo4jContactRepository",
    "PendingContact",
    "PendingNotFound",
    "Person",
    "RelationshipContext",
]
