"""In-memory implementation of ContactRepository (no DB)."""

from bimoi.application.dto import ContactCardData
from bimoi.domain import Person, RelationshipContext
from bimoi.infrastructure.phone import normalize_phone


def _normalize_telegram_id(value: int | str | None) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


class InMemoryContactRepository:
    """Stores contacts in memory. Order preserved by insertion.
    contact_name is the name the owner saved for the contact (on the link); Person.name on node is signup name only.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, Person] = {}
        self._order: list[str] = []
        self._contact_names: dict[str, str] = {}  # person_id -> contact_name (owner's name for this contact)

    def _person_with_display_name(self, person: Person) -> Person:
        """Return Person with name = contact_name (owner's name for contact), fallback to node name."""
        display_name = self._contact_names.get(person.id, person.name) or person.name or ""
        if display_name == person.name:
            return person
        return Person(
            id=person.id,
            name=display_name,
            phone_number=person.phone_number,
            external_id=person.external_id,
            created_at=person.created_at,
            relationship_context=person.relationship_context,
        )

    def add(
        self,
        person: Person,
        *,
        link_to_existing_id: str | None = None,
    ) -> None:
        contact_name = (person.name or "").strip() or ""
        if link_to_existing_id is not None and link_to_existing_id.strip() != "":
            self._contact_names[link_to_existing_id] = contact_name
            if link_to_existing_id in self._by_id and link_to_existing_id not in self._order:
                self._order.append(link_to_existing_id)
            return
        if person.id in self._by_id:
            return
        stored_phone = normalize_phone((person.phone_number or "").strip(), default_region=None) or person.phone_number
        person_to_store = Person(
            id=person.id,
            name="",
            phone_number=stored_phone,
            external_id=person.external_id,
            created_at=person.created_at,
            relationship_context=person.relationship_context,
        )
        self._contact_names[person.id] = contact_name
        self._by_id[person.id] = person_to_store
        self._order.append(person.id)

    def get_by_id(self, person_id: str) -> Person | None:
        person = self._by_id.get(person_id)
        if person is None:
            return None
        return self._person_with_display_name(person)

    def list_all(self) -> list[Person]:
        return [
            self._person_with_display_name(self._by_id[pid])
            for pid in self._order
            if pid in self._by_id
        ]

    def find_duplicate(self, card: ContactCardData) -> Person | None:
        raw_phone = (card.phone_number or "").strip() or None
        card_phone = normalize_phone(raw_phone, default_region=None) if raw_phone else None
        card_tid = _normalize_telegram_id(card.telegram_user_id)
        for person in self._by_id.values():
            if card_tid and person.external_id and person.external_id == card_tid:
                return self._person_with_display_name(person)
            if card_phone and person.phone_number:
                person_phone = normalize_phone(person.phone_number, default_region=None) or person.phone_number
                if person_phone == card_phone:
                    return self._person_with_display_name(person)
        return None

    def get_mutual_contact_ids(self) -> set[str]:
        """Return person_ids of contacts who have also added the current user. In-memory has no reverse KNOWS."""
        return set()

    def append_context(self, person_id: str, additional_text: str) -> bool:
        person = self._by_id.get(person_id)
        if not person:
            return False
        ctx = person.relationship_context
        suffix = "\n\n— " + (additional_text or "").strip()
        new_ctx = RelationshipContext(
            id=ctx.id,
            description=ctx.description + suffix,
            created_at=ctx.created_at,
        )
        new_person = Person(
            id=person.id,
            name=person.name,
            phone_number=person.phone_number,
            external_id=person.external_id,
            created_at=person.created_at,
            relationship_context=new_ctx,
            bio=getattr(person, "bio", None),
        )
        self._by_id[person_id] = new_person
        return True
