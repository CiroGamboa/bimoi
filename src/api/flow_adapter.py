"""
Adapter: map events to XState events and state/transition to effects.

Uses standard XState machine (xstate_machine); all Bimoi/Telegram behavior
lives here (messages, keyboards, ContactService calls).
"""

from dataclasses import dataclass
from typing import Any

from api.flow_loader import get_flow
from api.xstate_machine import get_machine, transition
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


WAITING_STATES = frozenset({"idle", "awaiting_context", "awaiting_search", "awaiting_add_context"})


def event_to_xstate(event: dict) -> str | None:
    """Map adapter event (type, subtype) to XState event string."""
    etype = event.get("type")
    subtype = event.get("subtype")
    if etype == "contact_shared":
        return "CONTACT_SHARED"
    if etype == "callback":
        return {
            "cmd_list": "CALLBACK_LIST",
            "cmd_search": "CALLBACK_SEARCH",
            "cmd_add": "CALLBACK_ADD",
            "addmore": "CALLBACK_ADDMORE",
            "addctx_done": "CALLBACK_ADDCTX_DONE",
            "person_id": "CALLBACK_PERSON_ID",
        }.get(subtype, None)
    if etype == "text":
        return {
            "command_start": "TEXT_COMMAND_START",
            "command_help": "TEXT_COMMAND_HELP",
            "command_list": "TEXT_COMMAND_LIST",
            "command_search": "TEXT_COMMAND_SEARCH",
            "command_add_contact": "TEXT_COMMAND_ADD_CONTACT",
            "search_keyword": "TEXT_SEARCH_KEYWORD",
            "add_context_text": "TEXT_ADD_CONTEXT",
            "pending_context_text": "TEXT_PENDING_CONTEXT",
            "unsupported": "TEXT_UNSUPPORTED",
        }.get(subtype, None)
    return None


def _format_message(messages: dict, message_id: str, template_vars: dict) -> str:
    text = messages.get(message_id) or message_id
    for k, v in template_vars.items():
        text = text.replace("{" + k + "}", str(v) if v is not None else "")
    return text


def _run_effect(
    state_value: str,
    event: dict,
    context: dict,
    service: Any,
    messages: dict,
) -> tuple[list, str | None]:
    """
    Run effect for state_value. Return (actions, outcome_event).
    outcome_event is the XState event to send next (e.g. DONE, PENDING).
    """
    actions: list = []
    payload = event.get("payload") or {}
    slots = context
    template_vars = {"name": slots.get("contact_name")}

    if state_value == "welcome":
        text = _format_message(messages, "welcome", template_vars)
        actions.append(SendMessage(text=text, keyboard="welcome"))
        return actions, "DONE"

    if state_value == "unsupported_msg":
        text = messages.get("unsupported", "Unsupported.")
        actions.append(SendMessage(text=text, keyboard="main"))
        return actions, "DONE"

    if state_value == "receive_contact":
        card = ContactCardData(
            name=(payload.get("name") or "").strip(),
            phone_number=payload.get("phone_number"),
            telegram_user_id=payload.get("telegram_user_id"),
        )
        result = service.receive_contact_card(card)
        if isinstance(result, PendingContact):
            actions.append(SetSlots(slots={"pending_id": result.pending_id}))
            text = _format_message(messages, "awaiting_context_prompt", {})
            actions.append(SendMessage(text=text))
            return actions, "PENDING"
        if isinstance(result, Duplicate):
            actions.append(
                SetSlots(slots={"person_id": result.person_id, "contact_name": result.name})
            )
            text = _format_message(
                messages, "duplicate_offer_add_context", {"name": result.name}
            )
            actions.append(SendMessage(text=text))
            return actions, "DUPLICATE"
        if isinstance(result, Invalid):
            actions.append(SendMessage(text=result.reason))
            return actions, "INVALID"
        return actions, "INVALID"

    if state_value == "do_submit_context":
        pending_id = slots.get("pending_id") or ""
        text = payload.get("text") or ""
        result = service.submit_context(pending_id, text)
        actions.append(ClearSlots(keys=["pending_id"]))
        if isinstance(result, ContactCreated):
            actions.append(
                SetSlots(slots={"person_id": result.person_id, "contact_name": result.name})
            )
            msg = _format_message(messages, "contact_created", {"name": result.name})
            actions.append(SendMessage(text=msg, keyboard="add_more_or_done"))
            return actions, "CREATED"
        text = messages.get("pending_lost", "")
        actions.append(SendMessage(text=text))
        return actions, "PENDING_NOT_FOUND"

    if state_value == "contact_created":
        return actions, "DONE"

    if state_value == "do_list":
        summaries = service.list_contacts()
        if not summaries:
            text = messages.get("empty_list", "")
            actions.append(SendMessage(text=text))
            return actions, "EMPTY"
        actions.append(SendContactList(summaries=summaries))
        return actions, "HAS_RESULTS"

    if state_value == "prompt_search":
        text = messages.get("search_prompt", "")
        actions.append(SendMessage(text=text))
        actions.append(SetSlots(slots={"search_pending": True}))
        return actions, "DONE"

    if state_value == "do_search":
        keyword = payload.get("text") or ""
        summaries = service.search_contacts(keyword)
        actions.append(ClearSlots(keys=["search_pending"]))
        if not summaries:
            text = messages.get("no_match", "")
            actions.append(SendMessage(text=text))
            return actions, "EMPTY"
        actions.append(SendContactList(summaries=summaries))
        return actions, "HAS_RESULTS"

    if state_value == "prompt_add_contact":
        text = messages.get("add_contact_howto", "")
        actions.append(SendMessage(text=text, keyboard="main"))
        return actions, "DONE"

    if state_value == "prompt_add_context_for_contact":
        person_id = payload.get("person_id") or ""
        contact = service.get_contact(person_id) if person_id else None
        if contact:
            actions.append(
                SetSlots(slots={"person_id": person_id, "contact_name": contact.name})
            )
            text = _format_message(
                messages, "add_context_button_prompt", {"name": contact.name}
            )
            actions.append(SendMessage(text=text))
            return actions, "FOUND"
        text = messages.get("add_context_not_found", "")
        actions.append(SendMessage(text=text))
        return actions, "NOT_FOUND"

    if state_value == "prompt_add_more_context":
        person_id = payload.get("person_id") or ""
        contact = service.get_contact(person_id) if person_id else None
        if contact:
            actions.append(
                SetSlots(slots={"person_id": person_id, "contact_name": contact.name})
            )
            text = _format_message(
                messages, "add_more_context_again", {"name": contact.name}
            )
            actions.append(SendMessage(text=text))
            return actions, "FOUND"
        text = messages.get("add_context_not_found", "")
        actions.append(SendMessage(text=text))
        return actions, "NOT_FOUND"

    if state_value == "do_add_context":
        person_id = slots.get("person_id") or ""
        text = payload.get("text") or ""
        result = service.add_context(person_id, text)
        if isinstance(result, AddContextSuccess):
            text = messages.get("add_more_or_done", "")
            actions.append(SendMessage(text=text, keyboard="add_more_or_done"))
            return actions, "SUCCESS"
        if isinstance(result, AddContextNotFound):
            text = messages.get("add_context_not_found", "")
            actions.append(SendMessage(text=text))
            return actions, "NOT_FOUND"
        if isinstance(result, AddContextInvalid):
            text = messages.get("add_context_empty", "")
            actions.append(SendMessage(text=text))
            return actions, "INVALID"
        return actions, "INVALID"

    if state_value == "add_context_done":
        actions.append(ClearSlots(keys=["person_id", "contact_name"]))
        text = messages.get("add_context_done", "")
        actions.append(SendMessage(text=text))
        return actions, "DONE"

    if state_value == "send_contact_first":
        text = messages.get("send_contact_first", "")
        actions.append(SendMessage(text=text, keyboard="main"))
        return actions, "DONE"

    return actions, None


def run_xstate_flow(
    state_value: str,
    event: dict,
    context: dict,
    service: Any,
    machine: dict | None = None,
    flow: dict | None = None,
) -> tuple[list, str, dict]:
    """
    Run one step: transition with event, run effects until we hit a waiting state.
    Returns (actions, new_state_value, new_context).
    """
    if machine is None:
        machine = get_machine()
    if flow is None:
        flow = get_flow()
    messages = flow.get("messages") or {}
    slots = dict(context or {})
    all_actions: list = []
    current = state_value or machine.get("initial", "idle")
    user_event = event
    max_steps = 50
    steps = 0
    while steps < max_steps:
        steps += 1
        if steps == 1:
            xevent = event_to_xstate(user_event)
            if xevent is None:
                break
            next_state = transition(machine, current, xevent)
        else:
            next_state = transition(machine, current, xevent)
        if next_state is None:
            break
        current = next_state
        if current in WAITING_STATES:
            break
        effect_actions, outcome = _run_effect(
            current, user_event, slots, service, messages
        )
        all_actions.extend(effect_actions)
        for a in effect_actions:
            if isinstance(a, SetSlots):
                slots.update(a.slots)
            if isinstance(a, ClearSlots):
                for k in a.keys:
                    slots.pop(k, None)
        if outcome is None:
            break
        xevent = outcome
    return all_actions, current, slots
