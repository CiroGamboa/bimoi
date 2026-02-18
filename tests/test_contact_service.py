"""Unit tests for ContactService. No Telegram; in-memory repo and ContactCardData only."""

from bimoi.application import (
    AddContextInvalid,
    AddContextNotFound,
    AddContextSuccess,
    ContactCardData,
    ContactCreated,
    ContactService,
    Duplicate,
    Invalid,
    PendingContact,
    PendingNotFound,
)
from bimoi.domain import Person, RelationshipContext
from bimoi.infrastructure import InMemoryContactRepository


def _service() -> ContactService:
    return ContactService(repository=InMemoryContactRepository())


def test_valid_contact_card_then_context_creates_contact() -> None:
    service = _service()
    card = ContactCardData(name="Alice", phone_number="+12025551234")
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
    card1 = ContactCardData(name="Alice", phone_number="+12025551111")
    r1 = service.receive_contact_card(card1)
    assert isinstance(r1, PendingContact)
    created = service.submit_context(r1.pending_id, "Engineer")
    assert isinstance(created, ContactCreated)
    person_id = created.person_id

    card2 = ContactCardData(name="Alice Other", phone_number="+12025551111")
    r2 = service.receive_contact_card(card2)
    assert isinstance(r2, Duplicate)
    assert r2.person_id == person_id
    assert r2.name == "Alice"
    assert len(service.list_contacts()) == 1


def test_duplicate_by_telegram_user_id() -> None:
    service = _service()
    card1 = ContactCardData(name="Bob", telegram_user_id=999)
    r1 = service.receive_contact_card(card1)
    assert isinstance(r1, PendingContact)
    created = service.submit_context(r1.pending_id, "Designer")
    assert isinstance(created, ContactCreated)
    person_id = created.person_id

    card2 = ContactCardData(name="Bob Clone", telegram_user_id=999)
    r2 = service.receive_contact_card(card2)
    assert isinstance(r2, Duplicate)
    assert r2.person_id == person_id
    assert r2.name == "Bob"
    assert len(service.list_contacts()) == 1


def test_same_name_different_phone_allowed() -> None:
    service = _service()
    card1 = ContactCardData(name="Alice", phone_number="+12025551111")
    p1 = service.receive_contact_card(card1)
    assert isinstance(p1, PendingContact)
    service.submit_context(p1.pending_id, "First Alice")

    card2 = ContactCardData(name="Alice", phone_number="+12025552222")
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


def test_get_contact_returns_summary() -> None:
    service = _service()
    card = ContactCardData(name="Ivan")
    p = service.receive_contact_card(card)
    service.submit_context(p.pending_id, "Backend dev")
    listed = service.list_contacts()
    assert len(listed) == 1
    person_id = listed[0].person_id

    contact = service.get_contact(person_id)
    assert contact is not None
    assert contact.name == "Ivan"
    assert contact.context == "Backend dev"
    assert contact.person_id == person_id

    assert service.get_contact("nonexistent-uuid") is None


def test_add_context_appends_and_search_finds() -> None:
    service = _service()
    card = ContactCardData(name="Julia")
    p = service.receive_contact_card(card)
    created = service.submit_context(p.pending_id, "Original note")
    assert isinstance(created, ContactCreated)
    person_id = created.person_id

    result = service.add_context(person_id, "Extra note from 2024")
    assert isinstance(result, AddContextSuccess)
    assert result.name == "Julia"

    listed = service.list_contacts()
    assert len(listed) == 1
    assert "Original note" in listed[0].context
    assert "Extra note from 2024" in listed[0].context
    assert service.search_contacts("Extra")[0].name == "Julia"


def test_add_context_unknown_person_returns_not_found() -> None:
    service = _service()
    result = service.add_context("nonexistent-uuid", "Some text")
    assert isinstance(result, AddContextNotFound)
    assert result.person_id == "nonexistent-uuid"


def test_add_context_empty_text_returns_invalid() -> None:
    service = _service()
    card = ContactCardData(name="Kate")
    p = service.receive_contact_card(card)
    created = service.submit_context(p.pending_id, "Initial")
    assert isinstance(created, ContactCreated)

    assert isinstance(service.add_context(created.person_id, ""), AddContextInvalid)
    assert isinstance(service.add_context(created.person_id, "   "), AddContextInvalid)


def test_submit_context_with_resolver_uses_existing_person_id() -> None:
    """When resolver returns an id, repo.add is called with link_to_existing_id and result uses that id."""
    repo = InMemoryContactRepository()
    existing_id = "existing-person-uuid"
    repo.add(
        Person(
            id=existing_id,
            name="Bob",
            relationship_context=RelationshipContext(description="Pre-existing"),
        )
    )

    def resolver(eid: str):
        return existing_id if eid == "123" else None

    service = ContactService(repository=repo, resolve_existing_person_id=resolver)

    card = ContactCardData(name="Bob", telegram_user_id=123)
    pending = service.receive_contact_card(card)
    assert isinstance(pending, PendingContact)
    result = service.submit_context(pending.pending_id, "Met at conference")
    assert isinstance(result, ContactCreated)
    assert result.person_id == existing_id
    assert result.name == "Bob"
    assert len(service.list_contacts()) == 1
    assert service.list_contacts()[0].person_id == existing_id
