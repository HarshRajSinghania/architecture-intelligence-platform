"""v0.4.0 I2.2 - lazily gives the `get_service_dependencies` MCP tool body access to a real
`ArchitectureIntelligenceService` (spec `docs/specifications/0.4.0/
i2-mcp-vertical-slice-and-evidence-drill-down.md` §8, §10).

Tool registration (`app.mcp.tools.register_tools`) happens at import time, inside `app.mcp.server`'s
module-level `mcp_server` construction - before FastAPI's lifespan (`app.main.lifespan`) builds
`app.state.driver`. Tool *dispatch* only ever happens per-request, strictly after lifespan startup,
so this module gives the tool body a level of indirection it can resolve lazily: `configure()` runs
once during lifespan startup, `get_service()` runs on every `get_service_dependencies` call.

Named `wiring.py`, not `runtime.py`, to avoid colliding with this codebase's existing "runtime"
vocabulary (`app.settings.RuntimeAnalysisConfig`, `app.api.runtime`), which means *observed* runtime
telemetry - an unrelated domain concept from MCP process wiring.

This module holds only a reference to an already-built `ArchitectureIntelligenceService`: it opens
no session, runs no Cypher and imports no `app.graph.repository` (spec §8 forbids the *adapter* from
doing those things; every real read's session lifecycle stays inside the service).

The production construction of the service itself (`build_production_service`,
`production_service_kwargs`) lives in `app.architecture_intelligence.bootstrap`; those names are
re-exported here so existing importers keep working.
"""

from __future__ import annotations

from app.architecture_intelligence.bootstrap import (
    build_production_service,
    production_service_kwargs,
)
from app.architecture_intelligence.service import ArchitectureIntelligenceService

__all__ = [
    "build_production_service",
    "configure",
    "get_service",
    "production_service_kwargs",
]

_service: ArchitectureIntelligenceService | None = None


def configure(service: ArchitectureIntelligenceService) -> None:
    global _service
    _service = service


def get_service() -> ArchitectureIntelligenceService:
    if _service is None:
        raise RuntimeError(
            "MCP runtime is not configured - call app.mcp.wiring.configure() during application "
            "startup before any tool dispatches"
        )
    return _service
