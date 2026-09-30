"""Capture-scope persistence and the revision-advance rule (v0.6.0 I2.2d, decision record D5).

Real Neo4j, real Kubernetes envelopes through the real discoverer and importer. An accepted
envelope's capture (namespaces, cluster, revision, mode, capturedAt) is persisted on the source's
`SourceState`; a change to it advances the fence when scoped v2 records exist (because it will feed
the scoped snapshot key) and leaves v0.5 behaviour untouched when none do.
"""

import shutil
import threading
from pathlib import Path

import pytest

from app.architecture_intelligence import repository
from app.graph.importer import (
    _remove_source_tx,
    import_all_sources,
    import_kubernetes_source,
)
from app.graph.revision_fence import bump_revision, lock_revision, read_revision
from app.graph.schema import ensure_schema
from app.sources.model import FilesystemSourceConfig
from tests.integration.test_importer import _deployment, _write_kubernetes_bundle

DATABASE = "neo4j"
EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
SOURCE, SCOPE, CLUSTER = "capture-source", "capture-scope", "capture-cluster"
V2_STUB = "CREATE (:ScopedObservedCallV2 {id: 'evidence:otel:calls-scoped:v2:capture-test'})"
CAPTURE_KEYS = {
    "capture_scope_namespaces",
    "capture_cluster_uid",
    "capture_revision",
    "capture_evidence_mode",
    "capture_captured_at",
}


@pytest.fixture
def graph(driver):
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n").consume()
        ensure_schema(session)
    return driver


@pytest.fixture
def session(graph):
    with graph.session(database=DATABASE) as s:
        yield s


def _resources():
    return [_deployment("checkout-api", "checkout", "deploy-uid-1")]


def _bundle(root, *, prior=None, namespaces=("checkout",), **kwargs):
    return _write_kubernetes_bundle(
        root,
        source_id=SOURCE,
        scope_id=SCOPE,
        cluster_uid=CLUSTER,
        namespaces=list(namespaces),
        resources=_resources(),
        expected_prior_inventory_revision=prior,
        **kwargs,
    )


def _inventory_revision(session) -> str:
    return session.run("MATCH (i:CurrentInventory) RETURN i.inventory_revision AS r").single()["r"]


def _first_import(graph, root, **kwargs):
    stats = import_kubernetes_source(
        graph, database=DATABASE, source_config=_bundle(root, **kwargs)
    )
    assert stats.committed is True
    return stats


def _reimport(graph, session, root, **kwargs):
    config = _bundle(root, prior=_inventory_revision(session), **kwargs)
    return import_kubernetes_source(graph, database=DATABASE, source_config=config)


def _capture(session) -> dict | None:
    record = session.run(
        "MATCH (s:SourceState) WHERE s.capture_cluster_uid IS NOT NULL "
        "RETURN s.capture_scope_namespaces AS namespaces, s.capture_cluster_uid AS cluster, "
        "s.capture_revision AS revision, s.capture_evidence_mode AS mode, "
        "s.capture_captured_at AS captured_at"
    ).single()
    return None if record is None else dict(record)


def _advanced(stats) -> bool:
    [source] = stats.per_source.values()
    return source.graph_revision_advanced


# --- persistence -------------------------------------------------------------------------------


def test_an_accepted_import_persists_the_capture_on_its_source_state(graph, session, tmp_path):
    _first_import(
        graph,
        tmp_path,
        namespaces=("payments", "checkout"),
        revision="rev-1",
        captured_at="2026-09-17T10:00:00Z",
    )

    assert _capture(session) == {
        "namespaces": ["checkout", "payments"],
        "cluster": CLUSTER,
        "revision": "rev-1",
        "mode": "CAPTURED_RESOURCE",
        "captured_at": "2026-09-17T10:00:00Z",
    }


def test_a_reimport_updates_every_capture_property(graph, session, tmp_path):
    _first_import(graph, tmp_path, revision="rev-1", captured_at="2026-09-17T10:00:00Z")

    _reimport(
        graph,
        session,
        tmp_path,
        namespaces=("checkout", "payments"),
        revision="rev-2",
        captured_at="2026-09-18T11:30:00Z",
    )

    assert _capture(session) == {
        "namespaces": ["checkout", "payments"],
        "cluster": CLUSTER,
        "revision": "rev-2",
        "mode": "CAPTURED_RESOURCE",
        "captured_at": "2026-09-18T11:30:00Z",
    }


def test_the_capture_is_the_raw_envelope_value_including_an_offset_free_capturedat(
    graph, session, tmp_path
):
    _first_import(graph, tmp_path, captured_at="2026-09-17T10:00:00Z")

    assert _capture(session)["captured_at"] == "2026-09-17T10:00:00Z"  # type: ignore[index]


def test_a_filesystem_source_gains_no_capture_properties_and_no_nulls(graph, session, tmp_path):
    root = tmp_path / "root"
    shutil.copytree(EXAMPLES_DIR / "product-service", root / "product-service")

    import_all_sources(
        graph,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id="capture-fs", root=root),
    )

    keys = [set(r["keys"]) for r in session.run("MATCH (s:SourceState) RETURN keys(s) AS keys")]
    assert keys and all(not (k & CAPTURE_KEYS) for k in keys)


def test_a_rejected_partial_import_leaves_the_persisted_capture_untouched(graph, session, tmp_path):
    """I1 L29: a rejected incomplete envelope never overwrites what was accepted."""
    _first_import(graph, tmp_path, revision="rev-1")
    before = _capture(session)
    revision_before = read_revision(session)

    rejected = _reimport(
        graph,
        session,
        tmp_path,
        namespaces=("checkout", "payments"),
        revision="rev-2",
        completeness_status="PARTIAL",
    )

    assert rejected.committed is False
    assert _capture(session) == before
    assert read_revision(session) == revision_before


def test_removing_a_source_drops_its_capture_with_its_source_state(graph, session, tmp_path):
    _first_import(graph, tmp_path)
    [state] = session.run("MATCH (s:SourceState) RETURN s.source_instance_id AS id").data()

    session.execute_write(_remove_source_tx, source_instance_id=state["id"])

    assert _capture(session) is None
    assert session.run("MATCH (s:SourceState) RETURN count(s) AS c").single()["c"] == 0


# --- the revision-advance rule -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "kwargs", "baseline_bumps"),
    [
        # Each of these alone is a replay no-op in v0.5: the fence stays where it is.
        ("scope only", {"namespaces": ("checkout", "payments"), "revision": "rev-1"}, False),
        ("revision only", {"revision": "rev-2"}, False),
        ("capturedAt only", {"captured_at": "2026-09-18T11:30:00Z", "revision": "rev-1"}, False),
        # A scope change together with a new revision changes real content, so v0.5 already bumps.
        ("scope and revision", {"namespaces": ("checkout", "payments"), "revision": "rev-2"}, True),
    ],
)
def test_a_capture_change_advances_the_revision_exactly_once_and_only_adds_a_bump_with_v2(
    graph, session, tmp_path, change, kwargs, baseline_bumps
):
    _first_import(graph, tmp_path, revision="rev-1")

    # Without any v2 record: exactly v0.5's behaviour, nothing added by the new rule.
    before_without = read_revision(session)
    stats_without = _reimport(graph, session, tmp_path, **kwargs)
    assert stats_without.committed is True
    assert _advanced(stats_without) is baseline_bumps, change
    assert read_revision(session) == before_without + (1 if baseline_bumps else 0), change

    # Back to the original capture, then the same change with a scoped v2 record present: the
    # fence advances exactly once - never twice, even where v0.5 already advances it.
    _reimport(graph, session, tmp_path, revision="rev-1")
    session.run(V2_STUB).consume()
    before = read_revision(session)
    stats_with = _reimport(graph, session, tmp_path, **{"revision": "rev-1", **kwargs})

    assert stats_with.committed is True
    assert _advanced(stats_with) is True, change
    assert read_revision(session) == before + 1, change


def test_an_unchanged_reimport_never_advances_the_revision_even_with_v2_records(
    graph, session, tmp_path
):
    _first_import(graph, tmp_path, revision="rev-1")
    session.run(V2_STUB).consume()
    before = read_revision(session)

    stats = _reimport(graph, session, tmp_path, revision="rev-1")

    assert stats.committed is True and _advanced(stats) is False
    assert read_revision(session) == before


def test_the_first_persisted_capture_on_an_existing_source_state_counts_as_a_change(
    graph, session, tmp_path
):
    """A graph imported before this rule has a SourceState with no capture: persisting it now must
    move the fence once v2 records exist, because it enters the scoped snapshot key."""
    _first_import(graph, tmp_path, revision="rev-1")
    session.run(
        "MATCH (s:SourceState) REMOVE s.capture_scope_namespaces, s.capture_cluster_uid, "
        "s.capture_revision, s.capture_evidence_mode, s.capture_captured_at"
    ).consume()
    assert _capture(session) is None
    session.run(V2_STUB).consume()
    before = read_revision(session)

    stats = _reimport(graph, session, tmp_path, revision="rev-1")

    assert _advanced(stats) is True and read_revision(session) == before + 1
    assert _capture(session) is not None


def test_a_change_that_already_bumps_is_not_bumped_twice(graph, session, tmp_path):
    _first_import(graph, tmp_path, revision="rev-1")
    session.run(V2_STUB).consume()
    before = read_revision(session)
    changed = _bundle(tmp_path, prior=_inventory_revision(session), revision="rev-2")
    # A new resource changes real content (so the import bumps by itself) and the capture.
    changed = _write_kubernetes_bundle(
        tmp_path,
        source_id=SOURCE,
        scope_id=SCOPE,
        cluster_uid=CLUSTER,
        namespaces=["checkout"],
        resources=[*_resources(), _deployment("cart-api", "checkout", "deploy-uid-2")],
        expected_prior_inventory_revision=_inventory_revision(session),
        revision="rev-2",
    )

    stats = import_kubernetes_source(graph, database=DATABASE, source_config=changed)

    assert stats.committed is True and _advanced(stats) is True
    assert read_revision(session) == before + 1


def test_the_same_revision_never_carries_two_different_captures(graph, session, tmp_path):
    """The point of the rule, read the way a stable snapshot read does: a (revision, capture) pair is
    trustworthy only if the revision did not move while reading it."""
    _first_import(graph, tmp_path, revision="rev-1")
    session.run(V2_STUB).consume()

    def stable_pair():
        revision = read_revision(session)
        capture = _capture(session)
        assert read_revision(session) == revision
        return revision, capture

    seen = [stable_pair()]
    _reimport(graph, session, tmp_path, namespaces=("checkout", "payments"), revision="rev-1")
    seen.append(stable_pair())

    by_revision: dict[int, list] = {}
    for revision, capture in seen:
        by_revision.setdefault(revision, []).append(capture)
    assert seen[0][1] != seen[1][1]
    assert all(len({str(c) for c in captures}) == 1 for captures in by_revision.values())


def test_an_import_racing_an_in_flight_first_v2_unit_still_advances_the_revision(
    graph, session, tmp_path
):
    """An ingestion unit that has taken the fence lock and written the first v2 record but not yet
    committed must not be invisible to a concurrent capture change: the import takes the same lock
    before looking, so it waits, then sees the committed record and advances the fence."""
    _first_import(graph, tmp_path, revision="rev-1")
    before = read_revision(session)
    outcome: dict = {}

    def import_scope_change():
        with graph.session(database=DATABASE) as own:
            # A revision-only change: a replay no-op, so v0.5 itself would not advance the fence and
            # only the new rule can - which is what this test isolates.
            outcome["stats"] = _reimport(graph, own, tmp_path, revision="rev-2")

    with graph.session(database=DATABASE) as holder:
        tx = holder.begin_transaction()
        lock_revision(tx)
        tx.run(V2_STUB).consume()
        thread = threading.Thread(target=import_scope_change)
        thread.start()
        thread.join(timeout=3)
        assert thread.is_alive(), "the import ran despite the held fence lock"
        bump_revision(tx)  # the in-flight unit's own bump
        tx.commit()
    thread.join(timeout=60)

    assert not thread.is_alive()
    assert outcome["stats"].committed is True and _advanced(outcome["stats"]) is True
    assert read_revision(session) == before + 2  # the ingestion unit's bump and the import's


# --- the no-v2 pin -----------------------------------------------------------------------------


def _fingerprint(session):
    state = repository.canonical_snapshot_state(session, coverage_qualification_enabled=True)
    return repository.snapshot_fingerprint(state)


def test_the_persisted_capture_never_changes_the_snapshot(graph, session, tmp_path):
    _first_import(graph, tmp_path, revision="rev-1")
    with_capture = _fingerprint(session)

    session.run(
        "MATCH (s:SourceState) REMOVE s.capture_scope_namespaces, s.capture_cluster_uid, "
        "s.capture_revision, s.capture_evidence_mode, s.capture_captured_at"
    ).consume()
    without_capture = _fingerprint(session)

    assert with_capture == without_capture
