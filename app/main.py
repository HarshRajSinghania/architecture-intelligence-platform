import logging
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from app.ai.provider import OpenAIProvider
from app.api import (
    analysis,
    architecture_intelligence,
    evidence,
    import_api,
    messages,
    query,
    queues,
    runtime,
    services,
    telemetry,
    ui,
)
from app.api.errors import register_exception_handlers
from app.architecture_intelligence.bootstrap import (
    build_production_service,
    production_service_kwargs,
)
from app.deps import get_driver, get_settings
from app.graph.repository import build_driver, open_session
from app.mcp import wiring as mcp_wiring
from app.mcp.app import build_mcp_app, mcp_session_manager_lifespan
from app.settings import Settings, config_path_from_env, load_config, load_secrets
from app.telemetry.correlation_buffer import HttpCorrelationBuffer
from app.version import package_version

CONFIG_PATH = config_path_from_env()
logger = logging.getLogger("architecture_intelligence.health")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The config `create_app` parsed once (also behind the MCP mount) - never re-read here, so the
    # whole app runs on one snapshot of config.yaml. Secrets are read now, at startup, so that
    # `create_app()` itself never requires NEO4J_PASSWORD.
    settings = Settings(config=app.state.config, secrets=load_secrets())
    app.state.settings = settings
    app.state.driver = build_driver(
        settings.config.graph.uri, settings.secrets.neo4j_user, settings.secrets.neo4j_password
    )
    # v0.4.0 I2.2 - the MCP tool bodies are registered at import time (app.mcp.server), before this
    # driver exists; app.mcp.wiring.get_service() is the lazy indirection they resolve it through on
    # every dispatch. See app.mcp.wiring's module docstring for why this can't be done eagerly.
    #
    # v0.5.0 I3 slice 5a: the same constructed service is also set on app.state so REST routes
    # (app.deps.get_architecture_intelligence_service) share the exact same instance, not a second
    # construction - see ADR 0016 decision #1/#2 (ArchitectureIntelligenceService is the single
    # semantic owner behind both public adapters).
    architecture_intelligence_service = build_production_service(
        app.state.driver, **production_service_kwargs(settings.config)
    )
    mcp_wiring.configure(architecture_intelligence_service)
    app.state.architecture_intelligence_service = architecture_intelligence_service
    openai_api_key = settings.secrets.openai_api_key
    if settings.config.llm.enabled and openai_api_key and openai_api_key.get_secret_value():
        app.state.llm_provider = OpenAIProvider(api_key=openai_api_key.get_secret_value())
    else:
        app.state.llm_provider = None
    http_correlation = settings.config.telemetry.http_correlation
    app.state.http_correlation_buffer = (
        HttpCorrelationBuffer(
            ttl_seconds=http_correlation.ttl_seconds,
            max_pending_spans=http_correlation.max_pending_spans,
        )
        if http_correlation.enabled
        else None
    )
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp_session_manager_lifespan())
        yield
    app.state.driver.close()


def create_app(config_path: Path | None = None) -> FastAPI:
    """Builds the FastAPI app from `config_path` (default: `CONFIG_PATH`, i.e. the `CONFIG_PATH` env
    var or `config.yaml`), parsing it exactly once. It never opens Neo4j or reads secrets - the driver
    and `NEO4J_PASSWORD`/`OPENAI_API_KEY` are only touched on lifespan startup."""
    config = load_config(config_path if config_path is not None else CONFIG_PATH)
    app = FastAPI(
        title="Architecture Intelligence PoC", version=package_version(), lifespan=lifespan
    )
    app.state.config = config

    app.include_router(services.router)
    app.include_router(queues.router)
    app.include_router(messages.router)
    app.include_router(analysis.router)
    app.include_router(import_api.router)
    app.include_router(query.router)
    app.include_router(evidence.router)
    app.include_router(architecture_intelligence.router)
    app.include_router(telemetry.router)
    app.include_router(runtime.runtime_router)
    app.include_router(runtime.runtime_analysis_router)
    app.include_router(ui.router)

    register_exception_handlers(app)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/health/neo4j")
    def health_neo4j(settings: Settings = Depends(get_settings), driver=Depends(get_driver)):
        try:
            with open_session(
                driver, database=settings.config.graph.database, read_only=True
            ) as session:
                session.run("RETURN 1").consume()
        except Exception:
            # CodeQL py/stack-trace-exposure: the exception (which for a Neo4j driver error can
            # include the bolt URI/hostname) is logged server-side only - an unauthenticated caller
            # of a health endpoint must never see internal connection detail in the response body.
            logger.exception("Neo4j health check failed")
            return JSONResponse(status_code=503, content={"status": "error"})
        return {"status": "ok"}

    # v0.4.0 I2.1 - mounted at "/" (not "/mcp") and registered last, so it only ever receives
    # requests no route above already claimed - in practice exactly `POST /mcp`, which is the
    # mounted sub-app's own route path (see app.mcp.app.build_mcp_app's docstring for why mounting
    # at an outer "/mcp" prefix instead 307-redirects a bare `POST /mcp`, confirmed live).
    # config.yaml's `mcp.allowed-origins`/`allowed-hosts` override, if any, comes from the config
    # parsed above; `load_config` never calls `load_secrets()`/requires NEO4J_PASSWORD, so
    # create_app() stays free of any hard secret dependency (spec §15: local/trusted-network only by
    # default; a deployment overrides via config.yaml, not by patching this function).
    mcp_config = config.mcp
    app.mount(
        "/",
        build_mcp_app(
            allowed_origins=mcp_config.allowed_origins, allowed_hosts=mcp_config.allowed_hosts
        ),
    )

    return app


app = create_app()
