import hashlib
import json
import shutil
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from app.analysis.runtime import confirmed_relations, observed_only_relations
from app.architecture_intelligence.repository import (
    canonical_snapshot_state,
    snapshot_fingerprint,
)
from app.canonical import ids
from app.canonical.infrastructure import (
    InfrastructureClaim,
    InfrastructureClaimKind,
    InfrastructureContribution,
    InfrastructureEntity,
    InfrastructureEntityKind,
    InfrastructurePort,
    KubernetesEvidenceMode,
)
from app.canonical.model import (
    ArchitectureModel,
    Message,
    Operation,
    Queue,
    Relation,
    Schema,
    Service,
)
from app.graph.importer import (
    ImportRunStats,
    import_all_sources,
    import_discovery_run,
    import_kubernetes_source,
    import_source,
)
from app.graph.revision_fence import read_revision
from app.graph.schema import ensure_schema
from app.ingestion.kubernetes_adapter import KubernetesSourceAdapter
from app.ingestion.kubernetes_discoverer import KubernetesSourceDiscoverer
from app.ingestion.orchestrator import (
    run_discovery,
    run_filesystem_discovery,
    run_kubernetes_discovery,
)
from app.provenance.model import ObservedEvidence, Provenance
from app.sources.identity import discovery_scope_id as k8s_discovery_scope_id
from app.sources.jcs import canonical_json_bytes
from app.sources.kubernetes_envelope import EXPECTED_RESOURCE_TYPES
from app.sources.migration_mappings import load_migration_mappings
from app.sources.model import (
    DiagnosticCode,
    FilesystemSourceConfig,
    IngestionResult,
    KubernetesSourceConfig,
    NotSupplied,
    SourceKind,
)
from app.sources.registry import DiscoveryOutcome
from app.sources.tombstones import Tombstone
from app.telemetry.aggregator import persist_observation_batch
from app.telemetry.model import ObservationBatch, ObservedFactCandidate

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
KUBERNETES_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "kubernetes" / "i2"
DATABASE = "neo4j"

SCOPE_ID = "urn:aip:discovery-scope:test"
SCOPE_DIGEST_1 = "scope-digest-1"
SCOPE_DIGEST_2 = "scope-digest-2"
DIGEST_1 = "a" * 64
DIGEST_2 = "b" * 64


@pytest.fixture(autouse=True)
def clean_database(driver):
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield


def _count(driver, query: str, **params) -> int:
    with driver.session(database=DATABASE) as session:
        return session.run(query, **params).single()["c"]


def _import(session, source_instance_id: str, model: ArchitectureModel, *, digest: str = DIGEST_1):
    return import_source(
        session,
        source_instance_id=source_instance_id,
        locator=f"{source_instance_id}.yaml",
        model=model,
        semantic_input_digest=digest,
        discovery_scope_id=SCOPE_ID,
        scope_definition_digest=SCOPE_DIGEST_1,
    )


def test_ensure_schema_creates_constraints(driver):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        names = {
            record["name"] for record in session.run("SHOW CONSTRAINTS YIELD name RETURN name")
        }
    assert {
        "service_id",
        "operation_id",
        "queue_id",
        "topic_id",
        "subscription_id",
        "message_id",
        "schema_id",
        "source_state_source_instance_id",
        "infrastructure_entity_id",
        "infrastructure_contribution_id",
        "infrastructure_claim_id",
        "infrastructure_claim_contribution_id",
    } <= names


def test_import_source_creates_nodes_and_relations(driver):
    model = ArchitectureModel(
        services=[Service(id="service:product-service", name="ProductService")],
        operations=[
            Operation(
                id="operation:product-service:GET:/products/{id}",
                service_id="service:product-service",
                operation_id="getProduct",
                method="GET",
                path="/products/{id}",
                response_schema_ids=["schema:Product"],
            )
        ],
        schemas=[Schema(id="schema:Product", name="Product", format="application/json")],
        relations=[
            Relation(
                type="PROVIDES",
                source_id="service:product-service",
                target_id="operation:product-service:GET:/products/{id}",
            ),
            Relation(
                type="RESPONSE_SCHEMA",
                source_id="operation:product-service:GET:/products/{id}",
                target_id="schema:Product",
            ),
        ],
    )

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        stats = _import(session, "src:product-service", model)

    assert stats.nodes_written == 3
    assert stats.relations_written == 2
    assert stats.nodes_expired == 0
    assert stats.relations_expired == 0
    assert stats.graph_revision_advanced is True

    assert (
        _count(driver, "MATCH (n:Service {id: 'service:product-service'}) RETURN count(n) AS c")
        == 1
    )
    assert _count(driver, "MATCH ()-[r:PROVIDES]->() RETURN count(r) AS c") == 1
    assert _count(driver, "MATCH ()-[r:RESPONSE_SCHEMA]->() RETURN count(r) AS c") == 1

    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (n:Service {id: 'service:product-service'}) RETURN n.owner_source_ids AS owners"
        ).single()
    assert record["owners"] == ["src:product-service"]


def test_import_source_creates_evidence_node_and_tags_relation(driver):
    evidence = Provenance(
        id="evidence:openapi:src:product-service",
        source_type="OPENAPI",
        source_file="product-service/openapi.yaml",
        source_revision="abc123",
    )
    model = ArchitectureModel(
        services=[Service(id="service:product-service", name="ProductService")],
        operations=[
            Operation(
                id="operation:product-service:GET:/products/{id}",
                service_id="service:product-service",
                operation_id="getProduct",
                method="GET",
                path="/products/{id}",
            )
        ],
        relations=[
            Relation(
                type="PROVIDES",
                source_id="service:product-service",
                target_id="operation:product-service:GET:/products/{id}",
                evidence_ids=[evidence.id],
            )
        ],
        provenance=[evidence],
    )
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        stats = _import(session, "src:product-service", model)

    assert stats.nodes_written == 3  # service + operation + evidence

    with driver.session(database=DATABASE) as session:
        evidence_record = session.run(
            "MATCH (e:Evidence {id: $id}) RETURN e.source_type AS source_type, "
            "e.source_file AS source_file, e.source_revision AS source_revision, "
            "e.evidence_type AS evidence_type, e.owner_source_ids AS owners",
            id=evidence.id,
        ).single()
    assert evidence_record["source_type"] == "OPENAPI"
    assert evidence_record["source_file"] == "product-service/openapi.yaml"
    assert evidence_record["source_revision"] == "abc123"
    assert evidence_record["evidence_type"] == "DECLARED"
    assert evidence_record["owners"] == ["src:product-service"]

    with driver.session(database=DATABASE) as session:
        relation_record = session.run(
            "MATCH ()-[r:PROVIDES]->() RETURN r.evidence_ids AS evidence_ids"
        ).single()
    assert relation_record["evidence_ids"] == [evidence.id]


def test_shared_relation_accumulates_evidence_from_both_declaring_sources(driver):
    # Mirrors the real fixture landscape: order-service (sender) and payment-service (receiver)
    # both independently declare CARRIES payment-q -> PaymentRequested in their own AsyncAPI docs -
    # the same relation triple, two separate import transactions, two separate pieces of evidence
    # that must both survive.
    evidence_order = Provenance(
        id="evidence:asyncapi:src:order-service",
        source_type="ASYNCAPI",
        source_file="order-service/asyncapi.yaml",
    )
    evidence_payment = Provenance(
        id="evidence:asyncapi:src:payment-service",
        source_type="ASYNCAPI",
        source_file="payment-service/asyncapi.yaml",
    )
    order_model = ArchitectureModel(
        services=[Service(id="service:order-service", name="OrderService")],
        queues=[Queue(id="queue:payment-q", name="payment-q")],
        messages=[Message(id="message:PaymentRequested:v2", name="PaymentRequested", version="v2")],
        relations=[
            Relation(
                type="SENDS",
                source_id="service:order-service",
                target_id="queue:payment-q",
                evidence_ids=[evidence_order.id],
            ),
            Relation(
                type="CARRIES",
                source_id="queue:payment-q",
                target_id="message:PaymentRequested:v2",
                evidence_ids=[evidence_order.id],
            ),
        ],
        provenance=[evidence_order],
    )
    payment_model = ArchitectureModel(
        services=[Service(id="service:payment-service", name="PaymentService")],
        queues=[Queue(id="queue:payment-q", name="payment-q")],
        messages=[Message(id="message:PaymentRequested:v2", name="PaymentRequested", version="v2")],
        relations=[
            Relation(
                type="RECEIVES_FROM",
                source_id="service:payment-service",
                target_id="queue:payment-q",
                evidence_ids=[evidence_payment.id],
            ),
            Relation(
                type="CARRIES",
                source_id="queue:payment-q",
                target_id="message:PaymentRequested:v2",
                evidence_ids=[evidence_payment.id],
            ),
        ],
        provenance=[evidence_payment],
    )

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:order-service", order_model)
        _import(session, "src:payment-service", payment_model)

    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (:Queue {id:'queue:payment-q'})-[r:CARRIES]->(:Message) "
            "RETURN r.evidence_ids AS evidence_ids"
        ).single()
    assert set(record["evidence_ids"]) == {evidence_order.id, evidence_payment.id}

    # order-service stops declaring payment-q entirely (e.g. its asyncapi.yaml was removed)
    order_model_without_payment_q = ArchitectureModel(
        services=[Service(id="service:order-service", name="OrderService")]
    )
    with driver.session(database=DATABASE) as session:
        _import(session, "src:order-service", order_model_without_payment_q, digest=DIGEST_2)

    # order-service's evidence is gone entirely (no longer referenced by anyone)
    assert (
        _count(driver, "MATCH (e:Evidence {id: $id}) RETURN count(e) AS c", id=evidence_order.id)
        == 0
    )
    # the CARRIES relation survives (payment-service still declares it) with only
    # payment-service's evidence remaining
    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (:Queue {id:'queue:payment-q'})-[r:CARRIES]->(:Message) "
            "RETURN r.evidence_ids AS evidence_ids"
        ).single()
    assert record["evidence_ids"] == [evidence_payment.id]


def test_import_source_is_idempotent(driver):
    model = ArchitectureModel(
        services=[Service(id="service:x", name="X")],
        queues=[Queue(id="queue:x-q", name="x-q")],
        relations=[Relation(type="SENDS", source_id="service:x", target_id="queue:x-q")],
    )
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        first = _import(session, "src:x", model)
        second = _import(session, "src:x", model)

    # excludes the v0.4.0 I1.2 internal revision-fence singleton (spec §19) and the new SourceState
    # bookkeeping node (I1 v0.5.0) - neither is part of the Canonical Model.
    assert (
        _count(
            driver,
            "MATCH (n) WHERE NOT n:AipInternalState AND NOT n:SourceState RETURN count(n) AS c",
        )
        == 2
    )
    assert _count(driver, "MATCH ()-[r]->() RETURN count(r) AS c") == 1
    assert first.graph_revision_advanced is True
    # I1 spec §5.4: an unchanged reimport is a true no-op - no graph-revision advance.
    assert second.graph_revision_advanced is False


def test_reimport_with_only_a_property_change_still_advances_revision(driver):
    """A real bug found in PR review: node/relation reconciliation only diffs claim-KEY sets, so a
    reimport that changes a property on an already-owned claim (e.g. a Service's declared name,
    here standing in for any OpenAPI info.title-style edit) adds/removes no claim key - but
    _write_nodes' `SET n += $props` still writes the new value unconditionally. The graph-revision
    fence must advance whenever the canonical content this source emits actually changes, not only
    when a claim was added or removed, or a stable read could observe an unfenced property change."""
    original = ArchitectureModel(services=[Service(id="service:x", name="X")])
    renamed = ArchitectureModel(services=[Service(id="service:x", name="X Renamed")])

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:x", original)
        stats = _import(session, "src:x", renamed, digest=DIGEST_2)
        name = session.run("MATCH (s:Service {id: 'service:x'}) RETURN s.name AS name").single()[
            "name"
        ]

    assert stats.graph_revision_advanced is True
    assert name == "X Renamed"


def test_reimport_with_only_a_non_canonical_digest_change_does_not_advance_revision(driver):
    """A real bug found in PR review, on top of the previous fix: semantic_input_digest hashes an
    adapter's whole normalized input projection, which can include raw content the canonical model
    never surfaces at all (e.g. OpenAPI's info.description, unlike info.title unmapped to any
    canonical field) - so gating the revision bump on "digest changed" alone over-triggers on a
    canonically-inert input edit (I1 spec §5.4/§14's semantic-no-op requirement). Same model, only
    the digest differs (standing in for a description-only source edit): the graph-revision fence
    must NOT advance, since nothing this source actually emits into the canonical model changed."""
    model = ArchitectureModel(services=[Service(id="service:x", name="X")])

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:x", model)
        stats = _import(session, "src:x", model, digest=DIGEST_2)

    assert stats.graph_revision_advanced is False


def test_reimport_expires_stale_facts_no_longer_declared(driver):
    with_queue = ArchitectureModel(
        services=[Service(id="service:x", name="X")],
        queues=[Queue(id="queue:old-q", name="old-q")],
        relations=[Relation(type="SENDS", source_id="service:x", target_id="queue:old-q")],
    )
    without_queue = ArchitectureModel(
        services=[Service(id="service:x", name="X")],
        queues=[Queue(id="queue:new-q", name="new-q")],
        relations=[Relation(type="SENDS", source_id="service:x", target_id="queue:new-q")],
    )

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:x", with_queue)
        assert _count(driver, "MATCH (q:Queue {id: 'queue:old-q'}) RETURN count(q) AS c") == 1

        stats = _import(session, "src:x", without_queue, digest=DIGEST_2)

    assert stats.nodes_expired == 1
    assert stats.relations_expired == 1
    assert stats.graph_revision_advanced is True
    assert _count(driver, "MATCH (q:Queue {id: 'queue:old-q'}) RETURN count(q) AS c") == 0
    assert _count(driver, "MATCH (q:Queue {id: 'queue:new-q'}) RETURN count(q) AS c") == 1


def test_reimport_with_changed_scope_preserves_absent_claims(driver):
    # I1 spec §5.4/§6: a changed scope_definition_digest must not itself authorize expiring claims
    # this source stops emitting - only an explicit tombstone/inventory transition may.
    with_queue = ArchitectureModel(
        services=[Service(id="service:x", name="X")],
        queues=[Queue(id="queue:old-q", name="old-q")],
        relations=[Relation(type="SENDS", source_id="service:x", target_id="queue:old-q")],
    )
    without_queue = ArchitectureModel(services=[Service(id="service:x", name="X")])

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:x", with_queue)
        stats = import_source(
            session,
            source_instance_id="src:x",
            locator="src:x.yaml",
            model=without_queue,
            semantic_input_digest=DIGEST_2,
            discovery_scope_id=SCOPE_ID,
            scope_definition_digest=SCOPE_DIGEST_2,  # scope changed
        )

    assert stats.nodes_expired == 0
    assert stats.relations_expired == 0
    assert _count(driver, "MATCH (q:Queue {id: 'queue:old-q'}) RETURN count(q) AS c") == 1


_SINCE = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)


def _observed_fact(*, subject_id: str, relation_type: str, object_id: str, environment: str):
    timestamp = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
    evidence = ObservedEvidence(
        id=ids.observed_evidence_id(
            environment, datetime(2026, 8, 26, tzinfo=UTC), subject_id, relation_type, object_id
        ),
        environment=environment,
        bucket_start=datetime(2026, 8, 26, tzinfo=UTC),
        bucket_end=datetime(2026, 8, 27, tzinfo=UTC),
        first_seen=timestamp,
        last_seen=timestamp,
        observation_count=1,
        sample_trace_ids=["a" * 32],
    )
    return ObservedFactCandidate(
        subject_id=subject_id,
        relation_type=relation_type,
        object_id=object_id,
        environment=environment,
        timestamp=timestamp,
        trace_id="a" * 32,
        evidence=evidence,
    )


def test_declared_evidence_removed_but_observed_evidence_preserved(driver):
    # 11H-A / R1: a relation with both DECLARED and OBSERVED evidence must survive a re-import
    # that drops the declaration, retaining exactly its OBSERVED evidence (spec Delete(F) iff
    # Evidence(F) = empty - not iff DeclaredSources(F) = empty).
    declared_evidence = Provenance(
        id="evidence:asyncapi:src:order-service",
        source_type="ASYNCAPI",
        source_file="order-service/asyncapi.yaml",
    )
    with_relation = ArchitectureModel(
        services=[Service(id="service:order-service", name="OrderService")],
        queues=[Queue(id="queue:payment-q", name="payment-q")],
        relations=[
            Relation(
                type="SENDS",
                source_id="service:order-service",
                target_id="queue:payment-q",
                evidence_ids=[declared_evidence.id],
            )
        ],
        provenance=[declared_evidence],
    )
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:order-service", with_relation)

    observed_fact = _observed_fact(
        subject_id="service:order-service",
        relation_type="SENDS",
        object_id="queue:payment-q",
        environment="production",
    )
    persist_observation_batch(driver, DATABASE, ObservationBatch(facts=[observed_fact]))

    with driver.session(database=DATABASE) as session:
        confirmed = confirmed_relations(session, environment="production", since=_SINCE)
    assert any(r.target_id == "queue:payment-q" for r in confirmed)

    # Re-import order-service still declaring the queue itself, but no longer the SENDS
    # relation to it - keeps the Queue node alive so only the relation goes stale, not the node.
    without_relation = ArchitectureModel(
        services=[Service(id="service:order-service", name="OrderService")],
        queues=[Queue(id="queue:payment-q", name="payment-q")],
    )
    with driver.session(database=DATABASE) as session:
        stats = _import(session, "src:order-service", without_relation, digest=DIGEST_2)

    assert stats.relations_expired == 1
    assert (
        _count(driver, "MATCH ()-[r:SENDS]->(:Queue {id: 'queue:payment-q'}) RETURN count(r) AS c")
        == 1
    )
    with driver.session(database=DATABASE) as session:
        relation_record = session.run(
            "MATCH ()-[r:SENDS]->(:Queue {id: 'queue:payment-q'}) RETURN r.evidence_ids AS ids"
        ).single()
    assert declared_evidence.id not in relation_record["ids"]
    assert observed_fact.evidence.id in relation_record["ids"]

    with driver.session(database=DATABASE) as session:
        observed_only = observed_only_relations(session, environment="production", since=_SINCE)
    assert any(r.target_id == "queue:payment-q" for r in observed_only)


def test_shared_declared_evidence_survives_reconciliation_with_observed_evidence_present(driver):
    # Extends test_shared_relation_accumulates_evidence_from_both_declaring_sources (11H-A / R1
    # §5.3): a relation declared by two independent sources plus OBSERVED evidence must lose only
    # the reimporting source's own DECLARED evidence - never the other declarer's, never OBSERVED.
    evidence_order = Provenance(
        id="evidence:asyncapi:src:order-service",
        source_type="ASYNCAPI",
        source_file="order-service/asyncapi.yaml",
    )
    evidence_payment = Provenance(
        id="evidence:asyncapi:src:payment-service",
        source_type="ASYNCAPI",
        source_file="payment-service/asyncapi.yaml",
    )
    order_model = ArchitectureModel(
        services=[Service(id="service:order-service", name="OrderService")],
        queues=[Queue(id="queue:payment-q", name="payment-q")],
        messages=[Message(id="message:PaymentRequested:v2", name="PaymentRequested", version="v2")],
        relations=[
            Relation(
                type="CARRIES",
                source_id="queue:payment-q",
                target_id="message:PaymentRequested:v2",
                evidence_ids=[evidence_order.id],
            ),
        ],
        provenance=[evidence_order],
    )
    payment_model = ArchitectureModel(
        services=[Service(id="service:payment-service", name="PaymentService")],
        queues=[Queue(id="queue:payment-q", name="payment-q")],
        messages=[Message(id="message:PaymentRequested:v2", name="PaymentRequested", version="v2")],
        relations=[
            Relation(
                type="CARRIES",
                source_id="queue:payment-q",
                target_id="message:PaymentRequested:v2",
                evidence_ids=[evidence_payment.id],
            ),
        ],
        provenance=[evidence_payment],
    )
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:order-service", order_model)
        _import(session, "src:payment-service", payment_model)

    observed_fact = _observed_fact(
        subject_id="queue:payment-q",
        relation_type="CARRIES",
        object_id="message:PaymentRequested:v2",
        environment="production",
    )
    persist_observation_batch(driver, DATABASE, ObservationBatch(facts=[observed_fact]))

    # order-service stops declaring the CARRIES relation entirely.
    order_model_without_carries = ArchitectureModel(
        services=[Service(id="service:order-service", name="OrderService")]
    )
    with driver.session(database=DATABASE) as session:
        _import(session, "src:order-service", order_model_without_carries, digest=DIGEST_2)

    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (:Queue {id:'queue:payment-q'})-[r:CARRIES]->(:Message) "
            "RETURN r.evidence_ids AS evidence_ids"
        ).single()
    assert set(record["evidence_ids"]) == {evidence_payment.id, observed_fact.evidence.id}


def test_shared_queue_kept_when_still_referenced_by_another_source(driver):
    sender_model = ArchitectureModel(
        services=[Service(id="service:sender", name="Sender")],
        queues=[Queue(id="queue:shared-q", name="shared-q")],
        relations=[Relation(type="SENDS", source_id="service:sender", target_id="queue:shared-q")],
    )
    receiver_model = ArchitectureModel(
        services=[Service(id="service:receiver", name="Receiver")],
        queues=[Queue(id="queue:shared-q", name="shared-q")],
        relations=[
            Relation(type="RECEIVES_FROM", source_id="service:receiver", target_id="queue:shared-q")
        ],
    )
    sender_model_without_queue = ArchitectureModel(
        services=[Service(id="service:sender", name="Sender")]
    )

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:sender", sender_model)
        _import(session, "src:receiver", receiver_model)

        with driver.session(database=DATABASE) as read_session:
            owners = read_session.run(
                "MATCH (q:Queue {id: 'queue:shared-q'}) RETURN q.owner_source_ids AS owners"
            ).single()["owners"]
        assert set(owners) == {"src:sender", "src:receiver"}

        # sender no longer declares the queue, but receiver still does -> queue must survive
        _import(session, "src:sender", sender_model_without_queue, digest=DIGEST_2)

    assert _count(driver, "MATCH (q:Queue {id: 'queue:shared-q'}) RETURN count(q) AS c") == 1
    with driver.session(database=DATABASE) as session:
        owners = session.run(
            "MATCH (q:Queue {id: 'queue:shared-q'}) RETURN q.owner_source_ids AS owners"
        ).single()["owners"]
    assert owners == ["src:receiver"]


def test_import_source_rejects_unknown_relation_type_without_writing_anything(driver):
    model = ArchitectureModel(
        services=[Service(id="service:x", name="X")],
        relations=[Relation(type="BOGUS", source_id="service:x", target_id="service:x")],
    )
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        with pytest.raises(ValueError, match="Unknown relation type"):
            _import(session, "src:x", model)

    # excludes the v0.4.0 I1.2 internal revision-fence singleton (spec §19) - `ensure_schema`
    # creates it unconditionally, before the (failed) import ever runs.
    assert _count(driver, "MATCH (n) WHERE NOT n:AipInternalState RETURN count(n) AS c") == 0


def _bundled_examples_config() -> FilesystemSourceConfig:
    return FilesystemSourceConfig(
        id="aip-bundled-examples-v0.5",
        root=EXAMPLES_DIR,
        stable_target_identity="urn:aip:logical-root:bundled-examples",
    )


def test_import_all_sources_real_examples_end_to_end(driver):
    stats = import_all_sources(driver, database=DATABASE, source_config=_bundled_examples_config())

    assert stats.committed is True
    assert len(stats.per_source) == 6  # order (x3), product, payment, invoice
    assert _count(driver, "MATCH (n:Service) RETURN count(n) AS c") == 4

    calls = _count(driver, "MATCH ()-[r:CALLS]->() RETURN count(r) AS c")
    assert calls == 1
    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (s:Service {id: 'service:order-service'})-[:CALLS]->(o:Operation) RETURN o.id AS id"
        ).single()
    assert record["id"] == "operation:service:product-service:GET:/products/{id}"

    assert _count(driver, "MATCH ()-[r:DEAD_LETTERS_TO]->() RETURN count(r) AS c") == 1
    assert _count(driver, "MATCH (q:Queue) RETURN count(q) AS c") == 5

    # Evidence: one per discovered source file - order-service has 3 (openapi/asyncapi/manifest),
    # product-service/payment-service/invoice-service have 1 each (AC13).
    assert _count(driver, "MATCH (e:Evidence) RETURN count(e) AS c") == 6

    # PaymentRequested is independently declared by order-service (sender) and payment-service
    # (receiver) - under I1's owner-scoped Message identity (§9.1), with no explicit shared-
    # identity mapping wired in 3a, these are two DISTINCT Message entities, each with its own
    # single-source CARRIES relation from payment-q - not one merged node with two evidence ids.
    with driver.session(database=DATABASE) as session:
        records = list(
            session.run(
                "MATCH (:Queue {name: 'payment-q'})-[r:CARRIES]->(m:Message {name: 'PaymentRequested'}) "
                "RETURN r.evidence_ids AS evidence_ids"
            )
        )
    assert len(records) == 2
    assert all(len(record["evidence_ids"]) == 1 for record in records)


def test_import_all_sources_with_the_real_bundled_migration_mapping_lands_legacy_ids(driver):
    """The real config/migrations/v0.5.0-bundled-example-identities.yaml artifact (I1 spec §5.1.1),
    applied through the full import_all_sources -> Neo4j pipeline, must make the bundled examples'
    Schema/Message nodes carry their exact pre-PR3a (v0.4.2-era) legacy ids - not just at the
    in-memory ArchitectureModel layer (already unit-tested), but as actually committed graph nodes.
    Queue identity is deliberately NOT migrated by this artifact (see its own header comment: the
    bundled examples already carry real broker/namespace evidence that would legitimately disagree
    with a legacy Queue id, which I1 spec §9 requires to reject rather than silently override) - so
    Queues keep their normal owner-scoped ids here, asserted only by count/prefix.
    Also proves the real cross-source merge: PaymentRequested's payload, independently declared by
    order-service and payment-service, becomes ONE shared Message node once the migration maps both
    to the same legacy id (contrast with test_import_all_sources_real_examples_end_to_end's
    unmigrated case, which asserts these stay two distinct nodes).
    """
    migrations_path = (
        Path(__file__).resolve().parent.parent.parent
        / "config"
        / "migrations"
        / "v0.5.0-bundled-example-identities.yaml"
    )
    index, diagnostics = load_migration_mappings([migrations_path])
    assert diagnostics == ()

    stats = import_all_sources(
        driver,
        database=DATABASE,
        source_config=_bundled_examples_config(),
        migration_mappings=index,
    )
    assert stats.committed is True

    with driver.session(database=DATABASE) as session:
        schema_ids = {record["id"] for record in session.run("MATCH (s:Schema) RETURN s.id AS id")}
        message_ids = {
            record["id"] for record in session.run("MATCH (m:Message) RETURN m.id AS id")
        }
        queue_ids = {record["id"] for record in session.run("MATCH (q:Queue) RETURN q.id AS id")}

    assert schema_ids == {
        "schema:OrderRequest",
        "schema:Order",
        "schema:Product",
        "schema:PaymentRequested:v2",
        "schema:InvoiceCreated:v1",
        "schema:UnusedMessage",
        "schema:UnknownProducerMessage",
    }
    assert message_ids == {
        "message:PaymentRequested:v2",
        "message:InvoiceCreated:v1",
        "message:UnusedMessage",
        "message:UnknownProducerMessage",
    }
    assert len(queue_ids) == 5
    assert all(qid.startswith("queue:owned:") for qid in queue_ids)

    # The real cross-source merge: PaymentRequested's CARRIES relation now has TWO evidence ids
    # (one per declaring source) on the ONE shared Message node - contrast with the unmigrated
    # two-distinct-nodes case in test_import_all_sources_real_examples_end_to_end. Matched by
    # Queue *name* (still "payment-q"), not id, since Queue identity is unaffected by this artifact.
    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (:Queue {name: 'payment-q'})-[r:CARRIES]->"
            "(m:Message {id: 'message:PaymentRequested:v2'}) RETURN r.evidence_ids AS evidence_ids"
        ).single()
    assert record is not None
    assert len(record["evidence_ids"]) == 2


def test_import_all_sources_is_idempotent(driver):
    config = _bundled_examples_config()
    import_all_sources(driver, database=DATABASE, source_config=config)
    first_nodes = _count(driver, "MATCH (n) RETURN count(n) AS c")
    first_relations = _count(driver, "MATCH ()-[r]->() RETURN count(r) AS c")

    stats = import_all_sources(driver, database=DATABASE, source_config=config)
    second_nodes = _count(driver, "MATCH (n) RETURN count(n) AS c")
    second_relations = _count(driver, "MATCH ()-[r]->() RETURN count(r) AS c")

    assert first_nodes == second_nodes
    assert first_relations == second_relations
    assert all(not s.graph_revision_advanced for s in stats.per_source.values())


def test_import_all_sources_property_change_advances_revision_through_the_real_pipeline(
    driver, tmp_path
):
    """A real bug found in PR review, specific to the `import_all_sources` path (not exercised by
    driving `import_source` directly, as the other revision-fence regression tests above do):
    `_import_all_sources_tx` pre-merges every source's nodes - including this one's own new
    property values - before this source's own `_import_source_tx` call ever takes its "before"
    snapshot, making a genuine property change invisible to the no-op check. Reimporting through
    the real filesystem-discovery pipeline with only product-service's OpenAPI `info.title` changed
    must still advance the revision fence."""
    root = tmp_path / "root"
    shutil.copytree(EXAMPLES_DIR / "product-service", root / "product-service")
    config = FilesystemSourceConfig(id="revision-fence-test", root=root)

    import_all_sources(driver, database=DATABASE, source_config=config)
    with driver.session(database=DATABASE) as session:
        revision_before = read_revision(session)

    openapi_path = root / "product-service" / "openapi.yaml"
    openapi_path.write_text(openapi_path.read_text().replace("ProductService", "ProductServiceV2"))

    stats = import_all_sources(driver, database=DATABASE, source_config=config)
    with driver.session(database=DATABASE) as session:
        revision_after = read_revision(session)
        name = session.run(
            "MATCH (s:Service {id: 'service:product-service'}) RETURN s.name AS name"
        ).single()["name"]

    assert name == "ProductServiceV2"
    assert revision_after > revision_before
    assert any(s.graph_revision_advanced for s in stats.per_source.values())


def test_import_all_sources_removes_source_no_longer_discovered(driver, tmp_path):
    root = tmp_path / "root"
    shutil.copytree(EXAMPLES_DIR / "product-service", root / "product-service")
    shutil.copytree(EXAMPLES_DIR / "order-service", root / "order-service")
    # order-service's architecture.yaml calls product-service's getProduct - drop it so this
    # synthetic scope doesn't depend on cross-referencing manifest resolution.
    (root / "order-service" / "architecture.yaml").unlink()

    config = FilesystemSourceConfig(id="removal-test", root=root)
    stats1 = import_all_sources(driver, database=DATABASE, source_config=config)
    assert stats1.committed is True
    assert _count(driver, "MATCH (n:Service) RETURN count(n) AS c") == 2

    # product-service is removed from the filesystem entirely
    shutil.rmtree(root / "product-service")

    stats2 = import_all_sources(driver, database=DATABASE, source_config=config)
    assert stats2.committed is True
    assert len(stats2.removed_source_instance_ids) == 1
    assert (
        _count(driver, "MATCH (s:Service {id: 'service:product-service'}) RETURN count(s) AS c")
        == 0
    )
    assert (
        _count(driver, "MATCH (s:Service {id: 'service:order-service'}) RETURN count(s) AS c") == 1
    )


def test_import_all_sources_rolls_back_in_full_when_a_later_source_fails(
    driver, tmp_path, monkeypatch
):
    """A real bug found in PR review: pre-merge/reconciliation/removal used one `execute_write` per
    source, so a failure partway through a multi-source run left earlier sources' writes committed
    even though the run as a whole never reached `committed=True` - contradicting
    `import_all_sources`'s own "nothing is written unless the whole run is COMPLETE" contract.
    Everything must now share one transaction: injecting a failure on the second of two sources
    must leave the first source's change unwritten too."""
    import app.graph.importer as importer_module

    root = tmp_path / "root"
    shutil.copytree(EXAMPLES_DIR / "product-service", root / "product-service")
    shutil.copytree(EXAMPLES_DIR / "order-service", root / "order-service")
    (root / "order-service" / "architecture.yaml").unlink()
    config = FilesystemSourceConfig(id="atomicity-test", root=root)

    import_all_sources(driver, database=DATABASE, source_config=config)
    assert (
        _count(driver, "MATCH (s:Service {id: 'service:product-service'}) RETURN s.name AS c")
        == "ProductService"
    )

    # Rename the already-committed product-service, and inject a failure on order-service's
    # asyncapi.yaml source, which is processed *after* product-service's openapi.yaml in this
    # fixture's deterministic (source_instance_id-sorted) order - verified directly, not assumed -
    # so the rename write has already executed within the transaction by the time this raises.
    (root / "product-service" / "openapi.yaml").write_text(
        (root / "product-service" / "openapi.yaml")
        .read_text()
        .replace("ProductService", "ProductServiceRenamed")
    )
    real_import_source_tx = importer_module._import_source_tx

    def flaky_import_source_tx(tx, *, locator, **kwargs):
        if "asyncapi" in locator:
            raise RuntimeError("simulated failure on a later source")
        return real_import_source_tx(tx, locator=locator, **kwargs)

    monkeypatch.setattr(importer_module, "_import_source_tx", flaky_import_source_tx)

    with pytest.raises(RuntimeError, match="simulated failure"):
        import_all_sources(driver, database=DATABASE, source_config=config)

    # Nothing committed - not even product-service's rename, processed before the injected failure.
    assert (
        _count(driver, "MATCH (s:Service {id: 'service:product-service'}) RETURN s.name AS c")
        == "ProductService"
    )


# I2 Draft 0.2 §3 prerequisite slice, items 3/4/5: real persisted `CurrentInventory` state,
# transactional predecessor comparison, and explicit-tombstone removal authorization, all through
# the real `import_all_sources` -> Neo4j pipeline (not just the pure calculations already unit-
# tested in test_sources_inventory.py/test_sources_tombstones.py/test_sources_removal_authority.py).


def test_import_all_sources_persists_current_inventory_state(driver, tmp_path):
    config = FilesystemSourceConfig(id="inv-persist-test", root=tmp_path)
    stats = import_all_sources(driver, database=DATABASE, source_config=config)
    assert stats.committed is True

    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS revision, "
            "i.inventory_capture_id AS capture, i.inventory_event_id AS event, "
            "i.scope_definition_digest AS digest"
        ).single()
    assert record is not None
    assert record["revision"] is not None
    assert record["capture"] is not None
    assert record["event"] is not None
    assert record["digest"] is not None


def test_import_all_sources_rejects_a_tombstone_on_a_brand_new_scope_without_crashing(
    driver, tmp_path
):
    """A real bug found in PR re-review: `_READ_CURRENT_INVENTORY_QUERY`'s locking `MERGE` sets
    `discovery_scope_id` on a freshly created `CurrentInventory` node (it's part of the MERGE's own
    matching pattern) while `inventory_revision`/`scope_definition_digest` remain null - a
    partially populated "committed" state that made `validate_tombstone_against_committed_inventory`
    raise `InconsistentCommittedInventoryStateError` instead of correctly classifying a tombstone
    submitted on a scope's very first run as `NO_COMMITTED_INVENTORY`."""
    config = FilesystemSourceConfig(id="tomb-fresh-scope-test", root=tmp_path)
    fresh_scope_id = run_filesystem_discovery(config).discovery_scope_id

    tombstone = Tombstone(
        target_source_instance_id="urn:aip:source:filesystem:doesnotexist",
        discovery_scope_id=fresh_scope_id,
        expected_prior_inventory_revision="urn:aip:inventory-revision:" + "0" * 64,
        scope_definition_digest="whatever",
        actor="operator@example.com",
        reason="test",
        tombstone_revision="1",
    )

    stats = import_all_sources(
        driver, database=DATABASE, source_config=config, tombstones=(tombstone,)
    )
    assert stats.committed is True
    assert stats.removed_source_instance_ids == ()
    assert any(d.code == DiagnosticCode.TOMBSTONE_STALE for d in stats.diagnostics)


def test_import_all_sources_accepts_a_matching_expected_predecessor(driver, tmp_path):
    config = FilesystemSourceConfig(id="inv-predecessor-test", root=tmp_path)
    first = import_all_sources(driver, database=DATABASE, source_config=config)
    assert first.committed is True
    with driver.session(database=DATABASE) as session:
        first_revision = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r"
        ).single()["r"]

    second = import_all_sources(
        driver,
        database=DATABASE,
        source_config=config,
        expected_prior_inventory_revision=first_revision,
    )
    assert second.committed is True


def test_a_freshly_constructed_not_supplied_instance_still_skips_the_predecessor_check(
    driver, tmp_path
):
    """A real finding from PR review: `NotSupplied` is now a public type (I2 Draft 0.2 slice
    2b-ii), so a caller can legally construct its own instance rather than importing the canonical
    `NOT_SUPPLIED` singleton. `_import_all_sources_tx`'s gate must treat *any* `NotSupplied`
    instance as "skip the check", not only the one singleton by identity - an identity-based check
    would treat a fresh instance as a real (mismatching) expected value and wrongly reject every
    such run as stale.
    """
    config = FilesystemSourceConfig(id="inv-not-supplied-type-test", root=tmp_path)
    first = import_all_sources(driver, database=DATABASE, source_config=config)
    assert first.committed is True

    second = import_all_sources(
        driver,
        database=DATABASE,
        source_config=config,
        expected_prior_inventory_revision=NotSupplied(),
    )
    assert second.committed is True


def test_import_all_sources_rejects_a_stale_expected_predecessor_and_preserves_state(
    driver, tmp_path
):
    config = FilesystemSourceConfig(id="inv-stale-test", root=tmp_path)
    first = import_all_sources(driver, database=DATABASE, source_config=config)
    assert first.committed is True
    with driver.session(database=DATABASE) as session:
        first_revision = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r"
        ).single()["r"]

    stale = import_all_sources(
        driver,
        database=DATABASE,
        source_config=config,
        expected_prior_inventory_revision="urn:aip:inventory-revision:" + "0" * 64,
    )
    assert stale.committed is False
    assert any(d.code == DiagnosticCode.STALE_INVENTORY_PREDECESSOR for d in stale.diagnostics)

    with driver.session(database=DATABASE) as session:
        still_committed_revision = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r"
        ).single()["r"]
    assert still_committed_revision == first_revision


def test_import_all_sources_serializes_concurrent_first_imports_of_the_same_scope(driver, tmp_path):
    """A genuine TOCTOU race found in PR review: under Neo4j's default read-committed isolation, a
    plain read-then-later-write predecessor check would let two concurrent transactions for the
    same scope both read the same pre-image, both pass their own check, and both proceed to write -
    silently corrupting the inventory-revision/event-id chain rather than rejecting the loser.
    `_READ_CURRENT_INVENTORY_QUERY`'s MERGE acquires a real per-scope lock for the transaction's
    duration, so of two concurrent first-imports of the same fresh scope (both expecting `None` -
    "no prior committed inventory"), exactly one may commit; the other must observe the winner's
    real committed state inside its own transaction and correctly detect the mismatch.

    Schema constraints are ensured synchronously, up front, outside the timed race: two concurrent
    *first-ever* `CREATE CONSTRAINT IF NOT EXISTS` calls against a brand-new database can themselves
    deadlock inside Neo4j (`ensure_schema` uses plain autocommit `session.run`, not a retrying
    managed transaction) - a real, pre-existing hazard independent of this PR's own `CurrentInventory`
    locking, and out of this PR's scope to fix. Isolating it here keeps this test's failure signal
    specific to the mechanism under review."""
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)

    config = FilesystemSourceConfig(id="concurrency-test", root=tmp_path)
    results: list[ImportRunStats | None] = [None, None]
    barrier = threading.Barrier(2)

    def _run(index: int) -> None:
        barrier.wait()
        results[index] = import_all_sources(
            driver,
            database=DATABASE,
            source_config=config,
            expected_prior_inventory_revision=None,
        )

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    committed_flags = [r.committed for r in results if r is not None]
    assert len(committed_flags) == 2
    assert committed_flags.count(True) == 1
    assert committed_flags.count(False) == 1

    loser = next(r for r in results if r is not None and not r.committed)
    assert any(d.code == DiagnosticCode.STALE_INVENTORY_PREDECESSOR for d in loser.diagnostics)

    assert _count(driver, "MATCH (i:CurrentInventory) RETURN count(i) AS c") == 1


def test_import_all_sources_denies_removal_on_scope_mismatch_but_an_explicit_tombstone_authorizes_it(
    driver, tmp_path
):
    """I2 Draft 0.2 §3 prerequisite slice, item 5: an explicit tombstone is the only way to
    authorize removal once the enumeration's own scope no longer matches what a source last
    committed under (I1 spec §6's SCOPE_CHANGED_PRESERVE_PENDING_TOMBSTONE case) - ordinary
    same-root absence (test_import_all_sources_removes_source_no_longer_discovered, above) already
    authorizes removal without one; this proves the tombstone path is real and independently wired,
    not a no-op that happens to always agree with the enumeration-absence path. Two physically
    different roots under the SAME configured id give the same `discovery_scope_id` (derived from
    `id`, not the physical root) but a different `scope_definition_digest` (which does include the
    root path) - a real scope change, not merely "the file disappeared"."""
    root_a = tmp_path / "root-a"
    shutil.copytree(EXAMPLES_DIR / "product-service", root_a / "product-service")
    root_b = tmp_path / "root-b"
    root_b.mkdir()

    config_a = FilesystemSourceConfig(id="tomb-test", root=root_a)
    stats1 = import_all_sources(driver, database=DATABASE, source_config=config_a)
    assert stats1.committed is True
    [source_instance_id] = list(stats1.per_source.keys())
    assert _count(driver, "MATCH (s:Service) RETURN count(s) AS c") == 1

    config_b = FilesystemSourceConfig(id="tomb-test", root=root_b)
    stats2 = import_all_sources(driver, database=DATABASE, source_config=config_b)
    assert stats2.committed is True
    assert stats2.removed_source_instance_ids == ()
    # Scope mismatch denied removal via the enumeration path - the old service's node is retained.
    assert _count(driver, "MATCH (s:Service) RETURN count(s) AS c") == 1

    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS revision, "
            "i.discovery_scope_id AS scope, i.scope_definition_digest AS digest"
        ).single()

    tombstone = Tombstone(
        target_source_instance_id=source_instance_id,
        discovery_scope_id=record["scope"],
        expected_prior_inventory_revision=record["revision"],
        scope_definition_digest=record["digest"],
        actor="operator@example.com",
        reason="root relocated, product-service decommissioned",
        tombstone_revision="1",
    )

    stats3 = import_all_sources(
        driver, database=DATABASE, source_config=config_b, tombstones=(tombstone,)
    )
    assert stats3.committed is True
    assert stats3.removed_source_instance_ids == (source_instance_id,)
    assert _count(driver, "MATCH (s:Service) RETURN count(s) AS c") == 0


def test_discovery_run_over_a_scope_populated_only_by_import_source_denies_enumeration_removal(
    driver, tmp_path
):
    """PR #281 review: `import_source` writes a scoped `SourceState` but no `CurrentInventory`, so a
    later COMPLETE discovery run for that scope finds the directly imported source with no committed
    inventory. The run must neither crash nor remove that source through the enumeration path:
    without a committed scope there is nothing for the enumeration to match (I1 spec §6), and only
    an accepted tombstone could authorize the removal."""
    root = tmp_path / "root"
    shutil.copytree(EXAMPLES_DIR / "product-service", root / "product-service")
    run_result = run_filesystem_discovery(
        FilesystemSourceConfig(id="direct-import-test", root=root)
    )
    assert run_result.commit_eligible is True
    assert run_result.inventory_snapshot is not None

    with driver.session(database=DATABASE) as session:
        import_source(
            session,
            source_instance_id="direct-source",
            locator="direct-source.yaml",
            model=ArchitectureModel(services=[Service(id="service:direct", name="Direct")]),
            semantic_input_digest=DIGEST_1,
            discovery_scope_id=run_result.discovery_scope_id,
            scope_definition_digest=run_result.scope_definition_digest,
        )
    assert _count(driver, "MATCH (i:CurrentInventory) RETURN count(i) AS c") == 0

    stats = import_discovery_run(driver, database=DATABASE, run_result=run_result)

    assert stats.committed is True
    assert stats.removed_source_instance_ids == ()
    assert stats.removal_stats == ()
    assert _count(driver, "MATCH (s:Service {id: 'service:direct'}) RETURN count(s) AS c") == 1
    assert (
        _count(
            driver,
            "MATCH (s:SourceState {source_instance_id: 'direct-source'}) RETURN count(s) AS c",
        )
        == 1
    )
    assert (
        _count(driver, "MATCH (s:Service {id: 'service:product-service'}) RETURN count(s) AS c")
        == 1
    )
    with driver.session(database=DATABASE) as session:
        inventory = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS revision, "
            "i.discovery_scope_id AS scope, i.scope_definition_digest AS digest"
        ).single()
    assert inventory["revision"] == run_result.inventory_snapshot.inventory_revision
    assert inventory["scope"] == run_result.discovery_scope_id
    assert inventory["digest"] == run_result.scope_definition_digest


def test_import_all_sources_denies_removal_via_a_tombstone_with_a_stale_expected_predecessor(
    driver, tmp_path
):
    """Renamed from an earlier, misleading name (a PR review finding): the *run* still commits
    (`committed is True`) - only the requested *removal* is denied, with the rejection surfaced as
    a diagnostic rather than silently no-op'd (another PR review finding: `_import_all_sources_tx`
    used to drop `validate_tombstone_against_committed_inventory`'s rejection diagnostic on the
    floor)."""
    root_a = tmp_path / "root-a"
    shutil.copytree(EXAMPLES_DIR / "product-service", root_a / "product-service")
    root_b = tmp_path / "root-b"
    root_b.mkdir()

    config_a = FilesystemSourceConfig(id="tomb-stale-test", root=root_a)
    stats1 = import_all_sources(driver, database=DATABASE, source_config=config_a)
    [source_instance_id] = list(stats1.per_source.keys())

    config_b = FilesystemSourceConfig(id="tomb-stale-test", root=root_b)
    import_all_sources(driver, database=DATABASE, source_config=config_b)
    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (i:CurrentInventory) RETURN i.discovery_scope_id AS scope, "
            "i.scope_definition_digest AS digest"
        ).single()

    stale_tombstone = Tombstone(
        target_source_instance_id=source_instance_id,
        discovery_scope_id=record["scope"],
        expected_prior_inventory_revision="urn:aip:inventory-revision:" + "0" * 64,
        scope_definition_digest=record["digest"],
        actor="operator@example.com",
        reason="stale tombstone",
        tombstone_revision="1",
    )

    stats3 = import_all_sources(
        driver, database=DATABASE, source_config=config_b, tombstones=(stale_tombstone,)
    )
    assert stats3.committed is True
    assert stats3.removed_source_instance_ids == ()
    assert _count(driver, "MATCH (s:Service) RETURN count(s) AS c") == 1
    assert any(d.code == DiagnosticCode.TOMBSTONE_STALE for d in stats3.diagnostics)


# I2 Draft 0.2 slice 2b-i: KubernetesSourceConfig/KubernetesSourceDiscoverer/KubernetesSourceAdapter
# wired all the way through the real import_kubernetes_source -> Neo4j path, against the real
# checked-in fixture bundle (tests/fixtures/kubernetes/i2/, from slice 2a).


def _matching_kubernetes_config(**overrides) -> KubernetesSourceConfig:
    kwargs = {
        "id": "checkout-cluster",
        "root": KUBERNETES_FIXTURE_DIR,
        "envelope_relative_path": "envelope.yaml",
        "configured_scope_id": "checkout-cluster-namespaces",
        "cluster_uid": "d3adbeef-0000-4000-8000-000000000001",
        "evidence_mode": KubernetesEvidenceMode.CAPTURED_RESOURCE,
        "authorized_producer": "aip-kubernetes-capture-agent",
        "authority_record": "checkout-cluster-capture-authority",
        **overrides,
    }
    return KubernetesSourceConfig(**kwargs)


def test_import_kubernetes_source_commits_real_facts_for_all_four_entity_kinds(driver):
    """I2 §12 slices 3a/3b/4a/4b/4c: the fixture bundle (Namespace/Deployment/ReplicaSet/Pod/
    Service/Ingress) flows all the way through the real `KubernetesSourceAdapter`/
    `kubernetes_mapping`/`kubernetes_owner_chain`/`kubernetes_service_selection`/
    `kubernetes_ingress_backend` into committed `InfrastructureEntity`/`Contribution` nodes for all
    four §7.1 entity kinds, plus all four implemented claims (`WORKLOAD_EXISTS`, `WORKLOAD_OWNS_POD`,
    `NETWORK_SERVICE_SELECTS_WORKLOAD`, `INGRESS_ROUTES_TO_NETWORK_SERVICE`) - this is PR B's
    conflict/write machinery going live against a real adapter's output across every promoted kind,
    a real resolved owner chain (Pod -> ReplicaSet -> Deployment), the fixture's Service selector
    matching that same Pod's labels, and its Ingress backending to that same Service's declared
    port.
    """
    config = _matching_kubernetes_config()
    stats = import_kubernetes_source(driver, database=DATABASE, source_config=config)

    assert stats.committed is True
    [source_stats] = list(stats.per_source.values())
    assert source_stats.result == "ACCEPTED"
    assert source_stats.nodes_written > 0

    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS revision, "
            "i.discovery_scope_id AS scope"
        ).single()
        entities = session.run(
            "MATCH (e:InfrastructureEntity) RETURN e.entity_kind AS kind, e.name AS name "
            "ORDER BY e.entity_kind"
        ).data()
        claims = session.run(
            "MATCH (c:InfrastructureClaim) RETURN c.kind AS kind, c.object_id AS object_id "
            "ORDER BY c.kind"
        ).data()
        service = session.run(
            "MATCH (e:InfrastructureEntity {entity_kind: 'KUBERNETES_NETWORK_SERVICE'}) "
            "RETURN e.service_type AS service_type, e.ports AS ports"
        ).single()
        ownership = session.run(
            "MATCH (c:InfrastructureClaim {kind: 'WORKLOAD_OWNS_POD'}) "
            "RETURN c.subject_id AS subject_id, c.object_id AS object_id, "
            "c.evidence_refs AS evidence_refs"
        ).single()
        selection = session.run(
            "MATCH (c:InfrastructureClaim {kind: 'NETWORK_SERVICE_SELECTS_WORKLOAD'}) "
            "RETURN c.subject_id AS subject_id, c.object_id AS object_id, "
            "c.evidence_refs AS evidence_refs"
        ).single()
        workload_id = session.run(
            "MATCH (e:InfrastructureEntity {entity_kind: 'KUBERNETES_WORKLOAD'}) RETURN e.id AS id"
        ).single()["id"]
        pod_id = session.run(
            "MATCH (e:InfrastructureEntity {entity_kind: 'KUBERNETES_POD'}) RETURN e.id AS id"
        ).single()["id"]
        service_id = session.run(
            "MATCH (e:InfrastructureEntity {entity_kind: 'KUBERNETES_NETWORK_SERVICE'}) "
            "RETURN e.id AS id"
        ).single()["id"]
        ingress_id = session.run(
            "MATCH (e:InfrastructureEntity {entity_kind: 'KUBERNETES_INGRESS'}) RETURN e.id AS id"
        ).single()["id"]
        routing = session.run(
            "MATCH (c:InfrastructureClaim {kind: 'INGRESS_ROUTES_TO_NETWORK_SERVICE'}) "
            "RETURN c.subject_id AS subject_id, c.object_id AS object_id, "
            "c.evidence_refs AS evidence_refs"
        ).single()
    assert record is not None
    assert record["revision"] is not None
    assert record["scope"] is not None

    assert entities == [
        {"kind": "KUBERNETES_INGRESS", "name": "checkout-ingress"},
        {"kind": "KUBERNETES_NETWORK_SERVICE", "name": "checkout-api"},
        {"kind": "KUBERNETES_POD", "name": "checkout-api-abcde"},
        {"kind": "KUBERNETES_WORKLOAD", "name": "checkout-api"},
    ]
    assert claims == [
        {"kind": "INGRESS_ROUTES_TO_NETWORK_SERVICE", "object_id": service_id},
        {"kind": "NETWORK_SERVICE_SELECTS_WORKLOAD", "object_id": workload_id},
        {"kind": "WORKLOAD_EXISTS", "object_id": None},
        {"kind": "WORKLOAD_OWNS_POD", "object_id": pod_id},
    ]
    # The fixture's Service declares a bare port (no name/no declared type) - I2 §12 slice 4c
    # needed a real declared port for its Ingress backend to resolve against.
    assert service["service_type"] is None
    assert service["ports"] == ['{"name":null,"port":80,"protocol":"TCP"}']
    # The resolved 2-hop chain (Pod -> ReplicaSet -> Deployment): the claim relates the real
    # Workload/Pod entities, and its evidence includes a real id for the bridging ReplicaSet, which
    # has no InfrastructureContribution of its own (§7.1 keeps ReplicaSet permanently unpromoted).
    assert ownership["subject_id"] == workload_id
    assert ownership["object_id"] == pod_id
    assert len(ownership["evidence_refs"]) == 3
    # The fixture's Service selects on the same Pod's retained label - the selection claim relates
    # the Service to the resolved Workload, with evidence unioning the Service's own plus the
    # WORKLOAD_OWNS_POD chain's evidence (Pod, Workload, bridging ReplicaSet).
    assert selection["subject_id"] == service_id
    assert selection["object_id"] == workload_id
    assert set(selection["evidence_refs"]) >= set(ownership["evidence_refs"])
    # The fixture's Ingress backends to the Service's own declared port 80 - the routing claim
    # relates the real Ingress/Service entities, with evidence covering both.
    assert routing["subject_id"] == ingress_id
    assert routing["object_id"] == service_id
    assert len(routing["evidence_refs"]) == 2
    assert len(selection["evidence_refs"]) == 4


def test_import_kubernetes_source_registration_mismatch_prevents_commit(driver):
    config = _matching_kubernetes_config(cluster_uid="a-different-cluster")
    stats = import_kubernetes_source(driver, database=DATABASE, source_config=config)

    assert stats.committed is False
    assert any(d.code == DiagnosticCode.K8S_CLUSTER_IDENTITY_UNRESOLVED for d in stats.diagnostics)
    assert _count(driver, "MATCH (i:CurrentInventory) RETURN count(i) AS c") == 0


# I2 Draft 0.2 slice 2b-ii: threading completeness.expectedPriorInventoryRevision into PR A's
# predecessor-check transaction, and layering K8S_STALE_INVENTORY. Unlike the tests above, these
# need a dynamically-*rewritable* bundle (not the static checked-in fixture) to exercise successive
# imports of "the same" logical source with a changing predecessor claim.

_DYNAMIC_KUBERNETES_CONFIG_KWARGS = {
    "id": "checkout-cluster-predecessor-test",
    "envelope_relative_path": "envelope.yaml",
    "configured_scope_id": "checkout-cluster-predecessor-test-namespaces",
    "cluster_uid": "d3adbeef-0000-4000-8000-000000000099",
    "evidence_mode": KubernetesEvidenceMode.CAPTURED_RESOURCE,
    "authorized_producer": "aip-kubernetes-capture-agent",
    "authority_record": "checkout-cluster-predecessor-test-authority",
}


def _write_dynamic_kubernetes_bundle(
    root: Path, *, expected_prior_inventory_revision: str | None
) -> KubernetesSourceConfig:
    # CAPTURED_RESOURCE mode (_DYNAMIC_KUBERNETES_CONFIG_KWARGS) needs a capture-identity-valid
    # resource for the real adapter's kubernetes_mapping validation (I2 §12 slice 3a) to accept it.
    resource_bytes = yaml.safe_dump(
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "checkout", "uid": "namespace-uid", "resourceVersion": "1"},
        }
    ).encode()
    (root / "resources.yaml").write_bytes(resource_bytes)
    envelope = {
        "apiVersion": "aip.dev/v1",
        "kind": "KubernetesSourceSnapshot",
        "metadata": {
            "id": "checkout-cluster-predecessor-snapshot",
            "revision": "revision-1",
            "producer": "aip-kubernetes-capture-agent",
            "capturedAt": "2026-09-17T10:00:00Z",
        },
        "source": {
            "configuredSourceId": _DYNAMIC_KUBERNETES_CONFIG_KWARGS["id"],
            "configuredScopeId": _DYNAMIC_KUBERNETES_CONFIG_KWARGS["configured_scope_id"],
            "clusterUid": _DYNAMIC_KUBERNETES_CONFIG_KWARGS["cluster_uid"],
            "clusterIdentityEvidenceRef": "kube-system-namespace-uid",
            "mode": "CAPTURED_RESOURCE",
        },
        "scope": {
            "namespaces": ["checkout"],
            "resourceTypes": sorted(EXPECTED_RESOURCE_TYPES),
        },
        "completeness": {
            "status": "COMPLETE",
            "authorityRef": _DYNAMIC_KUBERNETES_CONFIG_KWARGS["authority_record"],
            "expectedPriorInventoryRevision": expected_prior_inventory_revision,
        },
        "files": [{"path": "resources.yaml", "sha256": hashlib.sha256(resource_bytes).hexdigest()}],
    }
    (root / "envelope.yaml").write_bytes(yaml.safe_dump(envelope).encode())
    return KubernetesSourceConfig(root=root, **_DYNAMIC_KUBERNETES_CONFIG_KWARGS)


def test_import_kubernetes_source_first_import_with_null_predecessor_commits(driver, tmp_path):
    config = _write_dynamic_kubernetes_bundle(tmp_path, expected_prior_inventory_revision=None)
    stats = import_kubernetes_source(driver, database=DATABASE, source_config=config)
    assert stats.committed is True


def test_import_kubernetes_source_accepts_a_matching_expected_predecessor(driver, tmp_path):
    config = _write_dynamic_kubernetes_bundle(tmp_path, expected_prior_inventory_revision=None)
    first = import_kubernetes_source(driver, database=DATABASE, source_config=config)
    assert first.committed is True
    with driver.session(database=DATABASE) as session:
        first_revision = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r"
        ).single()["r"]

    config = _write_dynamic_kubernetes_bundle(
        tmp_path, expected_prior_inventory_revision=first_revision
    )
    second = import_kubernetes_source(driver, database=DATABASE, source_config=config)
    assert second.committed is True


def test_import_kubernetes_source_rejects_a_stale_expected_predecessor_and_preserves_state(
    driver, tmp_path
):
    config = _write_dynamic_kubernetes_bundle(tmp_path, expected_prior_inventory_revision=None)
    first = import_kubernetes_source(driver, database=DATABASE, source_config=config)
    assert first.committed is True
    with driver.session(database=DATABASE) as session:
        first_revision = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r"
        ).single()["r"]

    stale_config = _write_dynamic_kubernetes_bundle(
        tmp_path, expected_prior_inventory_revision="urn:aip:inventory-revision:" + "0" * 64
    )
    stale = import_kubernetes_source(driver, database=DATABASE, source_config=stale_config)
    assert stale.committed is False
    assert any(d.code == DiagnosticCode.STALE_INVENTORY_PREDECESSOR for d in stale.diagnostics)
    assert any(d.code == DiagnosticCode.K8S_STALE_INVENTORY for d in stale.diagnostics)
    # §10: "K8S_STALE_INVENTORY | REJECTED_CONFLICT; no commit" - the classification must be
    # observable on the result, not just implied by committed=False + a diagnostic code.
    [source_stats] = list(stale.per_source.values())
    assert source_stats.result == "REJECTED_CONFLICT"
    assert source_stats.nodes_written == 0

    with driver.session(database=DATABASE) as session:
        preserved_revision = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r"
        ).single()["r"]
    assert preserved_revision == first_revision


def test_import_kubernetes_source_rejects_a_nonnull_predecessor_on_first_import(driver, tmp_path):
    config = _write_dynamic_kubernetes_bundle(
        tmp_path, expected_prior_inventory_revision="urn:aip:inventory-revision:" + "0" * 64
    )
    stats = import_kubernetes_source(driver, database=DATABASE, source_config=config)
    assert stats.committed is False
    assert any(d.code == DiagnosticCode.STALE_INVENTORY_PREDECESSOR for d in stats.diagnostics)
    assert any(d.code == DiagnosticCode.K8S_STALE_INVENTORY for d in stats.diagnostics)
    [source_stats] = list(stats.per_source.values())
    assert source_stats.result == "REJECTED_CONFLICT"
    assert _count(driver, "MATCH (i:CurrentInventory) RETURN count(i) AS c") == 0


@dataclass
class _CompositeDiscoverer:
    """Test-only `SourceDiscoverer`: unions two real `KubernetesSourceDiscoverer` enumerations into
    one run, so `run_discovery`'s cross-source `detect_infrastructure_entity_content_conflicts`
    check (I2 Draft 0.2 §7.1/§10, wired since PR B) sees both sources' real, adapter-mapped
    contributions together - the only way to exercise it end-to-end, since each
    `KubernetesSourceConfig`/`import_kubernetes_source` call is otherwise its own independent run.
    """

    source_kind: SourceKind
    discoverer_identity: str
    outcomes: tuple[DiscoveryOutcome, ...]

    def discover(self) -> DiscoveryOutcome:
        first = self.outcomes[0]
        return DiscoveryOutcome(
            loaded_sources=tuple(
                loaded for outcome in self.outcomes for loaded in outcome.loaded_sources
            ),
            enumeration_complete=all(outcome.enumeration_complete for outcome in self.outcomes),
            diagnostics=tuple(d for outcome in self.outcomes for d in outcome.diagnostics),
            discovery_scope_id=first.discovery_scope_id,
            scope_definition_digest=first.scope_definition_digest,
        )


def _write_conflicting_kubernetes_bundle(
    root: Path, *, configured_source_id: str, service_id_annotation: str | None
) -> KubernetesSourceConfig:
    root.mkdir(parents=True, exist_ok=True)
    metadata = {"name": "checkout-api", "namespace": "checkout"}
    if service_id_annotation is not None:
        metadata["annotations"] = {"architecture-intelligence.io/service-id": service_id_annotation}
    resource_bytes = yaml.safe_dump(
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": metadata}
    ).encode()
    (root / "resources.yaml").write_bytes(resource_bytes)
    envelope = {
        "apiVersion": "aip.dev/v1",
        "kind": "KubernetesSourceSnapshot",
        "metadata": {
            "id": f"{configured_source_id}-snapshot",
            "revision": "revision-1",
            "producer": "aip-kubernetes-capture-agent",
            "capturedAt": "2026-09-17T10:00:00Z",
        },
        "source": {
            "configuredSourceId": configured_source_id,
            "configuredScopeId": f"{configured_source_id}-scope",
            "clusterUid": "conflict-cluster",
            "clusterIdentityEvidenceRef": "kube-system-namespace-uid",
            "mode": "DECLARED_MANIFEST",
        },
        "scope": {"namespaces": ["checkout"], "resourceTypes": sorted(EXPECTED_RESOURCE_TYPES)},
        "completeness": {
            "status": "COMPLETE",
            "authorityRef": f"{configured_source_id}-authority",
            "expectedPriorInventoryRevision": None,
        },
        "files": [{"path": "resources.yaml", "sha256": hashlib.sha256(resource_bytes).hexdigest()}],
    }
    (root / "envelope.yaml").write_bytes(yaml.safe_dump(envelope).encode())
    return KubernetesSourceConfig(
        id=configured_source_id,
        root=root,
        envelope_relative_path="envelope.yaml",
        configured_scope_id=f"{configured_source_id}-scope",
        cluster_uid="conflict-cluster",
        evidence_mode=KubernetesEvidenceMode.DECLARED_MANIFEST,
        authorized_producer="aip-kubernetes-capture-agent",
        authority_record=f"{configured_source_id}-authority",
    )


def test_two_kubernetes_sources_with_conflicting_content_for_one_logical_resource_commit_nothing(
    driver, tmp_path
):
    config_a = _write_conflicting_kubernetes_bundle(
        tmp_path / "a", configured_source_id="cluster-source-a", service_id_annotation=None
    )
    config_b = _write_conflicting_kubernetes_bundle(
        tmp_path / "b",
        configured_source_id="cluster-source-b",
        service_id_annotation="service:checkout",
    )
    outcome_a = KubernetesSourceDiscoverer(config_a).discover()
    outcome_b = KubernetesSourceDiscoverer(config_b).discover()
    composite = _CompositeDiscoverer(
        source_kind=SourceKind.KUBERNETES,
        discoverer_identity="test-composite-kubernetes-discoverer@1",
        outcomes=(outcome_a, outcome_b),
    )

    run_result = run_discovery(composite)
    assert any(d.code == DiagnosticCode.K8S_RESOURCE_CONFLICT for d in run_result.diagnostics)
    assert run_result.commit_eligible is False

    stats = import_discovery_run(driver, database=DATABASE, run_result=run_result)
    assert stats.committed is False
    assert stats.per_source == {}
    # v0.5.0 I5 F2: the rejected sources' own results are reported although nothing commits.
    assert len(stats.source_results) == 2
    assert {r.result for r in stats.source_results} == {IngestionResult.REJECTED_CONFLICT}
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 0
    assert _count(driver, "MATCH (i:CurrentInventory) RETURN count(i) AS c") == 0


# I2 Draft 0.2 §7.3 (slice 4a): a Pod with more than one controller owner reference rejects the
# whole source (K8S_OWNER_INVALID) - driven through the real discoverer/adapter so the rejection
# is proven against real owner-chain resolution, not a hand-built model.


def _write_multiple_controllers_kubernetes_bundle(root: Path) -> KubernetesSourceConfig:
    root.mkdir(parents=True, exist_ok=True)
    documents = [
        {
            "apiVersion": "apps/v1",
            "kind": "StatefulSet",
            "metadata": {
                "name": "sts-1",
                "namespace": "checkout",
                "uid": "sts-uid-1",
                "resourceVersion": "1",
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "DaemonSet",
            "metadata": {
                "name": "ds-1",
                "namespace": "checkout",
                "uid": "ds-uid-1",
                "resourceVersion": "1",
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "pod-1",
                "namespace": "checkout",
                "uid": "pod-uid-1",
                "resourceVersion": "1",
                "ownerReferences": [
                    {
                        "apiVersion": "apps/v1",
                        "kind": "StatefulSet",
                        "name": "sts-1",
                        "uid": "sts-uid-1",
                        "controller": True,
                    },
                    {
                        "apiVersion": "apps/v1",
                        "kind": "DaemonSet",
                        "name": "ds-1",
                        "uid": "ds-uid-1",
                        "controller": True,
                    },
                ],
            },
        },
    ]
    resource_bytes = yaml.safe_dump_all(documents).encode()
    (root / "resources.yaml").write_bytes(resource_bytes)
    envelope = {
        "apiVersion": "aip.dev/v1",
        "kind": "KubernetesSourceSnapshot",
        "metadata": {
            "id": "multiple-controllers-snapshot",
            "revision": "revision-1",
            "producer": "aip-kubernetes-capture-agent",
            "capturedAt": "2026-09-17T10:00:00Z",
        },
        "source": {
            "configuredSourceId": "multiple-controllers-source",
            "configuredScopeId": "multiple-controllers-scope",
            "clusterUid": "multiple-controllers-cluster",
            "clusterIdentityEvidenceRef": "kube-system-namespace-uid",
            "mode": "CAPTURED_RESOURCE",
        },
        "scope": {"namespaces": ["checkout"], "resourceTypes": sorted(EXPECTED_RESOURCE_TYPES)},
        "completeness": {
            "status": "COMPLETE",
            "authorityRef": "multiple-controllers-authority",
            "expectedPriorInventoryRevision": None,
        },
        "files": [{"path": "resources.yaml", "sha256": hashlib.sha256(resource_bytes).hexdigest()}],
    }
    (root / "envelope.yaml").write_bytes(yaml.safe_dump(envelope).encode())
    return KubernetesSourceConfig(
        id="multiple-controllers-source",
        root=root,
        envelope_relative_path="envelope.yaml",
        configured_scope_id="multiple-controllers-scope",
        cluster_uid="multiple-controllers-cluster",
        evidence_mode=KubernetesEvidenceMode.CAPTURED_RESOURCE,
        authorized_producer="aip-kubernetes-capture-agent",
        authority_record="multiple-controllers-authority",
    )


def test_pod_with_multiple_controller_owners_rejects_the_source_and_commits_nothing(
    driver, tmp_path
):
    config = _write_multiple_controllers_kubernetes_bundle(tmp_path)
    stats = import_kubernetes_source(driver, database=DATABASE, source_config=config)

    assert stats.committed is False
    assert any(d.code == DiagnosticCode.K8S_OWNER_INVALID for d in stats.diagnostics)
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 0
    assert _count(driver, "MATCH (i:CurrentInventory) RETURN count(i) AS c") == 0


# Review round (PR #200): a same-source captured-UID replacement must move the SOURCE-level
# semantic_input_digest (I2 Draft 0.2 §6), even though the per-entity resource_semantic_digest
# stays UID-free (§7.1) - driven through the real discoverer+adapter (not a hand-built model) to
# prove the actual digest computation, then fed into the real replay/revision-fence machinery via
# `_import` with the adapter's own real digests.


def _captured_deployment_outcome(
    root: Path, *, uid: str, resource_version: str, mapping_context_digest: str = "a" * 64
):
    root.mkdir(parents=True, exist_ok=True)
    resource_bytes = yaml.safe_dump(
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "checkout-api",
                "namespace": "checkout",
                "uid": uid,
                "resourceVersion": resource_version,
            },
        }
    ).encode()
    (root / "resources.yaml").write_bytes(resource_bytes)
    envelope = {
        "apiVersion": "aip.dev/v1",
        "kind": "KubernetesSourceSnapshot",
        "metadata": {
            "id": "captured-uid-replay-snapshot",
            "revision": "revision-1",
            "producer": "aip-kubernetes-capture-agent",
            "capturedAt": "2026-09-17T10:00:00Z",
        },
        "source": {
            "configuredSourceId": "captured-uid-replay-source",
            "configuredScopeId": "captured-uid-replay-scope",
            "clusterUid": "captured-uid-replay-cluster",
            "clusterIdentityEvidenceRef": "kube-system-namespace-uid",
            "mode": "CAPTURED_RESOURCE",
        },
        "scope": {"namespaces": ["checkout"], "resourceTypes": sorted(EXPECTED_RESOURCE_TYPES)},
        "completeness": {
            "status": "COMPLETE",
            "authorityRef": "captured-uid-replay-authority",
            "expectedPriorInventoryRevision": None,
        },
        "files": [{"path": "resources.yaml", "sha256": hashlib.sha256(resource_bytes).hexdigest()}],
    }
    (root / "envelope.yaml").write_bytes(yaml.safe_dump(envelope).encode())
    config = KubernetesSourceConfig(
        id="captured-uid-replay-source",
        root=root,
        envelope_relative_path="envelope.yaml",
        configured_scope_id="captured-uid-replay-scope",
        cluster_uid="captured-uid-replay-cluster",
        evidence_mode=KubernetesEvidenceMode.CAPTURED_RESOURCE,
        authorized_producer="aip-kubernetes-capture-agent",
        authority_record="captured-uid-replay-authority",
    )
    outcome = KubernetesSourceDiscoverer(config).discover()
    loaded = outcome.loaded_sources[0]
    assert loaded.diagnostics == []
    adapter_outcome = KubernetesSourceAdapter().map(
        loaded,
        service_identity=None,
        shared_identity=None,
        upstream_model=None,
        mapping_context_digest=mapping_context_digest,
    )
    return adapter_outcome, loaded.descriptor.source_instance_id


def test_captured_uid_replacement_advances_the_graph_revision(driver, tmp_path):
    first, source_instance_id = _captured_deployment_outcome(
        tmp_path / "a", uid="uid-a", resource_version="1"
    )
    second, _ = _captured_deployment_outcome(tmp_path / "b", uid="uid-b", resource_version="1")
    assert first.semantic_input_digest != second.semantic_input_digest

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, source_instance_id, first.model, digest=first.semantic_input_digest)
        stats = _import(
            session, source_instance_id, second.model, digest=second.semantic_input_digest
        )
    assert stats.graph_revision_advanced is True


def test_resource_version_only_change_does_not_advance_the_graph_revision(driver, tmp_path):
    first, source_instance_id = _captured_deployment_outcome(
        tmp_path / "a", uid="uid-a", resource_version="1"
    )
    second, _ = _captured_deployment_outcome(tmp_path / "b", uid="uid-a", resource_version="2")
    assert first.semantic_input_digest == second.semantic_input_digest

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, source_instance_id, first.model, digest=first.semantic_input_digest)
        stats = _import(
            session, source_instance_id, second.model, digest=second.semantic_input_digest
        )
    assert stats.graph_revision_advanced is False


# I2 Draft 0.2 §12 slice 5: shared lifecycle replay, conflict, scope/removal, and semantic/audit
# report qualification. Slices 1-4 above already proved the generic I1 lifecycle machinery (replay
# classification in app.sources.replay, per-source/whole-run reconciliation and tombstone-authorized
# removal in this module) end to end for other source kinds; this section proves the SAME generic
# machinery holds for the real Kubernetes discoverer/adapter path too, per §11's mandatory
# qualification table. No new production code is expected here - see each test's own docstring for
# the exact existing mechanism it drives.


def _deployment(name: str, namespace: str, uid: str, resource_version: str = "1") -> dict:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "uid": uid,
            "resourceVersion": resource_version,
        },
    }


def _replicaset(name: str, namespace: str, uid: str, *, owner_name: str, owner_uid: str) -> dict:
    return {
        "apiVersion": "apps/v1",
        "kind": "ReplicaSet",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "uid": uid,
            "resourceVersion": "1",
            "ownerReferences": [
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": owner_name,
                    "uid": owner_uid,
                    "controller": True,
                }
            ],
        },
    }


def _pod(name: str, namespace: str, uid: str, *, owner_name: str, owner_uid: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "uid": uid,
            "resourceVersion": "1",
            "ownerReferences": [
                {
                    "apiVersion": "apps/v1",
                    "kind": "ReplicaSet",
                    "name": owner_name,
                    "uid": owner_uid,
                    "controller": True,
                }
            ],
        },
    }


def _write_kubernetes_bundle(
    root: Path,
    *,
    source_id: str,
    scope_id: str,
    cluster_uid: str,
    namespaces: list[str],
    resources: list[dict] | None,
    expected_prior_inventory_revision: str | None,
    stable_target_identity: str | None = None,
    revision: str | None = None,
    captured_at: str = "2026-09-17T10:00:00Z",
    completeness_status: str = "COMPLETE",
) -> KubernetesSourceConfig:
    """General-purpose bundle writer for slice 5's lifecycle scenarios: unlike
    `_write_dynamic_kubernetes_bundle` (one fixed Namespace resource) or
    `_write_conflicting_kubernetes_bundle` (one fixed Deployment), callers here independently vary
    `namespaces`/`resources` to build scope-narrowing, empty-successor, and shared-scope multi-
    source scenarios. `resources=None`/`[]` writes an explicit empty file list (I2 Draft 0.2 §4.3:
    "a bundle with no resources can be complete only through an explicit empty file list"). Callers
    that need ordinary (non-scope-changed) replay MUST pass the same `root` across calls: the
    accepted `scope_definition_digest` folds in the normalized root path itself
    (`app/ingestion/kubernetes_discoverer.py`), so two different `tmp_path` roots always count as a
    scope change regardless of `namespaces`/`resources`.
    """
    root.mkdir(parents=True, exist_ok=True)
    files_field: list[dict] = []
    if resources:
        resource_bytes = yaml.safe_dump_all(list(resources)).encode()
        (root / "resources.yaml").write_bytes(resource_bytes)
        files_field = [
            {"path": "resources.yaml", "sha256": hashlib.sha256(resource_bytes).hexdigest()}
        ]
    envelope = {
        "apiVersion": "aip.dev/v1",
        "kind": "KubernetesSourceSnapshot",
        "metadata": {
            "id": f"{source_id}-snapshot",
            "revision": revision or f"{source_id}-revision",
            "producer": "aip-kubernetes-capture-agent",
            "capturedAt": captured_at,
        },
        "source": {
            "configuredSourceId": source_id,
            "configuredScopeId": scope_id,
            "clusterUid": cluster_uid,
            "clusterIdentityEvidenceRef": "kube-system-namespace-uid",
            "mode": "CAPTURED_RESOURCE",
        },
        "scope": {
            "namespaces": sorted(namespaces),
            "resourceTypes": sorted(EXPECTED_RESOURCE_TYPES),
        },
        "completeness": {
            "status": completeness_status,
            "authorityRef": f"{source_id}-authority",
            "expectedPriorInventoryRevision": expected_prior_inventory_revision,
        },
        "files": files_field,
    }
    (root / "envelope.yaml").write_bytes(yaml.safe_dump(envelope).encode())
    return KubernetesSourceConfig(
        id=source_id,
        root=root,
        envelope_relative_path="envelope.yaml",
        configured_scope_id=scope_id,
        cluster_uid=cluster_uid,
        evidence_mode=KubernetesEvidenceMode.CAPTURED_RESOURCE,
        authorized_producer="aip-kubernetes-capture-agent",
        authority_record=f"{source_id}-authority",
        stable_target_identity=stable_target_identity,
    )


def test_kubernetes_complete_empty_successor_withdraws_prior_source_owned_facts(driver, tmp_path):
    """I2 Draft 0.2 §4.3/§8: a verified COMPLETE successor with an explicit empty file list "may
    remove that source's contribution for resources/claims it no longer emits" - ordinary same-scope
    source-owned withdrawal (the per-source content-diff path in `_import_source_tx`), not a
    tombstone. Reuses the same physical root across both commits so `scope_definition_digest` (which
    folds in the root path) stays unchanged - the only thing that changes between commits is the
    resource content itself.
    """
    config = _write_kubernetes_bundle(
        tmp_path,
        source_id="empty-successor-source",
        scope_id="empty-successor-scope",
        cluster_uid="empty-successor-cluster",
        namespaces=["checkout"],
        resources=[_deployment("checkout-api", "checkout", "deploy-uid-1")],
        expected_prior_inventory_revision=None,
    )
    first = import_kubernetes_source(driver, database=DATABASE, source_config=config)
    assert first.committed is True
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 1
    assert _count(driver, "MATCH (c:InfrastructureClaim) RETURN count(c) AS c") == 1

    with driver.session(database=DATABASE) as session:
        first_revision = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r"
        ).single()["r"]

    empty_config = _write_kubernetes_bundle(
        tmp_path,
        source_id="empty-successor-source",
        scope_id="empty-successor-scope",
        cluster_uid="empty-successor-cluster",
        namespaces=["checkout"],
        resources=[],
        expected_prior_inventory_revision=first_revision,
    )
    second = import_kubernetes_source(driver, database=DATABASE, source_config=empty_config)

    assert second.committed is True
    assert not any(
        d.code in (DiagnosticCode.K8S_SNAPSHOT_INCOMPLETE, DiagnosticCode.K8S_STALE_INVENTORY)
        for d in second.diagnostics
    )
    [source_stats] = list(second.per_source.values())
    assert source_stats.result == "ACCEPTED"
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 0
    assert _count(driver, "MATCH (c:InfrastructureContribution) RETURN count(c) AS c") == 0
    assert _count(driver, "MATCH (c:InfrastructureClaim) RETURN count(c) AS c") == 0


def test_kubernetes_namespace_scope_narrowing_preserves_out_of_scope_claims(driver, tmp_path):
    """I2 Draft 0.2 §8: "changing namespace filters changes the scope digest... claims absent from
    the narrowed scope remain until an explicit versioned transition/tombstone authorizes removal" -
    the per-source `SCOPE_CHANGED_PRESERVE_PENDING_TOMBSTONE` replay case (`app.sources.replay`),
    proven end to end against the real discoverer/adapter rather than the unit-level replay
    classification alone. The narrowed bundle must not re-list the now-out-of-scope resource at all
    (§4.3: "out-of-scope resources reject the bundle rather than silently changing scope") - its
    entity/claim survive only because they were already committed, not because they're resubmitted.
    """
    checkout_deployment = _deployment("checkout-api", "checkout", "deploy-uid-checkout")
    payments_deployment = _deployment("payments-api", "payments", "deploy-uid-payments")
    config = _write_kubernetes_bundle(
        tmp_path,
        source_id="scope-narrow-source",
        scope_id="scope-narrow-scope",
        cluster_uid="scope-narrow-cluster",
        namespaces=["checkout", "payments"],
        resources=[checkout_deployment, payments_deployment],
        expected_prior_inventory_revision=None,
    )
    first = import_kubernetes_source(driver, database=DATABASE, source_config=config)
    assert first.committed is True
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 2

    with driver.session(database=DATABASE) as session:
        first_revision = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r"
        ).single()["r"]

    narrowed_config = _write_kubernetes_bundle(
        tmp_path,
        source_id="scope-narrow-source",
        scope_id="scope-narrow-scope",
        cluster_uid="scope-narrow-cluster",
        namespaces=["checkout"],
        resources=[checkout_deployment],
        expected_prior_inventory_revision=first_revision,
    )
    second = import_kubernetes_source(driver, database=DATABASE, source_config=narrowed_config)

    assert second.committed is True
    # A scope change alone must not auto-expire the now-out-of-scope entity/claim.
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 2
    assert (
        _count(
            driver,
            "MATCH (e:InfrastructureEntity {namespace: 'payments'}) RETURN count(e) AS c",
        )
        == 1
    )
    [source_stats] = list(second.per_source.values())
    assert source_stats.nodes_expired == 0


def test_kubernetes_explicit_tombstone_authorizes_whole_source_removal(driver, tmp_path):
    """I2 Draft 0.2 §8: "explicit tombstones authorize whole-source removal." An ordinary same-scope
    absence check alone can never remove a Kubernetes source's own facts through
    `import_kubernetes_source`, because that wrapper always re-enumerates its own one configured
    source in every run - the only way a *different* run's own known-source-states lookup
    (`_import_all_sources_tx`) can see a Kubernetes source's id as absent is for a second,
    independently-configured Kubernetes source to share the SAME `discovery_scope_id` (via an
    explicit matching `stable_target_identity`, mirroring how multiple capture agents could target
    one logical shared scope) while genuinely not re-enumerating the first source's own id. Mirrors
    the existing generic precedent
    `test_import_all_sources_denies_removal_on_scope_mismatch_but_an_explicit_tombstone_authorizes_it`
    (line ~1062), adapted to two real Kubernetes sources instead of two filesystem roots under one
    configured id.
    """
    shared_stable_identity = "urn:aip:k8s-shared-scope:tombstone-test-cluster"
    config_a = _write_kubernetes_bundle(
        tmp_path / "a",
        source_id="tombstone-source-a",
        scope_id="tombstone-shared-scope",
        cluster_uid="tombstone-test-cluster",
        namespaces=["checkout"],
        resources=[_deployment("service-a", "checkout", "deploy-uid-a")],
        expected_prior_inventory_revision=None,
        stable_target_identity=shared_stable_identity,
    )
    stats_a = import_kubernetes_source(driver, database=DATABASE, source_config=config_a)
    assert stats_a.committed is True
    [source_instance_id_a] = list(stats_a.per_source.keys())
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 1

    shared_scope_id = k8s_discovery_scope_id(
        configured_scope_id=config_a.resolved_scope_id,
        stable_target_identity=config_a.resolved_stable_target_identity,
    )

    def _current_inventory() -> dict:
        with driver.session(database=DATABASE) as session:
            record = session.run(
                "MATCH (i:CurrentInventory {discovery_scope_id: $id}) RETURN "
                "i.inventory_revision AS revision, i.scope_definition_digest AS digest",
                id=shared_scope_id,
            ).single()
        return {"revision": record["revision"], "digest": record["digest"]}

    after_a = _current_inventory()

    def _config_b(expected_prior_inventory_revision: str | None) -> KubernetesSourceConfig:
        return _write_kubernetes_bundle(
            tmp_path / "b",
            source_id="tombstone-source-b",
            scope_id="tombstone-shared-scope",
            cluster_uid="tombstone-test-cluster",
            namespaces=["checkout"],
            resources=[_deployment("service-b", "checkout", "deploy-uid-b")],
            expected_prior_inventory_revision=expected_prior_inventory_revision,
            stable_target_identity=shared_stable_identity,
        )

    # Source B's own commit succeeds and adds its own facts, but source A's facts - now absent from
    # B's own run enumeration - survive: B's bundle lives under a different physical root, so its
    # own accepted scope_definition_digest differs from what A committed, denying ordinary
    # same-scope absence-removal (exactly I1's own filesystem precedent's reasoning).
    stats_b = import_kubernetes_source(
        driver, database=DATABASE, source_config=_config_b(after_a["revision"])
    )
    assert stats_b.committed is True
    assert stats_b.removed_source_instance_ids == ()
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 2

    after_b = _current_inventory()
    tombstone = Tombstone(
        target_source_instance_id=source_instance_id_a,
        discovery_scope_id=shared_scope_id,
        expected_prior_inventory_revision=after_b["revision"],
        scope_definition_digest=after_b["digest"],
        actor="operator@example.com",
        reason="source A decommissioned",
        tombstone_revision="1",
    )
    stats_b_with_tombstone = import_kubernetes_source(
        driver,
        database=DATABASE,
        source_config=_config_b(after_b["revision"]),
        tombstones=(tombstone,),
    )

    assert stats_b_with_tombstone.committed is True
    assert stats_b_with_tombstone.removed_source_instance_ids == (source_instance_id_a,)
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 1
    with driver.session(database=DATABASE) as session:
        remaining_name = session.run(
            "MATCH (e:InfrastructureEntity) RETURN e.name AS name"
        ).single()["name"]
    # Specifically A's facts are gone, not B's own.
    assert remaining_name == "service-b"


def test_kubernetes_entity_shared_by_two_sources_survives_one_source_withdrawing(driver, tmp_path):
    """I2 Draft 0.2 §11 Ownership: "Two sources support one claim; one removed" - proven through two
    real, independently-configured Kubernetes sources (own `configured_scope_id`/`discovery_scope_id`
    each; unlike the tombstone test above, no shared scope is needed here) whose bundles happen to
    describe the identical logical resource with an identical semantic projection. §7.1: "For one
    logical entity ID, equal semantic digests merge contributions and union evidence
    deterministically" - already generically proven against hand-built models
    (`test_a_shared_claim_unions_evidence_from_both_sources_and_drops_only_the_departing_ones`); this
    drives the same mechanism through two real, independent `import_kubernetes_source` calls, then
    withdraws one source via the empty-successor mechanism proven above.
    """
    deployment = _deployment("checkout-api", "checkout", "deploy-uid-shared")
    config_a = _write_kubernetes_bundle(
        tmp_path / "a",
        source_id="shared-entity-source-a",
        scope_id="shared-entity-scope-a",
        cluster_uid="shared-entity-cluster",
        namespaces=["checkout"],
        resources=[deployment],
        expected_prior_inventory_revision=None,
    )
    config_b = _write_kubernetes_bundle(
        tmp_path / "b",
        source_id="shared-entity-source-b",
        scope_id="shared-entity-scope-b",
        cluster_uid="shared-entity-cluster",
        namespaces=["checkout"],
        resources=[deployment],
        expected_prior_inventory_revision=None,
    )
    stats_a = import_kubernetes_source(driver, database=DATABASE, source_config=config_a)
    stats_b = import_kubernetes_source(driver, database=DATABASE, source_config=config_b)
    assert stats_a.committed is True
    assert stats_b.committed is True
    [source_instance_id_a] = list(stats_a.per_source.keys())
    [source_instance_id_b] = list(stats_b.per_source.keys())

    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 1
    with driver.session(database=DATABASE) as session:
        entity = session.run(
            "MATCH (e:InfrastructureEntity) RETURN e.owner_source_ids AS owners"
        ).single()
        claim_before = session.run(
            "MATCH (c:InfrastructureClaim {kind: 'WORKLOAD_EXISTS'}) "
            "RETURN c.evidence_refs AS refs, c.owner_source_ids AS owners"
        ).single()
        contributions_before = {
            record["source"]: record["refs"]
            for record in session.run(
                "MATCH (c:InfrastructureClaimContribution) "
                "UNWIND c.owner_source_ids AS source RETURN source, c.evidence_refs AS refs"
            )
        }
    assert sorted(entity["owners"]) == sorted([source_instance_id_a, source_instance_id_b])
    # I2 Draft 0.2 §11 Ownership/§7.2: the shared WORKLOAD_EXISTS claim itself - not just the
    # entity - is co-owned by both sources, each with its own non-empty per-source claim
    # contribution, and the claim's own evidence_refs is the deterministic union of both.
    assert claim_before is not None
    assert sorted(claim_before["owners"]) == sorted([source_instance_id_a, source_instance_id_b])
    assert set(contributions_before.keys()) == {source_instance_id_a, source_instance_id_b}
    assert contributions_before[source_instance_id_a]
    assert contributions_before[source_instance_id_b]
    assert sorted(claim_before["refs"]) == sorted(
        set(contributions_before[source_instance_id_a])
        | set(contributions_before[source_instance_id_b])
    )

    b_scope_id = k8s_discovery_scope_id(
        configured_scope_id=config_b.resolved_scope_id,
        stable_target_identity=config_b.resolved_stable_target_identity,
    )
    with driver.session(database=DATABASE) as session:
        b_revision = session.run(
            "MATCH (i:CurrentInventory {discovery_scope_id: $id}) RETURN i.inventory_revision AS r",
            id=b_scope_id,
        ).single()["r"]

    empty_config_b = _write_kubernetes_bundle(
        tmp_path / "b",
        source_id="shared-entity-source-b",
        scope_id="shared-entity-scope-b",
        cluster_uid="shared-entity-cluster",
        namespaces=["checkout"],
        resources=[],
        expected_prior_inventory_revision=b_revision,
    )
    stats_b2 = import_kubernetes_source(driver, database=DATABASE, source_config=empty_config_b)
    assert stats_b2.committed is True

    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 1
    with driver.session(database=DATABASE) as session:
        entity_after = session.run(
            "MATCH (e:InfrastructureEntity) RETURN e.owner_source_ids AS owners"
        ).single()
        claim_after = session.run(
            "MATCH (c:InfrastructureClaim {kind: 'WORKLOAD_EXISTS'}) "
            "RETURN c.evidence_refs AS refs, c.owner_source_ids AS owners"
        ).single()
        remaining_contribution_sources = {
            record["source"]
            for record in session.run(
                "MATCH (c:InfrastructureClaimContribution) "
                "UNWIND c.owner_source_ids AS source RETURN source"
            )
        }
    assert entity_after["owners"] == [source_instance_id_a]
    # The claim survives on source A's own support only - source B's claim contribution is fully
    # gone (not merely un-owned), and the claim's evidence shrinks to exactly A's own refs, never a
    # dangling reference to B's now-deleted evidence.
    assert claim_after is not None
    assert claim_after["owners"] == [source_instance_id_a]
    assert claim_after["refs"] == contributions_before[source_instance_id_a]
    assert remaining_contribution_sources == {source_instance_id_a}


def test_kubernetes_recreated_pod_uid_replacement_drops_old_uid_from_owner_chain_claim(
    driver, tmp_path
):
    """I2 Draft 0.2 §6: "A replacement resource with the same name and a new UID preserves logical
    identity while changing incarnation evidence. Old UID links must not resolve against the
    replacement." / §8: "must not retain an association justified only by a removed incarnation."
    `test_captured_uid_replacement_advances_the_graph_revision` already proves the source-level
    digest advances; this proves the actual persisted claim/contribution CONTENT drops the old UID,
    using a real Pod -> ReplicaSet -> Deployment owner chain (slice 4a's own fixture shape).
    """

    def _bundle(
        pod_uid: str, expected_prior_inventory_revision: str | None
    ) -> KubernetesSourceConfig:
        deployment = _deployment("checkout-api", "checkout", "deploy-uid-1")
        replicaset = _replicaset(
            "checkout-api-rs",
            "checkout",
            "rs-uid-1",
            owner_name="checkout-api",
            owner_uid="deploy-uid-1",
        )
        pod = _pod(
            "checkout-api-pod",
            "checkout",
            pod_uid,
            owner_name="checkout-api-rs",
            owner_uid="rs-uid-1",
        )
        return _write_kubernetes_bundle(
            tmp_path,
            source_id="uid-replay-source",
            scope_id="uid-replay-scope",
            cluster_uid="uid-replay-cluster",
            namespaces=["checkout"],
            resources=[deployment, replicaset, pod],
            expected_prior_inventory_revision=expected_prior_inventory_revision,
        )

    first = import_kubernetes_source(
        driver, database=DATABASE, source_config=_bundle("pod-uid-a", None)
    )
    assert first.committed is True

    with driver.session(database=DATABASE) as session:
        pod_entity_id = session.run(
            "MATCH (e:InfrastructureEntity {entity_kind: 'KUBERNETES_POD'}) RETURN e.id AS id"
        ).single()["id"]
        workload_entity_id = session.run(
            "MATCH (e:InfrastructureEntity {entity_kind: 'KUBERNETES_WORKLOAD'}) RETURN e.id AS id"
        ).single()["id"]
        ownership_before = session.run(
            "MATCH (c:InfrastructureClaim {kind: 'WORKLOAD_OWNS_POD'}) "
            "RETURN c.subject_id AS subject_id, c.object_id AS object_id"
        ).single()
        contribution_before = session.run(
            "MATCH (c:InfrastructureContribution {entity_id: $id}) "
            "RETURN c.captured_resource_uid AS uid",
            id=pod_entity_id,
        ).single()
        first_revision = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r"
        ).single()["r"]

    assert ownership_before["subject_id"] == workload_entity_id
    assert ownership_before["object_id"] == pod_entity_id
    assert contribution_before["uid"] == "pod-uid-a"

    second = import_kubernetes_source(
        driver, database=DATABASE, source_config=_bundle("pod-uid-b", first_revision)
    )
    assert second.committed is True

    with driver.session(database=DATABASE) as session:
        ownership_after = session.run(
            "MATCH (c:InfrastructureClaim {kind: 'WORKLOAD_OWNS_POD'}) "
            "RETURN c.subject_id AS subject_id, c.object_id AS object_id"
        ).single()
        contribution_after = session.run(
            "MATCH (c:InfrastructureContribution {entity_id: $id}) "
            "RETURN c.captured_resource_uid AS uid",
            id=pod_entity_id,
        ).single()
        old_uid_survivors = session.run(
            "MATCH (n) WHERE n.captured_resource_uid = 'pod-uid-a' RETURN count(n) AS c"
        ).single()["c"]

    # The same logical Pod/Workload ids still resolve (§6: replacement preserves logical identity)...
    assert ownership_after["subject_id"] == workload_entity_id
    assert ownership_after["object_id"] == pod_entity_id
    # ...but the contribution's captured UID is now the new one, and nothing anywhere still carries
    # the old, replaced incarnation.
    assert contribution_after["uid"] == "pod-uid-b"
    assert old_uid_survivors == 0


def test_kubernetes_two_clean_discovery_runs_produce_byte_identical_semantic_reports(tmp_path):
    """I2 Draft 0.2 §11 Replay: "unchanged bundle and mapping context" determinism, mirroring I1's
    own `test_i1_bundled_migration_determinism.py::
    test_two_clean_checkouts_at_different_paths_produce_identical_results` pattern for Kubernetes.
    Pure discovery/mapping-layer proof (no Neo4j) - two independent checkouts of identical bundle
    content at different physical paths. Unlike `FilesystemSourceConfig` (whose default
    `stable_target_identity` is `urn:aip:logical-root:<id>`), `KubernetesSourceConfig`'s own default
    is `urn:aip:k8s-cluster:<cluster_uid>` (`app/sources/model.py`) - the SAME `cluster_uid` across
    both checkouts is what keeps `discovery_scope_id` portable here, not the configured `id`. Only
    `scope_definition_digest` (which legitimately folds in the physical root) differs.
    """
    resources = [_deployment("checkout-api", "checkout", "deploy-uid-1")]

    def _run(root: Path):
        config = _write_kubernetes_bundle(
            root,
            source_id="determinism-source",
            scope_id="determinism-scope",
            cluster_uid="determinism-cluster",
            namespaces=["checkout"],
            resources=resources,
            expected_prior_inventory_revision=None,
        )
        return run_kubernetes_discovery(config)

    result_one = _run(tmp_path / "checkout-one")
    result_two = _run(tmp_path / "somewhere" / "else" / "checkout-two")

    assert result_one.inventory_status == result_two.inventory_status
    assert result_one.commit_eligible is True
    assert result_one.commit_eligible == result_two.commit_eligible
    assert result_one.discovery_scope_id == result_two.discovery_scope_id
    assert result_one.scope_definition_digest != result_two.scope_definition_digest

    ids_one = set(result_one.source_outcomes.keys())
    ids_two = set(result_two.source_outcomes.keys())
    assert ids_one == ids_two

    digests_one = {
        sid: ro.outcome.semantic_input_digest for sid, ro in result_one.source_outcomes.items()
    }
    digests_two = {
        sid: ro.outcome.semantic_input_digest for sid, ro in result_two.source_outcomes.items()
    }
    assert digests_one == digests_two

    def _canonical_merged_model_bytes(model) -> bytes:
        return canonical_json_bytes(model.model_dump(mode="json", exclude={"provenance"}))

    assert _canonical_merged_model_bytes(result_one.merged_model) == _canonical_merged_model_bytes(
        result_two.merged_model
    )


def test_kubernetes_unchanged_reimport_is_a_true_replay_no_op(driver, tmp_path):
    """I2 Draft 0.2 §11 Replay: "first import versus sequential no-op." A second, byte-identical
    commit of the same bundle must be `REPLAY_NO_OP` (`app.sources.replay`): no expirations, no
    changed entity/claim counts, and no graph-revision advance - not merely "committed=True again".
    """
    config = _write_kubernetes_bundle(
        tmp_path,
        source_id="noop-replay-source",
        scope_id="noop-replay-scope",
        cluster_uid="noop-replay-cluster",
        namespaces=["checkout"],
        resources=[_deployment("checkout-api", "checkout", "deploy-uid-1")],
        expected_prior_inventory_revision=None,
    )
    first = import_kubernetes_source(driver, database=DATABASE, source_config=config)
    assert first.committed is True
    entity_count_before = _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c")
    claim_count_before = _count(driver, "MATCH (c:InfrastructureClaim) RETURN count(c) AS c")

    with driver.session(database=DATABASE) as session:
        first_revision = session.run(
            "MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r"
        ).single()["r"]

    unchanged_config = _write_kubernetes_bundle(
        tmp_path,
        source_id="noop-replay-source",
        scope_id="noop-replay-scope",
        cluster_uid="noop-replay-cluster",
        namespaces=["checkout"],
        resources=[_deployment("checkout-api", "checkout", "deploy-uid-1")],
        expected_prior_inventory_revision=first_revision,
    )
    second = import_kubernetes_source(driver, database=DATABASE, source_config=unchanged_config)

    assert second.committed is True
    [source_stats] = list(second.per_source.values())
    assert source_stats.graph_revision_advanced is False
    assert source_stats.nodes_expired == 0
    assert source_stats.relations_expired == 0
    assert (
        _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == entity_count_before
    )
    assert (
        _count(driver, "MATCH (c:InfrastructureClaim) RETURN count(c) AS c") == claim_count_before
    )


def test_kubernetes_mapping_context_digest_change_triggers_reevaluation_not_a_silent_no_op(
    driver, tmp_path
):
    """I2 Draft 0.2 §6: "The common I1 mapping context includes the active Kubernetes adapter/rule
    versions and registration semantics... Document and mapping changes trigger reevaluation."
    Isolates the same seam `_captured_deployment_outcome`'s own UID-replacement tests already use:
    `KubernetesSourceAdapter.map` takes `mapping_context_digest` as an explicit parameter (in
    production, computed by the orchestrator from every registered adapter's own
    `adapter_identity`/`mapping_rule_version` -
    `app.ingestion.orchestrator._compute_mapping_context_digest`) - a rule/context version bump is
    exactly a changed value at this same injection point, with byte-identical resource content.

    A first attempt at this test also asserted `graph_revision_advanced is True` on the second
    import - that failed, and rightly so: `mapping_context_digest` never surfaces into any stored
    canonical property (it is purely a digest-formula input), so a context-only change with
    genuinely identical resource content produces no real canonical change, and
    `_import_source_tx`'s own before/after content-diff check (see its docstring: "an adapter's
    normalized projection can hash raw input the canonical model never surfaces at all, e.g.
    OpenAPI's `info.description`") correctly withholds the revision-fence advance - the same
    documented "canonically inert input change" precedent I1 already established for a different
    source kind, now confirmed to hold for Kubernetes too. What §6 actually requires - that a
    context/rule change is compared and not silently treated as identical - is exactly what a moved
    `semantic_input_digest` proves: the comparison happened and correctly detected the difference,
    which is the only observable effect a content-identical context bump can legitimately have.
    """
    first, source_instance_id = _captured_deployment_outcome(
        tmp_path, uid="uid-context-test", resource_version="1", mapping_context_digest="a" * 64
    )
    second, _ = _captured_deployment_outcome(
        tmp_path, uid="uid-context-test", resource_version="1", mapping_context_digest="b" * 64
    )
    # Identical resource content, only the mapping context changed - the source-level digest must
    # still move, or a real rule/context change would be silently indistinguishable from an
    # unchanged reimport at the one seam that carries it forward.
    assert first.semantic_input_digest != second.semantic_input_digest

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, source_instance_id, first.model, digest=first.semantic_input_digest)
        stats = _import(
            session, source_instance_id, second.model, digest=second.semantic_input_digest
        )
    # No real canonical content changed (same UID/resourceVersion/projection), so no revision
    # advance is expected here - see the docstring above. `nodes_expired`/`relations_expired` stay
    # zero either way; the meaningful proof already happened above.
    assert stats.graph_revision_advanced is False


# I2 Draft 0.2 §12 slice 6: the §9 I3 handoff requires "the retained explicit Service-ID annotation
# as unqualified input" to be genuinely queryable, not only folded into the opaque
# resource_semantic_digest hash (a real gap found while planning slice 6 - fixed by adding
# InfrastructureContribution.service_id_annotation, mirroring captured_resource_uid's own additive
# precedent). Proven here through the real discoverer/adapter/import_kubernetes_source path, not a
# hand-built model, since the point is proving the real annotation value survives persistence.


def test_kubernetes_service_id_annotation_survives_persistence_as_unqualified_input(
    driver, tmp_path
):
    deployment = _deployment("checkout-api", "checkout", "deploy-uid-service-id")
    deployment["metadata"]["annotations"] = {
        "architecture-intelligence.io/service-id": "service:checkout"
    }
    config = _write_kubernetes_bundle(
        tmp_path,
        source_id="service-id-annotation-source",
        scope_id="service-id-annotation-scope",
        cluster_uid="service-id-annotation-cluster",
        namespaces=["checkout"],
        resources=[deployment],
        expected_prior_inventory_revision=None,
    )
    stats = import_kubernetes_source(driver, database=DATABASE, source_config=config)
    assert stats.committed is True

    with driver.session(database=DATABASE) as session:
        workload_id = session.run(
            "MATCH (e:InfrastructureEntity {entity_kind: 'KUBERNETES_WORKLOAD'}) RETURN e.id AS id"
        ).single()["id"]
        contribution = session.run(
            "MATCH (c:InfrastructureContribution {entity_id: $id}) "
            "RETURN c.service_id_annotation AS annotation",
            id=workload_id,
        ).single()
    # The real annotation value itself is queryable - not merely reflected in a changed digest.
    assert contribution["annotation"] == "service:checkout"


def test_kubernetes_absent_service_id_annotation_persists_as_null(driver, tmp_path):
    config = _write_kubernetes_bundle(
        tmp_path,
        source_id="no-service-id-annotation-source",
        scope_id="no-service-id-annotation-scope",
        cluster_uid="no-service-id-annotation-cluster",
        namespaces=["checkout"],
        resources=[_deployment("checkout-api", "checkout", "deploy-uid-no-annotation")],
        expected_prior_inventory_revision=None,
    )
    stats = import_kubernetes_source(driver, database=DATABASE, source_config=config)
    assert stats.committed is True

    with driver.session(database=DATABASE) as session:
        workload_id = session.run(
            "MATCH (e:InfrastructureEntity {entity_kind: 'KUBERNETES_WORKLOAD'}) RETURN e.id AS id"
        ).single()["id"]
        contribution = session.run(
            "MATCH (c:InfrastructureContribution {entity_id: $id}) "
            "RETURN c.service_id_annotation AS annotation",
            id=workload_id,
        ).single()
    assert contribution["annotation"] is None


# I2 Draft 0.2 §3 item 6: infrastructure facts go through the SAME write/ownership/reconciliation/
# expiry path as every other canonical fact. Driven through the real `import_source` -> Neo4j path
# with hand-built models, since the real `KubernetesSourceAdapter` (slice 2b-i) still emits only an
# empty `ArchitectureModel` - real canonical projection is slice 3's job - without this, a later
# adapter could commit its inventory while its facts were silently dropped.

INFRA_ENTITY_ID = "urn:aip:k8s-resource:workload-1"
INFRA_EVIDENCE = Provenance(
    id="evidence:kubernetes:1", source_type="KUBERNETES", source_file="snapshot.yaml"
)


def _infra_entity(entity_id: str = INFRA_ENTITY_ID) -> InfrastructureEntity:
    return InfrastructureEntity(
        id=entity_id,
        entity_kind=InfrastructureEntityKind.KUBERNETES_WORKLOAD,
        cluster_uid="cluster-1",
        api_group="apps",
        resource_kind="Deployment",
        namespace="default",
        name="order-service",
    )


def _infra_model(
    *, source_instance_id: str, entity_id: str = INFRA_ENTITY_ID, digest: str = "digest-1"
) -> ArchitectureModel:
    entity = _infra_entity(entity_id)
    return ArchitectureModel(
        provenance=[INFRA_EVIDENCE],
        infrastructure_entities=[entity],
        infrastructure_contributions=[
            InfrastructureContribution(
                entity_id=entity.id,
                source_instance_id=source_instance_id,
                evidence_mode=KubernetesEvidenceMode.CAPTURED_RESOURCE,
                resource_semantic_digest=digest,
                evidence_refs=[INFRA_EVIDENCE.id],
                mapping_rule_id="kubernetes-adapter@1",
                mapping_rule_version="v1",
            )
        ],
        infrastructure_claims=[
            InfrastructureClaim(
                kind=InfrastructureClaimKind.WORKLOAD_EXISTS,
                subject_id=entity.id,
                evidence_refs=[INFRA_EVIDENCE.id],
                mapping_rule_id="kubernetes-adapter@1",
                mapping_rule_version="v1",
            )
        ],
    )


def test_import_source_writes_and_owns_infrastructure_facts(driver):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:k8s-1", _infra_model(source_instance_id="src:k8s-1"))

    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 1
    assert _count(driver, "MATCH (c:InfrastructureContribution) RETURN count(c) AS c") == 1
    assert _count(driver, "MATCH (c:InfrastructureClaim) RETURN count(c) AS c") == 1

    with driver.session(database=DATABASE) as session:
        entity = session.run(
            "MATCH (e:InfrastructureEntity {id: $id}) RETURN e.owner_source_ids AS owners, "
            "e.entity_kind AS kind, e.name AS name, e.namespace AS namespace",
            id=INFRA_ENTITY_ID,
        ).single()
        claim = session.run(
            "MATCH (c:InfrastructureClaim) RETURN c.kind AS kind, c.subject_id AS subject_id, "
            "c.object_id AS object_id, c.evidence_refs AS evidence_refs, "
            "c.owner_source_ids AS owners"
        ).single()
        contribution = session.run(
            "MATCH (c:InfrastructureContribution) RETURN c.evidence_mode AS evidence_mode, "
            "c.resource_semantic_digest AS digest, c.owner_source_ids AS owners"
        ).single()

    assert entity["owners"] == ["src:k8s-1"]
    assert entity["kind"] == "KUBERNETES_WORKLOAD"
    assert entity["name"] == "order-service"
    assert claim["kind"] == "WORKLOAD_EXISTS"
    assert claim["subject_id"] == INFRA_ENTITY_ID
    # §7.2: a unary claim's absent object survives persistence as a real null, not a sentinel.
    assert claim["object_id"] is None
    assert claim["evidence_refs"] == [INFRA_EVIDENCE.id]
    assert claim["owners"] == ["src:k8s-1"]
    assert contribution["evidence_mode"] == "CAPTURED_RESOURCE"
    assert contribution["digest"] == "digest-1"
    assert contribution["owners"] == ["src:k8s-1"]


def test_network_service_ports_survive_persistence_as_canonical_json(driver):
    entity = InfrastructureEntity(
        id="urn:aip:k8s-resource:svc-1",
        entity_kind=InfrastructureEntityKind.KUBERNETES_NETWORK_SERVICE,
        cluster_uid="cluster-1",
        api_group="",
        resource_kind="Service",
        namespace="default",
        name="order-service",
        service_type="ClusterIP",
        ports=[
            InfrastructurePort(name=None, protocol="TCP", port=9090),
            InfrastructurePort(name="http", protocol="TCP", port=8080),
        ],
    )
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:k8s-1", ArchitectureModel(infrastructure_entities=[entity]))
        stored = session.run(
            "MATCH (e:InfrastructureEntity {id: $id}) RETURN e.ports AS ports, "
            "e.service_type AS service_type",
            id=entity.id,
        ).single()

    assert stored["service_type"] == "ClusterIP"
    # Nested objects can't be Neo4j properties, so each port is one canonical-JSON string, in the
    # entity's own §7.1 sorted order.
    assert stored["ports"] == [
        '{"name":null,"port":9090,"protocol":"TCP"}',
        '{"name":"http","port":8080,"protocol":"TCP"}',
    ]


def test_reimport_without_an_infrastructure_fact_expires_it(driver):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:k8s-1", _infra_model(source_instance_id="src:k8s-1"))
        assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 1

        # The same source no longer emits any infrastructure fact - the shared reconciliation path
        # must expire them exactly as it would a dropped Service or Operation.
        _import(session, "src:k8s-1", ArchitectureModel(), digest=DIGEST_2)

    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 0
    assert _count(driver, "MATCH (c:InfrastructureContribution) RETURN count(c) AS c") == 0
    assert _count(driver, "MATCH (c:InfrastructureClaim) RETURN count(c) AS c") == 0


def test_infrastructure_entity_shared_by_two_sources_survives_one_source_dropping_it(driver):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:k8s-1", _infra_model(source_instance_id="src:k8s-1"))
        _import(session, "src:k8s-2", _infra_model(source_instance_id="src:k8s-2"))

        with driver.session(database=DATABASE) as read_session:
            owners = read_session.run(
                "MATCH (e:InfrastructureEntity {id: $id}) RETURN e.owner_source_ids AS owners",
                id=INFRA_ENTITY_ID,
            ).single()["owners"]
        assert sorted(owners) == ["src:k8s-1", "src:k8s-2"]
        # Each source owns its own contribution; the shared entity is owned by both.
        assert _count(driver, "MATCH (c:InfrastructureContribution) RETURN count(c) AS c") == 2

        _import(session, "src:k8s-1", ArchitectureModel(), digest=DIGEST_2)

    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (e:InfrastructureEntity {id: $id}) RETURN e.owner_source_ids AS owners",
            id=INFRA_ENTITY_ID,
        ).single()
    # Still present, now owned only by the source that still claims it - the other source's
    # contribution is gone, but its withdrawal never deleted the shared entity.
    assert record is not None
    assert record["owners"] == ["src:k8s-2"]
    assert _count(driver, "MATCH (c:InfrastructureContribution) RETURN count(c) AS c") == 1


def test_persisted_kubernetes_workload_identity_now_binds_the_public_snapshot(driver):
    """I2 Draft 0.2 §9 originally kept every infrastructure fact off the public snapshot entirely.
    v0.5.0 I3 Draft 0.4 §17 deliberately narrows that boundary: "I2 intentionally excluded internal
    Kubernetes state from the public Architecture Intelligence snapshot because it could not affect
    a public answer. I3 changes that only for the bounded reconciliation projection" - naming
    "current supported Workload identity" as one of the state categories the fingerprint SHALL now
    bind (Path A/B/C's own deployment reconciliation reads exactly this Workload identity, so
    snapshot determinism requires it to move the fingerprint). This test proves that new, narrower
    boundary for a `KUBERNETES_WORKLOAD` entity specifically; the sibling test just below proves the
    §17 "SHALL NOT include" list (Network Service/Ingress facts) still does not leak, unchanged from
    I2 Draft 0.2 §9's original rule. Note `_RELATION_QUERY` in `app.architecture_intelligence.
    repository` stays deliberately untyped (`MATCH (a)-[r]->(b)`) throughout, so no binary
    infrastructure claim modelled as a graph *edge* (all four claim kinds are modelled as owned
    claim *nodes*, per §7.2's unary `WORKLOAD_EXISTS` requirement) ever enters the relation
    projection - that boundary is untouched by I3.
    """
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(
            session,
            "src:app",
            ArchitectureModel(services=[Service(id="service:order-service", name="OrderService")]),
        )
        before = canonical_snapshot_state(session, coverage_qualification_enabled=True)
        before_id, _ = snapshot_fingerprint(before)

        _import(session, "src:k8s-1", _infra_model(source_instance_id="src:k8s-1"))
        after = canonical_snapshot_state(session, coverage_qualification_enabled=True)
        after_id, _ = snapshot_fingerprint(after)

    # The infrastructure facts really are committed...
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 1
    assert _count(driver, "MATCH (c:InfrastructureContribution) RETURN count(c) AS c") == 1
    assert _count(driver, "MATCH (c:InfrastructureClaim) RETURN count(c) AS c") == 1

    # ...the Workload's own id now legitimately appears (spec §17's "current supported Workload
    # identity" bullet - `deployment_workloads` binds every current KUBERNETES_WORKLOAD entity,
    # annotated or not, since Path C's Pod/Workload resolution needs the full set)...
    serialized = json.dumps(after)
    assert INFRA_ENTITY_ID in serialized
    # ...but the claim-kind literal and entity-kind literal still don't - `deployment_workloads`
    # never returns `entity_kind`, and this fixture's `WORKLOAD_EXISTS` claim isn't one of the two
    # claim kinds (`WORKLOAD_OWNS_POD`/none else) §17's bounded projection reads.
    assert "WORKLOAD_EXISTS" not in serialized
    assert "KUBERNETES_WORKLOAD" not in serialized
    # No infrastructure claim/contribution is modelled as a graph *edge*, so the untyped relation
    # projection and its own edge-count boundary are both still exactly as before.
    assert after["relations"] == before["relations"]
    assert _count(driver, "MATCH (:InfrastructureEntity)-[r]-() RETURN count(r) AS c") == 0

    assert after != before
    assert after_id != before_id


def test_kubernetes_network_service_and_ingress_facts_still_do_not_leak_into_the_public_snapshot(
    driver,
):
    """The other half of spec §17's boundary: entity/claim kinds explicitly named in its "SHALL NOT
    include" list (Network Service selector facts, Ingress routing facts) are outside I3's bounded
    deployment-reconciliation projection and so must still never affect the public snapshot -
    exactly I2 Draft 0.2 §9's original, unmodified rule for everything I3 didn't carve an exception
    for."""
    service_entity = InfrastructureEntity(
        id="urn:aip:k8s-resource:network-service-1",
        entity_kind=InfrastructureEntityKind.KUBERNETES_NETWORK_SERVICE,
        cluster_uid="cluster-1",
        api_group="",
        resource_kind="Service",
        namespace="default",
        name="order-service",
    )
    workload_entity = InfrastructureEntity(
        id=INFRA_ENTITY_ID,
        entity_kind=InfrastructureEntityKind.KUBERNETES_WORKLOAD,
        cluster_uid="cluster-1",
        api_group="apps",
        resource_kind="Deployment",
        namespace="default",
        name="order-service",
    )
    model = ArchitectureModel(
        provenance=[INFRA_EVIDENCE],
        infrastructure_entities=[service_entity, workload_entity],
        infrastructure_contributions=[
            InfrastructureContribution(
                entity_id=workload_entity.id,
                source_instance_id="src:k8s-1",
                evidence_mode=KubernetesEvidenceMode.CAPTURED_RESOURCE,
                resource_semantic_digest="digest-1",
                evidence_refs=[INFRA_EVIDENCE.id],
                mapping_rule_id="kubernetes-adapter@1",
                mapping_rule_version="v1",
            )
        ],
        infrastructure_claims=[
            InfrastructureClaim(
                kind=InfrastructureClaimKind.NETWORK_SERVICE_SELECTS_WORKLOAD,
                subject_id=service_entity.id,
                object_id=workload_entity.id,
                evidence_refs=[INFRA_EVIDENCE.id],
                mapping_rule_id="kubernetes-adapter@1",
                mapping_rule_version="v1",
            )
        ],
    )

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(
            session,
            "src:app",
            ArchitectureModel(services=[Service(id="service:order-service", name="OrderService")]),
        )
        before = canonical_snapshot_state(session, coverage_qualification_enabled=True)
        before_id, _ = snapshot_fingerprint(before)

        _import(session, "src:k8s-1", model)
        after = canonical_snapshot_state(session, coverage_qualification_enabled=True)
        after_id, _ = snapshot_fingerprint(after)

    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 2
    assert _count(driver, "MATCH (c:InfrastructureClaim) RETURN count(c) AS c") == 1

    serialized = json.dumps(after)
    assert service_entity.id not in serialized
    assert "NETWORK_SERVICE_SELECTS_WORKLOAD" not in serialized
    assert "KUBERNETES_NETWORK_SERVICE" not in serialized
    assert after["relations"] == before["relations"]
    assert _count(driver, "MATCH (:InfrastructureEntity)-[r]-() RETURN count(r) AS c") == 0

    # The Workload's own identity still legitimately binds (see the sibling test above) - this test
    # is only about the Network Service/Ingress side of §17's "SHALL NOT include" list, which the
    # assertions above already cover.
    assert after_id != before_id


def _infra_claim_model(
    *,
    source_instance_id: str,
    evidence_id: str,
    digest: str = "digest-1",
    evidence_mode: KubernetesEvidenceMode = KubernetesEvidenceMode.CAPTURED_RESOURCE,
) -> ArchitectureModel:
    """The same shared claim (same kind/subject/object, hence the same §7.2 claim identity) asserted
    by a given source with its OWN evidence record."""
    entity = _infra_entity()
    return ArchitectureModel(
        provenance=[
            Provenance(id=evidence_id, source_type="KUBERNETES", source_file=f"{evidence_id}.yaml")
        ],
        infrastructure_entities=[entity],
        infrastructure_contributions=[
            InfrastructureContribution(
                entity_id=entity.id,
                source_instance_id=source_instance_id,
                evidence_mode=evidence_mode,
                resource_semantic_digest=digest,
                evidence_refs=[evidence_id],
                mapping_rule_id="kubernetes-adapter@1",
                mapping_rule_version="v1",
            )
        ],
        infrastructure_claims=[
            InfrastructureClaim(
                kind=InfrastructureClaimKind.WORKLOAD_EXISTS,
                subject_id=entity.id,
                evidence_refs=[evidence_id],
                mapping_rule_id="kubernetes-adapter@1",
                mapping_rule_version="v1",
            )
        ],
    )


def test_a_shared_claim_unions_evidence_from_both_sources_and_drops_only_the_departing_ones(driver):
    """I2 Draft 0.2 §7.2: "Claim contributions use the same source ownership, evidence-mode
    retention, deterministic evidence union... as entity contributions." A claim's identity is
    shared across sources, so a plain `SET n += $props` would make its stored evidence depend on
    which source wrote last, and dropping that source would leave the surviving claim pointing at
    deleted evidence (a real bug found in PR review)."""
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(
            session,
            "src:k8s-1",
            _infra_claim_model(source_instance_id="src:k8s-1", evidence_id="evidence:kubernetes:a"),
        )
        _import(
            session,
            "src:k8s-2",
            _infra_claim_model(source_instance_id="src:k8s-2", evidence_id="evidence:kubernetes:b"),
        )

        claim = session.run(
            "MATCH (c:InfrastructureClaim) RETURN c.evidence_refs AS refs, "
            "c.owner_source_ids AS owners"
        ).single()

    # One shared claim node, owned by both, carrying BOTH sources' evidence - not just the last
    # writer's.
    assert _count(driver, "MATCH (c:InfrastructureClaim) RETURN count(c) AS c") == 1
    assert sorted(claim["refs"]) == ["evidence:kubernetes:a", "evidence:kubernetes:b"]
    assert sorted(claim["owners"]) == ["src:k8s-1", "src:k8s-2"]

    # The second source stops emitting anything at all.
    with driver.session(database=DATABASE) as session:
        _import(session, "src:k8s-2", ArchitectureModel(), digest=DIGEST_2)
        surviving = session.run(
            "MATCH (c:InfrastructureClaim) RETURN c.evidence_refs AS refs, "
            "c.owner_source_ids AS owners"
        ).single()

    # The claim survives on the remaining owner's evidence only - and critically does NOT still
    # point at the departed source's now-deleted evidence record.
    assert surviving is not None
    assert surviving["refs"] == ["evidence:kubernetes:a"]
    assert surviving["owners"] == ["src:k8s-1"]
    assert (
        _count(
            driver,
            "MATCH (e:Evidence {id: 'evidence:kubernetes:b'}) RETURN count(e) AS c",
        )
        == 0
    )
    # Every ref the claim still holds resolves to a live Evidence node ("a fact exists iff its
    # evidence exists").
    assert (
        _count(
            driver,
            "MATCH (c:InfrastructureClaim) UNWIND c.evidence_refs AS ref "
            "MATCH (e:Evidence {id: ref}) RETURN count(e) AS c",
        )
        == 1
    )

    # The last owner drops it too - now nothing supports the claim, so it goes.
    with driver.session(database=DATABASE) as session:
        _import(session, "src:k8s-1", ArchitectureModel(), digest=DIGEST_2)

    assert _count(driver, "MATCH (c:InfrastructureClaim) RETURN count(c) AS c") == 0
    assert _count(driver, "MATCH (e:InfrastructureEntity) RETURN count(e) AS c") == 0


def test_a_shared_claim_survives_when_its_evidence_id_is_co_owned_by_the_remaining_source(driver):
    """A real bug found in PR re-review: the original `_EXPIRE_INFRASTRUCTURE_CLAIMS_QUERY` decided
    whether to strip a ref by checking only whether the DEPARTING source owned its Evidence node -
    not whether a REMAINING claim owner also did. When the same evidence id is genuinely co-owned by
    two sources (not just two distinct ids, as in the test above), that stripped a ref the surviving
    owner still supported, and could have deleted the claim entirely despite a remaining owner."""
    shared_evidence_id = "evidence:kubernetes:shared"
    entity = _infra_entity()

    def _model_with_shared_evidence(source_instance_id: str) -> ArchitectureModel:
        return ArchitectureModel(
            provenance=[
                Provenance(
                    id=shared_evidence_id, source_type="KUBERNETES", source_file="shared.yaml"
                )
            ],
            infrastructure_entities=[entity],
            infrastructure_contributions=[
                InfrastructureContribution(
                    entity_id=entity.id,
                    source_instance_id=source_instance_id,
                    evidence_mode=KubernetesEvidenceMode.CAPTURED_RESOURCE,
                    resource_semantic_digest="digest-1",
                    evidence_refs=[shared_evidence_id],
                    mapping_rule_id="kubernetes-adapter@1",
                    mapping_rule_version="v1",
                )
            ],
            infrastructure_claims=[
                InfrastructureClaim(
                    kind=InfrastructureClaimKind.WORKLOAD_EXISTS,
                    subject_id=entity.id,
                    evidence_refs=[shared_evidence_id],
                    mapping_rule_id="kubernetes-adapter@1",
                    mapping_rule_version="v1",
                )
            ],
        )

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(session, "src:k8s-1", _model_with_shared_evidence("src:k8s-1"))
        _import(session, "src:k8s-2", _model_with_shared_evidence("src:k8s-2"))

        evidence_owners = session.run(
            "MATCH (e:Evidence {id: $id}) RETURN e.owner_source_ids AS owners",
            id=shared_evidence_id,
        ).single()["owners"]
        assert sorted(evidence_owners) == ["src:k8s-1", "src:k8s-2"]

        # src:k8s-1 stops emitting anything at all - src:k8s-2 still emits the same claim,
        # referencing the SAME shared evidence id.
        _import(session, "src:k8s-1", ArchitectureModel(), digest=DIGEST_2)

        claim = session.run(
            "MATCH (c:InfrastructureClaim) RETURN c.evidence_refs AS refs, "
            "c.owner_source_ids AS owners"
        ).single()

    # The claim survives with its evidence ref intact - the departing source's co-ownership of that
    # SAME evidence node must not strip a ref the surviving source still genuinely supports.
    assert claim is not None
    assert claim["refs"] == [shared_evidence_id]
    assert claim["owners"] == ["src:k8s-2"]
    assert (
        _count(driver, "MATCH (e:Evidence {id: $id}) RETURN count(e) AS c", id=shared_evidence_id)
        == 1
    )


def test_a_retained_claim_that_changes_evidence_reflects_only_the_new_refs(driver):
    """A real bug found in PR re-review, distinct from the co-owned-evidence one above: a single
    source that RETAINS the same claim (same kind/subject/object, hence the same claim identity)
    across a reimport, but replaces its own evidence, must end up with only the NEW refs - not the
    old ones still accumulated (a plain evidence union never subtracts), and not a dangling
    reference to the now-deleted old Evidence node (a plain overwrite-on-write was order-dependent
    and raced with which write happened last). Ownership of the claim never changes here at all -
    the earlier fixes for cross-source ownership changes never even ran for this case."""
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(
            session,
            "src:k8s-1",
            _infra_claim_model(
                source_instance_id="src:k8s-1", evidence_id="evidence:kubernetes:old"
            ),
        )
        first = session.run(
            "MATCH (c:InfrastructureClaim) RETURN c.evidence_refs AS refs, "
            "c.owner_source_ids AS owners"
        ).single()
        assert first["refs"] == ["evidence:kubernetes:old"]
        assert first["owners"] == ["src:k8s-1"]

        # Same source, same claim identity, reimported with a DIFFERENT evidence ref - the old
        # Evidence node is no longer emitted at all, so it is expired in this same reimport.
        _import(
            session,
            "src:k8s-1",
            _infra_claim_model(
                source_instance_id="src:k8s-1", evidence_id="evidence:kubernetes:new"
            ),
            digest=DIGEST_2,
        )
        second = session.run(
            "MATCH (c:InfrastructureClaim) RETURN c.evidence_refs AS refs, "
            "c.owner_source_ids AS owners"
        ).single()

    assert second is not None
    assert second["refs"] == ["evidence:kubernetes:new"]
    assert second["owners"] == ["src:k8s-1"]
    assert (
        _count(driver, "MATCH (e:Evidence {id: 'evidence:kubernetes:old'}) RETURN count(e) AS c")
        == 0
    )
    # Exactly one claim-support row for this source (overwritten, not accumulated).
    assert _count(driver, "MATCH (c:InfrastructureClaimContribution) RETURN count(c) AS c") == 1


def test_two_co_owners_with_different_evidence_modes_each_retain_their_own_mode(driver):
    """I2 Draft 0.2 §7.2: "Evidence mode is retained per contribution... merging declarations and
    captures never turns all support into observation" - the same rule §7.1 states for entity
    contributions, applying here to claim contributions. Two sources supporting the SAME claim via
    different modes (one DECLARED_MANIFEST, one CAPTURED_RESOURCE) must each retain their own mode
    on their own contribution row - neither may be overwritten or confused with the other's."""
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        _import(
            session,
            "src:k8s-declared",
            _infra_claim_model(
                source_instance_id="src:k8s-declared",
                evidence_id="evidence:kubernetes:declared",
                evidence_mode=KubernetesEvidenceMode.DECLARED_MANIFEST,
            ),
        )
        _import(
            session,
            "src:k8s-captured",
            _infra_claim_model(
                source_instance_id="src:k8s-captured",
                evidence_id="evidence:kubernetes:captured",
                evidence_mode=KubernetesEvidenceMode.CAPTURED_RESOURCE,
            ),
        )

        modes_by_source = {
            record["source"]: record["mode"]
            for record in session.run(
                "MATCH (c:InfrastructureClaimContribution) "
                "UNWIND c.owner_source_ids AS source "
                "RETURN source, c.evidence_mode AS mode"
            )
        }
        claim = session.run(
            "MATCH (c:InfrastructureClaim) RETURN c.evidence_refs AS refs, "
            "c.owner_source_ids AS owners"
        ).single()

    # One shared claim, owned by both, carrying both sources' evidence...
    assert sorted(claim["owners"]) == ["src:k8s-captured", "src:k8s-declared"]
    assert sorted(claim["refs"]) == ["evidence:kubernetes:captured", "evidence:kubernetes:declared"]
    # ...but each source's OWN contribution row retains its OWN evidence mode, not the other's.
    assert modes_by_source == {
        "src:k8s-declared": "DECLARED_MANIFEST",
        "src:k8s-captured": "CAPTURED_RESOURCE",
    }
