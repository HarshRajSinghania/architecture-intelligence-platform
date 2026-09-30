"""D2 graph-reachability gate against a real Neo4j (v0.6.0 I2.1b).

Covers the two layers separately and together, through the real `ArchitectureQuestionService.ask`
path: the syntactic node-pattern rule, and the `EXPLAIN` plan check on the pinned Neo4j image.
Each layer is also proven on its own by switching the other one off, so neither test passes
merely because the other layer already rejected the query.
"""

import pytest

from app.ai import question_service
from app.ai.cypher_validator import CypherValidationError
from app.ai.graph_reachability import GraphReachabilityError, check_plan
from app.ai.question_service import ArchitectureQuestionService

DATABASE = "neo4j"


class FakeProvider:
    def __init__(self, cypher: str):
        self.cypher = cypher
        self.compose_calls = 0

    def generate_cypher(self, *, question: str, schema_description: str) -> str:
        return self.cypher

    def compose_answer(self, *, question: str, cypher: str, rows: list[dict]) -> str:
        self.compose_calls += 1
        return f"Found {len(rows)} row(s)."


@pytest.fixture(scope="module", autouse=True)
def graph(driver):
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
        session.run(
            "CREATE (s:Service {id: 'service:orders', name: 'OrderService'})"
            "-[:CALLS]->(o:Operation {id: 'operation:pricing:GET:/prices'}), "
            "(s)-[:SENDS]->(:Queue {id: 'queue:payments', name: 'payments'}), "
            "(:Evidence {id: 'evidence:x'}), "
            # Stand-ins for internal nodes a generated query must never reach.
            "(:AipInternalState {id: 'internal', secret: 'do-not-leak'}), "
            "(:ScopedObservedCallV2 {id: 'evidence:otel:calls-scoped:v2:0', caller_pod_uid: 'p1'})"
        )


def _plan(driver, cypher: str):
    with driver.session(database=DATABASE) as session:
        return session.run("EXPLAIN " + cypher).consume().plan  # pyright: ignore[reportArgumentType]


# Shapes recorded in tests/unit/test_graph_reachability.py, here checked against the live planner.
PLAN_ACCEPTED = [
    "MATCH (s:Service) RETURN s.id LIMIT 5",
    "MATCH (s:Service {id: 'service:orders'}) RETURN s.name LIMIT 5",
    "MATCH (s:Service)-[:CALLS]->(o) RETURN o.id LIMIT 5",
    "MATCH ()-[r:CALLS]->() RETURN r.evidence_ids LIMIT 5",
    "MATCH (s:Service) OPTIONAL MATCH (s)-[:SENDS]->(q:Queue) RETURN s.id, q.id LIMIT 5",
    "MATCH (s:Service) WHERE EXISTS { MATCH (s)-[:SENDS]->(q:Queue) } RETURN s.id LIMIT 5",
    "MATCH (s:Service) RETURN s.id, COUNT { MATCH (s)-[:SENDS]->(:Queue) } AS c LIMIT 5",
    "MATCH (e:Evidence) WHERE e.id IN ['evidence:x'] RETURN e.id LIMIT 5",
    "MATCH (s:Service)-[:CALLS*1..3]->(o:Operation) RETURN o.id LIMIT 5",
    "MATCH (s:Service), (q:Queue) RETURN s.id, q.id LIMIT 5",
]

PLAN_REJECTED = [
    "MATCH (n) RETURN n.id LIMIT 5",
    "MATCH (n:AipInternalState) RETURN n.secret LIMIT 5",
    "MATCH (n:ScopedObservedCallV2) RETURN n.caller_pod_uid LIMIT 5",
    "MATCH (n:Service|AipInternalState) RETURN n.id LIMIT 5",
    "MATCH ()-[r]->() RETURN r LIMIT 5",
    "MATCH (a:Service)-[r]->(b) RETURN b.id LIMIT 5",
    "MATCH (n) WHERE elementId(n) = '4:x:1' RETURN n LIMIT 5",
]


@pytest.mark.parametrize("cypher", PLAN_ACCEPTED)
def test_the_planner_output_for_authorized_queries_passes_the_plan_check(driver, cypher):
    check_plan(_plan(driver, cypher))


@pytest.mark.parametrize("cypher", PLAN_REJECTED)
def test_the_planner_output_for_unbounded_reads_fails_the_plan_check(driver, cypher):
    with pytest.raises(GraphReachabilityError):
        check_plan(_plan(driver, cypher))


# Queries the older validators accept, so only the new gate stops them.
UNREACHABLE = [
    "MATCH (n) RETURN n.secret AS s",
    "MATCH (n) RETURN n.id AS id",
    "MATCH (n:`AipInternalState`) RETURN n.secret AS s",
    "MATCH (n:Service|AipInternalState) RETURN n.secret AS s",
    "MATCH (s:Service) RETURN labels(s) AS l",
    "MATCH ()-[r]->() RETURN r.evidence_ids AS e",
]

# An explicit internal label is already rejected by validate_cypher, before the gate runs.
ALREADY_REJECTED = [
    "MATCH (n:AipInternalState) RETURN n.secret AS s",
    "MATCH (n:ScopedObservedCallV2) RETURN n.caller_pod_uid AS pod",
]


@pytest.mark.parametrize("cypher", UNREACHABLE)
def test_ask_never_executes_a_query_that_can_reach_internal_nodes(driver, cypher):
    provider = FakeProvider(cypher)
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    with pytest.raises(GraphReachabilityError):
        service.ask("show me everything")

    assert provider.compose_calls == 0


@pytest.mark.parametrize("cypher", ALREADY_REJECTED)
def test_ask_rejects_explicit_internal_labels(driver, cypher):
    provider = FakeProvider(cypher)
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    with pytest.raises(CypherValidationError, match="unknown node label"):
        service.ask("show me everything")

    assert provider.compose_calls == 0


def test_ask_still_answers_authorized_questions(driver):
    provider = FakeProvider("MATCH (s:Service)-[:CALLS]->(o:Operation) RETURN s.name AS name")
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    result = service.ask("who calls something?")

    assert [row["name"] for row in result.rows] == ["OrderService"]
    assert provider.compose_calls == 1


def test_the_plan_check_alone_stops_an_unlabeled_scan(driver, monkeypatch):
    """With the syntactic rule switched off, `MATCH (n)` is still rejected: by the plan."""
    monkeypatch.setattr(question_service, "check_node_patterns", lambda cypher: None)
    provider = FakeProvider("MATCH (n) RETURN n.secret AS s")
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    with pytest.raises(GraphReachabilityError, match="query plan"):
        service.ask("leak")
    assert provider.compose_calls == 0


def test_the_syntactic_rule_alone_stops_an_unlabeled_scan(driver, monkeypatch):
    """With the plan check switched off, the same query is rejected: by the syntax rule."""
    monkeypatch.setattr(question_service, "check_plan", lambda plan: None)
    provider = FakeProvider("MATCH (n) RETURN n.secret AS s")
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    with pytest.raises(GraphReachabilityError, match="every node pattern"):
        service.ask("leak")
    assert provider.compose_calls == 0


def test_with_both_layers_off_the_internal_node_would_be_readable(driver, monkeypatch):
    """Control: proves the fixture really holds a reachable internal node, so the rejections
    above are the gate's doing and not an empty graph."""
    monkeypatch.setattr(question_service, "check_node_patterns", lambda cypher: None)
    monkeypatch.setattr(question_service, "check_plan", lambda plan: None)
    provider = FakeProvider("MATCH (n) WHERE n.secret IS NOT NULL RETURN n.secret AS s")
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    result = service.ask("leak")

    assert [row["s"] for row in result.rows] == ["do-not-leak"]
