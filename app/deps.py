from collections.abc import Iterator

import neo4j
from fastapi import Depends, HTTPException, Request

from app.ai.provider import LLMProvider
from app.ai.question_service import ArchitectureQuestionService
from app.architecture_intelligence.service import ArchitectureIntelligenceService
from app.graph.repository import open_session
from app.settings import Settings
from app.telemetry.correlation_buffer import HttpCorrelationBuffer


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_driver(request: Request) -> neo4j.Driver:
    return request.app.state.driver


def get_architecture_intelligence_service(request: Request) -> ArchitectureIntelligenceService:
    """v0.5.0 I3 slice 5a - the same `ArchitectureIntelligenceService` singleton
    `app.mcp.wiring.configure()` gives the MCP tools, set on `app.state` once during
    `app.main.lifespan`'s startup. REST routes depend on this rather than importing
    `app.mcp.wiring.get_service` directly: every other REST dependency in this module is already an
    `app.state`-backed `Depends` wrapper, and importing another public adapter's own wiring module
    would make REST and MCP share hidden module-global state instead of the request-scoped `app.state`
    every other dependency here already uses - it also means REST/service equivalence is definitional
    (same instance, same producer), not something that could silently drift."""
    return request.app.state.architecture_intelligence_service


def get_read_session(request: Request) -> Iterator[neo4j.Session]:
    settings = get_settings(request)
    driver = get_driver(request)
    with open_session(driver, database=settings.config.graph.database, read_only=True) as session:
        yield session


def get_http_correlation_buffer(request: Request) -> HttpCorrelationBuffer | None:
    """None when http-correlation is disabled via config (or in tests that never set it up) - the
    same optional-object pattern as get_llm_provider's own app.state lookup."""
    return getattr(request.app.state, "http_correlation_buffer", None)


def get_llm_provider(request: Request) -> LLMProvider:
    provider = getattr(request.app.state, "llm_provider", None)
    if provider is None:
        raise HTTPException(status_code=503, detail="LLM query subsystem is not configured")
    return provider


def _question_service(
    settings: Settings, driver: neo4j.Driver, provider: LLMProvider
) -> ArchitectureQuestionService:
    return ArchitectureQuestionService(
        driver=driver,
        database=settings.config.graph.database,
        provider=provider,
        max_depth=settings.config.graph.max_traversal_depth,
        max_result_rows=settings.config.llm.max_result_rows,
    )


def build_question_service(request: Request) -> ArchitectureQuestionService | None:
    """Returns None (rather than raising) when the LLM subsystem isn't configured - for callers like the UI page that want to render a friendly message instead of a 503."""
    provider = getattr(request.app.state, "llm_provider", None)
    if provider is None:
        return None
    return _question_service(get_settings(request), get_driver(request), provider)


def get_question_service(
    settings: Settings = Depends(get_settings),
    driver: neo4j.Driver = Depends(get_driver),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ArchitectureQuestionService:
    return _question_service(settings, driver, provider)
