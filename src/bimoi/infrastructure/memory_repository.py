"""In-memory implementation of ContactRepository (no DB)."""

from bimoi.application.dto import ContactCardData
from bimoi.domain import Person, RelationshipContext


def _normalize_telegram_id(value: int | str | None) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


class InMemoryContactRepository:
    """Stores contacts in memory. Order preserved by insertion."""

    def __init__(self) -> None:
        self._by_id: dict[str, Person] = {}
        self._order: list[str] = []

    def add(
        self,
        person: Person,
        *,
        link_to_existing_id: str | None = None,
    ) -> None:
        if link_to_existing_id is not None and link_to_existing_id.strip() != "":
            if link_to_existing_id in self._by_id and link_to_existing_id not in self._order:
                self._order.append(link_to_existing_id)
            return
        if person.id in self._by_id:
            return
        self._by_id[person.id] = person
        self._order.append(person.id)

    def get_by_id(self, person_id: str) -> Person | None:
        return self._by_id.get(person_id)

    def list_all(self) -> list[Person]:
        return [self._by_id[pid] for pid in self._order if pid in self._by_id]

    def find_duplicate(self, card: ContactCardData) -> Person | None:
        card_phone = (card.phone_number or "").strip() or None
        card_tid = _normalize_telegram_id(card.telegram_user_id)
        for person in self._by_id.values():
            if card_tid and person.external_id and person.external_id == card_tid:
                return person
            if card_phone and person.phone_number and person.phone_number == card_phone:
                return person
        return None

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
        )
        self._by_id[person_id] = new_person
        return True
