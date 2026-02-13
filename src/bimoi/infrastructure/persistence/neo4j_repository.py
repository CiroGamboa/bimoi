"""Neo4j implementation of ContactRepository.
Graph: single Person label with registered flag.
(owner:Person {id: user_id, registered: true})-[:KNOWS]->(contact:Person {registered: false})-[:HAS_CONTEXT]->(RelationshipContext).
"""

from datetime import datetime

from bimoi.application.dto import ContactCardData
from bimoi.domain import Person, RelationshipContext


def _datetime_to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _iso_to_datetime(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _normalize_telegram_id(value: int | str | None) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


class Neo4jContactRepository:
    """Stores contact aggregates in Neo4j, scoped by user_id.
    Single Person label: owner has registered: true, contacts have registered: false.
    """

    def __init__(self, driver: object, user_id: str = "default") -> None:
        self._driver = driver
        self._user_id = user_id

    def add(self, person: Person) -> None:
        ctx = person.relationship_context
        with self._driver.session() as session:
            session.run(
                """
                MERGE (owner:Person {id: $user_id, registered: true})
                CREATE (p:Person {
                    id: $person_id,
                    name: $name,
                    phone_number: $phone_number,
                    external_id: $external_id,
                    created_at: $person_created_at,
                    registered: false
                })
                CREATE (c:RelationshipContext {
                    id: $ctx_id,
                    description: $description,
                    created_at: $ctx_created_at
                })
                CREATE (owner)-[:KNOWS]->(p)
                CREATE (p)-[:HAS_CONTEXT]->(c)
                """,
                user_id=self._user_id,
                person_id=person.id,
                name=person.name,
                phone_number=person.phone_number or "",
                external_id=person.external_id or "",
                person_created_at=_datetime_to_iso(person.created_at),
                ctx_id=ctx.id,
                description=ctx.description,
                ctx_created_at=_datetime_to_iso(ctx.created_at),
            )

    def get_by_id(self, person_id: str) -> Person | None:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (owner:Person {id: $user_id, registered: true})-[:KNOWS]->
                      (p:Person)-[:HAS_CONTEXT]->(c:RelationshipContext)
                WHERE p.id = $id AND p.registered = false
                RETURN p, c
                """,
                user_id=self._user_id,
                id=person_id,
            )
            record = result.single()
        if not record:
            return None
        return _record_to_person(record)

    def list_all(self) -> list[Person]:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (owner:Person {id: $user_id, registered: true})-[:KNOWS]->
                      (p:Person)-[:HAS_CONTEXT]->(c:RelationshipContext)
                WHERE p.registered = false
                RETURN p, c
                ORDER BY p.created_at
                """,
                user_id=self._user_id,
            )
            return [_record_to_person(rec) for rec in result]

    def find_duplicate(self, card: ContactCardData) -> Person | None:
        card_phone = (card.phone_number or "").strip() or None
        card_tid = _normalize_telegram_id(card.telegram_user_id)
        if not card_phone and not card_tid:
            return None
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (owner:Person {id: $user_id, registered: true})-[:KNOWS]->
                      (p:Person)-[:HAS_CONTEXT]->(c:RelationshipContext)
                WHERE p.registered = false
                  AND (($phone <> '' AND p.phone_number = $phone)
                   OR ($external_id <> '' AND p.external_id = $external_id))
                RETURN p, c
                LIMIT 1
                """,
                user_id=self._user_id,
                phone=card_phone or "",
                external_id=card_tid or "",
            )
            record = result.single()
        if not record:
            return None
        return _record_to_person(record)

    def append_context(self, person_id: str, additional_text: str) -> bool:
        """Append suffix to the contact's context. Returns True if updated, False if not found."""
        suffix = "\n\n— " + (additional_text or "").strip()
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (owner:Person {id: $user_id, registered: true})-[:KNOWS]->
                      (p:Person)-[:HAS_CONTEXT]->(c:RelationshipContext)
                WHERE p.id = $person_id AND p.registered = false
                SET c.description = c.description + $suffix
                RETURN 1 AS ok
                """,
                user_id=self._user_id,
                person_id=person_id,
                suffix=suffix,
            )
            return result.single() is not None


def _record_to_person(record) -> Person:
    p = record["p"]
    c = record["c"]
    person_id = p["id"]
    name = p["name"]
    phone_number = p.get("phone_number") or None
    if phone_number == "":
        phone_number = None
    external_id = p.get("external_id") or None
    if external_id == "":
        external_id = None
    person_created_at = _iso_to_datetime(p["created_at"])
    ctx_id = c["id"]
    description = c["description"]
    ctx_created_at = _iso_to_datetime(c["created_at"])
    ctx = RelationshipContext(
        id=ctx_id,
        description=description,
        created_at=ctx_created_at,
    )
    return Person(
        id=person_id,
        name=name,
        phone_number=phone_number,
        external_id=external_id,
        created_at=person_created_at,
        relationship_context=ctx,
    )
