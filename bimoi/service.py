"""Contact creation, list, and search. Single pending per service instance."""

import uuid

import domain
from bimoi.contact_card import (
    ContactCardData,
    ContactCreated,
    ContactSummary,
    Duplicate,
    Invalid,
    PendingContact,
    PendingNotFound,
)
from bimoi.repository import ContactRepository


class ContactService:
    """Core flow: receive contact card -> pending -> submit context -> stored. List and search."""

    def __init__(self, repository: ContactRepository) -> None:
        self._repo = repository
        self._pending_id: str | None = None
        self._pending_card: ContactCardData | None = None

    def receive_contact_card(
        self, card: ContactCardData
    ) -> PendingContact | Duplicate | Invalid:
        """Accept a contact card. Returns pending (wait for context), duplicate, or invalid."""
        name = (card.name or "").strip()
        if not name:
            return Invalid(reason="Name is required.")

        existing = self._repo.find_duplicate(card)
        if existing is not None:
            return Duplicate()

        pending_id = str(uuid.uuid4())
        self._pending_id = pending_id
        self._pending_card = card
        return PendingContact(pending_id=pending_id, name=name)

    def submit_context(
        self, pending_id: str, context_text: str
    ) -> ContactCreated | PendingNotFound:
        """Submit context for a pending contact. Creates and stores the aggregate."""
        if self._pending_id != pending_id or self._pending_card is None:
            return PendingNotFound(pending_id=pending_id)

        context_clean = (context_text or "").strip()
        if not context_clean:
            return PendingNotFound(pending_id=pending_id)

        try:
            relationship_context = domain.RelationshipContext(description=context_clean)
        except ValueError:
            return PendingNotFound(pending_id=pending_id)

        card = self._pending_card
        external_id = (
            str(card.telegram_user_id).strip()
            if card.telegram_user_id is not None
            else None
        )
        external_id = external_id or None
        phone = (card.phone_number or "").strip() or None

        try:
            person = domain.Person(
                name=card.name.strip(),
                phone_number=phone,
                external_id=external_id,
                relationship_context=relationship_context,
            )
        except ValueError:
            return PendingNotFound(pending_id=pending_id)

        self._repo.add(person)
        self._pending_id = None
        self._pending_card = None
        return ContactCreated(person_id=person.id, name=person.name)

    def list_contacts(self) -> list[ContactSummary]:
        """Return all contacts (name, context, created_at)."""
        out = []
        for person in self._repo.list_all():
            ctx = person.relationship_context
            out.append(
                ContactSummary(
                    name=person.name,
                    context=ctx.description,
                    created_at=person.created_at,
                )
            )
        return out

    def search_contacts(self, keyword: str) -> list[ContactSummary]:
        """Return contacts whose context contains the keyword (case-insensitive, partial)."""
        if not keyword or not keyword.strip():
            return []
        needle = keyword.strip().lower()
        out = []
        for person in self._repo.list_all():
            if needle in person.relationship_context.description.lower():
                ctx = person.relationship_context
                out.append(
                    ContactSummary(
                        name=person.name,
                        context=ctx.description,
                        created_at=person.created_at,
                    )
                )
        return out
