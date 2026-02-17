# Neo4j graph model (Bimoi)

All data is scoped by `user_id`. Identity is handled by **Account** and **ChannelLink**; contacts use **Person** nodes with context stored on **KNOWS** relationships.

## Identity (Account + ChannelLink)

One canonical account per user; channels (Telegram, WhatsApp, web) resolve to that account.

- **Account** — `(a:Account { id: uuid, created_at: iso, name?: string, bio?: string })`. One per user; created when they first use a channel. Optional `name` (e.g. from Telegram) and `bio` (required at onboarding; short user-provided bio). Both are validated in the domain ([AccountProfile](src/bimoi/domain/entities.py)) with max lengths (name 500, bio 2000 chars).
- **ChannelLink** — `(c:ChannelLink { channel: "telegram"|"whatsapp"|..., external_id: string })` with unique constraint on `(channel, external_id)`. `(c)-[:BELONGS_TO]->(a:Account)`.
- Lookup: `(channel, external_id)` → Account id. First use creates Account and link; later uses return the same id. `get_or_create_user_id(driver, channel, external_id, initial_name=...)` returns `(user_id, is_new_account)`. See [src/bimoi/infrastructure/identity.py](../src/bimoi/infrastructure/identity.py). Constraint is created at backend/bot startup via `ensure_channel_link_constraint(driver)`.

Extensibility: add new channel names (e.g. `"whatsapp"`, `"web"`) at call sites; no schema change.

## Contacts (Person + KNOWS with context)

- **Person** — Single label for everyone in the contact graph.
  - **Account owner (registered):** `Person { id: user_id, registered: true }`. `user_id` is the Account id (UUID for new users). Created with `MERGE` when the first contact is added.
  - **Contact (not registered):** `Person { id, name, phone_number?, external_id?, created_at, registered: false }`. Created when the user adds a contact.

- **KNOWS relationship** — Connects owner to contact with context properties:
  - `context_id` (UUID)
  - `context_description` (text)
  - `context_created_at` (ISO timestamp)
  - `context_updated_at` (ISO timestamp)

**Graph structure:**
```cypher
(owner:Person {id: user_id, registered: true})
  -[:KNOWS {context_id, context_description, context_created_at, context_updated_at}]->
(contact:Person {registered: false})
```

**Why context on relationships?**
Context describes the relationship between owner and contact, not the contact itself. This is more efficient (single query for contact + context) and semantically correct.

## Scoping

- **add:** `MERGE` the owner `Person { id: user_id, registered: true }`, then `CREATE` the contact Person with `registered: false` and a `KNOWS` relationship with context properties.
- **get_by_id, list_all, find_duplicate:** All queries match from the owner via `KNOWS` relationship and restrict to `p.registered = false` so only contacts (not the account node) are returned.
- **append_context:** Updates the `context_description` and `context_updated_at` properties on the `KNOWS` relationship.

## Implementation

- [src/bimoi/infrastructure/identity.py](../src/bimoi/infrastructure/identity.py) — `get_or_create_user_id(driver, channel, external_id, initial_name=...)` → `(user_id, is_new_account)`, `ensure_channel_link_constraint(driver)`, `update_account_profile(driver, user_id, name=..., bio=...)` (validates length), `get_account_profile(driver, user_id)` → `AccountProfile | None`. Domain type: [AccountProfile](src/bimoi/domain/entities.py) (name, bio; optional; max lengths).
- [src/bimoi/infrastructure/persistence/neo4j_repository.py](../src/bimoi/infrastructure/persistence/neo4j_repository.py) — `Neo4jContactRepository(driver, user_id=...)`.
- Integration tests: [tests/test_neo4j_repository.py](../tests/test_neo4j_repository.py) (contacts), [tests/test_identity.py](../tests/test_identity.py) (identity).
- Optional migrations:
  - [scripts/migrate_telegram_ids_to_accounts.py](../scripts/migrate_telegram_ids_to_accounts.py) — Migrate pre-Account Telegram owners.
  - [scripts/migrate_context_to_relationships.py](../scripts/migrate_context_to_relationships.py) — Migrate RelationshipContext nodes to KNOWS properties.
