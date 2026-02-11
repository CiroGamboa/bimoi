# Neo4j graph model (Bimoi)

All data is scoped by `user_id`. One node type (**Person**) is used for both the account owner and their contacts; an attribute **registered** distinguishes them.

## Graph structure

- **Person** — Single label for everyone in the graph.
  - **Account owner (registered):** `Person { id: user_id, registered: true }`. One per account; created with `MERGE` when the first contact is added.
  - **Contact (not registered):** `Person { id, name, phone_number?, external_id?, created_at, registered: false }`. Created when the user adds a contact.
- **RelationshipContext** — Unchanged: `id`, `description`, `created_at`. One per contact via `(Person)-[:HAS_CONTEXT]->(RelationshipContext)`.

**Edges:**

- `(owner:Person {registered: true})-[:KNOWS]->(contact:Person {registered: false})` — Contacts are linked to the account owner.
- `(contact:Person)-[:HAS_CONTEXT]->(RelationshipContext)` — One-to-one per contact.

## Scoping

- **add:** `MERGE` the owner `Person { id: user_id, registered: true }`, then `CREATE` the contact Person with `registered: false`, the RelationshipContext, and the edges.
- **get_by_id, list_all, find_duplicate:** All queries match from the owner and restrict to `p.registered = false` so only contacts (not the account node) are returned.

## Implementation

- [src/bimoi/infrastructure/persistence/neo4j_repository.py](../src/bimoi/infrastructure/persistence/neo4j_repository.py) — `Neo4jContactRepository(driver, user_id="default")`.
- Integration tests in [tests/test_neo4j_repository.py](../tests/test_neo4j_repository.py) use testcontainers and cover add, get_by_id, list_all, find_duplicate, and multi-user isolation.
