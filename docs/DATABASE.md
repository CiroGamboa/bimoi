# Neo4j graph model (Bimoi)

All data is scoped by `user_id`. Today there is a single implicit user (`user_id="default"`); when you add authentication, pass the authenticated user id into the repository.

## Graph structure

- **User** — One node per (future) account. Properties: `id` (string). Single user today = one User with `id = "default"`.
- **Person** — A contact known by that user. Properties: `id`, `name`, `phone_number` (optional), `external_id` (optional), `created_at`.
- **RelationshipContext** — The user’s free-text description of why the person matters. Properties: `id`, `description`, `created_at`.

**Edges:**

- `(User)-[:KNOWS]->(Person)` — Each Person is owned by exactly one User.
- `(Person)-[:HAS_CONTEXT]->(RelationshipContext)` — One-to-one; creating a contact creates Person + RelationshipContext + both edges in one transaction.

## Scoping

- **add:** `MERGE` the User by `user_id`, then create Person and RelationshipContext and link them to the User.
- **get_by_id, list_all, find_duplicate:** All queries match `(u:User {id: $user_id})-[:KNOWS]->(p:Person)-[:HAS_CONTEXT]->(c:RelationshipContext)` so each user only sees their own contacts. Duplicate check (same phone or external_id) is per user.

## Implementation

- [src/bimoi/infrastructure/persistence/neo4j_repository.py](../src/bimoi/infrastructure/persistence/neo4j_repository.py) — `Neo4jContactRepository(driver, user_id="default")`.
- Integration tests in [tests/test_neo4j_repository.py](../tests/test_neo4j_repository.py) use testcontainers (short-lived Neo4j) and cover add, get_by_id, list_all, find_duplicate, and multi-user isolation.
