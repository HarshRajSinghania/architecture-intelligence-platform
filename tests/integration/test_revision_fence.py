from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.architecture_intelligence.repository import (
    canonical_snapshot_state,
    read_stable_snapshot_from_session,
    snapshot_fingerprint,
)
from app.canonical import ids
from app.canonical.model import ArchitectureModel, Relation, Service
from app.graph.importer import import_all_sources, import_source
from app.graph.revision_fence import RevisionSingletonMissing, bump_revision, read_revision
from app.graph.schema import ensure_schema
from app.provenance.model import ObservedEvidence
from app.sources.model import FilesystemSourceConfig
from app.telemetry.aggregator import persist_observation_batch
from app.telemetry.model import ObservationBatch, ObservedFactCandidate

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
DATABASE = "neo4j"


@pytest.fixture(autouse=True)
def clean_database(driver):
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield


def test_ensure_schema_creates_revision_singleton_at_zero_idempotently(driver):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        assert read_revision(session) == 0
        ensure_schema(session)  # idempotent: must not reset an already-created revision
        assert read_revision(session) == 0


def test_ensure_schema_creates_aip_internal_state_uniqueness_constraint(driver):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        names = {
            record["name"] for record in session.run("SHOW CONSTRAINTS YIELD name RETURN name")
        }
    assert "aip_internal_state_id" in names


@pytest.mark.parametrize("bad_revision", [None, "not-a-number", -1, True])
def test_read_revision_rejects_a_corrupted_revision_value(driver, bad_revision):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        if bad_revision is None:
            session.run("MATCH (s:AipInternalState {id: 'architecture'}) REMOVE s.revision")
        else:
            session.run(
                "MATCH (s:AipInternalState {id: 'architecture'}) SET s.revision = $value",
                value=bad_revision,
            )
        with pytest.raises(RevisionSingletonMissing):
            read_revision(session)


def test_bump_revision_heals_a_null_revision_instead_of_propagating_it(driver):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        session.run("MATCH (s:AipInternalState {id: 'architecture'}) REMOVE s.revision")

        session.execute_write(bump_revision)

        assert read_revision(session) == 1


def test_import_all_sources_bumps_revision_once_per_write_transaction(driver):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        revision_before = read_revision(session)

    stats = import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id="test-revision-fence-examples", root=EXAMPLES_DIR),
    )

    with driver.session(database=DATABASE) as session:
        revision_after = read_revision(session)

    # PR3a: the pre-merge pass no longer bumps the revision fence itself (MERGE is idempotent);
    # exactly one conditional bump happens per source, inside its own reconciliation transaction.
    assert revision_after - revision_before == len(stats.per_source)


def test_rolled_back_import_does_not_advance_revision(driver):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        revision_before = read_revision(session)

        model = ArchitectureModel(
            services=[Service(id="service:x", name="X")],
            relations=[
                Relation(type="NOT_A_REAL_RELATION", source_id="service:x", target_id="service:x")
            ],
        )
        with pytest.raises(ValueError):
            import_source(
                session,
                source_instance_id="urn:aip:source:test:x",
                locator="test-locator",
                model=model,
                semantic_input_digest="deadbeef",
                discovery_scope_id="urn:aip:scope:test",
                scope_definition_digest="deadbeef",
            )

        revision_after = read_revision(session)

    assert revision_after == revision_before


def test_persist_observation_batch_advances_revision_by_one(driver):
    import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id="test-revision-fence-examples", root=EXAMPLES_DIR),
    )
    with driver.session(database=DATABASE) as session:
        revision_before = read_revision(session)

    subject_id = ids.service_id("order-service")
    object_id = ids.operation_id(ids.service_id("product-service"), "GET", "/products/{id}")
    bucket_start = datetime(2026, 8, 26, tzinfo=UTC)
    bucket_end = datetime(2026, 8, 27, tzinfo=UTC)
    evidence = ObservedEvidence(
        id=ids.observed_evidence_id("test", bucket_start, subject_id, "CALLS", object_id),
        environment="test",
        bucket_start=bucket_start,
        bucket_end=bucket_end,
        first_seen=bucket_start,
        last_seen=bucket_start,
        observation_count=1,
        sample_trace_ids=["a" * 32],
    )
    batch = ObservationBatch(
        facts=[
            ObservedFactCandidate(
                subject_id=subject_id,
                relation_type="CALLS",
                object_id=object_id,
                environment="test",
                timestamp=bucket_start,
                trace_id="a" * 32,
                evidence=evidence,
            )
        ]
    )
    persist_observation_batch(driver, DATABASE, batch)

    with driver.session(database=DATABASE) as session:
        revision_after = read_revision(session)
    assert revision_after - revision_before == 1


def _fingerprint(driver):
    with driver.session(database=DATABASE) as session:
        return snapshot_fingerprint(
            canonical_snapshot_state(session, coverage_qualification_enabled=True)
        )


def test_snapshot_fingerprint_is_stable_across_reimport_of_identical_sources(driver):
    import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id="test-revision-fence-examples", root=EXAMPLES_DIR),
    )
    fingerprint_1 = _fingerprint(driver)

    import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id="test-revision-fence-examples", root=EXAMPLES_DIR),
    )  # idempotent reimport
    fingerprint_2 = _fingerprint(driver)

    assert fingerprint_1 == fingerprint_2


def test_snapshot_fingerprint_changes_when_a_node_property_changes(driver):
    import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id="test-revision-fence-examples", root=EXAMPLES_DIR),
    )
    fingerprint_before = _fingerprint(driver)

    with driver.session(database=DATABASE) as session:
        session.run(
            "MATCH (s:Service {id: $id}) SET s.version = 'v2-test'",
            id=ids.service_id("order-service"),
        )

    fingerprint_after = _fingerprint(driver)
    assert fingerprint_before != fingerprint_after


def test_snapshot_fingerprint_changes_when_evidence_changes(driver):
    import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id="test-revision-fence-examples", root=EXAMPLES_DIR),
    )
    with driver.session(database=DATABASE) as session:
        fingerprint_before = snapshot_fingerprint(
            canonical_snapshot_state(session, coverage_qualification_enabled=True)
        )
        any_evidence_id = session.run("MATCH (e:Evidence) RETURN e.id AS id LIMIT 1").single()["id"]

    with driver.session(database=DATABASE) as session:
        session.run(
            "MATCH (e:Evidence {id: $id}) SET e.source_revision = 'changed-for-test'",
            id=any_evidence_id,
        )

    fingerprint_after = _fingerprint(driver)
    assert fingerprint_before != fingerprint_after


def test_snapshot_fingerprint_unaffected_by_reconciliation_only_metadata(driver):
    import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id="test-revision-fence-examples", root=EXAMPLES_DIR),
    )
    fingerprint_before = _fingerprint(driver)

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)  # re-running only touches AipInternalState/constraints

    fingerprint_after = _fingerprint(driver)
    assert fingerprint_before == fingerprint_after


def test_read_stable_snapshot_from_session_matches_independent_computation(driver):
    """The actual Neo4j-wired entry point I1.3 will call - proves the retry loop, the revision
    fence, and the canonical projection compose correctly against a real database, not just as
    individually tested pieces."""
    import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id="test-revision-fence-examples", root=EXAMPLES_DIR),
    )

    with driver.session(database=DATABASE) as session:
        result = read_stable_snapshot_from_session(session, coverage_qualification_enabled=True)

    expected_snapshot_id, expected_model_revision = _fingerprint(driver)
    assert result.snapshot_id == expected_snapshot_id
    assert result.model_revision == expected_model_revision
    assert result.extra is None


def test_read_stable_snapshot_from_session_passes_through_a_real_read_extra(driver):
    import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id="test-revision-fence-examples", root=EXAMPLES_DIR),
    )

    def count_services(session):
        return session.run("MATCH (n:Service) RETURN count(n) AS c").single()["c"]

    with driver.session(database=DATABASE) as session:
        result = read_stable_snapshot_from_session(
            session, coverage_qualification_enabled=True, read_extra=count_services
        )

    with driver.session(database=DATABASE) as session:
        expected_count = count_services(session)
    assert result.extra == expected_count
    assert expected_count > 0


def test_concurrent_bumps_each_advance_the_revision_exactly_once(driver):
    """Every committed writer must move the fence by one, or two different committed states could
    share a revision and a stable read could not tell them apart."""
    import threading

    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n").consume()
        ensure_schema(session)
        before = read_revision(session)

    workers = 16
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def run() -> None:
        try:
            barrier.wait()
            with driver.session(database=DATABASE) as own:
                own.execute_write(bump_revision)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    with driver.session(database=DATABASE) as session:
        assert errors == []
        assert read_revision(session) == before + workers


def test_concurrent_lock_then_bump_units_each_advance_the_revision_exactly_once(driver):
    """`lock_revision` must only take the lock. If it wrote back the revision it had read before the
    lock was granted, a waiting unit would undo the increment a committed unit had just made."""
    import threading

    from app.graph.revision_fence import lock_revision

    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n").consume()
        ensure_schema(session)
        before = read_revision(session)

    def unit(tx):
        lock_revision(tx)
        return bump_revision(tx)

    workers = 12
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []
    returned: list[int | None] = []

    def run() -> None:
        try:
            barrier.wait()
            with driver.session(database=DATABASE) as own:
                returned.append(own.execute_write(unit))
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    with driver.session(database=DATABASE) as session:
        assert errors == []
        assert sorted(returned) == list(range(before + 1, before + workers + 1))
        assert read_revision(session) == before + workers
