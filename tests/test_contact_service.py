"""Unit tests for ContactService. No Telegram; in-memory repo and ContactCardData only."""


from bimoi.contact_card import (
    ContactCardData,
    ContactCreated,
    Duplicate,
    Invalid,
    PendingContact,
    PendingNotFound,
)
from bimoi.memory_repository import InMemoryContactRepository
from bimoi.service import ContactService


def _service() -> ContactService:
    return ContactService(repository=InMemoryContactRepository())


def test_valid_contact_card_then_context_creates_contact() -> None:
    service = _service()
    card = ContactCardData(name="Alice", phone_number="+123")
    r1 = service.receive_contact_card(card)
    assert isinstance(r1, PendingContact)
    assert r1.name == "Alice"
    pending_id = r1.pending_id

    r2 = service.submit_context(pending_id, "Frontend engineer, React")
    assert isinstance(r2, ContactCreated)
    assert r2.name == "Alice"

    listed = service.list_contacts()
    assert len(listed) == 1
    assert listed[0].name == "Alice"
    assert "React" in listed[0].context


def test_search_finds_by_keyword() -> None:
    service = _service()
    card = ContactCardData(name="Bob", telegram_user_id=42)
    pending = service.receive_contact_card(card)
    assert isinstance(pending, PendingContact)
    service.submit_context(pending.pending_id, "VC circles and startups")

    results = service.search_contacts("VC")
    assert len(results) == 1
    assert results[0].name == "Bob"
    assert "VC" in results[0].context

    assert len(service.search_contacts("nonexistent")) == 0


def test_search_case_insensitive() -> None:
    service = _service()
    card = ContactCardData(name="Carol")
    pending = service.receive_contact_card(card)
    assert isinstance(pending, PendingContact)
    service.submit_context(pending.pending_id, "React and TypeScript")

    assert len(service.search_contacts("react")) == 1
    assert len(service.search_contacts("REACT")) == 1
    assert len(service.search_contacts("typescript")) == 1


def test_duplicate_by_phone() -> None:
    service = _service()
    card1 = ContactCardData(name="Alice", phone_number="+111")
    r1 = service.receive_contact_card(card1)
    assert isinstance(r1, PendingContact)
    service.submit_context(r1.pending_id, "Engineer")

    card2 = ContactCardData(name="Alice Other", phone_number="+111")
    r2 = service.receive_contact_card(card2)
    assert isinstance(r2, Duplicate)
    assert len(service.list_contacts()) == 1


def test_duplicate_by_telegram_user_id() -> None:
    service = _service()
    card1 = ContactCardData(name="Bob", telegram_user_id=999)
    r1 = service.receive_contact_card(card1)
    assert isinstance(r1, PendingContact)
    service.submit_context(r1.pending_id, "Designer")

    card2 = ContactCardData(name="Bob Clone", telegram_user_id=999)
    r2 = service.receive_contact_card(card2)
    assert isinstance(r2, Duplicate)
    assert len(service.list_contacts()) == 1


def test_same_name_different_phone_allowed() -> None:
    service = _service()
    card1 = ContactCardData(name="Alice", phone_number="+111")
    p1 = service.receive_contact_card(card1)
    assert isinstance(p1, PendingContact)
    service.submit_context(p1.pending_id, "First Alice")

    card2 = ContactCardData(name="Alice", phone_number="+222")
    p2 = service.receive_contact_card(card2)
    assert isinstance(p2, PendingContact)
    service.submit_context(p2.pending_id, "Second Alice")

    assert len(service.list_contacts()) == 2


def test_invalid_missing_name() -> None:
    service = _service()
    r = service.receive_contact_card(ContactCardData(name=""))
    assert isinstance(r, Invalid)
    assert "name" in r.reason.lower()

    r2 = service.receive_contact_card(ContactCardData(name="   "))
    assert isinstance(r2, Invalid)


def test_contact_not_stored_until_context_submitted() -> None:
    service = _service()
    card = ContactCardData(name="Dave")
    service.receive_contact_card(card)
    assert len(service.list_contacts()) == 0


def test_pending_not_found_wrong_id() -> None:
    service = _service()
    card = ContactCardData(name="Eve")
    service.receive_contact_card(card)
    r = service.submit_context("wrong-uuid-here", "Some context")
    assert isinstance(r, PendingNotFound)
    assert r.pending_id == "wrong-uuid-here"
    assert len(service.list_contacts()) == 0


def test_pending_not_found_after_consumed() -> None:
    service = _service()
    card = ContactCardData(name="Frank")
    p = service.receive_contact_card(card)
    assert isinstance(p, PendingContact)
    service.submit_context(p.pending_id, "Valid context")
    r = service.submit_context(p.pending_id, "Second time")
    assert isinstance(r, PendingNotFound)
    assert len(service.list_contacts()) == 1


def test_empty_context_rejected() -> None:
    service = _service()
    card = ContactCardData(name="Grace")
    p = service.receive_contact_card(card)
    assert isinstance(p, PendingContact)
    r = service.submit_context(p.pending_id, "   ")
    assert isinstance(r, PendingNotFound)
    assert len(service.list_contacts()) == 0


def test_new_contact_card_replaces_pending() -> None:
    service = _service()
    p1 = service.receive_contact_card(ContactCardData(name="First"))
    assert isinstance(p1, PendingContact)
    first_id = p1.pending_id

    p2 = service.receive_contact_card(ContactCardData(name="Second"))
    assert isinstance(p2, PendingContact)
    assert p2.pending_id != first_id
    assert p2.name == "Second"

    r = service.submit_context(first_id, "Context for first")
    assert isinstance(r, PendingNotFound)
    service.submit_context(p2.pending_id, "Context for second")
    assert len(service.list_contacts()) == 1
    assert service.list_contacts()[0].name == "Second"


def test_search_empty_keyword_returns_empty() -> None:
    service = _service()
    card = ContactCardData(name="Hank")
    p = service.receive_contact_card(card)
    service.submit_context(p.pending_id, "Some context")
    assert len(service.search_contacts("")) == 0
    assert len(service.search_contacts("   ")) == 0
