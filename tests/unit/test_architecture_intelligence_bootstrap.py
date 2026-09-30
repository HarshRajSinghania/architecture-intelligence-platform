"""v0.4.0 I2.2 review fix - `app.architecture_intelligence.bootstrap._resolve_build_revision` must
never crash application startup, in particular in this repo's production container (`Dockerfile`'s `python:3.13-slim` base
has no `git` binary and no `.git` directory copied in). The first version of this module ran
`git rev-parse HEAD` with `check=True` unconditionally, which would have crashed every real
deployment before serving any endpoint - this is the regression test for that fix.

The `build_production_service` tests below (v0.5.0 I3 slice 5b) cover the opposite direction for
its own new configured mapping-artifact loading: spec §19 requires a diagnostics-producing artifact
to fail startup loudly, not silently become an unresolved identity.
"""

from __future__ import annotations

import subprocess
from unittest.mock import Mock

import pytest

from app.architecture_intelligence import bootstrap

_VALID_SHA = "a" * 40


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(bootstrap._BUILD_REVISION_ENV_VAR, raising=False)


def test_explicit_env_var_is_used_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(bootstrap._BUILD_REVISION_ENV_VAR, _VALID_SHA)
    assert bootstrap._resolve_build_revision() == _VALID_SHA


def test_malformed_explicit_env_var_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(bootstrap._BUILD_REVISION_ENV_VAR, "not-a-sha")
    with pytest.raises(RuntimeError, match="AIP_BUILD_REVISION"):
        bootstrap._resolve_build_revision()


def test_falls_back_to_git_head_when_env_var_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "_current_git_sha", lambda: _VALID_SHA)
    assert bootstrap._resolve_build_revision() == _VALID_SHA


def test_missing_git_binary_falls_back_to_placeholder_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates this repo's actual production container: no AIP_BUILD_REVISION, no git binary."""

    def _raise_missing_git() -> str:
        raise FileNotFoundError("git")

    monkeypatch.setattr(bootstrap, "_current_git_sha", _raise_missing_git)
    assert bootstrap._resolve_build_revision() == bootstrap._UNKNOWN_BUILD_REVISION


def test_no_git_directory_falls_back_to_placeholder_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates a git binary present but no .git directory (e.g. a stripped-down image copy)."""

    def _raise_not_a_repo() -> str:
        raise subprocess.CalledProcessError(128, ["git", "rev-parse", "HEAD"])

    monkeypatch.setattr(bootstrap, "_current_git_sha", _raise_not_a_repo)
    assert bootstrap._resolve_build_revision() == bootstrap._UNKNOWN_BUILD_REVISION


# --- build_production_service: configured mapping-artifact startup wiring (v0.5.0 I3 slice 5b) ---


def test_build_production_service_with_no_mapping_configured_leaves_document_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(bootstrap._BUILD_REVISION_ENV_VAR, _VALID_SHA)
    service = bootstrap.build_production_service(Mock(), database="neo4j")
    assert service._service_workload_mapping_document is None
    assert service._configured_kubernetes_sources == ()
    assert service._service_aliases == {}


def test_build_production_service_threads_configured_sources_and_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(bootstrap._BUILD_REVISION_ENV_VAR, _VALID_SHA)
    service = bootstrap.build_production_service(
        Mock(),
        database="neo4j",
        configured_kubernetes_sources=[("checkout-cluster", "cluster-uid-1")],
        service_aliases={"order-svc": "service:order-service"},
    )
    assert service._configured_kubernetes_sources == (("checkout-cluster", "cluster-uid-1"),)
    assert service._service_aliases == {"order-svc": "service:order-service"}


def test_build_production_service_fails_startup_on_a_malformed_mapping_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """spec §19: "a diagnostics-producing [mapping] file SHALL fail startup/load rather than
    silently become an unresolved identity" - not a soft warning, and never a silently-empty
    document."""
    monkeypatch.setenv(bootstrap._BUILD_REVISION_ENV_VAR, _VALID_SHA)
    malformed = tmp_path / "service-workload-mapping.yaml"
    malformed.write_text("not: [valid, - yaml: structure\n")
    with pytest.raises(RuntimeError, match="service-workload mapping artifact failed to load"):
        bootstrap.build_production_service(
            Mock(), database="neo4j", service_workload_mapping_path=malformed
        )


def test_mcp_wiring_reexports_the_bootstrap_builders_for_existing_importers():
    # `examples/runtime-demo/check_fixture_state.py` is pinned by the release golden path's
    # SHA256SUMS and still imports the builder from `app.mcp.wiring`, so that path must keep working.
    from app.mcp import wiring

    assert wiring.build_production_service is bootstrap.build_production_service
    assert wiring.production_service_kwargs is bootstrap.production_service_kwargs
