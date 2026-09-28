"""AIP v0.4.1 I1.1 - the single semantic owner for declared-vs-observed qualification
(docs/specifications/0.4.1/i1-qualification-consistency.md, spec sections cited inline below).

This module is deliberately dependency-free: it imports nothing from `neo4j`, FastAPI, MCP,
`app.architecture_intelligence.*`, or `app.analysis.runtime` (spec §8). `app.analysis.runtime`
imports *this* module in I1.2, so the reverse import would be circular - which is also why this
module never accepts a `ServiceTelemetryCoverage` object (owned by `app.analysis.runtime`), only
flat booleans.

Both the Cypher/analysis path (`app.analysis.runtime`) and the Architecture Intelligence/MCP path
(`app.architecture_intelligence.dependency_projection`) consume this module after I1.2 (ADR 0010).
The objective is one semantic rule, not layer convergence: each path keeps its own request shape
and destination-resolution/claim-construction responsibilities (spec §14/§16); only DECLARED/
OBSERVED evidence matching, environment/window matching, coverage classification, and the
qualification table live here.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, LiteralString

CONFIRMED = "CONFIRMED"
OBSERVED_ONLY = "OBSERVED_ONLY"
NOT_OBSERVED_IN_WINDOW = "NOT_OBSERVED_IN_WINDOW"

COVERAGE_SUFFICIENT = "SUFFICIENT"
COVERAGE_PARTIAL = "PARTIAL"
COVERAGE_NONE = "NONE"
COVERAGE_UNKNOWN = "UNKNOWN"

_DECLARED = "DECLARED"
_OBSERVED = "OBSERVED"

# v0.5.0 I4 slice 4 (spec §12.5): a declared `PUBLISHES_TO` route is NOT_OBSERVED_IN_WINDOW "only
# under the existing messaging-coverage rule" - it is a messaging relation, not a new relation kind.
_MESSAGING_RELATION_TYPES = frozenset({"SENDS", "RECEIVES_FROM", "PUBLISHES_TO"})


def matches_declared_evidence(
    evidence_ids: Collection[str],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Spec §10.1. Environment and window never apply to DECLARED evidence. A dangling id (present
    in `evidence_ids` but absent from `evidence_by_id`) counts as neither declared nor observed.
    Deduplicated (spec §10.4) - a repeated id never produces a repeated semantic reference."""
    return sorted(
        {
            eid
            for eid in evidence_ids
            if eid in evidence_by_id and evidence_by_id[eid].get("evidence_type") == _DECLARED
        }
    )


def matches_observed_evidence(
    evidence_ids: Collection[str],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    *,
    environment: str,
    window_start: datetime,
    window_end: datetime | None,
) -> list[str]:
    """Spec §10.2/§10.3. Both window bounds are inclusive; `window_end=None` means an open-ended
    upper bound (path A's REST `until` may be omitted - spec §21). Environment matching is exact
    equality only - no case-folding, aliasing, or wildcards (spec §10.3). An OBSERVED row whose
    `last_seen` is null never matches (spec §25.2), distinctly from a dangling evidence id.
    Deduplicated (spec §10.4), same as `matches_declared_evidence`."""
    matches: set[str] = set()
    for eid in evidence_ids:
        row = evidence_by_id.get(eid)
        if row is None or row.get("evidence_type") != _OBSERVED:
            continue
        if row.get("environment") != environment:
            continue
        last_seen = row.get("last_seen")
        if last_seen is None or last_seen < window_start:
            continue
        if window_end is not None and last_seen > window_end:
            continue
        matches.add(eid)
    return sorted(matches)


def relevant_coverage_signal(
    relation_type: str, *, http_observed: bool, messaging_observed: bool
) -> bool:
    """Spec §12.1's relation-kind -> telemetry mapping: CALLS -> http_observed;
    SENDS/RECEIVES_FROM/PUBLISHES_TO -> messaging_observed. Exhaustive - an unrecognized relation_type raises
    rather than silently falling through to "messaging", since I1 introduces no new relation
    families (spec §31) and a caller passing anything else is a programming error, not a valid
    input to classify."""
    if relation_type == "CALLS":
        return http_observed
    if relation_type in _MESSAGING_RELATION_TYPES:
        return messaging_observed
    raise ValueError(f"unsupported relation_type for coverage classification: {relation_type!r}")


def classify_coverage(
    relation_type: str,
    *,
    http_observed: bool,
    messaging_observed: bool,
    spans_observed: bool,
    coverage_row_exists: bool,
    qualification_enabled: bool,
) -> str:
    """Spec §12.2/§25.3. UNKNOWN when qualification is disabled or no coverage row exists for the
    subject at all ("cannot assess coverage", not NONE - spec §25.3). Otherwise: SUFFICIENT if the
    service has observed telemetry of the *same* relation kind; PARTIAL if it emits some telemetry
    but not of this kind; NONE if it emitted no usable telemetry at all in this window/environment.

    `coverage_row_exists=False` is currently unreachable from either production caller as of I1
    (both `app.analysis.runtime.telemetry_coverage` and
    `app.architecture_intelligence.repository.read_service_dependency_rows` always synthesize
    exactly one coverage row per requested service_id) - it is supported and tested here regardless,
    per spec §25.3's normative requirement, not because either caller can trigger it today."""
    if not qualification_enabled or not coverage_row_exists:
        return COVERAGE_UNKNOWN
    if relevant_coverage_signal(
        relation_type, http_observed=http_observed, messaging_observed=messaging_observed
    ):
        return COVERAGE_SUFFICIENT
    if spans_observed:
        return COVERAGE_PARTIAL
    return COVERAGE_NONE


@dataclass(frozen=True)
class QualifiedRelation:
    """The result of qualifying one relation's evidence against one observation context (spec
    §11). `coverage` is populated only for NOT_OBSERVED_IN_WINDOW; CONFIRMED/OBSERVED_ONLY always
    carry `coverage=None` (coverage is meaningful only for a not-observed finding)."""

    qualification: str
    coverage: str | None
    evidence_refs: list[str]


def qualify_relation(
    evidence_ids: Collection[str],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    *,
    environment: str,
    window_start: datetime,
    window_end: datetime | None,
    relation_type: str,
    http_observed: bool,
    messaging_observed: bool,
    spans_observed: bool,
    coverage_row_exists: bool,
    qualification_enabled: bool,
) -> QualifiedRelation | None:
    """Spec §11's qualification table. Returns `None` for the table's fourth row - "no supported
    qualified relation/claim" - when the relation has neither valid declared nor valid observed
    evidence; the caller MUST NOT promote such a relation into a claim merely because the
    underlying graph relation exists (spec §11 closing paragraph).

    `evidence_ids` is consumed twice (once for declared matching, once for observed matching) -
    callers MUST pass a reusable `Collection`, not a one-shot iterator/generator."""
    declared = matches_declared_evidence(evidence_ids, evidence_by_id)
    observed = matches_observed_evidence(
        evidence_ids,
        evidence_by_id,
        environment=environment,
        window_start=window_start,
        window_end=window_end,
    )
    if declared and observed:
        return QualifiedRelation(CONFIRMED, None, sorted(set(declared) | set(observed)))
    if observed:
        return QualifiedRelation(OBSERVED_ONLY, None, observed)
    if declared:
        coverage = classify_coverage(
            relation_type,
            http_observed=http_observed,
            messaging_observed=messaging_observed,
            spans_observed=spans_observed,
            coverage_row_exists=coverage_row_exists,
            qualification_enabled=qualification_enabled,
        )
        return QualifiedRelation(NOT_OBSERVED_IN_WINDOW, coverage, declared)
    return None


def observed_evidence_condition(
    evidence_var: LiteralString = "e", *, environment_optional: bool = False
) -> LiteralString:
    """Spec §13's positive OBSERVED predicate, as a WHERE-clause condition (not wrapped in
    EXISTS{}) - used both by `observed_evidence_exists` below and directly by O1's inline filter,
    which is the one caller that needs `environment_optional=True` (O1 is a raw,
    all-filters-optional listing; every other consumer always supplies a concrete environment)."""
    environment_clause = (
        f"($environment IS NULL OR {evidence_var}.environment = $environment)"
        if environment_optional
        else f"{evidence_var}.environment = $environment"
    )
    return (
        f"{evidence_var}.evidence_type = 'OBSERVED' AND {environment_clause} "
        f"AND {evidence_var}.last_seen >= $since "
        f"AND ($until IS NULL OR {evidence_var}.last_seen <= $until)"
    )


def declared_evidence_condition(evidence_var: LiteralString = "e") -> LiteralString:
    """Spec §13's positive DECLARED predicate. No environment/window clause - matches §10.1."""
    return f"{evidence_var}.evidence_type = 'DECLARED'"


def observed_evidence_exists(
    eid_var: LiteralString = "eid", evidence_var: LiteralString = "e"
) -> LiteralString:
    """Spec §13. Always exact-environment-equality - O1's environment-optional inline clause is
    built directly from `observed_evidence_condition(environment_optional=True)` instead, since it
    isn't wrapped in EXISTS{}."""
    return (
        f"EXISTS {{ UNWIND r.evidence_ids AS {eid_var} "
        f"MATCH ({evidence_var}:Evidence {{id: {eid_var}}}) "
        f"WHERE {observed_evidence_condition(evidence_var)} }}"
    )


def declared_evidence_exists(
    eid_var: LiteralString = "eid2", evidence_var: LiteralString = "e2"
) -> LiteralString:
    """Spec §13. Default variable names (`eid2`/`e2`) match today's code, distinct from
    `observed_evidence_exists`'s (`eid`/`e`) so both guards can appear in one WHERE clause without
    Cypher variable collision (`_status_query` in `app.analysis.runtime` composes exactly this)."""
    return (
        f"EXISTS {{ UNWIND r.evidence_ids AS {eid_var} "
        f"MATCH ({evidence_var}:Evidence {{id: {eid_var}}}) "
        f"WHERE {declared_evidence_condition(evidence_var)} }}"
    )


def not_observed_evidence_exists(
    eid_var: LiteralString = "eid", evidence_var: LiteralString = "e"
) -> LiteralString:
    """Spec §13's own literal example: "NOT (<authoritative observed-exists expression>)" rather
    than an independently authored `NOT EXISTS {...}` copy. Produces `NOT (EXISTS {...})`, not
    today's literal `NOT EXISTS {...}` text - semantically equivalent Cypher, but the exact text
    differs; verified against real Neo4j in I1.2, not assumed here."""
    return f"NOT ({observed_evidence_exists(eid_var, evidence_var)})"


def not_declared_evidence_exists(
    eid_var: LiteralString = "eid2", evidence_var: LiteralString = "e2"
) -> LiteralString:
    """See `not_observed_evidence_exists` - same construction, same verification caveat."""
    return f"NOT ({declared_evidence_exists(eid_var, evidence_var)})"
