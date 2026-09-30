import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, SecretStr

from app.sources.model import FilesystemSourceConfig, KubernetesSourceConfig


class _ConfigModel(BaseModel):
    """Base for config sections that accept both the YAML's kebab-case aliases and field names."""

    model_config = {"populate_by_name": True}


class SourcesConfig(BaseModel):
    directories: list[FilesystemSourceConfig] = Field(
        default_factory=lambda: [FilesystemSourceConfig(id="default", root=Path("./repositories"))]
    )
    # I2 Draft 0.2 slice 2b-i's second source kind - unlike `directories`, there is no sensible
    # bundled-example default for a Kubernetes cluster registration, so this defaults to empty.
    clusters: list[KubernetesSourceConfig] = Field(default_factory=list)
    # I1 spec §5.1.1/§8.1/§9/§9.1's explicit shared-identity/migration mapping mechanism (PR4) - a
    # list, not a single fixed path, since the mechanism is general (any configured source may
    # supply one); the bundled examples/ migration artifact is simply its first real instance.
    # Defaults to empty: "Explicit empty arrays represent absent mapping categories" (§5.3).
    migrations: list[Path] = Field(default_factory=list)
    # I2 Draft 0.2 §3 prerequisite slice's minimal operator-facing surface for submitting an
    # explicit whole-source/scope-transition tombstone (I1 spec §6) - see
    # app.sources.tombstones.load_tombstones. Defaults to empty: no tombstone is declared unless an
    # operator configures one.
    tombstones: list[Path] = Field(default_factory=list)
    # v0.5.0 I3 spec §8.1's configured Service<->Workload identity-mapping artifact (Path B) -
    # deliberately a single optional path, not a list: §8.1 states "Path B uses one local,
    # versioned mapping artifact" (PR #215 review finding - an earlier `list[Path]` shape let two
    # artifacts silently collide on the same group key, violating §13.1's exactly-once reduction).
    # `None` (the default): no configured mapping is declared unless an operator configures one.
    service_workload_mapping: Path | None = None


class GraphConfig(BaseModel):
    uri: str = "bolt://localhost:7687"
    database: str = "neo4j"
    max_traversal_depth: int = 5


class ImportConfig(BaseModel):
    openapi: bool = True
    asyncapi: bool = True
    architecture_manifest: bool = True


class LLMConfig(BaseModel):
    enabled: bool = True
    max_result_rows: int = 100


class IntentRouterConfig(BaseModel):
    deterministic_threshold: float = 0.90


class HttpCorrelationConfig(_ConfigModel):
    """11H R2/spec §6/§22 - the cross-batch HTTP CLIENT/SERVER correlation buffer's bounds. Must
    stay optional with safe defaults so an existing config.yaml with none of these keys still
    starts the app unchanged (spec §22)."""

    enabled: bool = True
    ttl_seconds: int = Field(default=60, gt=0, alias="ttl-seconds")
    max_pending_spans: int = Field(default=10000, gt=0, alias="max-pending-spans")


class CoverageConfig(_ConfigModel):
    """11H R7/spec §11/§22 - whether O4's NOT_OBSERVED_IN_WINDOW rows get qualified with a
    SUFFICIENT/PARTIAL/NONE/UNKNOWN coverage classification. Must stay optional with a safe
    default so an existing config.yaml with none of these keys still starts the app unchanged
    (spec §22); disabling it degrades every row's `coverage` to UNKNOWN rather than omitting the
    field, so API consumers never need to branch on its presence."""

    qualification_enabled: bool = Field(default=True, alias="qualification-enabled")


class ScopedEvidenceConfig(_ConfigModel):
    """v0.6.0 I2 decision record D1/D10 - whether accepted CALLS also produce an isolated
    caller-Pod-scoped v2 record. Off by default: with it off the graph, the snapshot and every v0.5
    answer are byte-identical to before, and an existing config.yaml with none of these keys starts
    unchanged. `stream-id` names this AIP instance's live `/v1/traces` stream in the operational
    transition report and cutover ledger."""

    enabled: bool = False
    stream_id: str = Field(default="otlp-http", min_length=1, alias="stream-id")


class TelemetryConfig(_ConfigModel):
    service_aliases: dict[str, str] = Field(default_factory=dict)
    queue_aliases: dict[str, str] = Field(default_factory=dict)
    # v0.5.0 I4 spec §9: configured runtime Topic aliases {destination name: canonical Topic id},
    # consulted only after no unique direct Topic match - never able to select a Queue, just as
    # queue_aliases can never select a Topic. No Subscription aliases are admitted.
    topic_aliases: dict[str, str] = Field(default_factory=dict)
    http_correlation: HttpCorrelationConfig = Field(
        default_factory=HttpCorrelationConfig, alias="http-correlation"
    )
    coverage: CoverageConfig = Field(default_factory=CoverageConfig)
    scoped_evidence: ScopedEvidenceConfig = Field(
        default_factory=ScopedEvidenceConfig, alias="scoped-evidence"
    )


class RuntimeAnalysisConfig(BaseModel):
    default_window_hours: int = 24
    default_environment: str = "production"


class MCPConfig(_ConfigModel):
    """v0.4.0 I2.1 - spec §15: MCP is local/trusted-network evaluation only, never production-safe
    public exposure. A request whose Origin header isn't in this list is rejected
    (`mcp.server.transport_security`) before it reaches any tool. Defaults cover local dev only -
    a trusted-network deployment MUST override this."""

    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:8000", "http://localhost:8000"],
        alias="allowed-origins",
    )
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1:8000", "localhost:8000"], alias="allowed-hosts"
    )


class AppConfig(_ConfigModel):
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    import_: ImportConfig = Field(default_factory=ImportConfig, alias="import")
    llm: LLMConfig = Field(default_factory=LLMConfig)
    intent_router: IntentRouterConfig = Field(default_factory=IntentRouterConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    runtime_analysis: RuntimeAnalysisConfig = Field(default_factory=RuntimeAnalysisConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)


class Secrets(BaseModel):
    neo4j_user: str
    neo4j_password: str
    # SecretStr so the key never shows up in a repr/log of Settings. NEO4J credentials stay plain
    # strings: SHA256SUMS-pinned demo scripts pass `neo4j_password` straight to the driver.
    openai_api_key: SecretStr | None = None


@dataclass(frozen=True)
class Settings:
    config: AppConfig
    secrets: Secrets


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"required environment variable {name} is not set")
    return value


CONFIG_PATH_ENV_VAR = "CONFIG_PATH"
DEFAULT_CONFIG_PATH = Path("config.yaml")


def config_path_from_env() -> Path:
    """The configured YAML path: `CONFIG_PATH` if set, else `config.yaml` in the working directory."""
    return Path(os.environ.get(CONFIG_PATH_ENV_VAR, DEFAULT_CONFIG_PATH))


def load_config(path: Path) -> AppConfig:
    """Loads the spec §17.1 YAML shape; NEO4J_URI env var overrides graph.uri (matches docker-compose.yml)."""
    raw = yaml.safe_load(path.read_text()) or {}
    config = AppConfig.model_validate(raw.get("architecture_intelligence", {}))
    uri_override = os.environ.get("NEO4J_URI")
    if uri_override:
        config = config.model_copy(
            update={"graph": config.graph.model_copy(update={"uri": uri_override})}
        )
    return config


def load_secrets() -> Secrets:
    """Reads NEO4J_USER/NEO4J_PASSWORD/OPENAI_API_KEY from the environment (spec §17.2) - never from the repo."""
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    return Secrets(
        neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
        neo4j_password=_require_env("NEO4J_PASSWORD"),
        openai_api_key=SecretStr(openai_api_key) if openai_api_key is not None else None,
    )


def load_settings(config_path: Path) -> Settings:
    return Settings(config=load_config(config_path), secrets=load_secrets())
