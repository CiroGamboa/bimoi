import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RelationshipContext:
    """
    Represents the explicit, human-authored meaning of a relationship.
    A RelationshipContext is immutable once created.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = field(default="")
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if not self.description or not self.description.strip():
            raise ValueError("RelationshipContext description must be non-empty.")


@dataclass(frozen=True)
class Person:
    """
    Represents a real individual known by the user.
    A Person cannot exist without a RelationshipContext.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = field(default="")
    phone_number: str | None = None
    external_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    relationship_context: RelationshipContext = field(default=None)

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("Person name must be non-empty.")

        if self.relationship_context is None:
            raise ValueError("Person must have an associated RelationshipContext.")
