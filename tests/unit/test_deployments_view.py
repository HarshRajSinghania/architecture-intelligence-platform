import json
from pathlib import Path

from app.architecture_intelligence.contracts import ArchitectureAnswer, ServiceDependenciesData
from app.architecture_intelligence.deployments_view import (
    ServiceDeploymentsView,
    project_service_deployments,
)

_I1 = Path(__file__).resolve().parents[1] / "fixtures" / "architecture_intelligence" / "i1"


def test_a_not_answered_refusal_projects_to_an_empty_view_that_keeps_its_limitations():
    payload = json.loads((_I1 / "not_answered_snapshot_not_available.json").read_text())
    answer = ArchitectureAnswer[ServiceDependenciesData].model_validate(payload)
    assert answer.data is None

    view = project_service_deployments(answer)

    assert isinstance(view, ServiceDeploymentsView)
    # `service` stays null: fabricating an EntityRef would invent knowledge the answer never
    # confirmed (PR #222 review finding).
    assert view.service is None
    assert view.deployment_claims == []
    assert view.deployment_resolutions == []
    assert view.evidence_refs == []
    assert view.limitations == answer.limitations
    assert view.snapshot == answer.snapshot
    assert view.observation_context == answer.observation_context
