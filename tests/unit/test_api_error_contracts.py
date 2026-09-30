"""Characterization of the REST error surface: the exact status codes and bodies the
architecture-intelligence and evidence routes, and the app-level semantic-query handler, return.
These are spec-frozen (§14.5, §15, §16.3, §5.10), so any refactoring of how the routes build
requests or translate errors must leave every assertion here unchanged."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.semantic_query_validator import SemanticValidationError
from app.api import architecture_intelligence, errors, evidence
from app.architecture_intelligence.repository import SnapshotUnstable
from app.deps import get_architecture_intelligence_service

_SNAPSHOT = "aip:snapshot:v1:" + "a" * 64
_OTHER_SNAPSHOT = "aip:snapshot:v1:" + "b" * 64


class _FakeService:
    """Only the evidence convenience methods are reachable in these tests; a 422 is decided before
    any service call, so the dependency/drift/deployment paths must never touch the service."""

    def __init__(self, *, current=_SNAPSHOT, row=None, unstable=False):
        self.current, self.row, self.unstable = current, row, unstable

    def list_public_evidence(self):
        if self.unstable:
            raise SnapshotUnstable("no stable snapshot")
        return self.current, [{"id": "e1"}]

    def get_public_evidence(self, evidence_id):
        if self.unstable:
            raise SnapshotUnstable("no stable snapshot")
        return self.current, self.row

    def get_service_dependencies(self, request):  # pragma: no cover - must not be reached
        raise AssertionError("the service must not be called for an invalid request")

    get_architecture_drift = get_service_dependencies


def _client(service) -> TestClient:
    app = FastAPI()
    app.include_router(architecture_intelligence.router)
    app.include_router(evidence.router)
    errors.register_exception_handlers(app)
    app.dependency_overrides[get_architecture_intelligence_service] = lambda: service
    return TestClient(app)


_WINDOW = {
    "environment": "production",
    "from": "2026-09-01T00:00:00Z",
    "to": "2026-09-02T00:00:00Z",
}
_REVERSED = {
    "environment": "production",
    "from": "2026-09-02T00:00:00Z",
    "to": "2026-09-01T00:00:00Z",
}


@pytest.mark.parametrize("path", ["dependencies", "drift"])
def test_a_malformed_snapshot_id_is_a_422_with_a_string_detail(path):
    response = _client(_FakeService()).get(
        f"/api/services/service:a/{path}", params={**_WINDOW, "snapshot_id": "not-a-snapshot"}
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("path", ["dependencies", "drift", "deployments"])
def test_a_reversed_observation_window_is_a_422_with_a_string_detail(path):
    response = _client(_FakeService()).get(f"/api/services/service:a/{path}", params=_REVERSED)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_deployments_requires_environment_and_window():
    response = _client(_FakeService()).get("/api/services/service:a/deployments")
    assert response.status_code == 422  # FastAPI's own required-Query validation


def test_evidence_list_unstable_snapshot_is_the_frozen_503_body():
    response = _client(_FakeService(unstable=True)).get(
        "/api/evidence", params={"snapshot_id": _SNAPSHOT}
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "SNAPSHOT_NOT_AVAILABLE",
            "message": "no consistent current snapshot could be acquired",
        }
    }


def test_evidence_lookup_unstable_snapshot_is_the_frozen_503_body():
    response = _client(_FakeService(unstable=True)).get(
        "/api/evidence/e1", params={"snapshot_id": _SNAPSHOT}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SNAPSHOT_NOT_AVAILABLE"


@pytest.mark.parametrize("path", ["/api/evidence", "/api/evidence/e1"])
def test_evidence_stale_snapshot_is_the_frozen_409_body(path):
    response = _client(_FakeService(current=_SNAPSHOT, row={"id": "e1"})).get(
        path, params={"snapshot_id": _OTHER_SNAPSHOT}
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "SNAPSHOT_NOT_AVAILABLE",
            "message": (
                f"requested snapshot {_OTHER_SNAPSHOT} is not the current stable snapshot "
                f"{_SNAPSHOT}"
            ),
        }
    }


def test_evidence_lookup_of_a_missing_row_is_a_404_and_a_hit_is_a_200():
    missing = _client(_FakeService(row=None)).get(
        "/api/evidence/e9", params={"snapshot_id": _SNAPSHOT}
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "evidence not found: e9"}
    hit = _client(_FakeService(row={"id": "e1"})).get(
        "/api/evidence/e1", params={"snapshot_id": _SNAPSHOT}
    )
    assert (hit.status_code, hit.json()) == (200, {"id": "e1"})


def test_evidence_list_at_the_current_snapshot_is_a_200_and_never_a_404():
    response = _client(_FakeService()).get("/api/evidence", params={"snapshot_id": _SNAPSHOT})
    assert (response.status_code, response.json()) == (200, [{"id": "e1"}])


def test_evidence_snapshot_id_must_match_the_pattern():
    response = _client(_FakeService()).get("/api/evidence", params={"snapshot_id": "nope"})
    assert response.status_code == 422


def test_semantic_validation_error_is_the_frozen_422_body():
    app = FastAPI()
    errors.register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise SemanticValidationError(
            "wrong direction",
            relation="SENDS",
            expected_source=frozenset({"Service"}),
            expected_target=frozenset({"Queue"}),
        )

    response = TestClient(app).get("/boom")
    assert response.status_code == 422
    assert response.json() == {
        "code": "SEMANTIC_QUERY_INVALID",
        "message": "wrong direction",
        "relation": "SENDS",
        "expectedSource": ["Service"],
        "expectedTarget": ["Queue"],
    }
