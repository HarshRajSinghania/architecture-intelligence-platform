# Development

```bash
uv sync                                # install dependencies
uv run pytest tests/unit               # fast unit tests (no Neo4j needed)
uv run pytest tests/integration        # Testcontainers-backed tests (needs Docker)
uv run ruff check .                    # lint
uv run ruff format .                   # format
uv run pyright                         # type check (app/)
```

Copy `.env.example` to `.env` and fill in `NEO4J_PASSWORD` (and `OPENAI_API_KEY` if you want the
natural-language query layer — the LLM query subsystem is fully optional and disables itself with a
friendly `503` if unset; see [`configuration.md`](configuration.md)). To run the app locally against
a Neo4j you start yourself:

```bash
export NEO4J_PASSWORD=devpassword     # and NEO4J_USER/OPENAI_API_KEY as needed
uv run uvicorn app.main:app --reload
```

`config.yaml` points `sources.directories` at `examples/`, so `POST /api/import` works out of the
box against this repo's fixture services. Or run the full stack via Docker Compose:

```bash
docker compose up
```

For the OpenTelemetry Collector-based runtime demo, see the README's "Runtime telemetry" section
and [`opentelemetry.md`](opentelemetry.md).

## Troubleshooting

### Neo4j authentication failures or startup health problems

The most common local issue is a mismatched or missing `NEO4J_PASSWORD`.

- Make sure you created `.env` from `.env.example` and that the password in `.env` matches what the
  Neo4j container or local Neo4j instance expects.
- Docker Compose already blocks the app on `depends_on: condition: service_healthy`, so check the
  `neo4j` service health and logs if startup fails:

```bash
docker compose ps
docker compose logs neo4j
```

If the logs show authentication errors or the container is still starting, confirm that the
credentials in `.env` match the Neo4j instance and wait until Neo4j reports healthy status before
retrying. When running the app directly with `uvicorn`, Neo4j may still be unavailable when the app
starts, so start Neo4j first and then launch the app.

Neo4j initializes its credentials only when its data volume is created. Changing `NEO4J_PASSWORD`
in `.env` does not update the credentials in an already initialized `neo4j-data` volume. To reset a
local Compose database, run `docker compose down -v` before starting it again, but note that this
deletes the local Compose volumes.

If you are running the app directly with `uvicorn`, make sure the same password is exported in your
shell as well:

```bash
export NEO4J_PASSWORD=devpassword
```

### Port conflicts on 7474, 7687, or 8000

This project uses Neo4j on ports `7474` (HTTP) and `7687` (bolt), and the FastAPI app on `8000`.
If one of those ports is already in use, Docker Compose or your local app start will fail or bind to
an unexpected port.

Check what is already listening:

```bash
docker compose ps
# Linux/macOS
lsof -i :8000
lsof -i :7687
lsof -i :7474
# Windows PowerShell
netstat -ano | findstr :8000
netstat -ano | findstr :7687
netstat -ano | findstr :7474
```

If a previous Neo4j or app instance is still running, stop it and retry. For Docker Compose, a
clean restart is often enough:

```bash
docker compose down
# then start again
docker compose up
```

If you are running `uvicorn` directly and `8000` is occupied, either stop the conflicting process or
start the app on another port, for example:

```bash
uv run uvicorn app.main:app --reload --port 8001
```

### Stale `.venv` after dependency changes

If you switch branches, update the project, or change dependencies, a stale virtual environment can
cause module import errors or cryptic runtime failures.

The reminder is simple: run:

```bash
uv sync
```

before rerunning tests or the app. If the environment still feels corrupted, remove the virtual
environment and recreate it:

```bash
rm -rf .venv
uv sync
```

### `POST /api/import` returns 500 because Neo4j is not reachable yet

The import endpoint depends on a working Neo4j connection; if the graph database is still booting or
its auth configuration is wrong, the request can fail with a 500. With Docker Compose, the app is
blocked on `depends_on: condition: service_healthy`, so inspect the Compose health status, Neo4j
logs, and the configured credentials:

```bash
docker compose ps
docker compose logs neo4j
```

Once Neo4j reports healthy status and the credentials match, retry `POST /api/import`. For a direct
`uvicorn` run, start Neo4j first and confirm the expected URI and password are available in the
environment before launching the app; the app may otherwise start while Neo4j is still unavailable.

The app is configured to work against this repo's fixture services in `examples/`, so once Neo4j is
reachable, `POST /api/import` should work immediately against the bundled reference architecture.

## Test layout

- `tests/unit/` — no external dependencies; runs in a couple of seconds.
- `tests/integration/` — Testcontainers-backed against a real Neo4j; the integration suite shares
  one session-scoped Neo4j container, while individual modules/tests reset and populate graph state
  as required for isolation.
- `tests/fixtures/` — shared synthetic fixture data used across both.
- `examples/` — the reference test-fixture landscape used across unit/integration tests and the
  local Quick Start (`order-service` calls `product-service` and sends to `payment-q`;
  `product-service` only provides `getProduct`; `payment-service` receives `payment-q` and sends
  `invoice-q`; `invoice-service` only receives `invoice-q`; `unused-q`/`unknown-producer-q` exist
  specifically to exercise the A3/A4 orphan-queue analyses).

## Adding a new source of declared or observed architecture

See [`adapter-development.md`](adapter-development.md) for the extension point a new adapter needs
to fit — what it must produce (an `ArchitectureModel` for a declared source, an `ObservationBatch`
for a runtime source) rather than a specific class hierarchy to inherit from.

## Contributing

A dedicated `CONTRIBUTING.md` with the full contribution workflow is planned but not yet published.
Until then, open an issue or pull request as usual, and see
[`security-model.md`](security-model.md) if your change touches the LLM layer, the OpenTelemetry
ingestion path, or the correlation buffer — those three have explicit trust-boundary rules any
change there must preserve.
