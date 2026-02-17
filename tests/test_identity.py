"""Integration tests for identity layer (get_or_create_user_id, profile). Require Docker (testcontainers)."""

import uuid

import pytest

from bimoi.infrastructure import (
    ensure_channel_link_constraint,
    get_account_profile,
    get_or_create_user_id,
    update_account_profile,
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
    # Ensure constraint exists (other tests may have created it)
    ensure_channel_link_constraint(neo4j_driver)


def test_get_or_create_returns_uuid_and_is_new(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    user_id, is_new = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "12345")
    assert user_id is not None
    uuid.UUID(user_id)
    assert is_new is True


def test_same_channel_and_external_id_returns_same_user_id_second_call_not_new(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    a, is_new_a = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "99999")
    b, is_new_b = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "99999")
    assert a == b
    assert is_new_a is True
    assert is_new_b is False


def test_different_external_id_returns_different_user_id(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    a, _ = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "111")
    b, _ = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "222")
    assert a != b


def test_different_channel_same_external_id_returns_different_user_id(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    a, _ = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "555")
    b, _ = get_or_create_user_id(clean_neo4j, "whatsapp", "555")
    assert a != b


def test_empty_external_id_raises(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    with pytest.raises(ValueError, match="external_id"):
        get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "")


def test_empty_channel_raises(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    with pytest.raises(ValueError, match="channel"):
        get_or_create_user_id(clean_neo4j, "", "12345")


def test_create_with_initial_name_stores_name(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    user_id, is_new = get_or_create_user_id(
        clean_neo4j, CHANNEL_TELEGRAM, "profile_user", initial_name="Alice Smith"
    )
    assert is_new is True
    profile = get_account_profile(clean_neo4j, user_id)
    assert profile is not None
    assert profile["name"] == "Alice Smith"
    assert profile["bio"] is None


def test_update_account_profile_sets_name_and_bio(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    user_id, _ = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "update_user")
    update_account_profile(clean_neo4j, user_id, name="Bob", bio="Developer")
    profile = get_account_profile(clean_neo4j, user_id)
    assert profile is not None
    assert profile["name"] == "Bob"
    assert profile["bio"] == "Developer"


def test_update_account_profile_partial_only_updates_given_fields(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    user_id, _ = get_or_create_user_id(
        clean_neo4j, CHANNEL_TELEGRAM, "partial_user", initial_name="Original"
    )
    update_account_profile(clean_neo4j, user_id, bio="Only bio set")
    profile = get_account_profile(clean_neo4j, user_id)
    assert profile is not None
    assert profile["name"] == "Original"
    assert profile["bio"] == "Only bio set"


def test_get_account_profile_returns_none_for_unknown_user(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    profile = get_account_profile(clean_neo4j, "00000000-0000-0000-0000-000000000000")
    assert profile is None


def test_update_account_profile_no_op_when_both_none(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    user_id, _ = get_or_create_user_id(
        clean_neo4j, CHANNEL_TELEGRAM, "noop_user", initial_name="Keep"
    )
    update_account_profile(clean_neo4j, user_id)
    profile = get_account_profile(clean_neo4j, user_id)
    assert profile is not None
    assert profile["name"] == "Keep"
