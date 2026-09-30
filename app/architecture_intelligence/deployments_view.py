"""v0.5.0 I3 spec §15: the REST-only projection `GET /api/services/{service_id}/deployments` returns.

Derived purely from one already-computed `get_service_dependencies` answer (spec §15: "MUST NOT
invoke deployment reconciliation, Neo4j queries, or qualification logic independently"). Kept out of
the route so the route only maps an outcome to a status code.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.architecture_intelligence.contracts import (
    ArchitectureAnswer,
    ArchitectureSchemaVersion,
    DeploymentClaim,
    DeploymentResolution,
    EntityRef,
    Limitation,
    ObservationContextRef,
    ServiceDependenciesData,
    SnapshotRef,
)


class ServiceDeploymentsView(BaseModel):
    """v0.5.0 I3 spec §15: the REST-only projection `GET /{service_id}/deployments` returns - not a
    public MCP contract type (there is no matching MCP tool for this view), so it lives here rather
    than in `contracts.py`. Every field is extracted from one already-computed
    `get_service_dependencies` answer (spec §15: "MUST NOT invoke deployment reconciliation, Neo4j
    queries, or qualification logic independently") - this model has no validators of its own beyond
    shape, since the answer it projects is already fully validated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: ArchitectureSchemaVersion
    snapshot: SnapshotRef | None
    observation_context: ObservationContextRef | None
    # PR #222 review finding (round 2): null, like `snapshot`/`observation_context`, for a
    # NOT_ANSWERED refusal - the underlying `ServiceDependenciesData.service` field itself doesn't
    # exist when `data is None`, so fabricating an `EntityRef` here (even from the request's own
    # `service_id`) would invent Architecture Knowledge the service answer never confirmed,
    # contradicting spec §15's "preserve the service answer semantics."
    service: EntityRef | None
    deployment_claims: list[DeploymentClaim]
    deployment_resolutions: list[DeploymentResolution]
    evidence_refs: list[str]
    limitations: list[Limitation]


def project_service_deployments(
    answer: ArchitectureAnswer[ServiceDependenciesData],
) -> ServiceDeploymentsView:
    """The deployments view of `answer`. An `UNKNOWN_ENTITY` refusal is the caller's 404; every
    other outcome, including any other NOT_ANSWERED refusal, is a normal view."""
    # PR #222 review finding: `data` is null for every NOT_ANSWERED outcome (ArchitectureAnswer's
    # own envelope invariant), not just UNKNOWN_ENTITY - a known service_id can also refuse with
    # e.g. SNAPSHOT_NOT_AVAILABLE. That must stay a 200 body with `limitations[]`, matching this
    # file's own "everything but UNKNOWN_ENTITY stays 200" rule, never a 500.
    if answer.data is None:
        return ServiceDeploymentsView(
            schema_version=answer.schema_version,
            snapshot=answer.snapshot,
            observation_context=answer.observation_context,
            service=None,
            deployment_claims=[],
            deployment_resolutions=[],
            evidence_refs=[],
            limitations=answer.limitations,
        )

    deployment_claims = [claim for claim in answer.claims if isinstance(claim, DeploymentClaim)]
    deployment_resolutions = answer.data.deployment_resolutions
    evidence_refs = sorted(
        {
            *(ref for claim in deployment_claims for ref in claim.evidence_refs),
            *(
                ref
                for resolution in deployment_resolutions
                for ref in (
                    *resolution.supporting_evidence_refs,
                    *resolution.conflicting_evidence_refs,
                )
            ),
        }
    )

    return ServiceDeploymentsView(
        schema_version=answer.schema_version,
        snapshot=answer.snapshot,
        observation_context=answer.observation_context,
        service=answer.data.service,
        deployment_claims=deployment_claims,
        deployment_resolutions=deployment_resolutions,
        evidence_refs=evidence_refs,
        limitations=answer.limitations,
    )
