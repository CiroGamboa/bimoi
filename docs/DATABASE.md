# Neo4j graph model (Bimoi)

All data is scoped by `user_id`. **One node type: Person.** The current user is a **Person** with account-like properties (`registered: true`); contacts are **Person** nodes with `registered: false`. Same shape; profile fields (name, bio, phone_number) on the owner may later move to a relational database.

## Identity (Person.telegram_id)

One canonical “owner” Person per user. Telegram user id is stored on the Person node as `telegram_id` (no separate ChannelLink node).

- **Person (owner)** — `(p:Person { id: uuid, telegram_id: string, created_at: iso, registered: true, name?: string, bio?: string, phone_number?: string })`. **Single node per user**: identity, profile, and owner of the user's contact graph. Created when they first use the bot. Unique constraint on `Person.telegram_id` so one Telegram id maps to one Person. Optional `name`, `bio`, `phone_number` (validated in domain [AccountProfile](src/bimoi/domain/entities.py)).
- Lookup: `(channel, external_id)` → for Telegram, `MATCH (p:Person { telegram_id: $telegram_id })`. First use creates that Person with `telegram_id`; later uses return the same id. If the Person was pre-created as a contact (when someone added them), we set `registered = true` and return that node. `get_or_create_user_id(driver, channel, external_id, initial_name=...)` returns `(user_id, is_new_account)`. Constraint is created at backend/bot startup via `ensure_identity_constraint(driver)`.

Extensibility: for other channels (e.g. WhatsApp) add a property like `whatsapp_id` on Person and extend lookup/create logic.

## Contacts (Person + KNOWS with context)

- **Person (owner)** is the owner of the contact graph: `(Person {id: user_id, registered: true})-[:KNOWS]->(Person)` (target may be `registered: false` or `registered: true`).
- **Person (contact)** — `Person { id, name, phone_number?, external_id?, telegram_id?, created_at, registered: false }`. Created when the user adds a contact who is not on the app. We set `telegram_id` when the contact card has a Telegram user id so that when they sign up we reuse this node (one Person per human).
- **Reusing existing users:** If the contact is already on the app (Person with matching `telegram_id` and `registered: true`), we create only `(owner)-[:KNOWS {context}]->(existing Person)`. Resolved via `get_person_id_by_channel_external_id(driver, channel, external_id)`. The same Person node can be the target of KNOWS from multiple owners.

- **KNOWS relationship** — Connects owner Person to contact Person with context properties:
  - `context_id` (UUID)
  - `context_description` (text)
  - `context_created_at` (ISO timestamp)
  - `context_updated_at` (ISO timestamp)

**Graph structure:**
```cypher
(owner:Person {id: user_id, registered: true})
  -[:KNOWS {context_id, context_description, context_created_at, context_updated_at}]->(contact:Person)
```
Contact may have `registered: false` (new contact) or `registered: true` (existing app user).

**Why context on relationships?**
Context describes the relationship between owner and contact, not the contact itself. One Person per user (owner); single query for contact + context.

## Scoping

- **add:** `MERGE` the `Person { id: user_id, registered: true }`. If the contact is already on the app (resolved via `telegram_id`), create only `(owner)-[:KNOWS]->(existing Person)`. Otherwise `CREATE` a new Person with `registered: false`, `telegram_id` when available, and `KNOWS` with context properties.
- **get_by_id, list_all, find_duplicate:** All queries match from the owner Person via `KNOWS`; targets may be any Person. `find_duplicate` matches by phone or by `telegram_id`/`external_id` on the Person node.
- **append_context:** Updates the `context_description` and `context_updated_at` on the `KNOWS` relationship (target may be any Person).

## Implementation

- [src/bimoi/infrastructure/identity.py](../src/bimoi/infrastructure/identity.py) — `get_or_create_user_id(driver, channel, external_id, initial_name=...)` → `(user_id, is_new_account)`, `ensure_identity_constraint(driver)` (unique on `Person.telegram_id`), `get_person_id_by_channel_external_id(driver, channel, external_id)` → `str | None`, `update_account_profile(driver, user_id, name=..., bio=..., phone_number=...)`, `get_account_profile(driver, user_id)` → `AccountProfile | None`. Owner is stored as a Person node with `telegram_id` and `registered: true`.
- [src/bimoi/infrastructure/persistence/neo4j_repository.py](../src/bimoi/infrastructure/persistence/neo4j_repository.py) — `Neo4jContactRepository(driver, user_id=...)`. Owner: `Person { id: user_id, registered: true }`. New contacts get `telegram_id` set when available so sign-up reuses the node.
- Integration tests: [tests/test_neo4j_repository.py](../tests/test_neo4j_repository.py), [tests/test_identity.py](../tests/test_identity.py).
- [scripts/migrate_context_to_relationships.py](../scripts/migrate_context_to_relationships.py) — Migrate RelationshipContext nodes to KNOWS properties (if needed).
