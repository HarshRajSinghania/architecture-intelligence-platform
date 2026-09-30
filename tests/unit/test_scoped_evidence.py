"""Order-independent merge of caller-Pod-scoped v2 records (v0.6.0 I2.2a).

The merge-permutation vectors (`MP01`, `MP02`) were authored by hand from the I1 v2 contract §3
before the implementation existed. Every permutation of their seeds, and any grouping of the folds,
must give the recorded result.
"""

import itertools
import json
from datetime import UTC, datetime, timedelta
from functools import reduce
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.provenance.model import ScopedObservedCall
from app.telemetry.scoped_attribution import ScopedCallSeed
from app.telemetry.scoped_evidence import (
    CONSISTENCY_FIELDS,
    SAMPLE_TRACE_ID_LIMIT,
    merge_scoped_call,
    record_from_seed,
)

VECTORS = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "specifications"
        / "0.6.0"
        / "i1-vectors"
        / "v2-evidence-id.json"
    ).read_text(encoding="utf-8")
)
V01 = next(v for v in VECTORS["key_vectors"] if v["id"] == "V01-base")["input"]
BASE = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)


def _seed(**overrides) -> ScopedCallSeed:
    fields = {
        "environment": V01["environment"],
        "bucket_utc_day": V01["bucket_utc_day"],
        "subject_id": V01["subject_id"],
        "object_id": V01["object_id"],
        "caller_cluster_uid": V01["caller_cluster_uid"],
        "caller_pod_uid": V01["caller_pod_uid"],
        "fact_timestamp": BASE,
        "trace_id": "a" * 32,
        "correlation_mode": "CLIENT_SERVER",
    }
    fields.update(overrides)
    return ScopedCallSeed(**fields)


def _fold(records) -> ScopedObservedCall:
    folded = None
    for record in records:
        folded = merge_scoped_call(folded, record)
    assert folded is not None
    return folded


def _seed_from_vector(seed: dict) -> ScopedCallSeed:
    return _seed(
        fact_timestamp=datetime.fromisoformat(seed["fact_timestamp"]),
        trace_id=seed["trace_id"],
        correlation_mode=seed["correlation_mode"],
        k8s_namespace_name=seed["k8s_namespace_name"],
        k8s_pod_name=seed["k8s_pod_name"],
        k8s_deployment_name=seed["k8s_deployment_name"],
        k8s_statefulset_name=seed["k8s_statefulset_name"],
        k8s_daemonset_name=seed["k8s_daemonset_name"],
    )


def _assert_expected(record: ScopedObservedCall, expected: dict) -> None:
    assert record.first_seen == datetime.fromisoformat(expected["first_seen"])
    assert record.last_seen == datetime.fromisoformat(expected["last_seen"])
    assert record.observation_count == expected["observation_count"]
    assert record.correlation_mode == expected["correlation_mode"]
    assert record.sample_trace_ids == expected["sample_trace_ids"]
    for field in CONSISTENCY_FIELDS:
        assert getattr(record, field) == expected[field], field
    assert (
        record.conflicting_consistency_attributes == expected["conflicting_consistency_attributes"]
    )


@pytest.mark.parametrize("vector", VECTORS["merge_permutation_vectors"], ids=lambda v: v["id"])
def test_every_permutation_gives_the_independent_result(vector):
    records = [record_from_seed(_seed_from_vector(s)) for s in vector["seeds"]]
    for order in itertools.permutations(records):
        _assert_expected(_fold(order), vector["expected"])


@pytest.mark.parametrize("vector", VECTORS["merge_permutation_vectors"], ids=lambda v: v["id"])
def test_any_grouping_of_the_folds_gives_the_same_record(vector):
    records = [record_from_seed(_seed_from_vector(s)) for s in vector["seeds"]]
    expected = _fold(records)
    for split in range(1, len(records)):
        left, right = _fold(records[:split]), _fold(records[split:])
        assert merge_scoped_call(left, right) == expected
        assert merge_scoped_call(right, left) == expected


def test_a_seed_becomes_a_one_observation_record_stamped_with_the_fact_time():
    record = record_from_seed(_seed(k8s_namespace_name="shop", k8s_deployment_name="orders"))

    assert record.observation_count == 1
    assert record.first_seen == record.last_seen == BASE
    assert record.sample_trace_ids == ["a" * 32]
    assert record.k8s_namespace_name == "shop"
    assert record.conflicting_consistency_attributes == []
    assert (
        record.id == next(v for v in VECTORS["key_vectors"] if v["id"] == "V01-base")["evidence_id"]
    )


def test_merging_into_nothing_returns_the_seed():
    record = record_from_seed(_seed())
    assert merge_scoped_call(None, record) is record


def test_records_with_different_ids_cannot_be_merged():
    a = record_from_seed(_seed())
    b = record_from_seed(_seed(caller_pod_uid="another-pod"))
    with pytest.raises(ValueError, match="different ids"):
        merge_scoped_call(a, b)


def test_a_missing_name_never_erases_a_known_one_in_either_order():
    known = record_from_seed(_seed(k8s_pod_name="orders-a"))
    unknown = record_from_seed(_seed(trace_id="b" * 32))
    for order in ((known, unknown), (unknown, known)):
        merged = _fold(order)
        assert merged.k8s_pod_name == "orders-a"
        assert merged.conflicting_consistency_attributes == []


def test_a_conflict_is_absorbing_even_if_a_later_seed_repeats_one_value():
    a, b = "orders-a", "orders-b"
    seeds = [
        record_from_seed(_seed(k8s_pod_name=name, trace_id=f"{i}" * 32))
        for i, name in enumerate((a, b, a), start=1)
    ]
    for order in itertools.permutations(seeds):
        merged = _fold(order)
        assert merged.k8s_pod_name is None
        assert merged.conflicting_consistency_attributes == ["k8s_pod_name"]


def test_two_workload_kind_names_are_kept_per_field_and_do_not_conflict_with_each_other():
    merged = _fold(
        [
            record_from_seed(_seed(k8s_deployment_name="orders", trace_id="1" * 32)),
            record_from_seed(_seed(k8s_statefulset_name="orders-db", trace_id="2" * 32)),
        ]
    )
    assert merged.k8s_deployment_name == "orders"
    assert merged.k8s_statefulset_name == "orders-db"
    assert merged.conflicting_consistency_attributes == []


def test_the_stronger_correlation_mode_wins_in_either_order():
    client_only = record_from_seed(_seed(correlation_mode="CLIENT_ONLY", trace_id="1" * 32))
    paired = record_from_seed(_seed(correlation_mode="CLIENT_SERVER", trace_id="2" * 32))
    assert _fold([client_only, paired]).correlation_mode == "CLIENT_SERVER"
    assert _fold([paired, client_only]).correlation_mode == "CLIENT_SERVER"


def test_samples_are_the_sorted_smallest_five_distinct_trace_ids():
    trace_ids = ["f", "3", "9", "3", "1", "8", "5", "2"]
    records = [record_from_seed(_seed(trace_id=t * 32)) for t in trace_ids]
    merged = _fold(records)
    assert merged.sample_trace_ids == [t * 32 for t in ("1", "2", "3", "5", "8")]
    assert len(merged.sample_trace_ids) == SAMPLE_TRACE_ID_LIMIT
    assert merged.observation_count == len(trace_ids)


def test_the_record_is_immutable():
    record = record_from_seed(_seed())
    with pytest.raises(ValueError):
        record.observation_count = 2  # pyright: ignore[reportAttributeAccessIssue]


_names = st.one_of(st.none(), st.sampled_from(["a", "b", "c"]))
_seeds = st.builds(
    lambda seconds, trace, mode, ns, pod, dep, sts, ds: record_from_seed(
        _seed(
            fact_timestamp=BASE + timedelta(seconds=seconds),
            trace_id=trace * 32,
            correlation_mode=mode,
            k8s_namespace_name=ns,
            k8s_pod_name=pod,
            k8s_deployment_name=dep,
            k8s_statefulset_name=sts,
            k8s_daemonset_name=ds,
        )
    ),
    st.integers(0, 3600),
    st.sampled_from(list("0123456789abcdef")),
    st.sampled_from(["CLIENT_ONLY", "CLIENT_SERVER"]),
    _names,
    _names,
    _names,
    _names,
    _names,
)


@given(st.lists(_seeds, min_size=1, max_size=6), st.randoms(use_true_random=False))
def test_property_the_fold_does_not_depend_on_order(records, rng):
    shuffled = list(records)
    rng.shuffle(shuffled)
    assert _fold(shuffled) == _fold(records)


@given(st.lists(_seeds, min_size=2, max_size=6), st.data())
def test_property_the_fold_does_not_depend_on_grouping(records, data):
    split = data.draw(st.integers(1, len(records) - 1))
    left, right = _fold(records[:split]), _fold(records[split:])
    assert merge_scoped_call(left, right) == _fold(records)
    assert reduce(merge_scoped_call, [right, left]) == _fold(records)


@given(st.lists(_seeds, min_size=1, max_size=8))
def test_property_counts_bounds_and_samples_follow_the_seeds(records):
    merged = _fold(records)
    assert merged.observation_count == len(records)
    assert merged.first_seen == min(r.first_seen for r in records)
    assert merged.last_seen == max(r.last_seen for r in records)
    assert merged.sample_trace_ids == sorted({t for r in records for t in r.sample_trace_ids})[:5]
    flagged = set(merged.conflicting_consistency_attributes)
    for field in CONSISTENCY_FIELDS:
        distinct = {getattr(r, field) for r in records} - {None}
        assert (field in flagged) is (len(distinct) > 1)
        expected = None if len(distinct) != 1 else next(iter(distinct))
        assert getattr(merged, field) == expected
