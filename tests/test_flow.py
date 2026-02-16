"""Tests for YAML flow loader, XState machine, and flow adapter."""

import pytest

from api.flow_adapter import SendMessage, event_to_xstate, run_xstate_flow
from api.flow_loader import get_flow_path, load_flow
from api.flow_runner import SendMessage as LegacySendMessage
from api.flow_runner import SetSlots, run_flow
from api.main import _update_to_event
from api.xstate_machine import load_machine, transition


def test_load_flow():
    path = get_flow_path()
    assert path.name == "telegram.yaml"
    flow = load_flow(path)
    assert "nodes" in flow
    assert "start_node" in flow
    assert flow["start_node"] == "start"
    assert "messages" in flow
    node_ids = [n["id"] for n in flow["nodes"] if isinstance(n, dict) and n.get("id")]
    assert "start" in node_ids
    assert flow["start_node"] in node_ids


def test_load_flow_invalid_start_node(tmp_path):
    yaml_content = """
start_node: missing
nodes:
  - id: start
    type: router
    edges: []
"""
    (tmp_path / "flow.yaml").write_text(yaml_content)
    with pytest.raises(ValueError, match="start_node.*must be a node id"):
        load_flow(tmp_path / "flow.yaml")


def test_run_flow_welcome():
    flow = load_flow()
    state = {"current_node_id": "start", "slots": {}}
    event = {"type": "text", "subtype": "command_start", "payload": {"text": "/start"}}

    class MockService:
        def list_contacts(self):
            return []

        def receive_contact_card(self, c):
            return None

        def get_contact(self, pid):
            return None

        def add_context(self, pid, t):
            return None

        def submit_context(self, pid, t):
            return None

        def search_contacts(self, k):
            return []

    actions, new_state = run_flow(state, event, MockService(), flow)
    assert new_state["current_node_id"] == "start"
    send_actions = [a for a in actions if isinstance(a, LegacySendMessage)]
    assert len(send_actions) >= 1
    assert "who" in send_actions[0].text.lower() or "contact" in send_actions[0].text.lower()


def test_run_flow_list_empty():
    flow = load_flow()
    state = {"current_node_id": "start", "slots": {}}
    event = {"type": "text", "subtype": "command_list", "payload": {"text": "/list"}}

    class MockService:
        def list_contacts(self):
            return []

        def receive_contact_card(self, c):
            return None

        def get_contact(self, pid):
            return None

        def add_context(self, pid, t):
            return None

        def submit_context(self, pid, t):
            return None

        def search_contacts(self, k):
            return []

    actions, new_state = run_flow(state, event, MockService(), flow)
    assert new_state["current_node_id"] == "start"
    send_actions = [a for a in actions if isinstance(a, LegacySendMessage)]
    assert len(send_actions) >= 1
    assert "No contacts" in send_actions[0].text or "no contacts" in send_actions[0].text.lower()


def test_run_flow_receive_contact_pending():
    from bimoi.application.dto import PendingContact

    flow = load_flow()
    state = {"current_node_id": "start", "slots": {}}
    event = {
        "type": "contact_shared",
        "subtype": None,
        "payload": {
            "name": "Alice",
            "phone_number": "+123",
            "telegram_user_id": None,
        },
    }

    class MockService:
        def list_contacts(self):
            return []

        def receive_contact_card(self, c):
            return PendingContact(pending_id="p-1", name=c.name)

        def get_contact(self, pid):
            return None

        def add_context(self, pid, t):
            return None

        def submit_context(self, pid, t):
            return None

        def search_contacts(self, k):
            return []

    actions, new_state = run_flow(state, event, MockService(), flow)
    assert new_state["current_node_id"] == "awaiting_context"
    assert new_state["slots"].get("pending_id") == "p-1"
    send_actions = [a for a in actions if isinstance(a, LegacySendMessage)]
    assert len(send_actions) >= 1
    set_slots_actions = [a for a in actions if isinstance(a, SetSlots)]
    assert any("p-1" in str(s.slots) for s in set_slots_actions)


def test_update_to_event_text_command_start():
    """Event from /start text message (minimal Telegram update payload)."""
    from telegram import Update

    body = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": 1, "is_bot": False, "first_name": "U"},
            "chat": {"id": 123, "type": "private"},
            "date": 1,
            "text": "/start",
        },
    }
    update = Update.de_json(body, None)
    event = _update_to_event(update, {})
    assert event is not None
    assert event["type"] == "text"
    assert event["subtype"] == "command_start"
    assert event["payload"]["text"] == "/start"


def test_update_to_event_callback_cmd_list():
    """Event from List contacts callback."""
    from telegram import Update

    body = {
        "update_id": 1,
        "callback_query": {
            "id": "cq1",
            "from": {"id": 1, "is_bot": False, "first_name": "U"},
            "message": {
                "message_id": 1,
                "chat": {"id": 123, "type": "private"},
                "date": 1,
            },
            "chat_instance": "x",
            "data": "cmd:list",
        },
    }
    update = Update.de_json(body, None)
    event = _update_to_event(update, {})
    assert event is not None
    assert event["type"] == "callback"
    assert event["subtype"] == "cmd_list"
    assert event["payload"]["data"] == "cmd:list"


def test_update_to_event_contact_shared():
    """Event from shared contact."""
    from telegram import Update

    body = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": 1, "is_bot": False, "first_name": "U"},
            "chat": {"id": 123, "type": "private"},
            "date": 1,
            "contact": {
                "phone_number": "+123",
                "first_name": "Alice",
                "last_name": "Smith",
                "user_id": 42,
            },
        },
    }
    update = Update.de_json(body, None)
    event = _update_to_event(update, {})
    assert event is not None
    assert event["type"] == "contact_shared"
    assert event["payload"]["name"] == "Alice Smith"
    assert event["payload"]["phone_number"] == "+123"


def test_xstate_machine_transition():
    """XState machine: standard transition by event."""
    machine = load_machine()
    assert machine["initial"] == "idle"
    next_state = transition(machine, "idle", "TEXT_COMMAND_START")
    assert next_state == "welcome"
    next_state = transition(machine, "welcome", "DONE")
    assert next_state == "idle"
    next_state = transition(machine, "idle", "CONTACT_SHARED")
    assert next_state == "receive_contact"


def test_event_to_xstate():
    """Adapter maps event dict to XState event string."""
    assert event_to_xstate({"type": "text", "subtype": "command_start", "payload": {}}) == "TEXT_COMMAND_START"
    assert event_to_xstate({"type": "callback", "subtype": "cmd_list", "payload": {}}) == "CALLBACK_LIST"
    assert event_to_xstate({"type": "contact_shared", "subtype": None, "payload": {}}) == "CONTACT_SHARED"


def test_run_xstate_flow_welcome():
    """XState adapter: /start sends welcome and returns to idle."""
    class MockService:
        def list_contacts(self): return []
        def receive_contact_card(self, c): return None
        def get_contact(self, pid): return None
        def add_context(self, pid, t): return None
        def submit_context(self, pid, t): return None
        def search_contacts(self, k): return []

    actions, state_value, slots = run_xstate_flow(
        "idle",
        {"type": "text", "subtype": "command_start", "payload": {"text": "/start"}},
        {},
        MockService(),
    )
    assert state_value == "idle"
    send_actions = [a for a in actions if isinstance(a, SendMessage)]
    assert len(send_actions) >= 1
    assert "who" in send_actions[0].text.lower() or "contact" in send_actions[0].text.lower()


def test_run_xstate_flow_receive_contact_pending():
    """XState adapter: contact_shared with pending outcome."""
    from bimoi.application.dto import PendingContact

    class MockService:
        def list_contacts(self): return []
        def receive_contact_card(self, c): return PendingContact(pending_id="p-1", name=c.name)
        def get_contact(self, pid): return None
        def add_context(self, pid, t): return None
        def submit_context(self, pid, t): return None
        def search_contacts(self, k): return []

    actions, state_value, slots = run_xstate_flow(
        "idle",
        {
            "type": "contact_shared",
            "subtype": None,
            "payload": {"name": "Alice", "phone_number": "+1", "telegram_user_id": None},
        },
        {},
        MockService(),
    )
    assert state_value == "awaiting_context"
    assert slots.get("pending_id") == "p-1"
    send_actions = [a for a in actions if isinstance(a, SendMessage)]
    assert len(send_actions) >= 1
