# Configuration

All installation-dependent values are controllable via `config.yaml` or environment variables —
nothing installation-specific is hardcoded. `config.yaml` (repo root) follows the shape
`app/settings.py::load_config` reads under a single top-level `architecture_intelligence:` key.

## Secrets — environment only, never `config.yaml`

`app/settings.py::load_secrets` reads these from the environment and only the environment:

| Variable | Required | Default |
|---|---|---|
| `NEO4J_USER` | no | `neo4j` |
| `NEO4J_PASSWORD` | **yes** | — (raises `RuntimeError` if unset) |
| `OPENAI_API_KEY` | no | `None` — the LLM query layer is disabled without it, everything else works |
| `NEO4J_URI` | no | overrides `graph.uri` from `config.yaml` if set (matches `docker-compose.yml`) |

Copy `.env.example` to `.env` and fill these in for local development.

## `config.yaml` sections

| Section | Fields (defaults) |
|---|---|
| `sources` | `directories` (`["./repositories"]`) — where to scan for OpenAPI/AsyncAPI/manifest files |
| `graph` | `uri` (`bolt://localhost:7687`), `database` (`neo4j`), `max_traversal_depth` (`5`) |
| `import` | `openapi`, `asyncapi`, `architecture_manifest` — each `true`, toggles that adapter |
| `llm` | `enabled` (`true`), `max_result_rows` (`100`) — `enabled: false` (or a missing API key) fully disables the LLM query layer with no other effect |
| `intent_router` | `deterministic_threshold` (`0.90`) — confidence threshold above which a question is routed to a deterministic analysis instead of the LLM |
| `telemetry.service_aliases` / `queue_aliases` | `{}` — map an observed name to its declared canonical name when they differ |
| `telemetry.http-correlation` | `enabled` (`true`), `ttl-seconds` (`60`), `max-pending-spans` (`10000`) — the cross-batch correlation buffer's bounds (11H-B) |
| `telemetry.coverage` | `qualification-enabled` (`true`) — the O4 coverage-classification kill switch (11H-E) |
| `telemetry.scoped-evidence` | `enabled` (`false`), `stream-id` (`otlp-http`) — v0.6.0: also persist an isolated, caller-Pod-scoped v2 record for each accepted CALLS whose original CLIENT carries `k8s.pod.uid`, `k8s.cluster.uid` and a matching environment. The record is internal (never `:Evidence`, no relationships, not in any answer or the snapshot) and off by default; with it off the graph is unchanged. `stream-id` names this instance's live trace stream in the operational transition report |
| `runtime_analysis` | `default_window_hours` (`24`), `default_environment` (`production`) |

## Backward compatibility guarantee

Every 11H-era property (`telemetry.http-correlation.*`, `telemetry.coverage.*`, and the v0.6.0 `telemetry.scoped-evidence.*`) is optional with a
safe default — an existing `config.yaml` written before these properties existed still starts the
app completely unchanged. This isn't just convention: `HttpCorrelationConfig` and `CoverageConfig`
are both plain Pydantic models with `Field(default=...)` on every property, and `TelemetryConfig`
constructs them via `default_factory` when the whole section is absent — there's no code path where
a missing 11H property prevents startup.

## LLM stays fully optional

The platform works completely without any LLM provider configured. `app/main.py` sets
`app.state.llm_provider = None` whenever `llm.enabled` is false or `OPENAI_API_KEY` is unset —
`POST /api/query` still answers every deterministically-routed question exactly as before; only a
genuinely unrecognized question, which would otherwise fall through to LLM-generated Cypher, returns
a `503` explaining the LLM subsystem isn't configured. See
[`semantic-validation.md`](semantic-validation.md) for the full generated-Cypher pipeline this only
gates the entry to.
