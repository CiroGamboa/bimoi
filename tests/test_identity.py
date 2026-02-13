"""Integration tests for identity layer (get_or_create_user_id). Require Docker (testcontainers)."""

import uuid

import pytest

from bimoi.infrastructure import ensure_channel_link_constraint, get_or_create_user_id
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
    # Ensure constraint exists (other tests may have created it)
    ensure_channel_link_constraint(neo4j_driver)


def test_get_or_create_returns_uuid(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    user_id = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "12345")
    assert user_id is not None
    uuid.UUID(user_id)


def test_same_channel_and_external_id_returns_same_user_id(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    a = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "99999")
    b = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "99999")
    assert a == b


def test_different_external_id_returns_different_user_id(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    a = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "111")
    b = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "222")
    assert a != b


def test_different_channel_same_external_id_returns_different_user_id(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    a = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "555")
    b = get_or_create_user_id(clean_neo4j, "whatsapp", "555")
    assert a != b


def test_empty_external_id_raises(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    with pytest.raises(ValueError, match="external_id"):
        get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "")


def test_empty_channel_raises(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    with pytest.raises(ValueError, match="channel"):
        get_or_create_user_id(clean_neo4j, "", "12345")
