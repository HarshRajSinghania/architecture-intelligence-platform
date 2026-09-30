# Roadmap

## Versioning

AIP follows [Semantic Versioning](https://semver.org/) with an additional product discipline from
`v0.5.0` onward:

> **A new `0.x.0` capability release should add at least one materially new class of
> evidence-qualified architecture question that AIP can answer safely and deterministically.**

The release is not complete merely because the semantic core exists. The new question must ship
end-to-end through the supported public adapters, with evidence/provenance continuity, qualification,
deterministic evaluation, and release qualification.

A patch release `0.x.y` is for a **post-release correction or maintenance change** that preserves
the `0.x.0` architecture-question space and intended semantic contract: for example a defect fix,
security/dependency patch, documentation correction, or semantics-preserving performance
improvement. Patch releases are not pre-planned buckets for unfinished `0.x.0` work.

After the final pre-1.0 capability release, contract freeze and production qualification use
`v1.0.0-rc.N` prereleases rather than inventing another `0.x.0` product release with no new
architecture question.

Historical `v0.1`–`v0.4` releases predate this question-oriented versioning doctrine and remain
unchanged.

Not yet guaranteed stable pre-1.0 — expect breaking changes on a capability-release minor bump or
during the `v1.0.0-rc.N` freeze phase:

- Canonical Model (`app/canonical/model.py`)
- REST API surface
- Graph persistence schema (node labels, relationship types/properties; implementation
  compatibility surface, not the public Architecture Knowledge contract)
- Adapter SPI (`docs/adapter-development.md`'s `Protocol` contracts)
- Configuration format (`config.yaml`)

## v0.1 — shipped

- ✓ OpenAPI adapter
- ✓ AsyncAPI adapter
- ✓ Evidence (persisted `Evidence`/`Provenance`, queryable via `/api/evidence`)
- ✓ Five deterministic analyses (queue senders/consumers, orphan queues, mixed-architecture blast
  radius)
- ✓ Semantic validation (Graph Schema + Semantic Query Validator for the LLM layer)
- ✓ OpenTelemetry (OTLP ingestion, service/environment resolution, REST + queue observation,
  evidence aggregation, a Collector-based demo)
- ✓ Declared vs observed (`CONFIRMED`/`OBSERVED_ONLY`/`NOT_OBSERVED_IN_WINDOW`, with the 11H
  evidence-reconciliation invariant and cross-batch HTTP correlation)

## v0.2 — shipped
Focus: make the architecture intelligence introduced in v0.1 reproducibly testable against known
ground truth.

- ✓ Ten deterministic core scenarios (REST/queue dependencies, topology/directionality, partial
  observation with qualitative coverage, evidence reconciliation, a pure declared-only case)
- ✓ Independent, hand-authored `expected.yaml` ground truth per scenario, never generated from
  AIP's own derivation code
- ✓ A deterministic evaluation runner and canonical-fact projector reading real AIP ingestion and
  runtime resolution
- ✓ Exhaustive missing/unexpected/forbidden-fact detection, strict scenario-schema validation, and
  deterministic comparison/report ordering
- ✓ Local reproducibility with no separately running Neo4j and no LLM API key required

The goal of v0.2 is not to add another architecture-intelligence dimension, but to provide a
reproducible way to demonstrate that the existing one behaves correctly. See
[`evaluation/README.md`](evaluation/README.md) and
[`docs/specifications/0.2.0/`](docs/specifications/0.2.0/) for the full design history.

## v0.3 — shipped

Focus: prove the architecture intelligence validated reproducibly in v0.2 survives real,
independently authored systems, and harden only where real evidence justifies it — not to add
another architecture-intelligence dimension. See
[`docs/specifications/0.3.0/`](docs/specifications/0.3.0/) for the full design history and
[`v0.3.0`](https://github.com/michaelegner/architecture-intelligence-platform/releases/tag/v0.3.0)
for the published release.

| Iteration | Purpose | Status |
|---|---|---|
| I1 — Real-World Validation Contract | Freeze methodology, finding vocabulary, dossier structure, comparison semantics, runbook contract | ✓ complete (internal iteration work; no separate tag cut) |
| I2 — Quarkus Super Heroes Validation | Validate against an external reference architecture | ✓ complete — `v0.3.0-alpha.2` |
| I3 — Apache Airflow Validation | Validate against real-world OSS software | ✓ complete (internal iteration work; no separate tag cut) |
| I4 — Cross-System Model Hardening | Apply only general fixes justified by independent real-system evidence; revalidate both systems | ✓ complete — `v0.3.0-rc.1` |
| I5 — Release Qualification | Qualify the exact candidate and publish `v0.3.0` | ✓ complete — **shipped as `v0.3.0`** |

- ✓ Zero production changes were justified by either system's independent evidence — see
  [`docs/real-world-validation/cross-system/report.md`](docs/real-world-validation/cross-system/report.md)
  for the full cross-system report, finding ledger, and the canonical-redesign-gate answer (`NO`, no
  fundamental Canonical Model redesign is required before v0.4).
- ✓ `v0.3.0-rc.1` was tagged at the I4-qualified candidate, then superseded by `v0.3.0-rc.2` after
  I5's entry qualification found `pyproject.toml`/`uv.lock` still declared project version
  `0.2.0` — a release-blocking inconsistency, fixed under this project's no-substitution policy
  (both RC tags remain immutable historical record).
- ✓ `v0.3.0-rc.2`'s fresh Quarkus/Airflow revalidation, Quick Start, GHCR artifact, and
  CI/CodeQL/Trivy qualification are all recorded in
  [`docs/release-validation/v0.3.0-go-no-go.md`](docs/release-validation/v0.3.0-go-no-go.md)
  (**GO**, decided by the repository owner 2026-09-02).
- ✓ `v0.3.0` was tagged at the exact GO candidate, published, and its GHCR artifact and tagged
  source independently re-verified — see
  [`docs/release-validation/v0.3.0-post-release-verification.md`](docs/release-validation/v0.3.0-post-release-verification.md).

## v0.4 — shipped

**Goal: Trusted Architecture Context for Agents**

Purpose: expose AIP's validated architecture model as stable, snapshot-bound, evidence-backed, and
machine-consumable context for AI agents and architecture tools. See
[`docs/specifications/0.4.0/`](docs/specifications/0.4.0/) for the full design history and
[`v0.4.0`](https://github.com/michaelegner/architecture-intelligence-platform/releases/tag/v0.4.0)
for the published release.

An agent consuming AIP must be able to determine not only what AIP claims about the architecture,
but why that claim exists and under which evidence and observation context it was derived.

| Iteration | Purpose | Status |
|---|---|---|
| I1 — Service Contract and Dependency Vertical Slice | `ArchitectureIntelligenceService`, `ArchitectureAnswer<T>`, snapshot fingerprinting, dependency projection | ✓ complete — `8031f64` |
| I2 — MCP Vertical Slice and Evidence Drill-Down | `get_service_dependencies`/`get_evidence` MCP tools, independent-client qualification | ✓ complete — `da56025` |
| I3 — Drift Capability and Deterministic Qualification | `get_architecture_drift`, full 3-tool deterministic evaluation, frozen Quarkus/Airflow qualification, hero demo | ✓ complete — `bbde691` |
| I4 — Release Candidate, Publication, and Verification | Candidate freeze, RC/final publication, published-artifact verification | ✓ complete — **shipped as `v0.4.0`** |

- ✓ Exactly three read-only MCP tools (`2026-07-28` protocol) — `get_architecture_drift`,
  `get_evidence`, `get_service_dependencies` — every answer snapshot-bound and, where
  runtime-sensitive, observation-context-bound; zero graph writes through any tool.
- ✓ A complete deterministic tool evaluation (23 scenarios, synthetic plus real-system-derived)
  passes two full clean-state runs with byte-identical semantic output, reusing `v0.3.0`'s frozen
  Quarkus/Airflow evidence rather than re-running either system live.
- ✓ A deterministic, timestamp-frozen hero demo: an independent MCP client discovers all three
  tools and finds `OrderService -> LegacyPricingService` = `OBSERVED_ONLY`, reproducibly from a
  clean state, with no LLM required — see [`docs/mcp.md`](docs/mcp.md).
- ✓ I4.1's entry audit caught a real pre-existing gap (the committed evaluation artifact was bound
  to a stale, pre-squash I3.3 commit rather than the actual I3.4-qualified candidate) and fixed it
  before candidate freeze — see
  [`docs/release-validation/v0.4.0-rc.1-candidate-preparation.md`](docs/release-validation/v0.4.0-rc.1-candidate-preparation.md).
- ✓ `v0.4.0-rc.1`'s full qualification (clean-checkout, hero demo, published-image golden path) and
  the GO decision are recorded in
  [`docs/release-validation/v0.4.0-go-no-go.md`](docs/release-validation/v0.4.0-go-no-go.md)
  (**GO**, decided by the repository owner 2026-09-07).
- ✓ `v0.4.0` was tagged at the exact GO candidate, published, and its GHCR artifact and tagged
  source independently re-verified — see
  [`docs/release-validation/v0.4.0-post-release-verification.md`](docs/release-validation/v0.4.0-post-release-verification.md),
  which also corrects an I4.2 Trivy query-scoping gap (same 3 pre-existing, non-exploitable
  findings already accepted for `v0.3.0`; release blocker count unaffected).

Principle:

> **AIP may help agents reason about architecture, but an agent must never become the source of
> architectural truth.**

The tool layer stays downstream of AIP's deterministic architecture model. It must not let an LLM,
agent, or MCP client create canonical facts, bypass semantic validation, or reach a graph write path.

## v0.4.1 — shipped

**Goal: Semantic Hardening for Broader Discovery**

Purpose: harden the qualification and messaging semantics `v0.4.0` shipped, and commit
reproducible evidence of current whole-graph read cost, before any `v0.5` discovery work widens
the surface those semantics govern. Adds no discovery source, Canonical Model family, or MCP tool.
See [`docs/specifications/0.4.1/`](docs/specifications/0.4.1/) for the full design history and
[`v0.4.1`](https://github.com/michaelegner/architecture-intelligence-platform/releases/tag/v0.4.1)
for the published release.

| Increment | Purpose | Status |
|---|---|---|
| I1 — Qualification Consistency | One declared-versus-observed semantic owner, real-Neo4j differential qualification | ✓ complete — `385604b` |
| I2 — Messaging Semantic Guards | Queue-compatible destination guard, safe messaging service-identity guard | ✓ complete — `d37399b` |
| I3 — Hardening, Qualification and Release | Committed snapshot/read-cost benchmark, exact-candidate qualification, RC/final publication, post-release verification | ✓ complete — **shipped as `v0.4.1`** |

- ✓ One declared-versus-observed semantic owner (`app/qualification/declared_observed.py`)
  governs both the analysis/REST path and MCP; qualification mismatches = 0, coverage mismatches =
  0 against a real-Neo4j differential fixture — see
  [`docs/adr/0010-single-qualification-rule.md`](docs/adr/0010-single-qualification-rule.md)
  (`Accepted`).
- ✓ Runtime messaging requires two independent guards (Queue-compatible destination, safe
  service-identity) before minting any canonical fact; either guard's refusal creates zero
  semantic artifacts — see
  [`docs/adr/0013-no-topic-family-without-guards.md`](docs/adr/0013-no-topic-family-without-guards.md)
  (satisfied).
- ✓ A committed, reproducible read-cost benchmark (`benchmarks/`) makes AIP's current whole-graph
  snapshot/read cost measurable, supplying the baseline half of
  [`docs/adr/0011-snapshot-identity-read-cost.md`](docs/adr/0011-snapshot-identity-read-cost.md)'s
  acceptance condition — no cache or retention change shipped; ADR 0011 stays `Proposed`.
- ✓ `v0.4.1-rc.1`'s full qualification (clean-checkout, hero demo, published-image golden path) and
  the GO decision are recorded in
  [`docs/release-validation/v0.4.1-go-no-go.md`](docs/release-validation/v0.4.1-go-no-go.md)
  (**GO**, decided by the repository owner 2026-09-10).
- ✓ `v0.4.1` was tagged at the exact GO candidate, published, and its GHCR artifact and tagged
  source independently re-verified — see
  [`docs/release-validation/v0.4.1-post-release-verification.md`](docs/release-validation/v0.4.1-post-release-verification.md).

## v0.4.2 — shipped

**Goal: MCP Client Interoperability**

Purpose: make the existing read-only Architecture Intelligence MCP surface directly consumable by
qualified coding-agent clients, without changing architecture semantics. Adds a negotiated MCP
transport mode alongside the existing direct-envelope mode; adds no discovery source, Canonical Model
family, or MCP tool. See [`docs/specifications/0.4.2/`](docs/specifications/0.4.2/) for the full
design history and
[`v0.4.2`](https://github.com/michaelegner/architecture-intelligence-platform/releases/tag/v0.4.2)
for the published release.

| Increment | Purpose | Status |
|---|---|---|
| I1 — Dual-Mode MCP Transport | Negotiated MCP transport mode alongside the existing direct envelope, identical Architecture Answer semantics in both | ✓ complete — `2b6f865` |
| I2 — Client-Ready Demo and Documentation | Candidate setup guides for Codex CLI, Claude Code, Cursor, and VS Code; local security boundary documentation | ✓ complete — `279c0ae` |
| I3 — Actual-Client Qualification, Release, and Post-Release Verification | Real-client qualification (not test-suite-only), candidate freeze, RC/final publication, post-release verification | ✓ complete — **shipped as `v0.4.2`** |

- ✓ A negotiated MCP transport mode (standard `initialize`/session handshake), dispatching to the
  same three read-only tools with byte-identical `ArchitectureAnswer` semantics as the existing
  direct-envelope mode — see [`docs/mcp.md`](docs/mcp.md) and
  [`docs/adr/0014-negotiated-mcp-client-interoperability.md`](docs/adr/0014-negotiated-mcp-client-interoperability.md).
- ✓ Four coding-agent client families qualified end to end against a real, running server — not only
  a test suite — each completing the full protocol-qualification and reconnect workflow with
  byte-for-byte identical architecture results: Codex CLI `0.154.0`, Claude Code CLI `2.1.270`,
  Cursor `3.20.17`, VS Code `1.137.0` + GitHub Copilot Chat. Cross-client semantic mismatches = `0`,
  evidence-meaning mismatches = `0` — see the
  [qualified client/platform matrix](docs/release-validation/v0.4.2-client-qualification.md).
- ✓ Actual-client qualification found and fixed two real interoperability defects the test suite
  alone had not caught: a negotiated-mode routing gap that let an unbounded direct-marked method
  reach the SDK and hang the server (found via Claude Code), and an over-strict rejection of a
  negotiated follow-up missing the `MCP-Protocol-Version` header, stricter than both the pinned SDK's
  own fallback and the MCP specification's own backward-compatibility allowance (found via VS
  Code/GitHub Copilot Chat) — both fixed and reconfirmed before candidate freeze; see ADR 0014's two
  Amendment sections.
- ✓ `v0.4.2`'s full qualification (candidate gate table, four qualified tuples, cross-client
  comparison) and the technical GO decision are recorded in
  [`docs/release-validation/v0.4.2-go-no-go.md`](docs/release-validation/v0.4.2-go-no-go.md)
  (**RELEASE_READY**, publication authorized by the repository owner 2026-09-14).
- ✓ `v0.4.2` was tagged at the exact GO candidate, published, and its GHCR artifact and tagged source
  independently re-verified — see
  [`docs/release-validation/v0.4.2-post-release-verification.md`](docs/release-validation/v0.4.2-post-release-verification.md),
  which also records an authorized-owner risk acceptance for 12 newly-disclosed HIGH/CRITICAL Trivy
  findings, all Debian base-image OS package patches unrelated to any AIP code or dependency change.

## v0.5 — Broader Architecture Discovery — shipped

**Goal: Broaden what AIP can safely know about distributed systems.**

Shipped and post-release verified as [`v0.5.0`](https://github.com/michaelegner/architecture-intelligence-platform/releases/tag/v0.5.0) on 2026-09-26 (`SHIPPED_VERIFIED`; see
[`docs/release-validation/v0.5.0-post-release-verification.md`](docs/release-validation/v0.5.0-post-release-verification.md)
and [`docs/specifications/0.5.0/`](docs/specifications/0.5.0/) for the full design history). I4 ended
`GO`; Kubernetes discovery shipped `OFFLINE_ONLY`.

**Product questions:**

> **Where is this service deployed?**  
> **Which deployment identities are unresolved?**

The [v0.5.0 parent specification](docs/specifications/0.5.0/specification.md) defines the release
contract. The scope combines ingestion hardening, one new discovery-source family, and bounded
identity reconciliation while preserving evidence, provenance, unsupported-case, and read-only
Architecture Intelligence guarantees.

| Increment | Scope and exit |
|---|---|
| I1 — Source Ingestion Foundation | One adapter/discoverer seam for existing OpenAPI, AsyncAPI, Architecture Manifest, and filesystem discovery; bounded local references, deterministic identity/inventory/replay, and explicit versioned migration mappings. |
| I2 — Kubernetes Discovery | Kubernetes is the only new source family. Deterministic offline discovery is mandatory; bounded read-only live discovery is optional and decided before implementation. Infrastructure claims do not establish application interaction. |
| I3 — Runtime Identity Reconciliation | Bounded declared-Service/Workload association through explicit annotations, configured mappings, or qualified OTel Pod-UID/owner-chain evidence. The public relation is `DEPLOYED_AS`; disagreements remain conflicts, not precedence-based guesses. Consolidates public Architecture Knowledge access around REST and standard negotiated MCP over one `ArchitectureIntelligenceService` semantic owner, retiring the v0.4.x direct MCP envelope. |
| I4 — Conditional Pub/Sub | Recorded `GO` or `DEFER`. Source-independent semantics require qualified Queue/Topic/Subscription distinctions and identity guards. No live broker adapter is introduced. |
| I5 — Cross-System Qualification | Two materially different systems and negative fixtures; deterministic cross-source qualification and evidence-justified hardening. |
| I6 — Release and Post-Release Verification | Exact-candidate qualification, publication disposition, and separate unpublished `RELEASE_READY_NOT_PUBLISHED` or published `SHIPPED_VERIFIED` outcomes. Publication requires authorization; shipped verification requires final-artifact and security evidence. |

The [I1 implementation contract](docs/specifications/0.5.0/i1-source-ingestion-foundation.md)
accepts exactly OpenAPI `3.0.3`/`3.1.0`/`3.1.2` (the last added by its Draft 0.3 amendment) and
AsyncAPI `2.6.0`. It preserves composition
structurally with explicit limitations. Equal content does not establish shared Schema/Message
identity: owner-scoped IDs remain distinct unless explicitly mapped. Portable, versioned
Service/Schema/Message/Queue mappings preserve qualified legacy fixture meaning without naming
fallbacks. Additional dialects require a reviewed amendment and qualification.

Source disappearance is not authorized removal. Expiration requires a qualified complete
same-scope inventory or an explicit versioned tombstone. Failed/incomplete discovery preserves the
last committed state; changed scopes cannot silently expire previous ownership.

I2/I3 freeze concrete claim schemas and public exposure locations before implementation and
fixtures. The existing three read-only MCP tools remain the scope budget. During I3, REST and
standard negotiated MCP become the two public Architecture Knowledge adapters over
`ArchitectureIntelligenceService`; the deterministic evaluator calls the service directly, and the
v0.4.x direct MCP envelope is retired. A live-discovery decision activates live-specific
qualification in I2, not I1.

> **WHERE something is does not establish HOW it interacts.**

Every source maps through the shared Canonical Model. Placement is retained as source/context
evidence only; v0.5 exposes no locality-qualified claim or projection.

```text
non-observation != absence
source disappearance != authorized source removal
unresolved identity > guessed identity
explicitly unsupported > incorrectly represented as supported
Queue != Topic
Topic != Subscription
Service != Kubernetes Service != Workload != Pod
co-location != dependency
observed behavior != intent
```

Exit capability:

> **AIP can safely discover a broader distributed-system Current State while retaining the context
> and locality required for later qualification.**

gRPC/protobuf, Kafka Connect, other new source families, explicit Intent, Current↔Intent assessment,
historical trajectories, and distributed local-assessor deployment are outside v0.5. I4 may end in
`DEFER` without blocking the remaining qualified release.

## v0.5.1 — Realistic Architecture Demo — shipped

Shipped and post-release verified as [`v0.5.1`](https://github.com/michaelegner/architecture-intelligence-platform/releases/tag/v0.5.1) on 2026-09-27 (`SHIPPED_VERIFIED`, lightweight release path; see
[`docs/release-validation/v0.5.1-release-record.md`](docs/release-validation/v0.5.1-release-record.md)
and [`docs/specifications/0.5.1/specification.md`](docs/specifications/0.5.1/specification.md)).

**Goal: Demonstrate how users and coding agents obtain architecture knowledge needed to work on a
realistic multi-service system.**

- provide a ready-to-run Quarkus Super Heroes demo using the final v0.5.0 I5 dossier and qualified evidence;
- demonstrate task-driven questions and follow-up exploration, starting with understanding the fight
  service before changing it;
- make dependencies, runtime qualification, deployment bindings, and supporting evidence accessible
  through existing REST and MCP capabilities;
- provide deterministic demo preparation/replay and example conversations using an existing agent client;
- preserve unsupported/unresolved boundaries and show limitations in answers;
- keep the existing minimal demo;
- no new Architecture Knowledge semantics, source families, or MCP tools.

Exit capability:

> **A user and their coding agent can obtain and inspect architecture context for a concrete Quarkus
> development task without reconstructing that context themselves.**

## v0.6 — Locality-Aware Current State (planned)

**Goal: Establish architecture knowledge locally and contextually before projecting it into broader
Current-State views.**

**Product questions:**

> **Where is this dependency established?**  
> **Does this relation differ by supported locality?**

Focus: make context/locality an explicit part of Current-State qualification without changing the
fundamental rule that Current State is derived only from Current-State evidence.

AIP should be able to qualify a local assertion under an explicit context such as environment,
region, cluster/namespace, workload identity, service version, or observation window when — and
only when — the available evidence can support that dimension.

Conceptually:

```text
Current-State Evidence
        ↓
Qualified Local Evidence Assessment
        ↓
Deterministic Current-State Projection
        ↓
Evidence-Qualified Current State
```

Key requirements:

- define a first-class internal semantics for qualified local evidence assessment;
- preserve locality/context from source evidence through qualification and projection;
- keep observation window separate from any future Intent effective interval;
- make projection completeness and limitations explicit;
- prevent locally established claims from being silently promoted into universal/global facts;
- treat local as an explicit scope, which may span components when supported by evidence;
- require separate applicable evidence and qualification rules for new cross-boundary or system-level
  claims; composing local results alone does not establish causal flows or end-to-end outcomes;
- keep place/locality and connectivity independent (`WHERE != HOW`);
- prove that adding locality does not weaken deterministic replay, evidence provenance, or
  unsupported/unresolved semantics.

The implementation may remain centralized. A sidecar, DaemonSet, local agent, OTel extension, or
other distributed Local Architecture Assessor is **not** a v0.6 requirement.

Exit capability:

> **AIP can establish what its evidence supports within an explicit locality and observation context,
> and can deterministically project those qualified local assessments into a bounded Current-State
> view.**

## v0.7 — API-Aware Current State (planned)

**Goal: Establish evidence-qualified Current-State knowledge of how APIs are exposed and consumed,
while retaining the distinct meanings of contracts, operations, gateway objects, application services,
consumers, and observed interactions.**

**Product question:**

> **How are APIs exposed and consumed, and what can the available evidence establish about those
> relationships?**

**First bounded validation question:**

> **Which configured consumer/API relationships have matching observed runtime usage in a selected
> environment and observation window, and which remain unestablished from the available evidence?**

The first vertical slice SHALL use **real gateway configuration and consumer-attributed usage
measurements**. Kong is the proposed initial reference system, not AIP's canonical terminology or a
required gateway for later adapters. Its actual source capability determines whether a relationship
can be described as a product subscription, access registration, ACL membership, or another
configured relationship; AIP must not invent a subscription from the mere presence of a consumer.
Broader gateway/provider support remains incremental and separately qualified.

Minimum requirements for the slice:

- freeze a small, **platform-independent semantic vocabulary**, keeping API contract/version,
  API operation, gateway route/service, application service, gateway consumer, configured access
  relationship, and observed interaction distinct; API product, business capability, domain boundary,
  and organizational owner must not be inferred from a technical name, URL, or graph proximity;
- reconcile source identities through accepted source-specific evidence or explicit mappings,
  including unresolved, ambiguous and conflicting cases; association is not necessarily entity
  equivalence;
- reuse source inventory, revision, authoritative-removal, snapshot/replay, and provenance semantics;
  preserve contract-version applicability and any evidenced source authority without treating the
  newest or similarly named artifact as automatically canonical;
- acquire or pin real, **consumer-attributed** usage evidence with bounded environment/window,
  measurement meaning, identity resolution, and applicable telemetry coverage; missing metrics must
  not turn into zero observed requests or a claim of non-use;
- qualify configured and observed relationships independently as Current State: configured access
  does not establish actual usage and does not become authoritative architectural Intent;
- expose one deterministic, question-specific Architecture Intelligence answer through the shared
  semantic service, REST and negotiated MCP, with same-snapshot evidence resolution, limitations,
  bounded enumeration, and independently authored positive/negative real-source tests;
- run a product-value pilot that includes useful answer coverage and the cost of setup, source
  synchronization, attribution, and identity mapping; record a continue/narrow/defer/stop disposition.

**Explicitly outside the initial v0.7 slice:** complete enterprise/API-product cataloging,
business-capability classification, automatic ownership inference, multiple gateway integrations as
a release gate, generic analytics/dashboarding, formal Intent, policy/compliance assessment, approval
workflows, and historical architecture reconstruction. Additional OpenAPI/AsyncAPI, repository,
CI/CD, architecture-model, and vendor sources may enter only through separately qualified,
question-driven increments. The new source family must not weaken the already accepted v0.6
locality or v0.5 Current-State contracts.

**External research inputs:** [Understanding API Landscapes, Not Just Managing Them](https://adorsys.com/en/techradar/understanding-api-landscapes-not-just-managing-them/)
and [The API Is Not the Boundary](https://adorsys.com/en/techradar/the-api-is-not-the-boundary/).
They motivate the validation question; they are not AIP's semantic authority.

Exit capability:

> **AIP can relate an API's evidenced exposure and configured consumers to independently observed,
> consumer-attributed usage, and state which relationships are established, unresolved, or
> insufficiently supported in the selected context without silently inventing product, business,
> authorization, or Intent claims.**

## v0.8 — Explicit Architecture Intent (planned)

**Goal: Represent explicit, attributable architectural intent without allowing Intent to alter
established Current State.**

**Product question:**

> **What explicit architecture intent applies here?**

Focus: introduce a source-neutral Intent/Assertion model after the Current-State path is already
locality-aware and independently qualified.

The governing invariant is:

> **With evidence, evaluation context, identity resolution, and mapping, qualification, and projection
> rule versions held constant, changing Intent must not change established Current State.**

Conceptually:

```text
CURRENT-STATE PATH

Current-State Evidence
        ↓
Qualified Local Evidence Assessments
        ↓
Current-State Projection


INTENT PATH

Explicit Attributable Intent Artifact
        ↓
Intent Assertion
        ↓
Applicable Intent Projection
```

Candidate Intent semantics include explicit promises, capability offers and acceptances, requirements,
constraints, required or prohibited relationships, scope, effective interval, and provenance.
Requirements, offers, acceptances, and promises retain distinct assertion kinds and attributable
actors. A consumer requirement does not establish a provider promise; a promise identifies its
promiser, content, conditions, and recipient or audience where applicable.

Intent applicability must distinguish authorship from authority and account for externally evidenced
approval status, authority scope, exceptions, revocation, and explicit supersession. Conflicting or
missing authority remains unresolved unless an explicit applicable resolution rule establishes
precedence. AIP consumes these decisions and does not own approval workflows.

Each applicable Intent projection requires a versioned identity and explicit lineage references to
its assertion revisions, authority/lifecycle evidence, evaluation context, and mapping/applicability
rule versions. Revoking an exception must produce a distinguishable projection even if the Intent
text remains unchanged. Identity/versioning does not promise historical retention or retrieval;
unavailable prior dependencies must be reported explicitly.

Potential carriers may include OpenAPI Overlay, AsyncAPI-compatible explicit extensions/artifacts,
standalone AIP Intent artifacts, OpenSpec, or other attributable machine-readable specifications.
The carrier must not become the semantic model: AIP should normalize Intent into source-neutral
assertions.

Intent must never be inferred as authoritative from runtime frequency, code structure, naming,
co-location, probabilistic interpretation, or agent-generated rationale.

Exit capability:

> **AIP can ingest distinct, attributable Intent assertions and establish their applicability from
> authority, lifecycle, scope, and time evidence, preserving versioned projection identity and lineage
> without treating Intent as evidence of Current State.**

No Current↔Intent compliance/enforcement engine, historical trajectory model, migration scripting,
or automatic remediation is required in v0.8.

## v0.9 — Qualified Architecture Assessment (planned)

**Goal: Assess independently established Current State against independently established applicable
Intent.**

**Product question:**

> **Where does Current State differ from applicable Intent?**

Focus: add a separate, read-only, evidence-linked assessment layer over the two already independent
semantic paths.

The dependency direction is:

```text
Current-State Evidence
        ↓
Qualified Local Evidence Assessments
        ↓
Current-State Projection
                         \
                          +--> Qualified Current ↔ Intent Assessment
                         /
Explicit Intent Artifacts
        ↓
Applicable Intent Projection
```

Never:

```text
Intent
  ↓
Current-State qualification
```

Assessment semantics must preserve both temporal dimensions independently:

```text
observation_window
    = when Current-State evidence was observed

effective_from / effective_until
    = when the explicit Intent applies
```

Assessment also requires explicit temporal compatibility between evidence and Intent, including
relevant service/deployment versions. Evidence predating an Intent's effective interval does not by
itself establish present fulfillment or violation. Partial overlaps require a qualified comparable
portion; otherwise the result remains inconclusive. Compatibility and coverage rules must be frozen
before qualification fixtures are authored.

Each assessment must reference the exact Current-State and versioned applicable-Intent projections
used, with their rule and evidence lineage. It must not silently replace earlier authority/lifecycle
inputs with their latest status. Where dependencies are unavailable, reproducibility limitations
must be explicit; historical retrieval remains beyond v1.0.

Independent evaluation does not imply independent evidence or complete verification of a change.
Assessments must preserve source modes and disclose known shared origins or unknown independence.
Re-importing an agent-edited contract establishes a declaration, not independent confirmation of
implementation or runtime behavior.

Possible assessment outcomes may include concepts such as `ESTABLISHED`, `CONTRADICTED`,
`NOT_ESTABLISHED`, `INSUFFICIENT_EVIDENCE`, and `CONFLICTING_EVIDENCE`, but the exact public
vocabulary must not be frozen until deterministic truth tables and independently authored evaluation
fixtures exist.

`CONTRADICTED` must never mean merely "not observed" unless an explicit closed-world rule permits
that interpretation.

The agent-facing surface may gain additional read-only Architecture Intelligence capabilities if
needed, but MCP transport should remain stable and generic graph/Cypher access should remain outside
the correctness path.

Exit capability:

> **AIP can explain where an independently established Current State aligns with, diverges from, or
> cannot yet be evaluated against the explicit Intent that applies in the selected context.**

Explicitly out of scope for v0.9:

- architecture trajectories / historical architecture state;
- migration planning or transformation scripting;
- automatic remediation;
- policy authoring, approval workflow, or CI blocking;
- distributed local-assessor deployment as a requirement;
- agent-generated authoritative Intent.

## v1.0 Release-Candidate Phase — Contract Freeze / Production Qualification (planned)

**Goal: Stabilize and production-qualify the architecture-intelligence contracts intended for
v1.0 without pretending that stabilization introduces a new architecture-question class.**

This phase uses `v1.0.0-rc.N` prereleases. It freezes only semantics and public contracts that have
survived implementation, deterministic evaluation, and real-system qualification across v0.5-v0.9.

Qualification/freeze scope includes, where actually implemented and accepted:

- Canonical Model compatibility review
- Current-State evidence and qualification semantics
- locality/context semantics and Current-State projection contracts
- qualified API exposure/consumption identity, source lifecycle, configured-vs-observed usage, and
  observation coverage contracts where accepted from the v0.7 pilot
- explicit Intent assertion kinds, authority/lifecycle applicability, and versioned projection contracts
- qualified Current↔Intent assessment contracts
- derivation-lineage and evidence/provenance requirements, including authority/lifecycle evidence
  references, rule versions, and exact projection binding
- temporal compatibility and coverage rules for Current↔Intent assessment
- REST and MCP contract stabilization
- graph-persistence compatibility and migration rules; the internal graph representation is not
  frozen as a public Architecture Knowledge contract
- Adapter SPI stabilization
- Configuration-format stabilization
- Migration and deprecation rules
- Security and production-operability qualification
- Performance and resilience qualification
- Release/support policy

Any known breaking redesign required for the stable contract must be completed before the final
`v1.0.0` release.

The release-candidate phase must not freeze hypothetical contracts merely because they appeared in
earlier strategy or roadmap text. A capability that did not survive implementation and
qualification is either removed, kept explicitly experimental, or deferred beyond v1.0.

Exit condition:

> **The architecture-intelligence model and public contracts intended for v1.0 are semantically
> stable, reproducible, migration-aware, and production-qualified.**

## v1.0 — Stable Architecture Intelligence Platform (planned)

Focus: publish the first stable AIP release with mature architecture-intelligence semantics and
public contracts. Requires: a stable architecture-intelligence model; stable public REST and MCP
contracts; a stable Adapter SPI where it is intentionally public; documented compatibility and
migration rules for graph persistence and configuration; production qualification completed;
critical semantic errors = 0; release blockers = 0.

## Sequencing principle

```text
v0.3  validation and hardening
  -> v0.4  trusted architecture context for agents
  -> v0.5  broader architecture discovery
  -> v0.6  locality-aware Current State
  -> v0.7  API-Aware Current State
  -> v0.8  explicit architecture Intent
  -> v0.9  qualified architecture assessment
  -> v1.0-rc  contract freeze and production qualification
  -> v1.0  stable platform
```

In capability terms:

```text
VALIDATE
   ↓
EXPOSE
   ↓
DISCOVER
   ↓
ESTABLISH LOCALLY
   ↓
CONNECT API EXPOSURE AND CONSUMPTION
   ↓
REPRESENT INTENT
   ↓
ASSESS
   ↓
FREEZE
```

In product-question terms:

```text
v0.5
WHAT is running WHERE?
        ↓
v0.6
WHERE does this architectural relationship hold?
        ↓
v0.7
HOW are APIs exposed and consumed, and what does the evidence establish?
        ↓
v0.8
WHAT explicit Intent applies here?
        ↓
v0.9
HOW does established Current State differ from applicable Intent?
        ↓
v1.0-rc
FREEZE and qualify the question space already implemented
```

This question progression is the product-facing expression of the semantic sequence above.

The Wardley-mapping result adds an investment rule:

```text
DIFFERENTIATE
evidence qualification
identity / reconciliation
provenance and bounded uncertainty
Architecture Knowledge semantics
deterministic question-specific projections

STANDARDIZE / CONSUME
MCP and REST transport
OpenAPI / OpenTelemetry / Kubernetes / Git interfaces
graph/database and persistence plumbing
other mature infrastructure
```

Roadmap scope should therefore prioritize expansion of AIP's safely answerable
architecture-question space. Core Domain work is justified where it is required to establish those
answers safely; Core Domain hardening without a materially new architecture-question class does not,
by itself, justify another `0.x.0` capability release.

Likewise, a new source adapter is not, by itself, a new product capability or capability-release
justification. It is strategically relevant when it enables materially new qualified Architecture
Knowledge, requires new evidence/reconciliation semantics, or unlocks a materially new recurring
architecture question. Proprietary transport, storage, or source plumbing should enter scope only
when correctness, interoperability, or evidence semantics require it.

The ordering is semantic, not merely chronological:

1. broader evidence must be trustworthy before it is used to establish more Current State;
2. locality-aware Current State must remain independently derivable before Intent exists;
3. API exposure and consumption are an additional Current-State question: qualified cross-source
   associations and observed use must not imply products, business capabilities, ownership, or Intent;
4. Intent must be explicit, attributable, and qualified for authority, lifecycle, scope, and time
   applicability before AIP compares Current State with it;
5. Current↔Intent assessment must remain read-only and downstream of both independent projections;
6. only implemented and qualified contracts are frozen for v1.0.

`v0.3` carried a hard gate: had either real-system dossier shown the Canonical Architecture Model
needed a fundamental breaking redesign, AIP would not proceed to v0.4 until that redesign was
specified, implemented, and revalidated — I4's
[`canonical-redesign-gate.md`](docs/real-world-validation/cross-system/decisions/canonical-redesign-gate.md)
answered `NO`, so that gate did not block.

None of the above are committed dates — this is a planning sequence, not a schedule. The detailed
scope of each planned release remains subject to its release specification and qualification gate;
the semantic dependency between the release themes is the stable part of this roadmap.

## Product validation gates

Planned scope, authorization to execute a release, and qualification for the stable v1.0 contract are
separate decisions. Planned status does not waive product-value or technical qualification gates.

Validate representative architecture tasks with and without AIP using comparable source access and
independently authored expected results. Define baselines and success/stop thresholds before the
pilot. Assess correctness together with useful answer coverage, justified abstention, false alarms,
and total engineering effort including setup, source maintenance, identity mapping, and clarification.
Reducing false claims only by returning more unresolved answers does not establish product value.

Record a continue, narrow, defer, or stop decision when evaluating these gates. Failed gates require
a documented scope decision and, where release assignment or product boundaries change materially,
a corresponding roadmap update. Apply these gates before accepting affected capabilities into the
stable contract. Detailed pilot design belongs in release-specific specifications; see
[Product Doctrine §6.4](docs/product-doctrine-and-strategic-direction.md#64-pilot-decision-gate).

## Additional discovery candidates (unscheduled)

gRPC/protobuf and Kafka Connect configuration remain candidates outside v0.5, with no assigned
release. Each requires a separately approved later-release specification, explicit semantics, and
deterministic conformance tests; the adapter seam does not automatically admit additional sources.

## Future (beyond v1.0, unscheduled)

- Externally sourced architecture decision-history linkage: relate a qualified finding or
  assessment to its review, accountable actor/team, recorded decision, rationale, and effective
  exception interval, without making AIP the approval authority or implying historical architecture
  reconstruction
- Historical architecture-state retention/import sufficient for principled temporal reasoning
- Architecture trajectories (how evidence-qualified Current State and applicable Intent evolve over
  time, once historical identity/provenance continuity exists)
- Distributed Local Architecture Assessor deployment options (for example sidecar, DaemonSet, OTel
  extension, or local gateway) if real-system evidence shows that moving deterministic qualification
  closer to the locality provides correctness or operational value
- Safe architecture transformation research, potentially including Bigraphical Reactive Systems,
  process calculi, type systems, temporal logic, or related formalisms
- Causal runtime flow analysis (beyond pairwise CLIENT/SERVER and send/receive correlation)
- GraphRAG (retrieval over the graph as LLM context, distinct from today's Cypher-generation-only
  query layer)
- Architecture Wiki (auto-generated narrative documentation from the graph)
- Backstage integration (surfacing the Architecture Knowledge Graph as a Backstage catalog/plugin)

See [`CONTRIBUTING.md`](CONTRIBUTING.md) if you want to help with any of it, and open an issue
before starting significant work on a roadmap item so it doesn't go to waste.
