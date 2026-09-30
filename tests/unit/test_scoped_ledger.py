"""Pure parts of the scoped-evidence provenance (v0.6.0 I2.2c): the primary-cause rule, the
membership digest, the counter identity, the legacy classification and the sampled logging."""

import logging

import pytest

from app.canonical import ids
from app.telemetry.scoped_attribution import (
    LocalityDisposition,
    ScopedIngressRefusal,
    primary_cause,
)
from app.telemetry.scoped_ledger import (
    SAMPLES_PER_REASON,
    _classify_legacy,
    counter_id,
    log_refusal_samples,
)

CLIENT_IDENTITY_MISSING = "LOCALITY_CLIENT_IDENTITY_MISSING"
CLUSTER_UID_MISSING = "LOCALITY_CLUSTER_UID_MISSING"
POD_UID_MISSING = "LOCALITY_POD_UID_MISSING"
ENV_MISMATCH = "LOCALITY_CLIENT_FACT_ENVIRONMENT_MISMATCH"
DAY_MISMATCH = "LOCALITY_CLIENT_FACT_DAY_MISMATCH"
INTERNAL_CONFLICT = "LOCALITY_CLIENT_INTERNAL_CONFLICT"
SERVER_ONLY = "LOCALITY_SERVER_ONLY_NO_CLIENT"

INSUFFICIENT = LocalityDisposition.INSUFFICIENT_EVIDENCE
INAPPLICABLE = LocalityDisposition.INAPPLICABLE
CONFLICT = LocalityDisposition.CONFLICT


def _refusal(disposition, *reasons: str, trace="a" * 32) -> ScopedIngressRefusal:
    return ScopedIngressRefusal(
        trace_id=trace,
        environment="production",
        bucket_utc_day="2026-09-28",
        disposition=disposition,
        reasons=tuple(sorted(reasons)),
    )


# Hand-derived from decision record D12.1 (smallest reason among those of the primary disposition),
# not from running the implementation: dispositions are CONFLICT > INAPPLICABLE > INSUFFICIENT, and
# only INTERNAL_CONFLICT is a CONFLICT, only the two mismatches are INAPPLICABLE.
PRIMARY_CAUSE_TABLE = [
    ("a single missing Pod UID", INSUFFICIENT, [POD_UID_MISSING], POD_UID_MISSING),
    (
        "missing environment and Pod UID: the smaller code",
        INSUFFICIENT,
        [CLIENT_IDENTITY_MISSING, POD_UID_MISSING],
        CLIENT_IDENTITY_MISSING,
    ),
    (
        "both UIDs missing: the smaller code",
        INSUFFICIENT,
        [CLUSTER_UID_MISSING, POD_UID_MISSING],
        CLUSTER_UID_MISSING,
    ),
    (
        "a conflict outranks a missing Pod UID even though the UID code sorts later",
        CONFLICT,
        [INTERNAL_CONFLICT, POD_UID_MISSING],
        INTERNAL_CONFLICT,
    ),
    (
        "an inapplicable mismatch outranks a missing Pod UID",
        INAPPLICABLE,
        [ENV_MISMATCH, POD_UID_MISSING],
        ENV_MISMATCH,
    ),
    (
        "two inapplicable causes: the smaller code",
        INAPPLICABLE,
        [ENV_MISMATCH, DAY_MISMATCH],
        DAY_MISMATCH,
    ),
    (
        "four causes: the conflict wins",
        CONFLICT,
        [INTERNAL_CONFLICT, CLUSTER_UID_MISSING, ENV_MISMATCH, DAY_MISMATCH],
        INTERNAL_CONFLICT,
    ),
    ("SERVER_ONLY", INSUFFICIENT, [SERVER_ONLY], SERVER_ONLY),
]


@pytest.mark.parametrize(
    ("disposition", "reasons", "expected"),
    [row[1:] for row in PRIMARY_CAUSE_TABLE],
    ids=[row[0] for row in PRIMARY_CAUSE_TABLE],
)
def test_primary_cause_follows_the_frozen_rule(disposition, reasons, expected):
    assert primary_cause(_refusal(disposition, *reasons)) == expected


def test_the_primary_cause_is_always_one_of_the_refusals_own_reasons():
    for _, disposition, reasons, _ in PRIMARY_CAUSE_TABLE:
        assert primary_cause(_refusal(disposition, *reasons)) in reasons


def test_the_membership_digest_matches_an_independent_sha256sum_and_ignores_input_order():
    # printf 'evidence:otel:a\nevidence:otel:b' | sha256sum   (printf turns \n into a real newline)
    expected = "54ce1c50f4a55fe1e98ed06914c28ad29a63a69cd82e62823a0841b7cfca36c0"

    assert ids.legacy_bucket_digest(["evidence:otel:a", "evidence:otel:b"]) == expected
    assert ids.legacy_bucket_digest(["evidence:otel:b", "evidence:otel:a"]) == expected
    assert ids.legacy_bucket_digest(iter(["evidence:otel:b", "evidence:otel:a"])) == expected


def test_the_digest_of_no_buckets_is_the_hash_of_the_empty_string():
    assert (
        ids.legacy_bucket_digest([])
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_a_counter_id_is_deterministic_and_distinguishes_every_key_part():
    base = ("stream", "production", "2026-09-28", "SCOPED_V2_REFUSED", POD_UID_MISSING)
    variants = [
        ("other", *base[1:]),
        (base[0], "staging", *base[2:]),
        (*base[:2], "2026-09-29", *base[3:]),
        (*base[:3], "SCOPED_V2_WRITTEN", base[4]),
        (*base[:4], CLUSTER_UID_MISSING),
        (*base[:4], None),
    ]
    assert counter_id(*base) == counter_id(*base)
    assert len({counter_id(*base), *(counter_id(*v) for v in variants)}) == 1 + len(variants)
    assert counter_id(*base).startswith("scoped-evidence-counter:")
    assert counter_id(base[0], None, *base[2:]) != counter_id(base[0], "", *base[2:])


# --- legacy classification ---------------------------------------------------------------------

_IDS = ["evidence:otel:a", "evidence:otel:b", "evidence:otel:c"]


def _ledger(**overrides):
    ledger = {
        "stream_id": "stream",
        "enabled_at_revision": 7,
        "count": 3,
        "digest": ids.legacy_bucket_digest(_IDS),
    }
    ledger.update(overrides)
    return ledger


def test_a_matching_membership_is_known_and_counts_legacy_and_mixed():
    membership = [(_IDS[0], None), (_IDS[1], 9), (_IDS[2], None)]

    legacy = _classify_legacy(_ledger(), membership, "stream")  # pyright: ignore[reportArgumentType]

    assert (legacy.known, legacy.unknown_reason) == (True, None)
    assert (legacy.legacy_unscoped_buckets, legacy.mixed_buckets) == (2, 1)
    assert legacy.enabled_at_revision == 7


@pytest.mark.parametrize(
    ("ledger", "membership", "stream", "reason"),
    [
        (None, [(i, None) for i in _IDS], "stream", "NO_LEDGER"),
        (_ledger(), [(i, None) for i in _IDS], "another-stream", "STREAM_ID_MISMATCH"),
        (_ledger(count=4), [(i, None) for i in _IDS], "stream", "MEMBERSHIP_MISMATCH"),
        (_ledger(), [(i, None) for i in _IDS[:2]], "stream", "MEMBERSHIP_MISMATCH"),
        (_ledger(digest="0" * 64), [(i, None) for i in _IDS], "stream", "MEMBERSHIP_MISMATCH"),
        (
            _ledger(),
            [(i, None) for i in [*_IDS[:2], "evidence:otel:z"]],
            "stream",
            "MEMBERSHIP_MISMATCH",
        ),
    ],
    ids=["no ledger", "other stream", "extra count", "missing node", "bad digest", "swapped node"],
)
def test_anything_unprovable_is_unknown_never_legacy_by_absence(ledger, membership, stream, reason):
    legacy = _classify_legacy(ledger, membership, stream)  # pyright: ignore[reportArgumentType]

    assert legacy.known is False
    assert legacy.unknown_reason == reason
    assert legacy.legacy_unscoped_buckets is None and legacy.mixed_buckets is None


def test_an_empty_membership_with_an_empty_ledger_is_known_with_nothing_legacy():
    ledger = _ledger(count=0, digest=ids.legacy_bucket_digest([]))

    legacy = _classify_legacy(ledger, [], "stream")  # pyright: ignore[reportArgumentType]

    assert legacy.known is True
    assert (legacy.legacy_unscoped_buckets, legacy.mixed_buckets) == (0, 0)


# --- sampled logging ---------------------------------------------------------------------------


def _messages(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "app.telemetry.scoped_ledger"]


def test_at_most_twenty_samples_per_primary_cause_and_one_overflow_line(caplog):
    refusals = [_refusal(INSUFFICIENT, POD_UID_MISSING, trace=f"{i:032x}") for i in range(25)]

    with caplog.at_level(logging.INFO, logger="app.telemetry.scoped_ledger"):
        log_refusal_samples("stream", refusals)

    lines = _messages(caplog)
    samples = [m for m in lines if "suppressed" not in m]
    assert len(samples) == SAMPLES_PER_REASON == 20
    assert [m for m in lines if "suppressed" in m] == [
        f"scoped-evidence refusal samples suppressed stream=stream primary_reason={POD_UID_MISSING} suppressed=5"
    ]


def test_samples_are_bounded_per_cause_not_globally(caplog):
    refusals = [_refusal(INSUFFICIENT, POD_UID_MISSING, trace=f"{i:032x}") for i in range(22)] + [
        _refusal(INAPPLICABLE, ENV_MISMATCH, trace=f"{i + 100:032x}") for i in range(3)
    ]

    with caplog.at_level(logging.INFO, logger="app.telemetry.scoped_ledger"):
        log_refusal_samples("stream", refusals)

    lines = _messages(caplog)
    assert sum(ENV_MISMATCH in m for m in lines) == 3
    assert sum("suppressed=2" in m and POD_UID_MISSING in m for m in lines) == 1


def test_a_log_line_carries_only_codes_and_identifiers(caplog):
    refusal = ScopedIngressRefusal(
        trace_id="c" * 32,
        environment="secret-environment",
        bucket_utc_day="2026-09-28",
        disposition=INSUFFICIENT,
        reasons=(POD_UID_MISSING,),
    )

    with caplog.at_level(logging.INFO, logger="app.telemetry.scoped_ledger"):
        log_refusal_samples("stream", [refusal])

    [line] = _messages(caplog)
    assert line == (
        f"scoped-evidence refusal stream=stream primary_reason={POD_UID_MISSING} "
        f"trace_id={'c' * 32} reasons={POD_UID_MISSING}"
    )
    assert "secret-environment" not in line


def test_no_refusals_log_nothing(caplog):
    with caplog.at_level(logging.INFO, logger="app.telemetry.scoped_ledger"):
        log_refusal_samples("stream", [])

    assert _messages(caplog) == []
