"""Integration tests for Neo4jContactRepository. Require Docker (testcontainers)."""

import pytest

from bimoi.application import ContactCardData
from bimoi.domain import Person, RelationshipContext
from bimoi.infrastructure import Neo4jContactRepository


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
        phone_number="+111",
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
        phone_number="+222",
        relationship_context=RelationshipContext(description="Designer"),
    )
    repo.add(person)

    assert repo.find_duplicate(ContactCardData(name="Other", phone_number="+222")) is not None
    assert repo.find_duplicate(ContactCardData(name="X", phone_number="+999")) is None


def test_find_duplicate_by_external_id(clean_neo4j):
    repo = Neo4jContactRepository(clean_neo4j, user_id="default")
    person = Person(
        name="Carol",
        external_id="123",
        relationship_context=RelationshipContext(description="VC"),
    )
    repo.add(person)

    assert repo.find_duplicate(ContactCardData(name="X", telegram_user_id=123)) is not None
    assert repo.find_duplicate(ContactCardData(name="X", telegram_user_id=456)) is None


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
        phone_number="+555",
        relationship_context=RelationshipContext(description="Only for A"),
    )
    repo_a.add(person)

    assert len(repo_a.list_all()) == 1
    assert len(repo_b.list_all()) == 0

    assert repo_a.find_duplicate(ContactCardData(name="X", phone_number="+555")) is not None
    assert repo_b.find_duplicate(ContactCardData(name="X", phone_number="+555")) is None

    assert repo_b.get_by_id(person.id) is None
    assert repo_a.get_by_id(person.id) is not None
