"""Minimal API tests. /health does not require Neo4j."""

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_pending_add_context_file_roundtrip(tmp_path, monkeypatch):
    """File-backed pending add-context: save then pop returns the same data."""

    from api import main as api_main

    pending_file = tmp_path / "cursor" / "pending_add_context.json"
    monkeypatch.setattr(api_main, "_pending_add_context_file", lambda: pending_file)

    api_main._save_pending_add_context("user1", 12345, "person-uuid-1", "Alice")
    assert pending_file.exists()
    assert api_main._load_pending_add_context("user1") == {12345: ("person-uuid-1", "Alice")}

    popped = api_main._pop_pending_add_context_from_file("user1", 12345)
    assert popped == ("person-uuid-1", "Alice")
    assert api_main._pop_pending_add_context_from_file("user1", 12345) is None
