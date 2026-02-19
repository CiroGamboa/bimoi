"""Integration tests for identity layer (get_or_create_user_id, profile). Require Docker (testcontainers)."""

import uuid
from datetime import datetime, timezone

import pytest

from bimoi.infrastructure import (
    ensure_channel_link_constraint,
    get_account_profile,
    get_or_create_user_id,
    get_person_id_by_channel_external_id,
    set_registered,
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


def test_unsupported_channel_raises(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    with pytest.raises(ValueError, match="Unsupported channel"):
        get_or_create_user_id(clean_neo4j, "whatsapp", "555")


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
    assert profile.name == "Alice Smith"
    assert profile.bio is None


def test_update_account_profile_sets_name_and_bio(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    user_id, _ = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "update_user")
    update_account_profile(clean_neo4j, user_id, name="Bob", bio="Developer")
    profile = get_account_profile(clean_neo4j, user_id)
    assert profile is not None
    assert profile.name == "Bob"
    assert profile.bio == "Developer"


def test_update_account_profile_partial_only_updates_given_fields(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    user_id, _ = get_or_create_user_id(
        clean_neo4j, CHANNEL_TELEGRAM, "partial_user", initial_name="Original"
    )
    update_account_profile(clean_neo4j, user_id, bio="Only bio set")
    profile = get_account_profile(clean_neo4j, user_id)
    assert profile is not None
    assert profile.name == "Original"
    assert profile.bio == "Only bio set"


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
    assert profile.name == "Keep"


def test_update_account_profile_raises_for_bio_over_max_length(clean_neo4j):
    from bimoi.domain.entities import BIO_MAX_LENGTH

    ensure_channel_link_constraint(clean_neo4j)
    user_id, _ = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "long_bio_user")
    with pytest.raises(ValueError, match=f"at most {BIO_MAX_LENGTH}"):
        update_account_profile(clean_neo4j, user_id, bio="x" * (BIO_MAX_LENGTH + 1))


def test_existing_contact_signup_returns_is_new_until_registered(clean_neo4j):
    """When a Person was added as contact (registered: false), signup sees is_new=True; after set_registered, is_new=False."""
    ensure_channel_link_constraint(clean_neo4j)
    # Simulate "Daniel" added by someone else: Person with telegram_id but registered: false
    daniel_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with clean_neo4j.session() as session:
        session.run(
            """
            CREATE (p:Person {
                id: $id,
                telegram_id: $telegram_id,
                created_at: $created_at,
                registered: false
            })
            """,
            id=daniel_id,
            telegram_id="daniel_telegram_555",
            created_at=created_at,
        )
    user_id, is_new = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "daniel_telegram_555")
    assert user_id == daniel_id
    assert is_new is True
    set_registered(clean_neo4j, user_id)
    _, is_new_after = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "daniel_telegram_555")
    assert is_new_after is False


def test_get_person_id_by_channel_external_id_returns_id_when_linked(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    user_id, _ = get_or_create_user_id(clean_neo4j, CHANNEL_TELEGRAM, "existing_telegram_123")
    person_id = get_person_id_by_channel_external_id(clean_neo4j, CHANNEL_TELEGRAM, "existing_telegram_123")
    assert person_id is not None
    assert person_id == user_id


def test_get_person_id_by_channel_external_id_returns_none_when_not_linked(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    person_id = get_person_id_by_channel_external_id(clean_neo4j, CHANNEL_TELEGRAM, "never_signed_up_456")
    assert person_id is None


def test_get_person_id_by_channel_external_id_returns_none_for_empty_input(clean_neo4j):
    ensure_channel_link_constraint(clean_neo4j)
    assert get_person_id_by_channel_external_id(clean_neo4j, "", "123") is None
    assert get_person_id_by_channel_external_id(clean_neo4j, CHANNEL_TELEGRAM, "") is None
