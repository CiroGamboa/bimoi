# Neo4j graph model (Bimoi)

All data is scoped by `user_id`. **One node type: Person.** The current user is a **Person** with account-like properties (`registered: true`); contacts are **Person** nodes with `registered: false`. Same shape; profile fields (name, bio) on the owner may later move to a relational database.

## Identity (Person owner + ChannelLink)

One canonical “owner” Person per user; channels (Telegram, WhatsApp, web) resolve to that Person.

- **Person (owner)** — `(p:Person { id: uuid, created_at: iso, registered: true, name?: string, bio?: string })`. **Single node per user**: identity, profile (name, bio), and owner of the user's contact graph. Created when they first use a channel. Optional `name` and `bio` (required at onboarding). Validated in the domain ([AccountProfile](src/bimoi/domain/entities.py)) with max lengths (name 500, bio 2000 chars).
- **ChannelLink** — `(c:ChannelLink { channel: "telegram"|"whatsapp"|..., external_id: string })` with unique constraint on `(channel, external_id)`. `(c)-[:BELONGS_TO]->(p:Person)` where `p.registered = true`.
- Lookup: `(channel, external_id)` → owner Person id. First use creates that Person and link; later uses return the same id. `get_or_create_user_id(driver, channel, external_id, initial_name=...)` returns `(user_id, is_new_account)`. See [src/bimoi/infrastructure/identity.py](../src/bimoi/infrastructure/identity.py). Constraint is created at backend/bot startup via `ensure_channel_link_constraint(driver)`.

Extensibility: add new channel names (e.g. `"whatsapp"`, `"web"`) at call sites; no schema change.

## Contacts (Person + KNOWS with context)

- **Person (owner)** is the owner of the contact graph: `(Person {id: user_id, registered: true})-[:KNOWS]->(Person)` (target may be `registered: false` or `registered: true`).
- **Person (contact)** — `Person { id, name, phone_number?, external_id?, created_at, registered: false }`. Created when the user adds a contact who is not on the app. Same label as owner; distinguished by `registered: false`.
- **Reusing existing users:** If the contact is already on the app (has a Person node from sign-up, linked via ChannelLink), we do **not** create a second Person. We create only `(owner)-[:KNOWS {context}]->(existing Person)`. Resolved via `get_person_id_by_channel_external_id(driver, channel, external_id)` (read-only). The same Person node can be the target of KNOWS from multiple owners (e.g. Bob is an app user; Alice and Carol both have Bob as a contact → one Bob node, two KNOWS edges).

- **KNOWS relationship** — Connects owner Person to contact Person with context properties:
  - `context_id` (UUID)
  - `context_description` (text)
  - `context_created_at` (ISO timestamp)
  - `context_updated_at` (ISO timestamp)

**Graph structure:**
```cypher
(owner:Person {id: user_id, registered: true})
  -[:KNOWS {context_id, context_description, context_created_at, context_updated_at}]->
(contact:Person)
```
Contact may have `registered: false` (new contact) or `registered: true` (existing app user).

**Why context on relationships?**
Context describes the relationship between owner and contact, not the contact itself. One Person per user (owner); single query for contact + context.

## Scoping

- **add:** `MERGE` the `Person { id: user_id, registered: true }`. If the contact is already on the app (resolved via channel + external_id), create only `(owner)-[:KNOWS]->(existing Person)`. Otherwise `CREATE` a new Person with `registered: false` and `KNOWS` with context properties.
- **get_by_id, list_all, find_duplicate:** All queries match from the owner Person via `KNOWS`; targets may be any Person (contacts or app users). `find_duplicate` matches by phone or external_id (including Person linked via ChannelLink when no `external_id` on node).
- **append_context:** Updates the `context_description` and `context_updated_at` on the `KNOWS` relationship (target may be any Person).

## Implementation

- [src/bimoi/infrastructure/identity.py](../src/bimoi/infrastructure/identity.py) — `get_or_create_user_id(driver, channel, external_id, initial_name=...)` → `(user_id, is_new_account)`, `ensure_channel_link_constraint(driver)`, `get_person_id_by_channel_external_id(driver, channel, external_id)` → `str | None` (read-only; use to detect “already on the app” and reuse Person node), `update_account_profile(driver, user_id, name=..., bio=...)` (validates length), `get_account_profile(driver, user_id)` → `AccountProfile | None`. Domain type: [AccountProfile](src/bimoi/domain/entities.py) (name, bio; optional; max lengths). Owner is stored as a Person node with `registered: true`.
- [src/bimoi/infrastructure/persistence/neo4j_repository.py](../src/bimoi/infrastructure/persistence/neo4j_repository.py) — `Neo4jContactRepository(driver, user_id=...)`. Owner: `Person { id: user_id, registered: true }`.
- Integration tests: [tests/test_neo4j_repository.py](../tests/test_neo4j_repository.py) (contacts), [tests/test_identity.py](../tests/test_identity.py) (identity).
- Optional migrations:
  - If you have existing data with the old model (owner `Account`), create a Person with the same `id`, `registered: true`, copy name/bio/created_at from Account, move KNOWS from Account to that Person, then delete the Account nodes.
  - [scripts/migrate_context_to_relationships.py](../scripts/migrate_context_to_relationships.py) — Migrate RelationshipContext nodes to KNOWS properties.
