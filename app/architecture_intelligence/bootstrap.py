"""Production assembly of the `ArchitectureIntelligenceService` (moved from `app.mcp.wiring`).

The service is the single semantic owner behind both public adapters (REST and MCP; ADR 0016), and
the real-world validation capture tool and demo scripts build it too - none of that is MCP-specific,
so its construction lives with the service rather than in an adapter package. `app.mcp.wiring` keeps
only the lazy accessor MCP tool bodies resolve it through.

`build_production_service`'s `Producer.build_revision` resolution (`_resolve_build_revision`) was
corrected during review: the first version unconditionally ran `git rev-parse HEAD` at lifespan
startup. This repo's production `Dockerfile` is `python:3.13-slim` - no `git` binary, no `.git`
directory copied in - so every real container crashed on startup before serving any endpoint, MCP or
otherwise. `_resolve_build_revision` now prefers an explicit `AIP_BUILD_REVISION` env var (a real
deployment's build/CI step sets this to the exact SHA it built - see `.github/workflows/docker.yml`
and `Dockerfile`'s `ARG`/`ENV`), validated as a real 40-hex SHA if present (a malformed *explicit*
value is a deploy misconfiguration and fails loudly, same as
`evaluation.architecture_answers.candidate.resolve_candidate_sha`'s own `InvalidCandidateSha`).
Only when the env var is absent does it fall back to `git rev-parse HEAD` for local/dev ergonomics
(where `.git` and `git` are normally both present) - and that fallback itself never raises: a missing
git binary or `.git` directory (any container without the env var set) logs a warning and returns the
literal `"unknown"` rather than crashing startup. Real production build-provenance wiring (spec §10)
remains a named I4 concern; this only has to not crash and not silently fabricate a plausible-looking
fake SHA - `"unknown"` is honestly what it is.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

import neo4j

from app.architecture_intelligence.contracts import PRODUCER_NAME, Producer
from app.architecture_intelligence.service import ArchitectureIntelligenceService
from app.settings import AppConfig
from app.sources.service_workload_mapping import load_service_workload_mapping
from app.version import package_version

logger = logging.getLogger("architecture_intelligence.bootstrap")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BUILD_REVISION_ENV_VAR = "AIP_BUILD_REVISION"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_UNKNOWN_BUILD_REVISION = "unknown"


def _current_git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=_REPO_ROOT
    )
    return result.stdout.strip()


def _resolve_build_revision() -> str:
    explicit = os.environ.get(_BUILD_REVISION_ENV_VAR)
    if explicit:
        if not _SHA_PATTERN.match(explicit):
            raise RuntimeError(
                f"{_BUILD_REVISION_ENV_VAR} must be a 40-hex git SHA, got {explicit!r}"
            )
        return explicit
    try:
        return _current_git_sha()
    except (OSError, subprocess.CalledProcessError):
        # No AIP_BUILD_REVISION and no git available (e.g. this repo's production container, which
        # has neither the git binary nor a .git directory) - never crash startup over this.
        logger.warning(
            "%s is not set and `git rev-parse HEAD` is unavailable; falling back to a placeholder "
            "build_revision. Set %s in any real deployment.",
            _BUILD_REVISION_ENV_VAR,
            _BUILD_REVISION_ENV_VAR,
        )
        return _UNKNOWN_BUILD_REVISION


def production_service_kwargs(config: AppConfig) -> dict:
    """The one Settings -> `build_production_service` keyword derivation. The app's startup and the
    real-world validation capture tool both use it (v0.5.0 I5 Slice 1), so a qualification capture
    builds its `ArchitectureIntelligenceService` from exactly the same configuration as the running
    app."""
    return {
        "database": config.graph.database,
        "service_workload_mapping_path": config.sources.service_workload_mapping,
        "configured_kubernetes_sources": [
            (cluster.id, cluster.cluster_uid) for cluster in config.sources.clusters
        ],
        "service_aliases": config.telemetry.service_aliases,
    }


def build_production_service(
    driver: neo4j.Driver,
    *,
    database: str,
    service_workload_mapping_path: Path | None = None,
    configured_kubernetes_sources: Sequence[tuple[str, str]] = (),
    service_aliases: dict[str, str] | None = None,
) -> ArchitectureIntelligenceService:
    producer = Producer(
        name=PRODUCER_NAME,
        version=package_version(),
        build_revision=_resolve_build_revision(),
    )
    # v0.5.0 I3 spec §19: "a diagnostics-producing [mapping] file SHALL fail startup/load rather
    # than silently become an unresolved identity" - unlike `load_migration_mappings`/
    # `load_tombstones`, which are read per-import-request and diagnosed into that request's own
    # response, this artifact is read once, held in memory, and consulted on every deployment
    # reconciliation - a malformed artifact silently producing `None` here would make every Path B
    # resolution silently behave as "no mapping configured" instead of failing loudly.
    document, diagnostics = load_service_workload_mapping(service_workload_mapping_path)
    if diagnostics:
        detail = "; ".join(f"{d.code.value}: {d.message}" for d in diagnostics)
        raise RuntimeError(f"service-workload mapping artifact failed to load: {detail}")
    return ArchitectureIntelligenceService(
        driver,
        database=database,
        producer=producer,
        service_workload_mapping_document=document,
        configured_kubernetes_sources=configured_kubernetes_sources,
        service_aliases=service_aliases,
    )
