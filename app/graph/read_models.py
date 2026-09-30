"""Read-side graph queries behind the REST catalog routes and the HTML explorer pages.

Moved out of `app/api/{services,queues,messages,ui,import_api}.py` so the routes only map results to
HTTP. Query text and row shapes are unchanged. Each function takes an open (read) `neo4j.Session`
and never manages one itself, mirroring `app.analysis.*`.
"""

from typing import LiteralString

import neo4j

# --- shared evidence ----------------------------------------------------------------------------

_EVIDENCE_BY_IDS_QUERY = (
    "UNWIND $ids AS eid "
    "MATCH (e:Evidence {id: eid}) "
    "RETURN e.id AS id, e.source_type AS source_type, e.source_file AS source_file, "
    "e.source_revision AS source_revision, e.evidence_type AS evidence_type, "
    "e.environment AS environment, e.first_seen AS first_seen, e.last_seen AS last_seen, "
    "e.observation_count AS observation_count"
)


def attach_evidence(session: neo4j.Session, rows: list[dict]) -> list[dict]:
    """Resolves each row's evidence_ids into full Evidence records in one batch query (spec §4.11)."""
    all_ids = {eid for row in rows for eid in row.get("evidence_ids") or []}
    evidence_by_id = (
        {
            record["id"]: record.data()
            for record in session.run(_EVIDENCE_BY_IDS_QUERY, ids=list(all_ids))
        }
        if all_ids
        else {}
    )
    for row in rows:
        row["evidence"] = [
            evidence_by_id[eid] for eid in row.get("evidence_ids") or [] if eid in evidence_by_id
        ]
    return rows


# Cypher can't parametrize a label; these are fixed module constants, never caller input.
def _incident_evidence_query(label: LiteralString) -> LiteralString:
    return (
        f"MATCH (:{label} {{id: $id}})-[r]-() "
        "UNWIND coalesce(r.evidence_ids, []) AS eid "
        "MATCH (e:Evidence {id: eid}) "
        "RETURN DISTINCT e.id AS id, e.source_type AS source_type, e.source_file AS source_file, "
        "e.source_revision AS source_revision, e.evidence_type AS evidence_type "
        "ORDER BY e.id"
    )


# --- services -----------------------------------------------------------------------------------

_SERVICE_LIST_QUERY = (
    "MATCH (s:Service) RETURN s.id AS id, s.name AS name, s.version AS version ORDER BY s.name"
)
_SERVICE_GET_QUERY = (
    "MATCH (s:Service {id: $id}) RETURN s.id AS id, s.name AS name, s.version AS version"
)
_SERVICE_EVIDENCE_QUERY = _incident_evidence_query("Service")
_SERVICE_EXISTS_QUERY = "MATCH (s:Service {id: $id}) RETURN count(s) AS c"


def list_services(session: neo4j.Session) -> list[dict]:
    return [record.data() for record in session.run(_SERVICE_LIST_QUERY)]


def get_service(session: neo4j.Session, service_id: str) -> dict | None:
    record = session.run(_SERVICE_GET_QUERY, id=service_id).single()
    return None if record is None else record.data()


def service_evidence(session: neo4j.Session, service_id: str) -> list[dict]:
    """Evidence backing every relation incident to this service (spec §4.10, AC13)."""
    return [record.data() for record in session.run(_SERVICE_EVIDENCE_QUERY, id=service_id)]


def service_exists(session: neo4j.Session, service_id: str) -> bool:
    record = session.run(_SERVICE_EXISTS_QUERY, id=service_id).single()
    assert record is not None  # a count() aggregate always yields exactly one row
    return record["c"] > 0


# --- queues -------------------------------------------------------------------------------------

_QUEUE_FIELDS = (
    "q.id AS id, q.name AS name, q.protocol AS protocol, q.namespace AS namespace, "
    "q.queue_type AS queue_type"
)
_QUEUE_LIST_QUERY = f"MATCH (q:Queue) RETURN {_QUEUE_FIELDS} ORDER BY q.name"
_QUEUE_GET_QUERY = f"MATCH (q:Queue {{id: $id}}) RETURN {_QUEUE_FIELDS}"
_QUEUE_EVIDENCE_QUERY = _incident_evidence_query("Queue")


def list_queues(session: neo4j.Session) -> list[dict]:
    return [record.data() for record in session.run(_QUEUE_LIST_QUERY)]


def get_queue(session: neo4j.Session, queue_id: str) -> dict | None:
    record = session.run(_QUEUE_GET_QUERY, id=queue_id).single()
    return None if record is None else record.data()


def queue_evidence(session: neo4j.Session, queue_id: str) -> list[dict]:
    """Evidence backing every relation incident to this queue (spec §4.10, AC13)."""
    return [record.data() for record in session.run(_QUEUE_EVIDENCE_QUERY, id=queue_id)]


# --- messages -----------------------------------------------------------------------------------

_MESSAGE_FIELDS = "m.id AS id, m.name AS name, m.version AS version, m.schema_id AS schema_id"
_MESSAGE_LIST_QUERY = f"MATCH (m:Message) RETURN {_MESSAGE_FIELDS} ORDER BY m.name"
_MESSAGE_GET_QUERY = f"MATCH (m:Message {{id: $id}}) RETURN {_MESSAGE_FIELDS}"


def list_messages(session: neo4j.Session) -> list[dict]:
    return [record.data() for record in session.run(_MESSAGE_LIST_QUERY)]


def get_message(session: neo4j.Session, message_id: str) -> dict | None:
    record = session.run(_MESSAGE_GET_QUERY, id=message_id).single()
    return None if record is None else record.data()


# --- HTML explorer pages ------------------------------------------------------------------------


def index_services(session: neo4j.Session) -> list[dict]:
    return session.run("MATCH (s:Service) RETURN s.id AS id, s.name AS name ORDER BY s.name").data()


def index_queues(session: neo4j.Session) -> list[dict]:
    return session.run("MATCH (q:Queue) RETURN q.id AS id, q.name AS name ORDER BY q.name").data()


def service_summary(session: neo4j.Session, service_id: str) -> dict | None:
    record = session.run(
        "MATCH (s:Service {id: $id}) RETURN s.id AS id, s.name AS name", id=service_id
    ).single()
    return None if record is None else record.data()


def service_provides(session: neo4j.Session, service_id: str) -> list[dict]:
    return attach_evidence(
        session,
        session.run(
            "MATCH (:Service {id: $id})-[r:PROVIDES]->(o:Operation) "
            "RETURN o.method AS method, o.path AS path, r.evidence_ids AS evidence_ids "
            "ORDER BY o.path",
            id=service_id,
        ).data(),
    )


def service_calls(session: neo4j.Session, service_id: str) -> list[dict]:
    return attach_evidence(
        session,
        session.run(
            "MATCH (:Service {id: $id})-[r:CALLS]->(o:Operation)<-[:PROVIDES]-(target:Service) "
            "RETURN target.name AS service_name, o.operation_id AS operation_id, "
            "r.evidence_ids AS evidence_ids ORDER BY target.name",
            id=service_id,
        ).data(),
    )


def service_sends(session: neo4j.Session, service_id: str) -> list[dict]:
    return attach_evidence(
        session,
        session.run(
            "MATCH (:Service {id: $id})-[r:SENDS]->(q:Queue) "
            "RETURN q.id AS id, q.name AS name, r.evidence_ids AS evidence_ids ORDER BY q.name",
            id=service_id,
        ).data(),
    )


def service_receives(session: neo4j.Session, service_id: str) -> list[dict]:
    return attach_evidence(
        session,
        session.run(
            "MATCH (:Service {id: $id})-[r:RECEIVES_FROM]->(q:Queue) "
            "RETURN q.id AS id, q.name AS name, r.evidence_ids AS evidence_ids ORDER BY q.name",
            id=service_id,
        ).data(),
    )


def queue_summary(session: neo4j.Session, queue_id: str) -> dict | None:
    record = session.run(
        "MATCH (q:Queue {id: $id}) RETURN q.id AS id, q.name AS name, q.protocol AS protocol",
        id=queue_id,
    ).single()
    return None if record is None else record.data()


def queue_messages(session: neo4j.Session, queue_id: str) -> list[dict]:
    return attach_evidence(
        session,
        session.run(
            "MATCH (:Queue {id: $id})-[r:CARRIES]->(m:Message) "
            "RETURN m.name AS name, m.version AS version, r.evidence_ids AS evidence_ids "
            "ORDER BY m.name",
            id=queue_id,
        ).data(),
    )


def queue_dead_letter(session: neo4j.Session, queue_id: str) -> dict | None:
    """The queue this one dead-letters to (with resolved evidence), or None."""
    record = session.run(
        "MATCH (:Queue {id: $id})-[r:DEAD_LETTERS_TO]->(d:Queue) "
        "RETURN d.id AS id, d.name AS name, r.evidence_ids AS evidence_ids",
        id=queue_id,
    ).single()
    return None if record is None else attach_evidence(session, [record.data()])[0]
