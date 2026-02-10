"""Abstract contact repository (port)."""

from typing import Protocol

import domain
from bimoi.contact_card import ContactCardData


class ContactRepository(Protocol):
    """Persists and queries contact aggregates (Person + RelationshipContext)."""

    def add(self, person: domain.Person) -> None:
        """Store a contact. Person must include its RelationshipContext."""
        ...

    def get_by_id(self, person_id: str) -> domain.Person | None:
        """Return the person with the given id, or None."""
        ...

    def list_all(self) -> list[domain.Person]:
        """Return all contacts in creation order (or any stable order)."""
        ...

    def find_duplicate(self, card: ContactCardData) -> domain.Person | None:
        """Return an existing contact that matches by telegram_user_id or phone_number, or None."""
        ...
