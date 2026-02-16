"""Run one flow step: state + event + service -> actions + new state."""

from dataclasses import dataclass
from typing import Any

from api.flow_loader import get_flow
from bimoi.application import (
    AddContextInvalid,
    AddContextNotFound,
    AddContextSuccess,
    ContactCardData,
    ContactCreated,
    ContactSummary,
    Duplicate,
    Invalid,
    PendingContact,
)


@dataclass
class SendMessage:
    text: str
    keyboard: str | None = None


@dataclass
class SendContactList:
    summaries: list[ContactSummary]


@dataclass
class SetSlots:
    slots: dict[str, Any]


@dataclass
class ClearSlots:
    keys: list[str]


@dataclass
class Transition:
    node_id: str


FlowAction = SendMessage | SendContactList | SetSlots | ClearSlots | Transition


def _resolve_path(path: str, event: dict, slots: dict, result: Any = None) -> Any:
    """Resolve a path like 'event.payload.text' or 'slots.pending_id' or 'result.name'."""
    parts = path.strip().split(".")
    if not parts:
        return None
    ctx = {"event": event, "slots": slots, "result": result}
    root = parts[0]
    if root not in ctx:
        return None
    obj = ctx[root]
    for p in parts[1:]:
        if obj is None:
            return None
        obj = obj.get(p) if isinstance(obj, dict) else getattr(obj, p, None)
    return obj


def _resolve_input(input_from: dict | str, event: dict, slots: dict) -> dict:
    """Resolve input_from spec to a flat dict of values."""
    if isinstance(input_from, str):
        if input_from == "event.payload":
            return event.get("payload") or {}
        return {}
    out: dict[str, Any] = {}
    for key, path in (input_from or {}).items():
        if isinstance(path, str):
            out[key] = _resolve_path(path, event, slots)
        else:
            out[key] = path
    return out


def _get_node(flow: dict, node_id: str) -> dict | None:
    for n in flow.get("nodes") or []:
        if isinstance(n, dict) and n.get("id") == node_id:
            return n
    return None


def _format_message(messages: dict, message_id: str, template_vars: dict | None) -> str:
    text = messages.get(message_id) or message_id
    if not template_vars:
        return text
    for k, v in (template_vars or {}).items():
        text = text.replace("{" + k + "}", str(v) if v is not None else "")
    return text


def _template_vars_from_slots(slots: dict) -> dict:
    return {"name": slots.get("contact_name")}


def _run_router(flow: dict, node: dict, event: dict) -> str | None:
    """Return next node_id if an edge matches, else None."""
    event_type = event.get("type")
    subtype = event.get("subtype")
    edges = node.get("edges") or []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        on_type = edge.get("event_type")
        when = edge.get("when")
        next_id = edge.get("next")
        if next_id is None:
            continue
        if on_type is not None and on_type != event_type:
            continue
        if when is not None and when != subtype:
            continue
        return next_id
    # Fallback: edge with only 'next'
    for edge in edges:
        if (
            isinstance(edge, dict)
            and edge.get("next")
            and "event_type" not in edge
        ):
            return edge["next"]
    return None


def _run_send_message(
    flow: dict, node: dict, state: dict
) -> tuple[list[FlowAction], str | None]:
    """Run a send_message node. Return (actions, next_node_id)."""
    actions: list[FlowAction] = []
    messages = flow.get("messages") or {}
    slots = state.get("slots") or {}
    template_vars = _template_vars_from_slots(slots)
    message_id = node.get("message")
    if message_id:
        text = _format_message(messages, message_id, template_vars)
        actions.append(SendMessage(text=text, keyboard=node.get("keyboard")))
    set_slots = node.get("set_slots")
    if set_slots:
        resolved = {}
        for k, path in (set_slots or {}).items():
            if isinstance(path, str) and path.startswith("slots."):
                resolved[k] = slots.get(path.split(".", 1)[1])
            else:
                resolved[k] = path
        if resolved:
            actions.append(SetSlots(slots=resolved))
    clear_slots = node.get("clear_slots")
    if clear_slots:
        actions.append(ClearSlots(keys=list(clear_slots)))
    next_id = None
    for edge in node.get("edges") or []:
        if isinstance(edge, dict) and edge.get("next"):
            next_id = edge["next"]
            break
    if next_id:
        actions.append(Transition(node_id=next_id))
    return actions, next_id


def _call_service(
    service: Any,
    action: str,
    input_from: dict | str,
    event: dict,
    slots: dict,
) -> tuple[Any, str]:
    """Call ContactService method; return (result, outcome)."""
    resolved = _resolve_input(input_from, event, slots) if input_from else {}
    if action == "receive_contact_card":
        card = ContactCardData(
            name=resolved.get("name") or "",
            phone_number=resolved.get("phone_number"),
            telegram_user_id=resolved.get("telegram_user_id"),
        )
        result = service.receive_contact_card(card)
        if isinstance(result, PendingContact):
            return result, "pending"
        if isinstance(result, Duplicate):
            return result, "duplicate"
        if isinstance(result, Invalid):
            return result, "invalid"
        return result, "invalid"
    if action == "submit_context":
        pending_id = resolved.get("pending_id") or ""
        text = resolved.get("text") or ""
        result = service.submit_context(pending_id, text)
        if isinstance(result, ContactCreated):
            return result, "created"
        return result, "pending_not_found"
    if action == "list_contacts":
        summaries = service.list_contacts()
        return summaries, "empty" if not summaries else "has_results"
    if action == "search_contacts":
        keyword = resolved.get("keyword") or (event.get("payload") or {}).get("text") or ""
        summaries = service.search_contacts(keyword)
        return summaries, "empty" if not summaries else "has_results"
    if action == "add_context":
        person_id = resolved.get("person_id") or slots.get("person_id") or ""
        text = resolved.get("text") or (event.get("payload") or {}).get("text") or ""
        result = service.add_context(person_id, text)
        if isinstance(result, AddContextSuccess):
            return result, "success"
        if isinstance(result, AddContextNotFound):
            return result, "not_found"
        if isinstance(result, AddContextInvalid):
            return result, "invalid"
        return result, "invalid"
    if action == "get_contact":
        person_id = resolved.get("person_id") or (event.get("payload") or {}).get("person_id") or ""
        contact = service.get_contact(person_id)
        if contact:
            return contact, "found"
        return None, "not_found"
    return None, "invalid"


def _run_call_service(
    flow: dict,
    node: dict,
    state: dict,
    event: dict,
    service: Any,
) -> tuple[list[FlowAction], str | None]:
    """Run a call_service node. Return (actions, next_node_id)."""
    actions: list[FlowAction] = []
    action = node.get("action")
    input_from = node.get("input_from")
    slots = state.get("slots") or {}
    result, outcome = _call_service(service, action, input_from, event, slots)
    messages = flow.get("messages") or {}
    edges = node.get("edges") or []
    matched_edge = None
    for edge in edges:
        if isinstance(edge, dict) and edge.get("outcome") == outcome:
            matched_edge = edge
            break
    if not matched_edge:
        return actions, None
    next_id = matched_edge.get("next")
    # Clear slots from node
    clear_slots = node.get("clear_slots")
    if clear_slots:
        actions.append(ClearSlots(keys=list(clear_slots)))
    # Set slots from edge
    set_slots_spec = matched_edge.get("set_slots")
    resolved_slots: dict[str, Any] = {}
    if set_slots_spec:
        for k, path in (set_slots_spec or {}).items():
            if isinstance(path, str):
                resolved_slots[k] = _resolve_path(path, event, slots, result)
            else:
                resolved_slots[k] = path
        if resolved_slots:
            actions.append(SetSlots(slots=resolved_slots))
            slots = {**slots, **resolved_slots}
    # Message from edge
    message_id = matched_edge.get("message")
    message_from_result = matched_edge.get("message_from_result")
    if message_from_result and result:
        reason = getattr(result, "reason", None) or ""
        actions.append(SendMessage(text=reason))
    elif message_id:
        template_vars = _template_vars_from_slots(slots)
        if result and hasattr(result, "name"):
            template_vars = dict(template_vars)
            template_vars["name"] = getattr(result, "name", None)
        text = _format_message(messages, message_id, template_vars)
        actions.append(SendMessage(text=text, keyboard=matched_edge.get("keyboard")))
    if matched_edge.get("send_contact_list") and result and isinstance(result, list):
        actions.append(SendContactList(summaries=result))
    if next_id:
        actions.append(Transition(node_id=next_id))
    return actions, next_id


def run_flow(
    state: dict,
    event: dict,
    service: Any,
    flow: dict | None = None,
) -> tuple[list[FlowAction], dict]:
    """
    Run one step of the flow. Returns (list of actions, new_state).
    state = { "current_node_id": str, "slots": dict }
    event = { "type": str, "subtype": str | None, "payload": dict }
    """
    if flow is None:
        flow = get_flow()
    slots = dict(state.get("slots") or {})
    current_id = state.get("current_node_id") or flow.get("start_node")
    all_actions: list[FlowAction] = []
    while True:
        node = _get_node(flow, current_id)
        if not node:
            break
        node_type = node.get("type")
        if node_type == "router":
            next_id = _run_router(flow, node, event)
            if next_id is None:
                break
            current_id = next_id
            continue
        if node_type == "send_message":
            actions, next_id = _run_send_message(flow, node, {"slots": slots})
            all_actions.extend(actions)
            for a in actions:
                if isinstance(a, SetSlots):
                    slots.update(a.slots)
                if isinstance(a, ClearSlots):
                    for k in a.keys:
                        slots.pop(k, None)
                if isinstance(a, Transition):
                    current_id = a.node_id
                    break
            else:
                if next_id:
                    current_id = next_id
            break
        if node_type == "call_service":
            actions, next_id = _run_call_service(flow, node, {"slots": slots}, event, service)
            all_actions.extend(actions)
            for a in actions:
                if isinstance(a, SetSlots):
                    slots.update(a.slots)
                if isinstance(a, ClearSlots):
                    for k in a.keys:
                        slots.pop(k, None)
                if isinstance(a, Transition):
                    current_id = a.node_id
                    break
            break
        break
    new_state = {"current_node_id": current_id, "slots": slots}
    return all_actions, new_state
