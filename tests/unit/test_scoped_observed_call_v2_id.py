"""The v2 scoped-call ID, checked against the independently authored I1 vectors (v0.6.0 I2.2a).

The vectors' canonical bytes and SHA-256 values were written by hand and hashed with `sha256sum`
before any implementation existed (`docs/specifications/0.6.0/i1-vectors/v2-evidence-id.json`); here
the real `scoped_observed_call_v2_id` must reproduce every one of them.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.architecture_intelligence.canonical_json import canonical_json_bytes
from app.canonical import ids
from app.provenance.model import ScopedObservedCall
from app.telemetry import scoped_attribution

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
KEY_VECTORS = VECTORS["key_vectors"]
_VARIABLE = (
    "environment",
    "bucket_utc_day",
    "subject_id",
    "object_id",
    "caller_cluster_uid",
    "caller_pod_uid",
)


def _id_from(key: dict) -> str:
    return ids.scoped_observed_call_v2_id(**{name: key[name] for name in _VARIABLE})


@pytest.mark.parametrize("vector", KEY_VECTORS, ids=lambda v: v["id"])
def test_the_implementation_reproduces_every_independent_vector(vector):
    assert _id_from(vector["input"]) == vector["evidence_id"]


def test_reordered_input_is_the_same_identity():
    v01 = next(v for v in KEY_VECTORS if v["id"] == "V01-base")
    reordered = dict(reversed(list(v01["input"].items())))
    assert list(reordered) != list(v01["input"])
    assert _id_from(reordered) == v01["evidence_id"]


def test_distinct_pod_cluster_operation_day_and_environment_are_distinct_identities():
    base = next(v for v in KEY_VECTORS if v["id"] == "V01-base")["input"]
    variants = {
        "pod": {**base, "caller_pod_uid": "another-pod"},
        "cluster": {**base, "caller_cluster_uid": "another-cluster"},
        "operation": {**base, "object_id": "operation:other:GET:/x"},
        "day": {**base, "bucket_utc_day": "2026-09-29"},
        "environment": {**base, "environment": "staging"},
        "caller": {**base, "subject_id": "service:other"},
    }
    seen = {_id_from(base)}
    for name, key in variants.items():
        identity = _id_from(key)
        assert identity not in seen, name
        seen.add(identity)


def test_the_id_is_the_full_sha256_of_the_snapshot_fingerprint_style_canonical_json():
    key = {
        "contract_version": 2,
        "source_type": "OPENTELEMETRY",
        "evidence_type": "OBSERVED",
        "relation_type": "CALLS",
        "environment": "prod-münchen",
        "bucket_utc_day": "2026-09-28",
        "subject_id": "service:orders",
        "object_id": "operation:pricing:GET:/prices",
        "caller_cluster_uid": "K",
        "caller_pod_uid": "P",
    }
    canonical = canonical_json_bytes(key)
    assert "ü".encode() in canonical  # raw UTF-8, not \u-escaped
    assert _id_from(key) == f"evidence:otel:calls-scoped:v2:{hashlib.sha256(canonical).hexdigest()}"
    assert len(_id_from(key).rsplit(":", 1)[1]) == 64


@pytest.mark.parametrize("vector", VECTORS["v1_unchanged"], ids=lambda v: v["id"])
def test_the_v1_evidence_id_is_unchanged_and_has_no_pod_or_cluster(vector):
    day = datetime.fromisoformat(vector["bucket_day"]).replace(tzinfo=UTC)
    subject, relation, obj = vector["seed_utf8"].split("|")
    assert (
        ids.observed_evidence_id(vector["environment"], day, subject, relation, obj)
        == (vector["evidence_id"])
    )


def test_the_key_constants_agree_across_the_three_modules_that_state_them():
    model = ScopedObservedCall.model_fields
    assert model["contract_version"].default == ids.SCOPED_CALL_V2_CONTRACT_VERSION
    assert model["source_type"].default == ids.SCOPED_CALL_V2_SOURCE_TYPE
    assert model["evidence_type"].default == ids.SCOPED_CALL_V2_EVIDENCE_TYPE
    assert model["relation_type"].default == ids.SCOPED_CALL_V2_RELATION_TYPE
    assert scoped_attribution.V2_CONTRACT_VERSION == ids.SCOPED_CALL_V2_CONTRACT_VERSION
    assert scoped_attribution.V2_SOURCE_TYPE == ids.SCOPED_CALL_V2_SOURCE_TYPE
    assert scoped_attribution.V2_EVIDENCE_TYPE == ids.SCOPED_CALL_V2_EVIDENCE_TYPE
    assert scoped_attribution.V2_RELATION_TYPE == ids.SCOPED_CALL_V2_RELATION_TYPE
    assert model["normalization_rule_id"].default == scoped_attribution.NORMALIZATION_RULE_ID
    assert (
        model["normalization_rule_version"].default == scoped_attribution.NORMALIZATION_RULE_VERSION
    )


def test_a_record_has_exactly_the_contract_fields():
    # I1 v2 contract §1 (ten identity fields) + §3 (non-identity) + `id`; the snapshot fragment
    # entries in the vector file use exactly this set.
    fragment_fields = set(VECTORS["snapshot_fragment"]["entries"][0])
    assert set(ScopedObservedCall.model_fields) == fragment_fields
