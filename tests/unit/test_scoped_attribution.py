"""Ingestion guards I-1..I-5 and the CLIENT carrier (v0.6.0 I2.1c).

The expected result of every ingestion variant is read from the independently authored I1 oracle
(`docs/specifications/0.6.0/i1-vectors/conformance-expected.json`) and compared with the
implementation. Only the *inputs* are constructed here, one hand-mapped case per oracle variant, so
the implementation is never asserted against its own output. The seed's key inputs are also hashed
with the I1 v2 canonicalization and compared with the I1 golden vector.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.telemetry.correlation_buffer import PendingHttpSpan
from app.telemetry.model import RuntimeSpan
from app.telemetry.scoped_attribution import (
    ClientCarrier,
    LocalityDisposition,
    ScopedCallSeed,
    ScopedIngressRefusal,
    admissible,
    evaluate_scoped_ingress,
    server_only_refusal,
    utc_day,
)

VECTORS = Path(__file__).resolve().parents[2] / "docs" / "specifications" / "0.6.0" / "i1-vectors"
ORACLE = json.loads((VECTORS / "conformance-expected.json").read_text(encoding="utf-8"))
V2 = json.loads((VECTORS / "v2-evidence-id.json").read_text(encoding="utf-8"))
WINDOW = json.loads((VECTORS / "utc-day-window.json").read_text(encoding="utf-8"))

K1 = ORACLE["fixtures"]["clusters"]["K1"]
P1 = ORACLE["fixtures"]["pods"]["P1"]
CALLER = "service:orders"
O1 = "operation:pricing:GET:/prices"
ENV = "production"
T01 = next(t for t in WINDOW["timestamp_roles"] if t["id"].startswith("T01"))
T02 = next(t for t in WINDOW["timestamp_roles"] if t["id"].startswith("T02"))
T03 = next(t for t in WINDOW["timestamp_roles"] if t["id"].startswith("T03"))


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _carrier(**overrides) -> ClientCarrier:
    fields = {
        "environment": ENV,
        "pod_uid": P1,
        "cluster_uid": K1,
        "end_time": _ts(T01["client_timestamp"]),
    }
    fields.update(overrides)
    return ClientCarrier(**fields)


def _evaluate(carrier, *, fact_ts=T01["fact_timestamp"], mode="CLIENT_SERVER", env=ENV):
    return evaluate_scoped_ingress(
        subject_id=CALLER,
        object_id=O1,
        fact_environment=env,
        fact_timestamp=_ts(fact_ts),
        trace_id="a" * 32,
        correlation_mode=mode,
        carrier=carrier,
    )


def _as_oracle(outcome) -> dict:
    if isinstance(outcome, ScopedCallSeed):
        return {
            "phase": "ingestion",
            "v1": "unchanged",
            "v2_written": True,
            "disposition": "APPLICABLE",
            "reasons": [],
        }
    assert isinstance(outcome, ScopedIngressRefusal)
    return {
        "phase": "ingestion",
        "v1": outcome.v1_status,
        "v2_written": False,
        "disposition": str(outcome.disposition),
        "reasons": list(outcome.reasons),
    }


def _server_only():
    return server_only_refusal(
        trace_id="a" * 32, environment=ENV, timestamp=_ts(T01["fact_timestamp"])
    )


# One hand-mapped input per oracle variant that has an `ingestion` expectation.
INPUTS = {
    "L06a": lambda: _evaluate(_carrier(pod_uid=None)),
    "L06b": lambda: _evaluate(_carrier(cluster_uid=None)),
    "L06c": lambda: _evaluate(_carrier(pod_uid=None, cluster_uid=None)),
    "L07a": lambda: _evaluate(_carrier()),
    "L08a": lambda: _evaluate(_carrier()),
    "L08b": lambda: _evaluate(_carrier()),
    "L09a": lambda: _evaluate(_carrier(), mode="CLIENT_ONLY"),
    "L09b": _server_only,
    "L10a": lambda: _evaluate(_carrier(environment="staging")),
    "L11a": lambda: _evaluate(
        _carrier(end_time=_ts(T02["client_timestamp"])), fact_ts=T02["fact_timestamp"]
    ),
    "L34a": lambda: _evaluate(_carrier(namespace="shop-old")),
    "L34b": lambda: _evaluate(_carrier(deployment_name="orders", statefulset_name="orders-db")),
    "L35a": _server_only,
    "L35b": lambda: _evaluate(None),
    "L35c": lambda: _evaluate(_carrier(pod_uid=None)),
    "L35d": lambda: _evaluate(_carrier(environment=None, pod_uid=None)),
    "L35e": lambda: _evaluate(_carrier(environment="staging")),
    "L35f": lambda: _evaluate(
        _carrier(end_time=_ts(T02["client_timestamp"])), fact_ts=T02["fact_timestamp"]
    ),
    "L35g": lambda: _evaluate(
        _carrier(pod_uid=None, deployment_name="orders", daemonset_name="orders-ds")
    ),
}


def _oracle_ingestion_variants() -> dict[str, dict]:
    found = {}
    for case in ORACLE["cases"]:
        for variant in case["variants"]:
            if "ingestion" in variant["expected"]:
                found[f"{case['id']}{variant['id']}"] = variant["expected"]["ingestion"]
    return found


ORACLE_INGESTION = _oracle_ingestion_variants()


def test_every_oracle_ingestion_variant_has_a_mapped_input():
    assert set(INPUTS) == set(ORACLE_INGESTION)


@pytest.mark.parametrize("variant", sorted(ORACLE_INGESTION))
def test_ingestion_outcome_matches_the_independent_oracle(variant):
    assert _as_oracle(INPUTS[variant]()) == ORACLE_INGESTION[variant]


def test_eligible_seed_hashes_to_the_i1_golden_v2_id():
    seed = _evaluate(_carrier())
    assert isinstance(seed, ScopedCallSeed)
    key = {
        "contract_version": 2,
        "source_type": "OPENTELEMETRY",
        "evidence_type": "OBSERVED",
        "relation_type": "CALLS",
        "environment": seed.environment,
        "bucket_utc_day": seed.bucket_utc_day,
        "subject_id": seed.subject_id,
        "object_id": seed.object_id,
        "caller_cluster_uid": seed.caller_cluster_uid,
        "caller_pod_uid": seed.caller_pod_uid,
    }
    canonical = json.dumps(key, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    v01 = next(v for v in V2["key_vectors"] if v["id"] == "V01-base")
    assert f"evidence:otel:calls-scoped:v2:{digest}" == v01["evidence_id"]


# --- timestamp roles (matrix §12.6; vectors T01-T03) --------------------------------------------


def test_paired_seed_takes_its_day_and_time_from_the_accepted_fact_not_the_client():
    seed = _evaluate(_carrier())
    assert isinstance(seed, ScopedCallSeed)
    assert seed.bucket_utc_day == T01["v2_bucket_utc_day"]
    assert seed.fact_timestamp == _ts(T01["fact_timestamp"])
    assert seed.fact_timestamp != _ts(T01["client_timestamp"])
    assert seed.fact_timestamp == _ts(T01["v2_first_seen"]) == _ts(T01["v2_last_seen"])


def test_client_only_seed_uses_the_shared_instant():
    seed = _evaluate(
        _carrier(end_time=_ts(T03["client_timestamp"])),
        fact_ts=T03["fact_timestamp"],
        mode="CLIENT_ONLY",
    )
    assert isinstance(seed, ScopedCallSeed)
    assert seed.bucket_utc_day == T03["v2_bucket_utc_day"]
    assert seed.fact_timestamp == _ts(T03["v2_first_seen"])


def test_cross_midnight_pair_is_refused_and_keeps_the_v1_day():
    refusal = _evaluate(
        _carrier(end_time=_ts(T02["client_timestamp"])), fact_ts=T02["fact_timestamp"]
    )
    assert isinstance(refusal, ScopedIngressRefusal)
    assert refusal.bucket_utc_day == T02["v1_bucket_day"]


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        (datetime(2026, 9, 28, 23, 59, 59, 999999, tzinfo=UTC), "2026-09-28"),
        (datetime(2026, 9, 29, 0, 0, tzinfo=UTC), "2026-09-29"),
        (datetime.fromisoformat("2026-09-29T01:30:00+02:00"), "2026-09-28"),
        (datetime(2026, 9, 28, 12, 0), "2026-09-28"),  # noqa: DTZ001 - deliberately naive: read as UTC, like v1
    ],
)
def test_utc_day(instant, expected):
    assert utc_day(instant).isoformat() == expected


# --- admissible values (matrix §10.2) ------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", 0, 7, True, False, [], ["a"], {}, {"a": 1}, b"x", 1.5])
def test_non_string_or_empty_values_are_missing(value):
    assert admissible(value) is None


@pytest.mark.parametrize("value", ["a", " ", " a ", "A", "0", "k8s-uid", "ü"])
def test_a_nonempty_string_is_kept_byte_for_byte(value):
    assert admissible(value) == value


def test_no_trimming_or_case_folding_in_the_environment_guard():
    refusal = _evaluate(_carrier(environment="Production"))
    assert isinstance(refusal, ScopedIngressRefusal)
    assert refusal.reasons == ("LOCALITY_CLIENT_FACT_ENVIRONMENT_MISMATCH",)
    assert isinstance(_evaluate(_carrier(environment="production ")), ScopedIngressRefusal)


# --- precedence, ordering, no double-emit ----------------------------------------------------------


def test_environment_mismatch_with_a_missing_uid_is_inapplicable_with_both_reasons_sorted():
    refusal = _evaluate(_carrier(environment="staging", pod_uid=None))
    assert isinstance(refusal, ScopedIngressRefusal)
    assert refusal.disposition is LocalityDisposition.INAPPLICABLE
    assert refusal.reasons == (
        "LOCALITY_CLIENT_FACT_ENVIRONMENT_MISMATCH",
        "LOCALITY_POD_UID_MISSING",
    )


def test_a_conflict_outranks_every_other_cause():
    refusal = _evaluate(
        _carrier(
            environment="staging",
            cluster_uid=None,
            deployment_name="a",
            statefulset_name="b",
            end_time=_ts(T02["client_timestamp"]),
        ),
        fact_ts=T02["fact_timestamp"],
    )
    assert isinstance(refusal, ScopedIngressRefusal)
    assert refusal.disposition is LocalityDisposition.CONFLICT
    assert list(refusal.reasons) == sorted(refusal.reasons)
    assert len(set(refusal.reasons)) == len(refusal.reasons) == 4


def test_a_missing_environment_is_never_also_a_mismatch():
    refusal = _evaluate(_carrier(environment=None))
    assert isinstance(refusal, ScopedIngressRefusal)
    assert refusal.reasons == ("LOCALITY_CLIENT_IDENTITY_MISSING",)


def test_a_missing_uid_never_adds_the_generic_carrier_code():
    refusal = _evaluate(_carrier(pod_uid=None, cluster_uid=None))
    assert isinstance(refusal, ScopedIngressRefusal)
    assert "LOCALITY_CLIENT_IDENTITY_MISSING" not in refusal.reasons


def test_a_single_workload_kind_name_is_not_a_conflict():
    for kind in ("deployment_name", "statefulset_name", "daemonset_name"):
        assert isinstance(_evaluate(_carrier(**{kind: "x"})), ScopedCallSeed)


def test_namespace_and_pod_name_are_never_compared_at_ingestion():
    seed = _evaluate(_carrier(namespace="anything", pod_name="whatever", deployment_name="d"))
    assert isinstance(seed, ScopedCallSeed)
    assert seed.k8s_namespace_name == "anything"
    assert seed.k8s_pod_name == "whatever"
    assert seed.k8s_deployment_name == "d"


def test_a_refusal_carries_codes_and_identifiers_but_no_attribute_values():
    refusal = _evaluate(_carrier(environment="staging", namespace="shop", pod_name="secret-pod"))
    dumped = refusal.model_dump_json()
    for value in (P1, K1, "shop", "secret-pod", "staging"):
        assert value not in dumped


def test_models_are_immutable():
    seed = _evaluate(_carrier())
    assert isinstance(seed, ScopedCallSeed)
    with pytest.raises(ValueError):
        seed.caller_pod_uid = "x"  # pyright: ignore[reportAttributeAccessIssue]


# --- carrier construction --------------------------------------------------------------------------


def _runtime_span(**overrides) -> RuntimeSpan:
    fields = {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "parent_span_id": None,
        "span_name": "op",
        "span_kind": "CLIENT",
        "service_name": "orders",
        "environment": ENV,
        "k8s_pod_uid": P1,
        "k8s_cluster_uid": K1,
        "k8s_namespace_name": "shop",
        "k8s_pod_name": "orders-abc",
        "k8s_deployment_name": "orders",
        "start_time": datetime(2026, 9, 28, 10, tzinfo=UTC),
        "end_time": datetime(2026, 9, 28, 10, 0, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return RuntimeSpan(**fields)


def test_carrier_from_a_runtime_span_uses_its_end_time_and_admitted_fields():
    carrier = ClientCarrier.from_span(_runtime_span())
    assert carrier == ClientCarrier(
        environment=ENV,
        pod_uid=P1,
        cluster_uid=K1,
        end_time=datetime(2026, 9, 28, 10, 0, 1, tzinfo=UTC),
        namespace="shop",
        pod_name="orders-abc",
        deployment_name="orders",
    )


def test_carrier_from_a_pending_span_uses_its_timestamp():
    pending = PendingHttpSpan(
        trace_id="a" * 32,
        span_id="b" * 16,
        parent_span_id=None,
        span_kind="CLIENT",
        service_name="orders",
        environment=ENV,
        timestamp=datetime(2026, 9, 28, 10, 0, 1, tzinfo=UTC),
        k8s_pod_uid=P1,
        k8s_cluster_uid=K1,
    )
    carrier = ClientCarrier.from_span(pending)
    assert carrier.pod_uid == P1
    assert carrier.cluster_uid == K1
    assert carrier.end_time == pending.timestamp
    assert carrier.namespace is None


def test_empty_strings_in_a_span_are_missing_in_the_carrier():
    carrier = ClientCarrier.from_span(_runtime_span(k8s_pod_uid="", environment=""))
    assert carrier.pod_uid is None
    assert carrier.environment is None
