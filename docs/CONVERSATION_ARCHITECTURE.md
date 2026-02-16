# Conversation architecture: fixed workflows and semantic layer

This document describes how Bimoi’s conversation flow is structured today and how it is intended to evolve when adding open-ended, LLM-powered queries (recommendations, semantic search) alongside the existing fixed workflows.

## Current design: one layer (fixed workflows)

Today the Telegram bot is driven by:

- **Machine definition:** [flows/telegram_machine.json](../flows/telegram_machine.json) — standard XState-style JSON (states, `on` events, string targets). Same format can be used in Stately Studio or JS XState.
- **Interpreter:** [src/api/xstate_machine.py](../src/api/xstate_machine.py) — uses **xstate-python** to run the machine (state + event → next state).
- **Adapter:** [src/api/flow_adapter.py](../src/api/flow_adapter.py) — maps Telegram updates to events, runs effects (send message, call ContactService), and drives the machine until a “waiting” state (idle, awaiting_context, etc.).
- **Copy:** [flows/telegram.yaml](../flows/telegram.yaml) — `messages` and legacy YAML used for text and keyboards.

All user actions are interpreted as **commands or structured actions** (e.g. /start, /list, shared contact, callback buttons). Unrecognized text is treated as “unsupported” and the flow stays in a known state.

## Future: two layers (fixed workflows + semantic)

The product direction includes both:

1. **Fixed workflows** — Add contact, submit context, list, structured search, (later) define search strategies. These stay **deterministic** and are best implemented as state machines (XState).
2. **Open-ended / semantic** — Queries like “recommend people who’ve been to Thailand”, “I need a good family psychologist”, “show me people from AIESEC”. These are **intent + retrieval/recommendation**, not a fixed sequence, and are best handled by **LLM + data** (and optionally an agent graph like LangGraph later).

So the architecture should support **both**:

- **Layer 1 – Fixed workflows (XState)**
  Same as today: state machine for add-contact, list, search, etc. Predictable and testable.

- **Layer 2 – Semantic / recommendations**
  Free-form text that doesn’t match a command or workflow is routed to a **semantic handler**: LLM (and/or embeddings) over contacts and relationship context to produce recommendations or filtered lists. Responses can reuse the same “list of people” or message shapes the bot already has.

## How the two layers fit together

- **Routing at entry:** When the user sends a message (or shares a contact):
  - **Workflow path:** Known command, shared contact, or callback from a button → run the **existing XState flow** (idle → welcome, receive_contact, do_list, etc.).
  - **Semantic path:** Everything else (free-form text) → send to the **semantic handler** (LLM/retrieval over contacts and context). Output can be the same kind of list or message the bot already uses (e.g. `SendContactList` or a “recommendations” response).

- **Fixed workflows** stay as they are: add contact, list, search, add context, and (later) “define search strategy” wizards.

- **Semantic handler** (to be implemented):
  - Input: free-form text.
  - Use LLM (and optionally embeddings over relationship context) to interpret intent and select relevant contacts (e.g. by topic, org, experience).
  - Output: reuse existing “list of people” or message types so the client experience is consistent.
  - If this later becomes multi-step (refinement, tool use, follow-up questions), that subgraph can be implemented with something like **LangGraph** while add-contact and other wizards remain in XState.

## Design choice: XState vs LangGraph

- **XState** is the right tool for “how we add a contact”, “how we run structured search”, “how we define a search strategy” — human-defined, step-by-step flows.
- **LLM + (optional) LangGraph** is the right tool for “answer open-ended questions and recommendations from the same data” — model-driven, possibly multi-step.

We do **not** replace the fixed flow with “everything through an LLM”. We **add** a semantic path next to it and route at the entry point.

## Preparing for the semantic layer

To add the semantic path later without refactoring the flow:

1. **Single “escape hatch” in the machine:**
   From `idle` (or a dedicated state), when the message is “not a command and not a contact”, emit an event such as `TEXT_FREE_FORM` and **route to the semantic handler** instead of “unsupported”. The handler can start as a stub (“Recommendations coming soon”) and later become LLM + retrieval or a LangGraph agent.

2. **Keep the same response types:**
   Semantic results (recommendations, filtered lists) should use the same actions the adapter already supports (e.g. `SendContactList`, `SendMessage`) so the Telegram webhook and clients stay unchanged.

3. **Optional:**
   Document in the machine or adapter which events lead to the semantic path so future changes (e.g. adding LangGraph) are easy to locate.

## Summary

| Layer            | Purpose                          | Technology              |
|-----------------|-----------------------------------|-------------------------|
| Fixed workflows | Add contact, list, search, wizards | XState (xstate-python)  |
| Semantic        | Recommendations, free-form queries | LLM + retrieval (later LangGraph) |

The conversation flow uses **xstate-python** and [flows/telegram_machine.json](../flows/telegram_machine.json). Messages and keyboards live in [flows/telegram.yaml](../flows/telegram.yaml). The webhook and flow adapter are in [src/api/](../src/api/).

**Install note:** The `api` extra depends on xstate-python, which requires Js2Py 0.71. If your pip index doesn’t have that version (e.g. a private index only has 0.74), install with PyPI as an extra index: `pip install --extra-index-url https://pypi.org/simple -e ".[dev,api]"`.
