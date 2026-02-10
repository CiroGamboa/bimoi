"""In-memory implementation of ContactRepository (no DB)."""

import domain
from bimoi.contact_card import ContactCardData


def _normalize_telegram_id(value: int | str | None) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


class InMemoryContactRepository:
    """Stores contacts in memory. Order preserved by insertion."""

    def __init__(self) -> None:
        self._by_id: dict[str, domain.Person] = {}
        self._order: list[str] = []

    def add(self, person: domain.Person) -> None:
        if person.id in self._by_id:
            return
        self._by_id[person.id] = person
        self._order.append(person.id)

    def get_by_id(self, person_id: str) -> domain.Person | None:
        return self._by_id.get(person_id)

    def list_all(self) -> list[domain.Person]:
        return [self._by_id[pid] for pid in self._order if pid in self._by_id]

    def find_duplicate(self, card: ContactCardData) -> domain.Person | None:
        card_phone = (card.phone_number or "").strip() or None
        card_tid = _normalize_telegram_id(card.telegram_user_id)
        for person in self._by_id.values():
            if card_tid and person.external_id and person.external_id == card_tid:
                return person
            if card_phone and person.phone_number and person.phone_number == card_phone:
                return person
        return None
