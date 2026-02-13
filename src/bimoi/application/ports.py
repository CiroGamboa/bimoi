"""Application ports (interfaces). Implemented by infrastructure adapters."""

from typing import Protocol

from bimoi.application.dto import ContactCardData
from bimoi.domain import Person


class ContactRepository(Protocol):
    """Persists and queries contact aggregates (Person + RelationshipContext)."""

    def add(self, person: Person) -> None:
        """Store a contact. Person must include its RelationshipContext."""
        ...

    def get_by_id(self, person_id: str) -> Person | None:
        """Return the person with the given id, or None."""
        ...

    def list_all(self) -> list[Person]:
        """Return all contacts in creation order (or any stable order)."""
        ...

    def find_duplicate(self, card: ContactCardData) -> Person | None:
        """Return an existing contact matching by telegram_user_id or phone_number, or None."""
        ...

    def append_context(self, person_id: str, additional_text: str) -> bool:
        """Append text to the contact's context. Returns True if updated, False if not found."""
        ...
