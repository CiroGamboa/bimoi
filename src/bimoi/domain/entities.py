"""Domain entities: Person, RelationshipContext, and AccountProfile."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

# Max length for profile fields stored on Account node.
BIO_MAX_LENGTH = 2000
NAME_MAX_LENGTH = 500


@dataclass(frozen=True)
class AccountProfile:
    """
    Profile data for an Account (name, bio, phone).
    Stored on the owner Person node in Neo4j; used by identity layer and onboarding.
    """

    name: str | None = None
    bio: str | None = None
    phone_number: str | None = None

    def __post_init__(self):
        if self.name is not None:
            name = self.name.strip()
            if len(name) > NAME_MAX_LENGTH:
                raise ValueError(
                    f"Account profile name must be at most {NAME_MAX_LENGTH} chars."
                )
            object.__setattr__(self, "name", name or None)
        if self.bio is not None:
            bio = self.bio.strip()
            if len(bio) > BIO_MAX_LENGTH:
                raise ValueError(
                    f"Account profile bio must be at most {BIO_MAX_LENGTH} chars."
                )
            object.__setattr__(self, "bio", bio or None)


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
