"""Neo4j implementation of ContactRepository.
Graph: single Person label with registered flag.
(owner:Person {id: user_id, registered: true})-[:KNOWS {context properties}]->(contact:Person {registered: false}).
Context stored as properties on KNOWS relationship.
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
    Context lives on KNOWS relationship properties.
    """

    def __init__(self, driver: object, user_id: str = "default") -> None:
        self._driver = driver
        self._user_id = user_id

    def add(self, person: Person) -> None:
        ctx = person.relationship_context
        ctx_timestamp = _datetime_to_iso(ctx.created_at)
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
                CREATE (owner)-[:KNOWS {
                    context_id: $ctx_id,
                    context_description: $description,
                    context_created_at: $ctx_created_at,
                    context_updated_at: $ctx_created_at
                }]->(p)
                """,
                user_id=self._user_id,
                person_id=person.id,
                name=person.name,
                phone_number=person.phone_number or "",
                external_id=person.external_id or "",
                person_created_at=_datetime_to_iso(person.created_at),
                ctx_id=ctx.id,
                description=ctx.description,
                ctx_created_at=ctx_timestamp,
            )

    def get_by_id(self, person_id: str) -> Person | None:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (owner:Person {id: $user_id, registered: true})-[k:KNOWS]->(p:Person)
                WHERE p.id = $id AND p.registered = false
                RETURN p, k
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
                MATCH (owner:Person {id: $user_id, registered: true})-[k:KNOWS]->(p:Person)
                WHERE p.registered = false
                RETURN p, k
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
                MATCH (owner:Person {id: $user_id, registered: true})-[k:KNOWS]->(p:Person)
                WHERE p.registered = false
                  AND (($phone <> '' AND p.phone_number = $phone)
                   OR ($external_id <> '' AND p.external_id = $external_id))
                RETURN p, k
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
        updated_at = _datetime_to_iso(datetime.utcnow())
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (owner:Person {id: $user_id, registered: true})-[k:KNOWS]->(p:Person)
                WHERE p.id = $person_id AND p.registered = false
                SET k.context_description = k.context_description + $suffix,
                    k.context_updated_at = $updated_at
                RETURN 1 AS ok
                """,
                user_id=self._user_id,
                person_id=person_id,
                suffix=suffix,
                updated_at=updated_at,
            )
            return result.single() is not None


def _record_to_person(record) -> Person:
    p = record["p"]
    k = record["k"]
    person_id = p["id"]
    name = p["name"]
    phone_number = p.get("phone_number") or None
    if phone_number == "":
        phone_number = None
    external_id = p.get("external_id") or None
    if external_id == "":
        external_id = None
    person_created_at = _iso_to_datetime(p["created_at"])
    ctx_id = k["context_id"]
    description = k["context_description"]
    ctx_created_at = _iso_to_datetime(k["context_created_at"])
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
