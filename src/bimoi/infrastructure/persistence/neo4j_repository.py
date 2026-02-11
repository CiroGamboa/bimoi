"""Neo4j implementation of ContactRepository.
Graph: (User)-[:KNOWS]->(Person)-[:HAS_CONTEXT]->(RelationshipContext).
All data scoped by user_id.
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
    (User)-[:KNOWS]->(Person)-[:HAS_CONTEXT]->(RelationshipContext).
    """

    def __init__(self, driver: object, user_id: str = "default") -> None:
        self._driver = driver
        self._user_id = user_id

    def add(self, person: Person) -> None:
        ctx = person.relationship_context
        with self._driver.session() as session:
            session.run(
                """
                MERGE (u:User {id: $user_id})
                CREATE (p:Person {
                    id: $person_id,
                    name: $name,
                    phone_number: $phone_number,
                    external_id: $external_id,
                    created_at: $person_created_at
                })
                CREATE (c:RelationshipContext {
                    id: $ctx_id,
                    description: $description,
                    created_at: $ctx_created_at
                })
                CREATE (u)-[:KNOWS]->(p)
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
                MATCH (u:User {id: $user_id})-[:KNOWS]->(p:Person)
                -[:HAS_CONTEXT]->(c:RelationshipContext)
                WHERE p.id = $id
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
                MATCH (u:User {id: $user_id})-[:KNOWS]->(p:Person)
                -[:HAS_CONTEXT]->(c:RelationshipContext)
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
                MATCH (u:User {id: $user_id})-[:KNOWS]->(p:Person)
                -[:HAS_CONTEXT]->(c:RelationshipContext)
                WHERE ($phone <> '' AND p.phone_number = $phone)
                   OR ($external_id <> '' AND p.external_id = $external_id)
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
