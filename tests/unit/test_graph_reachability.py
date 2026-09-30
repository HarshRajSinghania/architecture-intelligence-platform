"""Unit tests for the D2 fail-closed graph-reachability gate (v0.6.0 I2.1b).

The plan fixtures below are the `EXPLAIN` shapes recorded from the pinned neo4j:5.26.31 image, so
the operator allowlist is checked against real operator names and `Details` strings.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.ai.cypher_validator import CypherValidationError
from app.ai.graph_reachability import (
    APPROVED_NL_LABELS,
    GraphReachabilityError,
    check_node_patterns,
    check_plan,
)
from app.graph.importer import KNOWN_RELATION_TYPES, NODE_LABELS

ACCEPTED = [
    "MATCH (s:Service) RETURN s.id",
    "MATCH (s:Service)-[:SENDS]->(q:Queue) RETURN s.name, q.name",
    "MATCH (s:Service)-[:CALLS]->(o) RETURN o.id",  # typed endpoint may be unlabeled
    "MATCH (o)<-[:PROVIDES]-(s:Service) RETURN o.id",
    "MATCH (s:Service)-[:SENDS|RECEIVES_FROM]->(q) RETURN q.id",
    "MATCH (s:Service)-[:CALLS*1..3]->(o:Operation) RETURN o.id",
    "MATCH (s:Service) MATCH (q:Queue) MATCH (s)-[:SENDS]->(q) RETURN s, q",
    "MATCH (s:Service) OPTIONAL MATCH (s)-[:SENDS]->(q:Queue) RETURN s, q",
    (
        "MATCH (s:Service)-[r:CALLS]->(o:Operation) MATCH (e:Evidence) "
        "WHERE e.id IN r.evidence_ids RETURN e.id"
    ),
    (
        "MATCH (c:Service)-[:RECEIVES_FROM]->(q:Queue) "
        "WHERE NOT EXISTS { MATCH (:Service)-[:SENDS]->(q) } RETURN c.id"
    ),
    "MATCH (s:Service) RETURN s.id, COUNT { MATCH (s)-[:SENDS]->(:Queue) } AS c",
    "MATCH (s:Service {id: 'service:orders'}) RETURN s.name",
    "MATCH (s:Service), (q:Queue) RETURN s.id, q.id",
    "MATCH (s:Service) WHERE s.name STARTS WITH 'O' RETURN count(s) AS n",
    "MATCH (s:Service) WHERE (s)-[:SENDS]->() RETURN s",  # typed endpoint, pattern expression
    "MATCH (s:Service) RETURN toLower(s.name) AS n",
    "MATCH (s:Service) WITH s, count(s) AS c RETURN s.id, c",
    "MATCH (n:Service:Operation) RETURN n.id",
    "MATCH (m:Message)-[:CONFORMS_TO]->(sc:Schema) RETURN m.id, sc.id",
]

REJECTED = [
    ("MATCH (n) RETURN n", "every node pattern"),
    ("MATCH (n) RETURN n.id", "every node pattern"),
    ("MATCH ()-[r]->() RETURN r", "every node pattern"),
    ("MATCH (a)-[r]->(b) RETURN a, b", "every node pattern"),
    ("MATCH (a:Service)-[r]->(b) RETURN b", "every node pattern"),
    ("MATCH (a)--(b) RETURN a, b", "every node pattern"),
    ("MATCH (a:Service)-->(b) RETURN b", "every node pattern"),
    ("MATCH (s:Service)-[:CALLS]->(o) MATCH (x) RETURN x", "every node pattern"),
    ("MATCH (n)-[:CALLS]->(o) MATCH (m) RETURN m", "every node pattern"),
    ("MATCH (n:Service|AipInternalState) RETURN n", "plain variable"),
    ("MATCH (n:Service&Operation) RETURN n", "plain variable"),
    ("MATCH (n:!Service) RETURN n", "plain variable"),
    ("MATCH (n:%) RETURN n", "plain variable"),
    ("MATCH (n:$(l)) RETURN n", "plain variable"),
    ("MATCH (n:`AipInternalState`) RETURN n", "plain variable"),
    ("MATCH (n:AipInternalState) RETURN n", "not allowed: AipInternalState"),
    ("MATCH (n:ScopedObservedCallV2) RETURN n", "not allowed: ScopedObservedCallV2"),
    ("MATCH (n:SourceState) RETURN n", "not allowed: SourceState"),
    ("MATCH (n:InfrastructureEntity) RETURN n", "not allowed: InfrastructureEntity"),
    ("MATCH (n:Service:SourceState) RETURN n", "not allowed: SourceState"),
    ("MATCH (s:Service) RETURN labels(s)", "labels()"),
    ("MATCH (s:Service) RETURN LABELS (s) AS l", "labels()"),
    ("MATCH (s:Service)-[:CALLS]->(o) RETURN labels(o)", "labels()"),
    # A variable is only bound once labeled: redeclaring an unlabeled node earlier is not bound.
    ("MATCH (n) MATCH (n:Service) RETURN n", "every node pattern"),
    ("MATCH (s:Service)-[:EVIL]->(o) RETURN o", "every node pattern"),
    ("MATCH (s:Service)-[:!CALLS]->(o) RETURN o", "every node pattern"),
    ("MATCH (s:Service)-[:%]->(o) RETURN o", "every node pattern"),
    ("MATCH (s:Service) WHERE EXISTS { MATCH (n) } RETURN s", "every node pattern"),
    ("MATCH (s:Service) OPTIONAL MATCH (n) RETURN s, n", "every node pattern"),
    ("MATCH (s:Service) RETURN [(a)-->(b) | b.id]", "every node pattern"),
]


@pytest.mark.parametrize("query", ACCEPTED)
def test_approved_patterns_pass(query):
    check_node_patterns(query)


@pytest.mark.parametrize(("query", "message"), REJECTED)
def test_unbound_or_unapproved_patterns_are_rejected(query, message):
    with pytest.raises(GraphReachabilityError, match=message):
        check_node_patterns(query)


def test_reachability_error_is_a_cypher_validation_error():
    assert issubclass(GraphReachabilityError, CypherValidationError)


def test_approved_labels_are_exactly_the_current_schema_labels():
    assert APPROVED_NL_LABELS == frozenset(NODE_LABELS.values())
    assert "Evidence" in APPROVED_NL_LABELS
    assert not {"AipInternalState", "ScopedObservedCallV2", "SourceState"} & APPROVED_NL_LABELS


def test_a_label_inside_a_string_or_comment_is_not_a_node_pattern():
    check_node_patterns("MATCH (s:Service) WHERE s.name = '(n)' RETURN s.id // MATCH (x)")


def test_a_label_in_a_string_cannot_hide_an_unbound_pattern():
    with pytest.raises(GraphReachabilityError):
        check_node_patterns("MATCH (s:Service) WHERE s.name = 'x' MATCH (n) RETURN n")


def test_unbalanced_parentheses_fail_closed():
    with pytest.raises(GraphReachabilityError, match="unbalanced"):
        check_node_patterns("MATCH (s:Service RETURN s")


# --- plan check --------------------------------------------------------------------------------


def _op(name, details="", *children, ids=("n",)):
    return {
        "operatorType": f"{name}@neo4j",
        "args": {"Details": details},
        "identifiers": list(ids),
        "children": list(children),
    }


def _plan(leaf):
    return _op("ProduceResults", "n", _op("Limit", "5", leaf))


ACCEPTED_LEAVES = [
    _op("NodeByLabelScan", "s:Service"),
    _op("NodeByLabelScan", "e:Evidence"),
    _op("NodeUniqueIndexSeek", "UNIQUE s:Service(id) WHERE id = $autostring_0, cache[s.id]"),
    _op("NodeUniqueIndexSeek", "UNIQUE e:Evidence(id) WHERE id = $autolist_0[0], cache[e.id]"),
    _op("NodeIndexSeek", "RANGE INDEX s:Service(name) WHERE name = $a, cache[s.name]"),
    _op("DirectedRelationshipTypeScan", "(anon_0)-[r:CALLS]->(anon_1)"),
    _op("DirectedRelationshipTypeScan", "(s)-[anon_0:CALLS]->(o)"),
    _op("UndirectedRelationshipTypeScan", "(a)-[r:SENDS]-(b)"),
    _op("DirectedUnionRelationshipTypesScan", "(a)-[r:SENDS|RECEIVES_FROM]->(b)"),
    _op("Argument", "s"),
]


@pytest.mark.parametrize("leaf", ACCEPTED_LEAVES, ids=lambda leaf: leaf["operatorType"])
def test_approved_leaf_operators_pass(leaf):
    check_plan(_plan(leaf))


REJECTED_LEAVES = [
    _op("AllNodesScan", "n"),
    _op("NodeByIdSeek", "n WHERE id(n) = $autoint_0"),
    _op("NodeByElementIdSeek", "n WHERE elementId(n) = $autostring_0"),
    _op("DirectedAllRelationshipsScan", "(anon_0)-[r]->(anon_1)"),
    _op("UndirectedAllRelationshipsScan", "(a)-[r]-(b)"),
    _op("NodeByLabelScan", "n:AipInternalState"),
    _op("NodeByLabelScan", "n:ScopedObservedCallV2"),
    _op("NodeByLabelScan", "n"),  # unparseable details are rejected, not trusted
    _op("NodeUniqueIndexSeek", "UNIQUE n:SourceState(source_instance_id) WHERE x = $a"),
    _op("NodeIndexSeek", "n:Service(id)"[:2]),
    _op("DirectedRelationshipTypeScan", "(a)-[r:EVIL]->(b)"),
    _op("DirectedRelationshipTypeScan", "(a)-[r:CALLS|EVIL]->(b)"),
    _op("DirectedRelationshipTypeScan", "garbage"),
    _op("NodeCountFromCountStore", "count( (:AipInternalState) ) AS c"),
    _op("SomeFutureOperator", "x"),
    {"children": []},
]


@pytest.mark.parametrize(
    "leaf", REJECTED_LEAVES, ids=lambda leaf: leaf.get("operatorType", "empty")
)
def test_unapproved_or_unknown_leaf_operators_are_rejected(leaf):
    with pytest.raises(GraphReachabilityError):
        check_plan(_plan(leaf))


def test_every_leaf_of_a_branching_plan_must_pass():
    good = _op("NodeByLabelScan", "s:Service")
    bad = _op("AllNodesScan", "n")
    check_plan(_op("CartesianProduct", "", good, _op("NodeByLabelScan", "q:Queue")))
    with pytest.raises(GraphReachabilityError):
        check_plan(_op("CartesianProduct", "", good, bad))


def test_a_deeply_nested_bad_leaf_is_found():
    nested = _op(
        "Apply", "", _op("Argument", "s"), _op("Expand(All)", "", _op("AllNodesScan", "n"))
    )
    with pytest.raises(GraphReachabilityError):
        check_plan(_op("ProduceResults", "n", nested))


@pytest.mark.parametrize("plan", [None, {}])
def test_a_missing_plan_is_rejected(plan):
    with pytest.raises(GraphReachabilityError, match="no query plan"):
        check_plan(plan)


# --- properties -----------------------------------------------------------------------------

_public_labels = st.sampled_from(sorted(APPROVED_NL_LABELS))
_internal_labels = st.sampled_from(
    [
        "AipInternalState",
        "SourceState",
        "CurrentInventory",
        "InfrastructureEntity",
        "InfrastructureContribution",
        "InfrastructureClaim",
        "RuntimeIdentityObservation",
        "PubSubDeclaration",
        "ScopedObservedCallV2",
        "ScopedEvidenceCutover",
    ]
)
_rel_types = st.sampled_from(sorted(KNOWN_RELATION_TYPES))
_variables = st.sampled_from(["a", "b", "n", "x", "node1"])


@given(_public_labels, _public_labels, _rel_types)
def test_property_fully_labeled_queries_pass(left, right, rel):
    check_node_patterns(f"MATCH (a:{left})-[:{rel}]->(b:{right}) RETURN a.id, b.id")


@given(_variables, _public_labels)
def test_property_an_unlabeled_standalone_node_is_always_rejected(variable, label):
    with pytest.raises(GraphReachabilityError):
        check_node_patterns(f"MATCH (s:{label}) MATCH ({variable}) RETURN {variable}")


@given(_variables, _internal_labels)
def test_property_an_internal_label_is_always_rejected(variable, label):
    with pytest.raises(GraphReachabilityError):
        check_node_patterns(f"MATCH ({variable}:{label}) RETURN {variable}")


@given(_variables, _public_labels, _internal_labels, st.sampled_from(["|", "&"]))
def test_property_a_label_expression_naming_an_internal_label_is_always_rejected(
    variable, public, internal, operator
):
    with pytest.raises(GraphReachabilityError):
        check_node_patterns(f"MATCH ({variable}:{public}{operator}{internal}) RETURN {variable}")


@given(_variables, _internal_labels)
def test_property_a_backtick_label_is_always_rejected(variable, label):
    with pytest.raises(GraphReachabilityError):
        check_node_patterns(f"MATCH ({variable}:`{label}`) RETURN {variable}")


@given(_variables, _rel_types)
def test_property_an_untyped_relationship_never_binds_its_endpoints(variable, rel):
    with pytest.raises(GraphReachabilityError):
        check_node_patterns(f"MATCH (s:Service)-[r]->({variable}) RETURN {variable}")
    check_node_patterns(f"MATCH (s:Service)-[:{rel}]->({variable}) RETURN {variable}")
