"""Contact creation, list, and search. Single pending per service instance."""

import uuid
from collections.abc import Callable

from bimoi.application.dto import (
    AddContextInvalid,
    AddContextNotFound,
    AddContextSuccess,
    ContactCardData,
    ContactCreated,
    ContactSummary,
    Duplicate,
    Invalid,
    PendingContact,
    PendingNotFound,
)
from bimoi.application.ports import ContactRepository
from bimoi.domain import Person, RelationshipContext


class ContactService:
    """Core flow: receive contact card -> pending -> submit context -> stored. List and search."""

    def __init__(
        self,
        repository: ContactRepository,
        *,
        resolve_existing_person_id: Callable[[str], str | None] | None = None,
    ) -> None:
        self._repo = repository
        self._resolve_existing_person_id = resolve_existing_person_id
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
            return Duplicate(person_id=existing.id, name=existing.name)

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
            relationship_context = RelationshipContext(description=context_clean)
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
            person = Person(
                name=card.name.strip(),
                phone_number=phone,
                external_id=external_id,
                relationship_context=relationship_context,
            )
        except ValueError:
            return PendingNotFound(pending_id=pending_id)

        link_to_existing_id: str | None = None
        if self._resolve_existing_person_id and card.telegram_user_id is not None:
            eid = str(card.telegram_user_id).strip()
            if eid:
                link_to_existing_id = self._resolve_existing_person_id(eid)
                if link_to_existing_id == "":
                    link_to_existing_id = None

        self._repo.add(person, link_to_existing_id=link_to_existing_id)
        effective_id = link_to_existing_id if link_to_existing_id else person.id
        self._pending_id = None
        self._pending_card = None
        return ContactCreated(person_id=effective_id, name=person.name)

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
                    person_id=person.id,
                    phone_number=person.phone_number,
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
                        person_id=person.id,
                        phone_number=person.phone_number,
                    )
                )
        return out

    def get_contact(self, person_id: str) -> ContactSummary | None:
        """Return a contact by id, or None if not found."""
        person = self._repo.get_by_id(person_id)
        if not person:
            return None
        ctx = person.relationship_context
        return ContactSummary(
            name=person.name,
            context=ctx.description,
            created_at=person.created_at,
            person_id=person.id,
            phone_number=person.phone_number,
        )

    def add_context(
        self, person_id: str, context_text: str
    ) -> AddContextSuccess | AddContextNotFound | AddContextInvalid:
        """Append context to an existing contact."""
        context_clean = (context_text or "").strip()
        if not context_clean:
            return AddContextInvalid()

        ok = self._repo.append_context(person_id, context_clean)
        if not ok:
            return AddContextNotFound(person_id=person_id)

        contact = self.get_contact(person_id)
        return AddContextSuccess(name=contact.name if contact else "Unknown")
