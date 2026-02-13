# Neo4j graph model (Bimoi)

All data is scoped by `user_id`. Identity is handled by **Account** and **ChannelLink**; contacts use **Person** and **RelationshipContext**.

## Identity (Account + ChannelLink)

One canonical account per user; channels (Telegram, WhatsApp, web) resolve to that account.

- **Account** — `(a:Account { id: uuid, created_at: iso })`. One per user; created when they first use a channel.
- **ChannelLink** — `(c:ChannelLink { channel: "telegram"|"whatsapp"|..., external_id: string })` with unique constraint on `(channel, external_id)`. `(c)-[:BELONGS_TO]->(a:Account)`.
- Lookup: `(channel, external_id)` → Account id. First use creates Account and link; later uses return the same id. See [src/bimoi/infrastructure/identity.py](../src/bimoi/infrastructure/identity.py). Constraint is created at backend/bot startup via `ensure_channel_link_constraint(driver)`.

Extensibility: add new channel names (e.g. `"whatsapp"`, `"web"`) at call sites; no schema change.

## Contacts (Person + RelationshipContext)

- **Person** — Single label for everyone in the contact graph.
  - **Account owner (registered):** `Person { id: user_id, registered: true }`. `user_id` is the Account id (UUID for new users). Created with `MERGE` when the first contact is added.
  - **Contact (not registered):** `Person { id, name, phone_number?, external_id?, created_at, registered: false }`. Created when the user adds a contact.
- **RelationshipContext** — `id`, `description`, `created_at`. One per contact via `(Person)-[:HAS_CONTEXT]->(RelationshipContext)`.

**Edges:**

- `(owner:Person {registered: true})-[:KNOWS]->(contact:Person {registered: false})` — Contacts are linked to the account owner.
- `(contact:Person)-[:HAS_CONTEXT]->(RelationshipContext)` — One-to-one per contact.

## Scoping

- **add:** `MERGE` the owner `Person { id: user_id, registered: true }`, then `CREATE` the contact Person with `registered: false`, the RelationshipContext, and the edges.
- **get_by_id, list_all, find_duplicate:** All queries match from the owner and restrict to `p.registered = false` so only contacts (not the account node) are returned.

## Implementation

- [src/bimoi/infrastructure/identity.py](../src/bimoi/infrastructure/identity.py) — `get_or_create_user_id(driver, channel, external_id)`, `ensure_channel_link_constraint(driver)`.
- [src/bimoi/infrastructure/persistence/neo4j_repository.py](../src/bimoi/infrastructure/persistence/neo4j_repository.py) — `Neo4jContactRepository(driver, user_id=...)`.
- Integration tests: [tests/test_neo4j_repository.py](../tests/test_neo4j_repository.py) (contacts), [tests/test_identity.py](../tests/test_identity.py) (identity).
- Optional migration for existing Telegram owners: [scripts/migrate_telegram_ids_to_accounts.py](../scripts/migrate_telegram_ids_to_accounts.py).
