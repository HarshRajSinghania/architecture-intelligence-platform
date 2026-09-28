# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/) — see [`ROADMAP.md`](ROADMAP.md) for which
parts of the surface (Canonical Model, REST API, Graph Schema, Adapter SPI, configuration format)
aren't yet guaranteed stable pre-1.0.

## [Unreleased]

### Added

- Static type checking: `uv run pyright` (standard mode) now runs in CI's `quality` job over all
  of `app/`. Existing type errors were fixed without behavior changes, except the two listed under
  Changed.

### Changed

- `ServiceIdentityResolution` now rejects, at construction, a `RESOLVED` outcome without a
  `service_id` (and a rejected outcome with one). Every built-in resolver already complied; a custom
  `ServiceIdentityResolver` returning an inconsistent resolution now fails loudly instead of
  producing canonical ids such as `operation:None:...`.
- The OpenAI provider now raises `LLMProviderError` when the model returns no parsed Cypher or no
  answer content (for example on a refusal), instead of an `AttributeError` or a `None` answer that
  failed when the query response was built. The HTTP outcome is unchanged (an error response on
  `/api/query` and the UI query page).

## [0.5.1] - 2026-09-27

### v0.5.1 — Realistic Architecture Demo

Shows how a developer and their coding agent get the architecture context for a real change in a
multi-service system, without reconstructing it themselves. Adds no Architecture Knowledge
semantics, source family or MCP tool; the public surface is v0.5.0's, and only `producer.version`
reports `0.5.1`. See the
[release notes](docs/release-validation/v0.5.1-release-notes.md).

### Added

- **Quarkus Super Heroes demo** (`examples/quarkus-super-heroes-demo/`, v0.5.1): one command replays
  the v0.5.0-qualified Quarkus Super Heroes evidence, plus a disclosed operator-authored AsyncAPI
  overlay for Kafka `fights`. It checks the `rest-fights` answer against the frozen evidence and
  prints a ready agent prompt. It comes with a question-by-question walkthrough and a recorded Claude
  Code conversation. No new Architecture Knowledge semantics or MCP tools.

## [0.5.0] - 2026-09-26

### v0.5.0 — Broader Architecture Discovery

Broadens what AIP can safely know about a distributed system's Current State. Kubernetes is added
as the single new discovery source family, and declared Services are associated with Kubernetes
Workloads only through explicit, evidence-backed identity paths. Topics and Subscriptions are
distinguished from Queues, independently of the broker. Every supported answer stays deterministic,
evidence-backed and read-only, and unresolved, conflicting and unsupported cases stay explicit. See
the [release notes](docs/release-validation/v0.5.0-release-notes.md).

- A source-ingestion foundation built on one adapter/discoverer seam, with exact dialect
  enforcement: OpenAPI `3.0.3`/`3.1.0`/`3.1.2` and AsyncAPI `2.6.0`. It adds bounded local `$ref`s,
  owner-scoped identities, and authoritative-inventory and tombstone rules, so that a missing source
  is never mistaken for a removal. `POST /api/import` adds a versioned import report,
  `aip-import-report/1` (see [`docs/ingestion.md`](docs/ingestion.md)).
- Offline Kubernetes discovery (`OFFLINE_ONLY`) of Deployments, StatefulSets, DaemonSets, Pods,
  Kubernetes Services and Ingress routing, from frozen resource bundles. It has no live client and
  performs no cluster writes.
- Deployment identity (`DEPLOYED_AS`) through an explicit Workload annotation, a configured mapping,
  or qualified OpenTelemetry Pod-UID and owner-chain evidence. Disagreement stays a `CONFLICT`, and
  name similarity never resolves an identity. The results are served through
  `get_service_dependencies` and `GET /api/services/{id}/deployments`.
- Source-independent Pub/Sub semantics: Topic and Subscription are distinct from Queue (see
  [ADR 0017](docs/adr/0017-source-independent-pubsub-semantics.md)). Runtime evidence qualifies but
  never creates them.
- REST and standard negotiated MCP are now the two public adapters over one
  `ArchitectureIntelligenceService`. The v0.4.x direct MCP envelope is retired
  ([ADR 0016](docs/adr/0016-public-architecture-knowledge-adapters.md)); this is an intentional
  pre-1.0 breaking change. There are still exactly three read-only MCP tools. The answers carry
  `schema_version = "0.5"`. REST evidence reads now require `snapshot_id`.
- Qualification on two real systems, Quarkus Super Heroes and Apache Airflow 3.3.1, against
  independently frozen ground truth, with zero incorrect supported facts. It led to two general
  fixes: canonical-validation failures became per-source results, and the import report became
  complete.

See [`docs/specifications/0.5.0/`](docs/specifications/0.5.0/) for the full design history and
completion records.

## [0.4.2] - 2026-09-14

### v0.4.2 — MCP Client Interoperability

Makes the existing read-only Architecture Intelligence MCP surface directly consumable by qualified
coding-agent clients, without changing architecture semantics. Adds a negotiated MCP transport mode
alongside the existing direct-envelope mode; adds no discovery source, Canonical Model family, or
MCP tool.

- A negotiated MCP transport mode (standard `initialize`/session handshake), dispatching to the same
  three read-only tools with byte-identical `ArchitectureAnswer` semantics as the existing
  direct-envelope mode (see [`docs/mcp.md`](docs/mcp.md) and
  [ADR 0014](docs/adr/0014-negotiated-mcp-client-interoperability.md)).
- Four coding-agent client families qualified end to end against a real, running server — not only a
  test suite: Codex CLI `0.154.0`, Claude Code CLI `2.1.270`, Cursor `3.20.17`, VS Code `1.137.0` +
  GitHub Copilot Chat. Cross-client semantic mismatches = 0, evidence-meaning mismatches = 0 — see
  the [qualified client/platform matrix](docs/release-validation/v0.4.2-client-qualification.md).
- Actual-client qualification found and fixed two real interoperability defects the test suite alone
  had not caught: a negotiated-mode routing gap that could hang the server on an unbounded
  direct-marked method, and an over-strict rejection of a negotiated follow-up missing the
  `MCP-Protocol-Version` header — both fixed and reconfirmed before candidate freeze.
- The shipped `v0.4` public contract is unchanged throughout: exactly three read-only MCP tools,
  `schema_version = "0.4"`, the `ArchitectureAnswer<T>` envelope family, zero graph writes through
  any tool.

See [`docs/specifications/0.4.2/`](docs/specifications/0.4.2/) for the full design history and
completion records.

## [0.4.1] - 2026-09-10

### v0.4.1 — Semantic Hardening for Broader Discovery

Hardens the qualification and messaging semantics `v0.4.0` shipped, and commits reproducible
evidence of current whole-graph read cost — before any broader discovery work widens the surface
those semantics govern. Adds no discovery source, Canonical Model family, or MCP tool.

- One declared-versus-observed semantic owner (`app/qualification/declared_observed.py`) now
  governs both the analysis/REST path and `ArchitectureIntelligenceService`/MCP, proven equivalent
  by a real-Neo4j differential fixture: qualification mismatches = 0, coverage mismatches = 0
  across declared-only, observed-only, confirmed, environment-mismatch, window-boundary, and
  unsupported/dangling-evidence cases. Found and fixed one real pre-existing coverage-window bug
  in the process (ADR 0010, now `Accepted`).
- Runtime messaging now requires two independent guards before minting any canonical fact: a
  Queue-compatible destination guard (default-deny — `messaging.system`/a destination name alone
  is never sufficient) and a safe service-identity guard (refuses the real OpenTelemetry SDK
  placeholder family, e.g. `unknown_service:<process>`, while still minting distinctive
  runtime-only names). Either guard's refusal creates zero Service/Queue/Evidence/relation
  artifacts. The frozen Quarkus Super Heroes Kafka and Apache Airflow/Celery shapes remain
  unsupported, with zero invented messaging facts, confirmed against their real captured attribute
  values (ADR 0013, satisfied).
- A committed, reproducible benchmark (`benchmarks/`, `uv run python -m benchmarks --profile
  {smoke,review-comparable}`) makes AIP's current whole-graph snapshot/read cost measurable —
  timing `canonical_snapshot_state()`/`snapshot_fingerprint()` and one end-to-end
  `get_service_dependencies` call through the real MCP boundary as unrelated total graph/evidence
  size grows, with a fixed target answer held semantically constant throughout. This supplies only
  the baseline half of [ADR 0011](docs/adr/0011-snapshot-identity-read-cost.md)'s acceptance
  condition — no cache, snapshot-identity change, or retention policy ships in this release; ADR
  0011 stays `Proposed`.
- The shipped `v0.4` public contract is unchanged throughout: exactly three read-only MCP tools,
  `schema_version = "0.4"`, the `ArchitectureAnswer<T>` envelope family, zero graph writes through
  any tool.

See [`docs/specifications/0.4.1/`](docs/specifications/0.4.1/) for the full design history and
completion records.

## [0.4.0] - 2026-09-07

### v0.4 — Trusted Architecture Context for Agents

AIP's validated architecture model is now exposed to AI agents and other MCP clients as stable,
snapshot-bound, evidence-backed, machine-consumable context — never as a system an agent can write
to or become the source of truth for.

- `ArchitectureIntelligenceService`: one semantic entry point in front of the graph, returning a
  uniform `ArchitectureAnswer<T>` envelope (`schema_version`, `producer`, `snapshot`, `outcome`,
  `claims`, `evidence_refs`, `limitations`) for every tool.
- Snapshot-bound, current-state answers: every answer names an exact, fingerprinted graph
  revision (`snapshot_id`/`model_revision`), with a bounded stable-read retry rather than a
  torn/partial read.
- Explicit observation context (`environment`/`window_start`/`window_end`) for the
  runtime-sensitive dependency and drift answers, normalized to a stable `context_id`;
  `get_evidence` is snapshot-bound and intentionally observation-context-free — it resolves
  provenance for already-identified references rather than producing qualified claims of its own.
- Evidence and provenance drill-down: every claim carries opaque evidence references resolvable,
  at the same snapshot, to sanitized `DECLARED`/`OBSERVED` provenance — no raw span/trace payload,
  headers, or secrets.
- Explicit claim qualification (`CONFIRMED`/`OBSERVED_ONLY`/`NOT_OBSERVED_IN_WINDOW`) and
  limitation vocabulary (e.g. `UNRESOLVED_IDENTITY`, `INSUFFICIENT_EVIDENCE`) — non-observation is
  never represented as absence, and an unresolved destination is never guessed.
- Exactly three read-only MCP tools (`2026-07-28` protocol, one `/mcp` endpoint), in frozen
  lexicographic order: `get_architecture_drift` (direct dependencies whose evidence shows a
  declared-versus-observed discrepancy), `get_evidence` (bounded evidence-reference resolution),
  `get_service_dependencies` (one-hop qualified direct dependencies). Closed input/output schemas;
  an independent client (no AIP internal module, no LLM key) can drive the full dependency/drift →
  evidence golden path over plain HTTP/JSON-RPC.
- A complete deterministic tool evaluation: 23 scenarios (synthetic plus real-system-derived) run
  against all three tools, two full clean-state passes producing byte-identical semantic output
  both times, plus cross-tool invariants (dependency↔drift, drift↔evidence) proven live rather than
  asserted.
- Frozen Quarkus Super Heroes/Apache Airflow-derived qualification: the three-tool surface is
  proven against both systems' already-validated (`v0.3.0`) evidence, with zero fresh live reruns
  and zero invented facts.
- A deterministic, timestamp-frozen hero demo: an independent MCP client discovers all three
  tools, then calls `get_architecture_drift`/`get_evidence` to find and explain a real,
  undocumented dependency — `OrderService -> LegacyPricingService`, qualified `OBSERVED_ONLY` —
  reproducibly from a clean state, in about five minutes, with no LLM required.
- No LLM is required for any tool's correctness — the entire architecture-intelligence surface
  this release adds is deterministic.

Important boundaries: the three tools return **direct** dependencies only (no transitive
traversal), no historical/point-in-time snapshots (current state only), no generic Cypher/graph
query surface, and zero graph writes through any tool. MCP is exposed for a local/trusted-network
posture, not hardened for direct public-internet exposure. Pre-1.0 contracts (REST/MCP surface,
Graph Schema, Canonical Model, Adapter SPI, configuration format) may still change on a minor
version bump — see `ROADMAP.md`.

See [`docs/specifications/0.4.0/`](docs/specifications/0.4.0/) for the full design history and
[`docs/mcp.md`](docs/mcp.md) for the tool reference and a runnable hero-demo walkthrough.

An initial release candidate, `v0.4.0-rc.1`, was published and fully qualified end to end — clean
checkout, hero demo, and the published GHCR image's own MCP golden path — see
[`docs/release-validation/v0.4.0-go-no-go.md`](docs/release-validation/v0.4.0-go-no-go.md) (**GO**,
decided by the repository owner 2026-09-07). `v0.4.0` was tagged at that exact candidate and
published; its GHCR artifact and tagged source were independently re-verified — see
[`docs/release-validation/v0.4.0-post-release-verification.md`](docs/release-validation/v0.4.0-post-release-verification.md).

## [0.3.0] - 2026-09-02

### v0.3 — Real-World Validation and Cross-System Hardening

AIP was validated against two independently authored real systems it was not built against:
**Quarkus Super Heroes** (a controlled, externally authored microservice reference architecture)
and **Apache Airflow** (a mature real-world system — API server, scheduler, workers, asynchronous
task execution). This does not add another architecture-intelligence dimension; it tests whether
the model validated reproducibly in `v0.2` survives contact with systems AIP's own authors did not
build.

- Independent real-world validation methodology frozen (I1): finding vocabulary, ground-truth
  independence rules, supported-scope rules, comparator semantics, dossier/runbook contract.
- Quarkus Super Heroes qualified (I2): **38 correct, 2 unsupported, 0 incorrect/missing
  supported** (comparator-only score, reproduced byte-identical across two independent runs);
  **1 insufficient evidence overall** (0 in the comparator-only score — `qsh-kafka-operation-
  type-gap`, discovered once by a separate diagnostic inspection, not emitted by either
  comparator run, carried forward as an accepted dossier disposition).
- Apache Airflow qualified (I3): **9 correct, 3 unsupported, 2 unresolved identity, 1 insufficient
  evidence, 0 incorrect/missing supported.** Two independent runs, byte-identical.
- Cross-system finding dispositions (I4): all 10 findings from both dossiers dispositioned
  `NO_CHANGE`, `DOCUMENT_UNSUPPORTED`, or `DEFER` — **zero required a production fix**. The
  canonical-redesign gate answered **NO**: no fundamental Canonical Model redesign is required
  before v0.4.
- **Zero material `INCORRECT_SUPPORTED` findings** across either system, across every qualifying
  run.
- **No production semantic changes** were justified by either system's independent evidence — the
  Canonical Model, relation semantics, identity resolution, and runtime-status classification are
  unchanged from `v0.2.0`.
- Explicit, bounded boundaries rather than silently-absorbed gaps: gRPC/protobuf calls, Kafka
  topic/subscription semantics, and PostgreSQL/database dependencies remain unsupported; Airflow
  Execution API caller identity and runtime-role identity remain unresolved rather than guessed;
  a legacy OpenTelemetry messaging-attribute shape and Celery messaging identity remain
  insufficient-evidence, deferred pending future evidence.
- I4/`v0.3.0-rc.1` candidate repeatability baseline: both systems' qualifying comparisons were
  re-executed twice each, from clean state, against that candidate (`9f95d48`), producing
  byte-identical captures and comparator reports both times.
- Final-candidate repeatability: after the version/lock fix below produced a new candidate
  (`v0.3.0-rc.2`), both systems were revalidated fresh against it — two runs each, from clean
  state — producing captures and comparator reports byte-identical to each other **and** to the
  `rc.1` baseline above, proving the fix changed no application-facing fact.

See
[`docs/real-world-validation/cross-system/report.md`](docs/real-world-validation/cross-system/report.md)
for the full cross-system report and finding ledger, and
[`docs/release-validation/v0.3.0-go-no-go.md`](docs/release-validation/v0.3.0-go-no-go.md) for the
final qualification record.

An initial release candidate, `v0.3.0-rc.1`, was tagged at the I4-qualified candidate — but I5's own
entry qualification found `pyproject.toml`/`uv.lock` still declared project version `0.2.0`, which
is release-blocking. That fix produced a new candidate, `v0.3.0-rc.2`; its fresh real-system
revalidation, Quick Start, GHCR artifact, and CI/CodeQL/Trivy qualification are all complete and
green, and the repository owner decided **`GO`** — see
[`v0.3.0-go-no-go.md`](docs/release-validation/v0.3.0-go-no-go.md). `v0.3.0` was tagged at that
exact candidate and published; its GHCR artifact and tagged source were independently re-verified —
see [`v0.3.0-post-release-verification.md`](docs/release-validation/v0.3.0-post-release-verification.md).

## [0.2.0] - 2026-08-31

Adds a deterministic evaluation suite that verifies the architecture intelligence introduced in
`v0.1` against independently authored ground truth — real AIP ingestion and runtime resolution,
compared against a hand-written `expected.yaml`, with deterministic PASS/FAIL. This release does
not add another architecture-intelligence dimension; it proves the existing one behaves correctly.
See [`evaluation/README.md`](evaluation/README.md) and
[`docs/specifications/0.2.0/`](docs/specifications/0.2.0/) for the full design history.

### Added

- A deterministic evaluation kernel (`evaluation/`): scenario fixtures run through real AIP
  ingestion and runtime resolution, projected to canonical facts, and compared against independent,
  hand-authored `expected.yaml` ground truth - never generated from AIP's own derivation code.
- Ten core scenarios covering REST (`CALLS`/`PROVIDES`) and queue-based (`SENDS`/`RECEIVES_FROM`)
  dependencies, the `CONFIRMED`/`OBSERVED_ONLY`/`NOT_OBSERVED_IN_WINDOW` status classifications,
  topology/directionality (orphan messaging, mixed sync/async, request/response queue pairs),
  partial observation with qualitative coverage, evidence reconciliation, and a pure declared-only
  REST relation.
- Exhaustive missing/unexpected/forbidden-fact detection - any in-scope actual fact that's neither
  expected nor explicitly forbidden fails the scenario, not just a silently-ignored diagnostic.
- `NOT_OBSERVED_IN_WINDOW` evaluation, context-qualified: a declared relation with no matching
  observed evidence in the selected environment/window remains a real canonical fact, never treated
  as absence.
- Evidence-reconciliation evaluation: proves that removing a service's stale `DECLARED` evidence for
  a relation never removes independently surviving `OBSERVED` evidence, and that the resulting
  status transition (`CONFIRMED -> OBSERVED_ONLY`) is read from AIP itself, never re-derived.
- Partial-observation coverage qualification: an unobserved relation's qualitative coverage
  (`SUFFICIENT`/`PARTIAL`/`NONE`/`UNKNOWN`) is asserted through AIP's own production
  runtime-analysis boundary, never reimplemented in the evaluator.
- Strict `expected.yaml` schema validation: unknown fields, invalid status/evidence values, naive
  (non-timezone-aware) timestamps, and scope-excluded assertions all fail at load time as
  deterministic configuration errors rather than silently weakening an assertion.
- Deterministic comparison and report ordering, independent of Python's internal set iteration
  order.
- Local reproducibility: the full suite runs from a clean checkout without a separately running
  Neo4j and without an LLM API key (`uv run python -m evaluation run`).

## [0.1.0-alpha.2] - 2026-08-27

Second public pre-release, cut specifically to give the fixed release pipeline (single Docker
workflow trigger) one clean run, and to re-verify the non-root container fix against the actual
published GHCR image rather than only a local build — both gaps left open by `v0.1.0-alpha.1`'s own
verification. See
[`docs/release-validation/v0.1.0-alpha.2-verification.md`](docs/release-validation/v0.1.0-alpha.2-verification.md).

### Fixed

- The container ran as `root` — no `USER` instruction in `Dockerfile`. Found via `v0.1.0-alpha.1`'s
  GHCR pull-and-run verification (spec §29's non-root check). Fixed: builds/runs as a dedicated `app`
  (uid 1000) user; verified end-to-end (health checks, import, an analysis) both standalone and in
  the runtime demo — and now also against the actual pulled, tagged `v0.1.0-alpha.2` GHCR image, not
  only a local build.
- `docker.yml` fired twice per release (`release: published` and `push: tags: "v*"` both matched one
  tag push), racing two builds from the same commit and letting whichever finished last silently
  overwrite the other's GHCR tag pointer — this is exactly what happened to `v0.1.0-alpha.1`. Now
  triggered only by `release: published`; confirmed under `v0.1.0-alpha.2`'s own release that exactly
  one run fires.
- README Quick Start referenced a placeholder clone URL and the wrong directory name, and never
  mentioned creating `.env` before `docker compose up`. Fixed with the real clone URL and a
  documented local-only default password (`.env.example`).
- `pyproject.toml` still carried the PoC-era package name/description
  (`architecture-intelligence-poc`); `uv.lock` regenerated to match.
- `tests/integration/test_runtime_api.py` used hardcoded absolute-datetime fixtures that would
  silently fall outside the runtime API's default rolling analysis window and start failing CI once
  enough real time had passed. Fixtures now compute their timestamps relative to "now".

### Added

- Branch protection on `main` (required CI status check, no force-push, no deletion — no required PR
  review, to preserve the direct-push-to-main workflow used throughout this solo-maintainer project).
- A demo screenshot in `README.md` and `examples/runtime-demo/README.md`'s runtime demo walkthrough.

## [0.1.0-alpha.1] - 2026-08-27

First public pre-release, cut to validate the complete release pipeline (GitHub Actions, CodeQL,
GHCR publishing, a fresh-clone Quick Start and runtime demo) before promoting to `v0.1.0`.

### Added

**Core PoC** — OpenAPI and AsyncAPI adapters, an Architecture Manifest adapter for REST-caller
information neither spec format can express, a shared Canonical Model (Pydantic) decoupling every
adapter from Neo4j persistence, a Neo4j importer with deterministic stable IDs and atomic
per-service reimport, five deterministic Cypher analyses (queue senders/consumers, orphan queues,
mixed sync/async blast radius), a minimal FastAPI UI, and a read-only natural-language query layer
(question → validated Cypher → explanation, LLM never a source of truth and never able to write to
the graph).

**H1–H3 hardening** — persisted `Evidence`/`Provenance` (previously in-memory only), a Graph Schema
+ Semantic Query Validator for the LLM layer, and a deterministic intent router for common questions
that don't need an LLM round-trip at all.

**H4 — OpenTelemetry** — an OTLP/HTTP ingestion endpoint (`/v1/traces`) that resolves observed spans
against declared architecture and persists observed facts/evidence alongside declared ones; service
and environment resolution; REST (CLIENT/SERVER correlation) and queue (send/receive) observation
paths; evidence aggregation; declared-vs-observed comparison (`CONFIRMED`/`OBSERVED_ONLY`/
`NOT_OBSERVED_IN_WINDOW`); a runtime API, runtime UI, and intent-router integration.

**11H — Runtime Correctness & Robustness** — fixed a stale-evidence relation-deletion bug in the
evidence-reconciliation path; hardened HTTP correlation (bounded, TTL-based, cross-batch-capable);
explicit handling for partial/single-sided HTTP instrumentation; an `OBSERVED PROVIDES` relation for
runtime-discovered operations with no declared provider, with later-declaration reconciliation;
qualitative telemetry-coverage classification (`SUFFICIENT`/`PARTIAL`/`NONE`/`UNKNOWN`) for
`NOT_OBSERVED_IN_WINDOW` findings, so a negative finding is never overstated as "unused"/"dead"; a
Collector-based OpenTelemetry demo topology.

**H5 — Open Source Readiness**:
- Apache License 2.0, `THIRD_PARTY_LICENSES.md` covering all direct dependencies, a repository
  secret/IP scan.
- A full public-facing `docs/` set (architecture, canonical model, graph/evidence model, ingestion,
  analyses, semantic validation, OpenTelemetry, configuration, security model, development, adapter
  development) plus `docs/specifications/` preserving the original design documents as design
  history.
- A self-demonstrating runtime demo: an undeclared `OrderService -> LegacyPricingService` call
  (`OBSERVED_ONLY`), periodic cross-batch HTTP correlation, and a documented walkthrough
  (`examples/runtime-demo/README.md`) covering all three declared-vs-observed states plus the 11H
  evidence-reconciliation scenario end-to-end.
- GitHub Actions CI (lint, unit + integration tests, `pip-audit`), CodeQL (Python + GitHub Actions),
  a release/tag-triggered Docker build published to GHCR with Trivy image scanning, and Dependabot
  (`uv`, `github-actions`, `docker`).
- `CONTRIBUTING.md`, `SECURITY.md` (GitHub private vulnerability reporting), `CODE_OF_CONDUCT.md`
  (Contributor Covenant v2.1), `SUPPORT.md`, four issue-report forms, and a pull request template.
- `CHANGELOG.md`, `ROADMAP.md`, and Architecture Decision Records under `docs/adr/`.

### Fixed

- A stale-`OBSERVED`-evidence relation could be incorrectly deleted during reconciliation (11H-A).
- The demo's traffic generator could send observed spans before `POST /api/import` ran, permanently
  splitting a service's declared and observed identities into two never-merging graph nodes (12C) —
  the generator now waits for the declared import before sending anything.
- `ruff format --check .` failed because ruff 0.16 formats Markdown code fences by default and
  wanted to rewrite `Protocol` stubs inside frozen historical spec documents (12D) — `*.md` is now
  excluded from ruff's formatting scope.
- `GET /health/neo4j` returned a raw exception message (`str(exc)`) to the caller on failure,
  which for a Neo4j driver error could include connection details — found by CodeQL
  (`py/stack-trace-exposure`) on its first run against real GitHub infrastructure (12G). Now
  logged server-side only; the response is a generic `{"status": "error"}`.
- `docker-compose.yml` required `OPENAI_API_KEY` (`:?` syntax), contradicting the documented
  LLM-optional guarantee — a fresh clone following the README's own Quick Start (which leaves the
  key blank) would fail to start at all. Found via 12G's fresh-clone validation.
- The natural-language query page and any O1-O5 API call without an explicit `environment`
  parameter silently returned zero rows against the runtime demo's data, because
  `config.yaml`'s `runtime_analysis.default_environment` (`production`) didn't match the demo's
  own `environment=demo` traffic tag. `docker-compose.demo.yml` now points the demo at
  `config.demo.yaml`, identical except for that one value.

### Security

- The LLM query layer treats LLM output as untrusted input: generated Cypher is restricted to a
  read-only allowlist (`MATCH`/`OPTIONAL MATCH`/`WHERE`/`WITH`/`RETURN`/`ORDER BY`/`LIMIT`) with
  depth/result-row limits, and the LLM never receives direct Neo4j credentials.
- The OTLP ingestion path and its bounded, TTL-based HTTP correlation buffer read only an explicit
  attribute allowlist and never persist raw span payloads, authorization headers, cookies, request/
  response bodies, or full URLs — see `docs/security-model.md`.
