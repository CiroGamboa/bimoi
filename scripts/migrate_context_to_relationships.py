#!/usr/bin/env python3
"""One-off migration: move RelationshipContext nodes to KNOWS relationship
properties.

Finds all (Person)-[:HAS_CONTEXT]->(RelationshipContext) patterns and copies
the context properties to the KNOWS relationship between owner and contact.
After this, the new repository code will work with the updated schema. Run
from repo root with .env (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD). Idempotent.
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

_FIND_CONTEXTS = """
MATCH (owner:Person {registered: true})-[:KNOWS]->
      (contact:Person {registered: false})-[:HAS_CONTEXT]->
      (ctx:RelationshipContext)
RETURN owner.id AS owner_id, contact.id AS contact_id,
       ctx.id AS ctx_id, ctx.description AS ctx_description,
       ctx.created_at AS ctx_created_at
"""

_MIGRATE_CONTEXT_TO_RELATIONSHIP = """
MATCH (owner:Person {id: $owner_id})-[k:KNOWS]->
      (contact:Person {id: $contact_id})
SET k.context_id = $ctx_id,
    k.context_description = $ctx_description,
    k.context_created_at = $ctx_created_at,
    k.context_updated_at = $ctx_created_at
RETURN 1 AS ok
"""

_CLEANUP_OLD_SCHEMA = """
MATCH (contact:Person)-[r:HAS_CONTEXT]->(ctx:RelationshipContext)
DELETE r, ctx
"""


def main() -> int:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687").strip()
    user = os.environ.get("NEO4J_USER", "neo4j").strip()
    password = os.environ.get("NEO4J_PASSWORD", "password").strip()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        # Find all contexts to migrate
        with driver.session() as session:
            result = session.run(_FIND_CONTEXTS)
            contexts = [
                {
                    "owner_id": r["owner_id"],
                    "contact_id": r["contact_id"],
                    "ctx_id": r["ctx_id"],
                    "ctx_description": r["ctx_description"],
                    "ctx_created_at": r["ctx_created_at"],
                }
                for r in result
            ]

        if not contexts:
            print("No contexts to migrate. Schema is already up to date.")
            return 0

        print(f"Found {len(contexts)} context(s) to migrate.")

        # Migrate each context to KNOWS relationship
        migrated = 0
        with driver.session() as session:
            for ctx in contexts:
                result = session.run(
                    _MIGRATE_CONTEXT_TO_RELATIONSHIP,
                    owner_id=ctx["owner_id"],
                    contact_id=ctx["contact_id"],
                    ctx_id=ctx["ctx_id"],
                    ctx_description=ctx["ctx_description"],
                    ctx_created_at=ctx["ctx_created_at"],
                )
                if result.single():
                    migrated += 1

        print(f"Successfully migrated {migrated} context(s) to KNOWS " "relationships.")

        # Clean up old schema (RelationshipContext nodes and HAS_CONTEXT)
        with driver.session() as session:
            result = session.run(_CLEANUP_OLD_SCHEMA)
            summary = result.consume()
            deleted_rels = summary.counters.relationships_deleted
            deleted_nodes = summary.counters.nodes_deleted
            print(
                f"Cleaned up old schema: deleted {deleted_rels} "
                f"HAS_CONTEXT relationships and {deleted_nodes} "
                "RelationshipContext nodes."
            )

        print("Migration complete!")
        return 0
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        return 1
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
