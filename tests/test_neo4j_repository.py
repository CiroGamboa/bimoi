"""Integration tests for Neo4jContactRepository. Require Docker
(testcontainers)."""

import pytest

from bimoi.application import ContactCardData, ContactService
from bimoi.domain import Person, RelationshipContext
from bimoi.infrastructure import (
    Neo4jContactRepository,
    ensure_channel_link_constraint,
    get_or_create_user_id,
)
from bimoi.infrastructure.identity import CHANNEL_TELEGRAM


@pytest.fixture(scope="session")
def neo4j_driver():
    from testcontainers.neo4j import Neo4jContainer

    with Neo4jContainer() as neo4j:
        driver = neo4j.get_driver()
        try:
            yield driver
        finally:
            driver.close()


@pytest.fixture
def clean_neo4j(neo4j_driver):
    """Clear the graph before each test so tests are independent."""
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield neo4j_driver


def test_add_get_by_id_list_all(clean_neo4j):
    repo = Neo4jContactRepository(clean_neo4j, user_id="default")
    ctx = RelationshipContext(description="Engineer, React")
    person = Person(
        name="Alice",
        phone_number="+12025551111",
        relationship_context=ctx,
    )
    repo.add(person)

    found = repo.get_by_id(person.id)
    assert found is not None
    assert found.id == person.id
    assert found.name == "Alice"
    assert found.relationship_context.description == "Engineer, React"

    all_contacts = repo.list_all()
    assert len(all_contacts) == 1
    assert all_contacts[0].id == person.id


def test_find_duplicate_by_phone(clean_neo4j):
    repo = Neo4jContactRepository(clean_neo4j, user_id="default")
    person = Person(
        name="Bob",
        phone_number="+12025552222",
        relationship_context=RelationshipContext(description="Designer"),
    )
    repo.add(person)

    card_dup = ContactCardData(name="Other", phone_number="+12025552222")
    assert repo.find_duplicate(card_dup) is not None
    card_no_dup = ContactCardData(name="X", phone_number="+12025559999")
    assert repo.find_duplicate(card_no_dup) is None


def test_find_duplicate_by_phone_e164_deduplication(clean_neo4j):
    """Different phone formats (same number) match the same Person (E.164 deduplication)."""
    repo = Neo4jContactRepository(clean_neo4j, user_id="default")
    person = Person(
        name="Bob",
        phone_number="+1 202-555-1234",
        relationship_context=RelationshipContext(description="Designer"),
    )
    repo.add(person)
    # Same number, different format (with country code so normalizes without default_region)
    card = ContactCardData(name="Other", phone_number="+1 (202) 555-1234")
    found = repo.find_duplicate(card)
    assert found is not None
    assert found.id == person.id
    assert found.phone_number == "+12025551234"


def test_find_duplicate_by_external_id(clean_neo4j):
    repo = Neo4jContactRepository(clean_neo4j, user_id="default")
    person = Person(
        name="Carol",
        external_id="123",
        relationship_context=RelationshipContext(description="VC"),
    )
    repo.add(person)

    card_dup = ContactCardData(name="X", telegram_user_id=123)
    assert repo.find_duplicate(card_dup) is not None
    card_no_dup = ContactCardData(name="X", telegram_user_id=456)
    assert repo.find_duplicate(card_no_dup) is None


def test_list_all_ordering(clean_neo4j):
    repo = Neo4jContactRepository(clean_neo4j, user_id="default")
    p1 = Person(
        name="First",
        relationship_context=RelationshipContext(description="First context"),
    )
    p2 = Person(
        name="Second",
        relationship_context=RelationshipContext(description="Second context"),
    )
    repo.add(p1)
    repo.add(p2)

    all_contacts = repo.list_all()
    assert len(all_contacts) == 2
    assert all_contacts[0].name == "First"
    assert all_contacts[1].name == "Second"


def test_multi_user_isolation(clean_neo4j):
    repo_a = Neo4jContactRepository(clean_neo4j, user_id="user_a")
    repo_b = Neo4jContactRepository(clean_neo4j, user_id="user_b")

    person = Person(
        name="Shared",
        phone_number="+12025555555",
        relationship_context=RelationshipContext(description="Only for A"),
    )
    repo_a.add(person)

    assert len(repo_a.list_all()) == 1
    assert len(repo_b.list_all()) == 0

    card = ContactCardData(name="X", phone_number="+12025555555")
    assert repo_a.find_duplicate(card) is not None
    assert repo_b.find_duplicate(card) is None

    assert repo_b.get_by_id(person.id) is None
    assert repo_a.get_by_id(person.id) is not None


def test_append_context(clean_neo4j):
    repo = Neo4jContactRepository(clean_neo4j, user_id="default")
    ctx = RelationshipContext(description="Original context")
    person = Person(
        name="Dave",
        phone_number="+12025554444",
        relationship_context=ctx,
    )
    repo.add(person)

    assert repo.append_context(person.id, "Extra note") is True
    found = repo.get_by_id(person.id)
    assert found is not None
    assert "Original context" in found.relationship_context.description
    assert "Extra note" in found.relationship_context.description
    assert "\n\n— " in found.relationship_context.description

    assert repo.append_context("nonexistent-id", "Text") is False


def test_context_stored_on_relationship(clean_neo4j):
    """Verify that context is stored on KNOWS relationship, not as separate
    nodes."""
    repo = Neo4jContactRepository(clean_neo4j, user_id="default")
    person = Person(
        name="Test",
        relationship_context=RelationshipContext(description="Test context"),
    )
    repo.add(person)

    # Verify structure: context is on KNOWS edge, not separate node
    with clean_neo4j.session() as session:
        result = session.run(
            "MATCH (owner)-[k:KNOWS]->(p:Person {id: $id}) "
            "RETURN k.context_description AS ctx",
            id=person.id,
        )
        record = result.single()
        assert record is not None
        assert record["ctx"] == "Test context"

        # Verify no RelationshipContext nodes exist
        result = session.run("MATCH (c:RelationshipContext) RETURN count(c) AS cnt")
        assert result.single()["cnt"] == 0


def test_add_link_to_existing_person_reuses_node(clean_neo4j):
    """When link_to_existing_id is set, only KNOWS is created; no new Person node."""
    ensure_channel_link_constraint(clean_neo4j)
    # Bob is already on the app (owner Person via identity)
    bob_id, _ = get_or_create_user_id(
        clean_neo4j, CHANNEL_TELEGRAM, "bob_telegram_999", initial_name="Bob"
    )
    # Alice adds Bob as a contact (link to existing Person)
    repo_alice = Neo4jContactRepository(clean_neo4j, user_id="alice-uuid")
    ctx = RelationshipContext(description="From conference")
    person_placeholder = Person(
        name="Bob",
        phone_number="+12025559999",
        relationship_context=ctx,
    )
    repo_alice.add(person_placeholder, link_to_existing_id=bob_id)

    # Alice's list includes Bob (one Person node for Bob)
    alice_contacts = repo_alice.list_all()
    assert len(alice_contacts) == 1
    assert alice_contacts[0].id == bob_id
    assert alice_contacts[0].name == "Bob"

    # Only one Person with id bob_id in the graph
    with clean_neo4j.session() as session:
        result = session.run(
            "MATCH (p:Person {id: $id}) RETURN count(p) AS cnt", id=bob_id
        )
        assert result.single()["cnt"] == 1
        result = session.run(
            "MATCH (owner:Person {id: 'alice-uuid'})-[k:KNOWS]->(p:Person {id: $id}) "
            "RETURN k.context_description AS ctx",
            id=bob_id,
        )
        rec = result.single()
        assert rec is not None
        assert rec["ctx"] == "From conference"


def test_find_duplicate_returns_registered_person(clean_neo4j):
    """find_duplicate matches by external_id even when Person has registered: true."""
    ensure_channel_link_constraint(clean_neo4j)
    bob_id, _ = get_or_create_user_id(
        clean_neo4j, CHANNEL_TELEGRAM, "tid_dup_777", initial_name="Bob"
    )
    repo = Neo4jContactRepository(clean_neo4j, user_id="owner-x")
    repo.add(
        Person(name="Bob", relationship_context=RelationshipContext(description="Friend")),
        link_to_existing_id=bob_id,
    )
    card = ContactCardData(name="Other", telegram_user_id="tid_dup_777")
    found = repo.find_duplicate(card)
    assert found is not None
    assert found.id == bob_id


def test_search_by_bio_returns_contact_when_keyword_in_bio(clean_neo4j):
    """Search matches keyword in contact's bio (registered users); result includes bio."""
    ensure_channel_link_constraint(clean_neo4j)
    owner_id, _ = get_or_create_user_id(
        clean_neo4j, CHANNEL_TELEGRAM, "owner_bio_search", initial_name="Alice"
    )
    repo = Neo4jContactRepository(clean_neo4j, user_id=owner_id)
    person = Person(
        name="Daniel",
        relationship_context=RelationshipContext(description="Met at conference"),
    )
    repo.add(person)
    with clean_neo4j.session() as session:
        session.run(
            "MATCH (p:Person {id: $id}) SET p.bio = $bio",
            id=person.id,
            bio="Engineer and guitarist",
        )
    service = ContactService(repo)
    results = service.search_contacts("guitarist")
    assert len(results) == 1
    assert results[0].person_id == person.id
    assert results[0].bio == "Engineer and guitarist"
    assert results[0].name == "Daniel"


def test_get_mutual_contact_ids_returns_ids_when_reverse_knows(clean_neo4j):
    """get_mutual_contact_ids returns person_ids of contacts who have also added the owner."""
    ensure_channel_link_constraint(clean_neo4j)
    alice_id, _ = get_or_create_user_id(
        clean_neo4j, CHANNEL_TELEGRAM, "alice_mutual", initial_name="Alice"
    )
    bob_id, _ = get_or_create_user_id(
        clean_neo4j, CHANNEL_TELEGRAM, "bob_mutual", initial_name="Bob"
    )
    repo_alice = Neo4jContactRepository(clean_neo4j, user_id=alice_id)
    repo_alice.add(
        Person(
            name="Bob",
            relationship_context=RelationshipContext(description="Friend"),
        ),
        link_to_existing_id=bob_id,
    )
    assert bob_id not in repo_alice.get_mutual_contact_ids()
    with clean_neo4j.session() as session:
        session.run(
            """
            MATCH (bob:Person {id: $bob_id}), (alice:Person {id: $alice_id})
            CREATE (bob)-[:KNOWS {
                context_id: $ctx_id,
                context_description: $desc,
                context_created_at: $ts,
                context_updated_at: $ts,
                contact_name: $contact_name
            }]->(alice)
            """,
            bob_id=bob_id,
            alice_id=alice_id,
            ctx_id="ctx-mutual",
            desc="Added Alice",
            ts="2020-01-01T00:00:00",
            contact_name="Alice",
        )
    mutual_ids = repo_alice.get_mutual_contact_ids()
    assert mutual_ids == {bob_id}
