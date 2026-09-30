# AIP Research Landscape

> A curated set of concepts, projects, standards, and publications relevant to the Architecture Intelligence Platform (AIP).
>
> **Purpose:** inform architecture and product decisions, identify adjacent work, and sharpen AIP's differentiation.
>
> Inclusion does not imply endorsement, dependency, or roadmap commitment. External ideas should influence AIP only where they survive AIP's own evidence, semantics, and validation requirements.

_Last reviewed: 2026-09-29_

## AIP anchor

AIP's strategic hierarchy is:

```text
Customer value proposition
Help coding agents work across multi-service systems
without reconstructing architecture
        ↓
Product concept
Moldable Architecture Knowledge
        ↓
Core Domain
Establishing Evidence-Qualified Architecture Knowledge
        ↓
Core-domain differentiation
applicability + identity/reconciliation + qualification
+ provenance/lineage + bounded uncertainty
        ↓
Product-level differentiation
deterministic question-specific projections + moldability
        ↓
Agent / human / contextual micro-tool
```

The Wardley-mapping implication is explicit: **differentiate where Architecture Knowledge is
established; standardize where it is transported and sourced**. Internal graph/storage
representation is replaceable; public architectural meaning is a versioned semantic contract rather
than implementation detail.

Future Intent and Current↔Intent assessment remain separate semantic layers; moldability does not
permit a consumer to rewrite evidence, qualification, provenance, or claim meaning.

The landscape is organized by the architectural question each source helps answer.

## Landscape map

This map is the navigation layer for the detailed research notes below. Each group names the
architectural question it helps AIP examine; inclusion remains research input rather than
endorsement, dependency, or roadmap commitment.

### Foundations and system semantics

[Bigraphs](#robin-milner--bigraphs--bigraphical-reactive-systems) ·
[Promise Theory](#mark-burgess--promise-theory) ·
[Designing Delivery / Promise Thinking](#jeff-sussna--designing-delivery--promise-thinking) ·
[Semantic Spacetime](#mark-burgess--semantic-spacetime) ·
[SSTorytime](#mark-burgess--sstorytime-and-context-investment) ·
[Strategic DDD](#domain-driven-design--strategic-patterns) ·
[SysML v2](#omg--sysml-v2)

**Core question:** How should AIP represent locality, connectivity, semantic boundaries, autonomous
promises, temporal context, and explicit system intent without collapsing them into one model?

### Evidence, discovery, and architecture products

[OpenTelemetry](#opentelemetry-semantic-conventions) ·
[OpenAPI as deterministic evidence](#kin-lane--openapi-as-a-deterministic-artifact-in-an-ai-generated-world) ·
[API knowledge beyond API management](#adorsys--understanding-api-landscapes-not-just-managing-them) ·
[Structurizr/C4](#structurizrc4--declared-architecture-models-and-views) ·
[Executable architecture rules](#archunit-and-jqassistant--executable-architecture-rules) ·
[Backstage](#backstage-software-catalog) ·
[Cartography](#cartography--infrastructure-and-security-graph-discovery) ·
[EventCatalog](#eventcatalog--connected-architecture-catalog-for-humans-and-agents) ·
[Evidence-backed relationships](#bipul-sinha--components-describe-a-system-relationships-reveal-its-architecture) ·
[Evidence-derived documentation](#sdlc-playbook--documentation-decay-and-evidence-derived-architecture-views) ·
[Axium](#mobilab-axium--semantic-ai-and-architecture-intelligence) ·
[ArchSmith](#sathish-siva-shankar--archsmith-and-intent-first-semantic-architecture-intelligence) ·
[ProvenMap](#provenmap--architecture-intelligence-intent-and-provenance) ·
[Logorythm](#logorythm--architecture-intelligence-from-static-analysis) ·
[Premise quality](#praveen-kasam--why-your-ai-agent-fails-the-answer-is-almost-never-the-model) ·
[Typed trace matrices](#spark-tsai--from-trace-ids-to-trace-matrix-what-does-a-change-actually-affect)

**Core question:** What can each source safely establish, how should conflicting evidence remain
visible, and where does qualified architecture knowledge differ from inventory, catalogs,
visualization, provenance, or retrieval?

### Agent context and machine consumption

[Moldable Architecture Knowledge](#moldable-development--glamorous-toolkit--rewilding-software-engineering) ·
[Architectural judgment](#michael-smith--line-of-sight-ai-and-architecture) ·
[Coordination bottlenecks](#cochran-et-al--when-coding-is-free-where-is-the-bottleneck) ·
[Decision substrate](#cockcroft-et-al--when-agents-decide) ·
[Symbolic Separation](#davletiyarov-khan-and-bartolini--symbolic-separation) ·
[Typed probabilistic judgment](#typesafe-ai--jev-and-typed-probabilistic-judgment) ·
[Enola](#enola--deterministic-architecture-context-and-regression-testing) ·
[Agent API Profile](#christian-posta--agent-api-profile) ·
[MCP](#model-context-protocol-mcp) ·
[Procedural Graphs](#lu-et-al--procedural-graphs) ·
[Agent-ready traceability and API boundaries](#daniel-kocot--agent-ready-apis-traceability-and-preserved-intent) ·
[BootUI](#bootui--runtime-context-for-coding-agents) ·
[Deterministic integration](#kin-lane--agents-should-write-code-to-integrate-not-infer-it-at-runtime) ·
[UI Atlas](#ui-atlas--ai-successors) ·
[Thoughtworks AI/works](#thoughtworks-aiworks) ·
[AI Agents — The Definitive Guide](#nicole-königstein--ai-agents-the-definitive-guide) ·
[Open source and protocols](#tim-oreilly--why-open-source-matters-for-ai) ·
[Gemini Enterprise](#google-cloud--gemini-enterprise-for-financial-services)

**Core question:** How should agents consume the smallest useful, bounded, portable, and
evidence-qualified architecture context without becoming the source of architectural truth?

### Intent, authority, and governance

[Confirmed versus inferred intent](#andreas-toth--ai-shouldnt-guess-what-we-mean-it-should-ask) ·
[ArchiMate and intent interchange](#archimate-and-intent-interchange) ·
[Mneme](#mneme-hq) ·
[Architecture guardrails](#oreilly--architectural-guardrails-for-ai-generated-code) ·
[AI-accelerated drift](#ankur-agnihotri--architecture-drift-reduction-with-llms) ·
[Design versus implementation](#alireza-rahmani-khalili--ai-did-not-eliminate-software-design) ·
[Architectural fitness](#raghunandan-e-srinivasan--from-architectural-debt-to-architectural-fitness) ·
[Bounded agency](#matthew-skelton--bounded-agency-and-the-ai-native-operating-model) ·
[Stewardship boundaries](#matthew-skelton--reframing-the-ai-native-sdlc-in-terms-of-stewardship-boundaries) ·
[Expert governance and code review](#rachel-laycock--expert-governance-and-code-review-in-an-ai-heavy-sdlc)

**Core question:** How should explicit intent, assumptions, fitness criteria, authority, and
organizational responsibility constrain agent action without being inferred from Current State?

### Verification, reliability, and observability

[Reliable AI systems](#rush-shahani--building-reliable-ai-systems) ·
[Agentic code review context](#davis-et-al--agentic-ai-and-code-reviews) ·
[Agent trajectory evaluation](#google--agent-evaluation-and-trajectory-metrics) ·
[Failure as a process](#zhao-et-al--failure-as-a-process) ·
[Long-running context drift](#agentic-software-how-ai-agents-are-restructuring-the-software-paradigm) ·
[ADMET-EvO](#zhou-et-al--admet-evo-and-evidence-gated-self-evolution) ·
[The Light Factory](#martien-de-jong--the-light-factory) ·
[OrcaReplay](#orcareplay--record-replay-and-fork-agent-runs) ·
[Deterministic backpressure](#lucas-f-costa--backpressure-is-all-you-need) ·
[Agent observability](#agent-observability)

**Core question:** How should AIP keep proposal, evidence judgment, deterministic verification,
agent behavior, delivery lineage, and release qualification independently inspectable?

---

## 1. Formal and strategic foundations

These sources are not product comparisons. They are theoretical or strategic design foundations for reasoning about structure, boundaries, interaction, intent, observation, and change.

### Robin Milner — Bigraphs / Bigraphical Reactive Systems

**Primary sources**

- [Bigraphical reactive systems: basic theory](https://www.cl.cam.ac.uk/techreports/UCAM-CL-TR-523.html)
- [Bigraphs and mobile processes (revised)](https://www.cl.cam.ac.uk/techreports/UCAM-CL-TR-580.html)
- [The Space and Motion of Communicating Agents](https://www.cambridge.org/core/books/space-and-motion-of-communicating-agents/267A0C3F2DB68EF43E7158DB5A7016C3)

**Core idea**

Bigraphs separate two dimensions of a system:

- **place / locality** — where components are nested or located;
- **link / connectivity** — how components communicate or relate.

Bigraphical Reactive Systems add rules for how those structures can change.

**Why this matters to AIP**

AIP may eventually need to distinguish cleanly between:

```text
WHERE something is
        ≠
HOW it interacts
```

For example, a service may be deployed in a namespace while simultaneously calling another service. This becomes increasingly relevant when AIP adds Kubernetes and other infrastructure sources. Bigraphs are also interesting for later work on architecture evolution, reconfiguration, mobility, and transformation.

**AIP stance**

Research input only. There is no reason to replace AIP's current Canonical Model with a bigraph formalism unless a concrete modeling problem justifies it.

### Mark Burgess — Promise Theory

**Primary sources**

- [Promise Theory](https://markburgess.org/promises.html)
- [Promise Theory FAQ](https://markburgess.org/promiseFAQ.html)

**Core idea**

Promise Theory models systems as autonomous agents and the promises they make about their own behavior and cooperation. It provides a language for relating **intent** to **outcome** without assuming centralized control.

**Why this matters to AIP**

Promise Theory may provide useful conceptual foundations for the future distinction between:

```text
INTENT
   ≠
DECLARED
   ≠
OBSERVED
```

A declaration says something was specified. Runtime evidence says something happened. Architectural intent expresses what agents or components are expected or permitted to do.

A Promise is not simply an ADR. ADRs, constraints, and policies are organizational artifacts; Promise Theory is a more general model of autonomous cooperation.

### Jeff Sussna — Designing Delivery / Promise Thinking

**Primary source**

- Jeff Sussna, *Designing Delivery: Rethinking IT in the Digital Service Economy* (O'Reilly, 2015), especially Chapter 11, "Service as a Chain of Promises," and Chapter 14, "Thinking in Promises"

**Core idea**

Sussna applies Promise Theory to complex digital service systems. He frames services as chains of
promises among autonomous participants and treats continuous quality as an ongoing process of
feedback, learning, promise keeping, and repair rather than centralized command and control.

A particularly relevant distinction for AIP is:

```text
explicit promise / intent
        ≠
established cooperation
        ≠
assessment of their relationship
```

Sussna also treats questioning as primary: maps, blueprints, and other representations are valuable
because they support continuous inquiry and adaptation, not because the artifact becomes operational
truth.

**Why this matters to AIP**

This reinforces AIP's independent semantic paths:

```text
Current-State evidence
        ↓
Evidence-Qualified Current State

Explicit attributable Intent / promises
        ↓
Applicable Intent

Current State + Intent
        ↓
Qualified Current ↔ Intent Assessment
```

It also supports **Moldable Architecture Knowledge**: recurring architecture questions can be exposed
through bounded, question-specific projections without making the underlying evidence, qualification,
provenance, or claim meaning consumer-moldable.

Sussna's "chain of promises" suggests a potentially useful future projection over explicit Intent
assertions and their dependencies. AIP must remain stricter than the design metaphor, however:
an OpenAPI operation, runtime interaction, or technical dependency does not by itself establish that
one component promised something to another.

**AIP stance**

Semantic and design foundation, not a product competitor or implementation model. AIP should preserve
the useful Promise-Theory distinctions around autonomy, relationships, feedback, and explicit
promises while adding its own evidence applicability, identity reconciliation, qualification,
provenance, bounded uncertainty, locality, and deterministic projection semantics.

This reference does not add roadmap scope. Promise-chain projections are a research direction unless
a concrete architecture-question class justifies them.

### Mark Burgess — Semantic Spacetime

**Primary sources**

- [Semantic Spacetimes](https://markburgess.org/spacetime.html)
- [Spacetimes with Semantics (I)](https://arxiv.org/abs/1411.5563)
- [Spacetimes with Semantics (II)](https://arxiv.org/abs/1505.01716)
- [Spacetimes with Semantics (III)](https://arxiv.org/abs/1608.02193)

**Core idea**

Semantic Spacetime treats systems as evolving discrete graphs whose topology, dynamics, semantics, locality, and observer perspective are related rather than treated as separate afterthoughts.

**Why this matters to AIP**

This is close to several long-term AIP questions around incomplete information, observation context, identity, locality, provenance, and architecture over time.

```text
Architecture(t0)
      ↓
evidence / change
      ↓
Architecture(t1)
      ↓
evidence / change
      ↓
Architecture(t2)
```

This is a natural theoretical reference for future **Architecture Trajectories**, but not a reason to expand v0.4 scope.

### Mark Burgess — SSTorytime and Context Investment

**Sources**

- [SSTorytime](https://github.com/markburgess/SSTorytime)
- [Describe the Scene! The Investment in Context](https://mark-burgess-oslo-mb.medium.com/describe-the-scene-the-investment-in-context-776c6a3d9125)

**Core idea**

SSTorytime is a concrete knowledge-graph implementation based on Semantic Spacetime. Burgess argues
that useful knowledge capture begins with describing events and their context, then progressively
organizing those descriptions rather than fixing a complete ontology in advance. SSTorytime groups
relations into four broad semantic families: `LEADSTO`, `CONTAINS`, `EXPRESSES-PROPERTY`, and
`SIMILARTO`.

**Why this matters to AIP**

The approach sharpens why an architectural edge is not meaningful without its frame:

```text
subject + relation + object
        +
source + time + scope + observer + intent
        ↓
interpretable architectural assertion
```

It also supports AIP's separation between retained source evidence and a projection that may be
recomputed as qualification rules or context change. A note or interpretation may evolve without
rewriting the evidence from which it was derived.

**AIP distinction**

AIP cannot defer all relation semantics until later. Public architecture answers require stable,
qualified meanings. Kubernetes selection, an observed OpenTelemetry call, an OpenAPI operation, and
an ADR constraint must not collapse into an undifferentiated `A -> B`.

SSTorytime is therefore most useful as an interoperability and contextual-projection reference, not
as a replacement for AIP's Canonical Model or as additional v0.5 scope.

### Domain-Driven Design — Strategic Patterns

**Primary sources**

- [Eric Evans — Domain-Driven Design](https://www.domainlanguage.com/ddd/)
- [Martin Fowler — Bounded Context](https://martinfowler.com/bliki/BoundedContext.html)
- [Context Mapper — Strategic DDD](https://contextmapper.org/docs/strategic-ddd/)

**Core idea**

Strategic Domain-Driven Design treats semantic boundaries as first-class design decisions. Important patterns include:

- **Bounded Context** — the boundary within which a domain model and its language have a specific, consistent meaning;
- **Context Map** — explicit relationships and integration patterns between Bounded Contexts;
- **Core / Supporting / Generic Subdomains** — strategic classification of domain areas;
- relationship patterns such as **Partnership**, **Shared Kernel**, **Customer/Supplier**, **Conformist**, **Anti-Corruption Layer**, **Open Host Service**, and **Published Language**.

**Why this matters to AIP**

Technical connectivity alone does not tell us where semantic boundaries should be:

```text
TECHNICAL RELATIONSHIP
Service A ──calls──> Service B

        ≠

SEMANTIC / DOMAIN BOUNDARY
Context A ──relationship──> Context B
```

AIP should not silently equate a service, Bounded Context, deployment unit, or team boundary. They may align, but that alignment is itself an architectural claim requiring evidence or explicit intent.

Strategic DDD can therefore inform a future split between evidence-backed Current State and explicit architectural intent, without treating domain design artifacts as proof of runtime behavior.

---

### OMG — SysML v2

**Sources**

- [OMG Systems Modeling Language](https://www.omg.org/sysml/)
- [SysML v2 release repository](https://github.com/Systems-Modeling/SysML-v2-Release)

**Core idea**

SysML v2 is a standardized language and API for specifying, analyzing, designing, and verifying
complex systems. Its textual notation, explicit semantics, relationships, requirements, constraints,
and verification concepts make it a plausible machine-readable source of architectural intent.

**Why this matters to AIP**

SysML v2 could eventually provide explicit intent evidence against which qualified Current State is
assessed. It complements rather than replaces Promise Theory:

```text
SysML v2
explicit model / requirement / constraint
        ↓
versioned intent evidence

Promise Theory
local promises by autonomous agents
        ↓
reasoning model for intended cooperation
```

A SysML model is not automatically authoritative, applicable, current, or satisfied. AIP would still
need provenance, model and element identity, version, scope, authority, applicability, and explicit
mapping into its Intent Model. Runtime evidence remains separate.

**AIP stance**

Research input for the post-Current-State Intent line. SysML v2 is not a v0.5 discovery source and
its presence in the landscape does not commit AIP to general-purpose MBSE support.

## 2. Evidence and Current State

### OpenTelemetry Semantic Conventions

**Sources**

- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
- [Messaging Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/messaging/)

**Why this matters to AIP**

OpenTelemetry is a primary source of **observed evidence**. Its semantic conventions define the meaning AIP can safely attach to runtime spans, resources, operations, messaging destinations, RPCs, databases, and related signals.

AIP must not silently assign stronger architectural meaning than the telemetry semantics support.

```text
Weak or ambiguous telemetry
        ↓
qualified / unresolved result

not

weak telemetry
        ↓
plausible-looking architecture fact
```

### Kin Lane — OpenAPI as a Deterministic Artifact in an AI-Generated World

**Sources**

- [Is OpenAPI Still Relevant When You Tell Claude "Make Me an API"?](https://apievangelist.com/2026/09/15/is-openapi-still-relevant-when-you-tell-claude-make-me-an-api/)
- [OpenAPI Overlay Specification](https://spec.openapis.org/overlay/latest.html)

**Core idea**

AI may generate an API, but its durable contract should land as an independently owned,
machine-readable artifact. OpenAPI, AsyncAPI, JSON Schema, Arazzo, overlays, and deterministic
rules can then be versioned, diffed, validated, governed, and consumed without repeatedly asking a
model to reconstruct the contract.

**Why this matters to AIP**

This reinforces the role of OpenAPI and AsyncAPI as declared evidence:

```text
probabilistic generation
        ↓
versioned deterministic contract
        ↓
AIP ingestion
        ↓
declared architecture claim
```

The deterministic artifact stabilizes what was declared; it does not establish that the deployed
system implements the contract or that the interaction occurred. AIP must continue to distinguish
declared, configured, and observed evidence and surface conflicts rather than selecting a winner
silently.

> **AI generation increases the value of durable contracts; it does not turn contracts into
> runtime truth.**

OpenAPI Overlay is relevant because it can keep policy, enrichment, or consumer-specific metadata
separate from the base description. A future AIP importer would need to retain the base document and
each overlay as independently identifiable sources, record their digests and application order, and
make failed targets or conflicting changes explicit. The effective overlaid document would still be
declared evidence, not observed behavior or automatically authoritative intent.

### adorsys — Understanding API Landscapes, Not Just Managing Them

**Sources**

- [Understanding API Landscapes, Not Just Managing Them](https://adorsys.com/en/techradar/understanding-api-landscapes-not-just-managing-them/)
- [The API Is Not the Boundary](https://adorsys.com/en/techradar/the-api-is-not-the-boundary/)

**Core idea**

An increasingly heterogeneous API landscape cannot be understood solely through the operational
views of individual API platforms. Contracts, exposure, consumers, actual usage, ownership, and
dependencies need traceable cross-source relationships. A graph-based knowledge layer is one
possible technical implementation; the enduring architectural value lies in the model and the
meaning of its relationships, not the database or its visualization.

**Why this matters to AIP**

This is external support for the already planned **v0.7 — API-Aware Current State**, not a new
roadmap proposal. AIP's bounded question is: *How are APIs exposed and consumed, and what can the
available evidence establish about those relationships?* Its first validation correlates configured
consumer/API access with independently observed consumer-attributed usage in an explicit context.

The source-neutral model must distinguish contract/version, operation, gateway route/service,
application service, consumer, configured access, and observed interaction. Identifying that
artifacts are related does not establish that they are the same entity. Cross-source transformations
must retain the claim kind, provenance, applicability, qualification, and any lost or unresolved
semantics. In particular:

```text
configured API access != observed API usage
API endpoint != application, domain, business, or authorization boundary
connected graph != evidence-qualified architectural answer
```

**AIP stance and roadmap effect**

This strengthens the rationale and validation criteria for the existing v0.7 slice; it does not
warrant a new release, a comprehensive API inventory, automatic ownership/capability inference, or
gateway-specific canonical terminology. Explicit architectural Intent remains independently
established in v0.8 and Current↔Intent assessment in v0.9. The research source is not semantic
authority for AIP; qualification against real, independently authored evidence is still required.

### Structurizr/C4 — Declared Architecture Models and Views

**Sources**

- [C4 model](https://c4model.com/)
- [Structurizr DSL](https://docs.structurizr.com/dsl)

**Core idea**

The C4 model describes software at several structural levels, while Structurizr provides a
model-as-code representation and derives multiple views from a shared model. This makes the
underlying elements and relationships more useful to AIP than rendered diagrams alone.

**Why this matters to AIP**

A Structurizr workspace could become a future declared architecture source, provided that AIP keeps
three distinctions explicit:

```text
authored model relationship  != observed interaction
diagram membership           != system membership
C4 identifier                != AIP identity without a qualified mapping
```

A relationship omitted from a view may still exist in the model, so view omission cannot establish
absence. Conversely, an authored relationship is evidence of what the model declares, not proof that
the deployed system behaves that way.

This is a source-adapter research candidate, not a v0.5 commitment.

### ArchUnit and jQAssistant — Executable Architecture Rules

**Sources**

- [ArchUnit](https://www.archunit.org/)
- [jQAssistant](https://github.com/jqassistant)

**Core idea**

ArchUnit evaluates architecture and coding rules against Java bytecode. jQAssistant scans software
artifacts into a graph and evaluates project-specific concepts and constraints over that graph. Both
turn selected architecture expectations into repeatable checks close to the implementation.

**Why this matters to AIP**

These tools expose three artifacts that AIP must not collapse:

```text
rule or constraint       = explicit intent
scanned code structure   = implementation evidence
rule evaluation result   = scope-bound assessment
```

A violation may provide strong evidence of drift from a stated rule. A passing check proves only
that the encoded rule held for the scanned scope and tool version; it does not establish global
architectural correctness.

They are useful references for future fitness criteria and code-discovery adapters, while their
language-specific findings remain outside v0.5.

### Backstage Software Catalog

**Sources**

- [Backstage Software Catalog](https://backstage.io/docs/features/software-catalog/)
- [Creating the Catalog Graph](https://backstage.io/docs/features/software-catalog/creating-the-catalog-graph/)

**Why this matters to AIP**

Backstage represents components, APIs, ownership, resources, and relationships in a developer-facing catalog. It is a natural integration point and an important comparison for what an architecture graph is — and is not.

```text
Backstage
human-maintained / catalog-oriented system knowledge

AIP
evidence-backed, qualified architecture knowledge
derived from declared and observed signals
```

### Cartography — Infrastructure and Security Graph Discovery

**Sources**

- [Cartography](https://github.com/cartography-cncf/cartography)
- [Kubernetes module](https://github.com/cartography-cncf/cartography/tree/master/docs/root/modules/kubernetes)

**Core idea**

Cartography ingests infrastructure assets and their relationships from Kubernetes, cloud platforms,
identity systems, source-control systems, and other operational sources into Neo4j. Its graph is
primarily designed for infrastructure inventory, security analysis, exposure paths, and
cross-provider queries.

Its Kubernetes ingestion is especially relevant to AIP v0.5. It models clusters, namespaces,
workload controllers, pods, services, ingress, storage, RBAC, and related infrastructure. It also
resolves controller ownership such as `Pod -> ReplicaSet -> Deployment` and protects previously
ingested state when a required discovery scope cannot be completed.

**Why this matters to AIP**

Cartography is a strong reference implementation for source adapters, Kubernetes discovery,
cross-provider graph modeling, and failure-aware reconciliation:

```text
Cartography
live infrastructure APIs
        ↓
asset and security graph
        ↓
inventory / path / exposure queries

AIP
source-bound observations
        ↓
typed evidence and claims
        ↓
qualification
        ↓
snapshot-bound architecture context
```

The overlap is strongest in discovery mechanics, not in epistemic semantics. A directly ingested
asset or relationship is not automatically a qualified AIP architecture claim. In particular, AIP
must not infer that a Kubernetes workload is an application service, that a selector establishes a
service dependency, or that co-location establishes communication.

Cartography's handling of incomplete discovery is a useful design comparison: failed or
unauthorized collection can preserve the last committed graph rather than treating missing results
as confirmed removal. AIP requires the stronger, source-explicit form of this rule through
successful-scope markers or tombstones, stable source identity, evidence continuity, and
deterministic reconciliation.

**AIP stance**

Use Cartography as a comparison implementation and possible future source-adapter boundary, not as
a dependency or authority for v0.5 semantics. A future adapter could import Cartography output as
source-bound evidence, but would still require separately approved mappings and deterministic
conformance tests before any relation entered an AIP Current-State projection.

### EventCatalog — Connected Architecture Catalog for Humans and Agents

**Sources**

- [EventCatalog](https://www.eventcatalog.dev/)
- [EventCatalog on GitHub](https://github.com/event-catalog/eventcatalog)

**Core idea**

EventCatalog exposes a broad, connected catalog of services, domains, events, schemas, and their
relationships for people, tools, and agents. Its scope includes more architectural and
organizational concepts than AIP currently models, making it an important product and positioning
reference.

**Why this matters to AIP**

```text
EventCatalog
source / catalog entry
      ↓
connected architecture catalog
      ↓
visualization / search / impact / agent access

AIP
source
      ↓
typed evidence
      ↓
canonical architecture fact
      ↓
qualification
      ↓
snapshot-bound architecture claim
      ↓
agent access
```

AIP should remain narrower where catalog breadth would blur its evidence and qualification
boundary. Integration may be more valuable than duplicating catalog capabilities.

> **EventCatalog makes architecture connected and queryable. AIP makes architecture claims
> evidence-qualified and independently inspectable.**

### Bipul Sinha — Components Describe a System. Relationships Reveal Its Architecture

**Source**

- [Bipul Sinha — LinkedIn](https://www.linkedin.com/in/sinhabipul/), article published
  2026-09-19

**Core idea**

Sinha argues that architecture understanding comes from contextualized relationships rather than
component inventories alone. He separates static evidence from runtime observation, observed facts
from architectural interpretation, deterministic discovery from AI-assisted interpretation, and
identifies architecture entity resolution as a distinct problem.

**Why this matters to AIP**

This is strong independent convergence with several AIP concerns:

- heterogeneous evidence has different semantics;
- runtime observation and static/declarative evidence must not be collapsed;
- identity reconciliation is required before architectural reasoning is reliable;
- deterministic software should answer deterministic graph questions before an LLM is asked to
  interpret them;
- evidence should remain visible behind architectural relationships.

**AIP distinction**

AIP makes the knowledge-establishment boundary stricter through evidence applicability, exact
identity/reconciliation, qualification, provenance, bounded uncertainty, snapshot context, and
Current-State/Intent separation. An "Architecture Knowledge Graph" is therefore a possible
representation, not AIP's durable semantic contract.

This is landscape validation, not additional roadmap scope.

### SDLC Playbook — Documentation Decay and Evidence-Derived Architecture Views

**Source**

- [Documentation Decay](https://sdlcplaybook.com/resources/documentation-decay/)

**Core idea**

SDLC Playbook argues that documentation decays when updating it is a separate remembered task.
Release notes, runbooks, and architecture views should instead be derived from evidence produced by
the delivery process and running system. Design-phase architecture still has value, but as explicit
intent alongside a view of current reality.

**Why this matters to AIP**

This strongly supports treating architecture views as projections rather than primary truth and
reinforces AIP's separation between evidence-qualified Current State and explicit attributable
Intent.

**AIP distinction**

"Generated from the source of truth" is not sufficient for AIP because architecture rarely has one
source of truth. Code, APIs, deployment state, telemetry, and intent artifacts establish different
kinds of claims. A generated view is trustworthy only to the extent that its source semantics,
applicability, reconciliation, qualification, provenance, and limitations are preserved.

### MobiLab Axium — Semantic AI and Architecture Intelligence

**Sources**

- [Axium](https://mobilabsolutions.com/axium/)
- [Energy: Connected Architecture Intelligence with Axium](https://mobilabsolutions.com/portfolio/energy-connected-architecture-intelligence-with-axium/)

**Core idea**

Axium provides a model-first semantic layer over heterogeneous enterprise data using ontologies and
knowledge graphs, with conversational exploration, generated APIs, source-linked answers, portable
semantic representations, and MCP access. Its architecture-intelligence use case connects
application portfolios, capabilities, interfaces, ownership, lifecycle, SLA, and other enterprise
context.

**Why this matters to AIP**

Axium is useful external evidence that "Architecture Intelligence" is becoming a product category
and that machine-consumable semantic architecture knowledge is valuable to both humans and agents.
Its storage-independent semantic positioning also supports AIP's rule that public architectural
meaning must not depend on the internal graph/database representation.

**AIP distinction**

Axium is primarily model-first: enterprise knowledge is unified under an authored semantic model.
AIP is evidence-first: it establishes what technical architecture claims heterogeneous evidence can
support. Source linkage provides traceability; it does not by itself qualify what a source is
allowed to mean.

### Sathish Siva Shankar — ArchSmith and Intent-First Semantic Architecture Intelligence

**Source**

- [Sathish Siva Shankar — LinkedIn](https://www.linkedin.com/in/sathish-siva-shankar-32018648/)

**Core idea**

ArchSmith normalizes requirements into explicit semantic architecture objects before generation:

```text
requirements
    ↓
capabilities
    ↓
services / APIs / events
    ↓
C4 / OpenAPI / AsyncAPI / Terraform / ADR / arc42
    ↓
impact analysis + governance + version history
```

The intent is to keep one semantic thread through architecture design and delivery rather than
producing disconnected AI-generated artifacts.

**Why this matters to AIP**

ArchSmith strongly overlaps with AIP's rejection of "prompt in, blob out" architecture and its
preference for explicit machine-readable semantics. Its generated artifacts could also become
attributable Intent or declaration inputs to a future AIP adapter boundary.

**AIP distinction**

The systems run in opposite epistemic directions:

```text
ArchSmith
intent → semantic design → generated delivery artifacts

AIP
technical evidence → applicability/reconciliation/qualification → Current-State knowledge
```

AIP should keep those layers connected but distinct. An approved or generated OpenAPI, ADR,
Terraform, or C4 artifact may establish attributable intent or declaration; it does not prove that
the running system behaves accordingly. This is a landscape/interoperability reference, not a
roadmap commitment.

### ProvenMap — Architecture Intelligence, Intent, and Provenance

**Sources**

- [Why Architecture Intelligence, Not Visualization](https://provenmap.com/blog/why-architecture-intelligence-not-visualization)
- [ProvenMap](https://provenmap.com/)
- [ProvenMap Documentation](https://provenmap.com/docs)
- [ProvenMap Intents](https://provenmap.com/docs/platform-features/intents)

**Core idea**

ProvenMap positions itself as an Architecture Intelligence platform rather than a diagramming tool.
Its sources populate an architecture model with provenance-carrying relationships, while
**Intents** act as living specifications of desired change anchored to existing architecture and
capable of returning verified rather than merely reported.

**Why this matters to AIP**

ProvenMap is currently AIP's closest strategic product neighbor:

```text
ProvenMap
sources → architecture model → IS / OUGHT → intent → verification

AIP
evidence → qualified Current State → Architecture Intelligence → trusted context for agents
```

Its proximity sharpens two related but distinct questions:

```text
Provenance
  where did this claim come from?

Qualification
  what does that evidence actually entitle us to claim?
```

AIP should retain both. Future derivation lineage should make reproducible how evidence, mapping
rules, applicability, observation context, and qualification combined to produce a claim.
`IS vs. OUGHT` also provides a useful comparison for AIP's future Current-State-to-Intent split,
while `Finding → Intent → implementation → verification` is a plausible reference for future
Transformation Lineage.

**AIP distinction**

Provenance does not by itself determine what a source legitimately establishes. AIP binds its
qualified answers to an observation context and snapshot and preserves unsupported or inconclusive
outcomes rather than promoting provenance-carrying data directly into authoritative architecture
knowledge.

> **Provenance tells you where a claim came from. Qualification tells you what that evidence is
> allowed to mean.**

### Logorythm — Architecture Intelligence from Static Analysis

**Source**

- [Logorythm](https://logorythm.io/en)

**Core idea**

Logorythm builds service maps from repositories using static analysis, with an explicit emphasis on discovering service dependencies without tracing, runtime instrumentation, or manual cross-repository investigation. This can reveal code paths that a runtime observation window has not exercised.

**Why this matters to AIP**

Logorythm is close to AIP's architecture-intelligence problem, but approaches evidence from the code side:

```text
Logorythm
code / static analysis
        ↓
service map + structural risk

AIP
declared evidence + observed evidence
        ↓
qualified architecture facts
```

The distinction is useful rather than competitive by definition. Static code evidence can answer what a system **can declare or encode as a dependency**; runtime evidence can answer what was **observed in a bounded context**. AIP's role is to preserve that distinction and qualify the resulting architectural claim rather than collapse the two into one notion of truth.

Logorythm is therefore a relevant reference for future code-discovery work, dependency extraction, structural-risk analysis, and possible adapter boundaries. It does not by itself change AIP's evidence or roadmap semantics.

### Praveen Kasam — Why Your AI Agent Fails: The Answer Is Almost Never the Model

**Source**

- [Why Your AI Agent Fails: The Answer Is Almost Never the Model](https://www.linkedin.com/pulse/why-your-ai-agent-fails-answer-almost-never-model-praveen-kasam-goaef/)

**Core idea**

Kasam argues that most agent failures trace back to the knowledge the agent reasoned over — stale, ambiguous, or incomplete premises — rather than to model capability. Reasoning quality cannot exceed the quality of what it reasons about.

**Why this matters to AIP**

This is a direct statement of AIP's founding assumption, seen from the agent-consumption side rather than the architecture side:

```text
Weak, stale, or ambiguous premise
      ↓
confident-looking but wrong conclusion

regardless of model capability
```

AIP's provenance and freshness guarantees — `source_revision`, `evidence_type`, per-service atomic reimport (no partial import ever left in the graph) — exist to keep the premises an agent reasons over evidence-backed and current, rather than merely plausible-looking. This reinforces why AIP treats provenance and qualification as architecture, not as an optional annotation.

### Spark Tsai — From Trace IDs to Trace Matrix: What Does a Change Actually Affect?

**Source**

- [From Trace IDs to Trace Matrix: What Does a Change Actually Affect?](https://www.linkedin.com/pulse/from-trace-ids-matrix-what-does-change-actually-affect-spark-tsai-u1rzc/)

**Core idea**

Tsai argues that answering "what does this change actually affect" well requires typed, structured relationships between artifacts — a trace matrix — rather than untyped trace IDs pointing at commits or tickets. Known, typed relationships let impact analysis run deterministically instead of being re-derived by an LLM each time it's asked.

**Why this matters to AIP**

```text
Known typed relationship (graph edge)
      ↓
deterministic traversal
      ↓
impact analysis

untyped reference
      ↓
LLM re-inference of the relationship, each time it's asked
      ↓
inconsistent / non-reproducible impact analysis
```

This mirrors AIP's own `PROVIDES` / `CALLS` / `SENDS` / `RECEIVES_FROM` model and the A5 blast-radius analysis: relationships are declared once, from evidence, and traversed deterministically rather than re-inferred by an LLM per question. It is also a plausible reference point for a future Intent / Transformation layer (Section 4): typed relationships between decisions and implementation would need the same discipline AIP already applies to typed relationships between services.

---

## 3. Agent context and machine consumption

### Cochran et al. — When Coding Is Free, Where Is the Bottleneck?

**Source**

- Timothy Cochran, Bryan Finster, Tim Ottersburg, Scott Prugh, and Amy Willard,
  *When Coding Is Free, Where Is the Bottleneck? A Guide for Leaders Building Agent-Ready
  Delivery Systems*, IT Revolution, *Enterprise Technology Leadership Journal*, Fall 2026.

**Core idea**

Accelerated code generation does not necessarily accelerate delivery when work still waits for
clarification, expertise, environments, approvals, or evidence. The paper describes three costs of
coordination—contention, coupling, and coherence—and five AI enablement properties: knowledge,
capability, capacity, parallelism, and optionality. Its example in which active coding represents
roughly 12% of lead time is illustrative, not a general measurement. Its *fractured modularity*
discussion shows why cross-team work sometimes reflects poorly aligned boundaries, but a dependency
graph alone does not establish such a diagnosis.

**Why this matters to AIP**

AIP's evidence-qualified architecture answers can reduce repeated investigation and dependence on
the person who knows how a service or landscape works. This supports a workflow-value measure in
addition to semantic correctness: how much time and expert coordination does a bounded, inspectable
architecture answer save a developer or coding agent?

**AIP stance**

AIP addresses one part of knowledge/coherence friction, not all delivery coordination. It is not a
process-mining, value-stream, organizational-design, or delivery orchestration platform. This is an
external validation input for the existing product proposition, not a new roadmap commitment.

### Cockcroft et al. — When Agents Decide

**Source**

- Adrian Cockcroft, Jeremy Eder, Joseph Enochs, Jenn Spykerman, and Brian Wald,
  *When Agents Decide: Continuous Decision Intelligence and the Substrate Beneath It*,
  IT Revolution, *Enterprise Technology Leadership Journal*, Fall 2026.

**Core idea**

Continuous Decision Intelligence combines evaluation, decision tracking, and policy enforcement.
The proposed decision substrate consists of **decision topology** (which decisions happen where
and under whose authority), **provenance** (which sources shaped a decision), and **governance**
(constraints before action and accountability afterward). The paper explores persistent context
outside ephemeral model sessions and a Context Bill of Materials (CxBOM) for decision traceability.

**Why this matters to AIP**

AIP can supply an independently qualified part of a downstream agent's decision context: bounded
Architecture Knowledge with claim semantics, snapshot/observation context, evidence references,
provenance, and explicit limitations. A future decision record could reference those identities
without treating a model's recall as architectural evidence. That is a prospective integration,
not a claim that AIP implements CDI or emits a CxBOM today.

Decision topology is not technical architecture topology: knowledge of a service dependency does
not establish who may approve or execute a change affecting it. Decision provenance does not
automatically make the decision or its inputs authoritative Architecture Knowledge.

**AIP stance**

External systems own agent evaluation, decision routing, organizational policy, approval,
execution, and decision records. AIP remains read-only and advisory. The paper supports existing
v0.8 Intent and v0.9 Assessment boundaries and the unscheduled Decision History linkage candidate,
without adding a pre-v1.0 capability or release gate.

### Michael Smith — Line of Sight: AI and Architecture

**Source**

- [Michael Smith — LinkedIn](https://www.linkedin.com/in/michael-smith-82358287/), *Line of Sight
  AI + Architecture* (2026)

**Core idea**

Smith argues that as AI makes production and documentation cheaper, architectural value shifts
toward briefing, evaluation, judgment, checking, and professional authentication. He also describes
"architectural thinking" becoming increasingly executable as domain experts can use AI to turn
structured intent into tools and workflows.

**Why this matters to AIP**

The analogy sharpens the consumer-side boundary around AIP:

```text
AIP
establishes what architecture evidence supports

agent
reason / explore / propose

human
judge / accept / change intent
```

As implementation velocity increases, trustworthy machine-readable architecture context becomes
more valuable because human reconstruction and review do not scale at the same rate.

**AIP distinction**

This is a cross-domain conceptual reference rather than a software-architecture implementation
model. AIP does not automate professional judgment or decision authority; it supplies bounded,
evidence-qualified premises on which humans and agents can reason.

### Moldable Development / Glamorous Toolkit / Rewilding Software Engineering

**Sources**

- [Moldable Development](https://moldabledevelopment.com/)
- [Glamorous Toolkit](https://gtoolkit.com/)
- [Glamorous Toolkit Book — What is Glamorous Toolkit?](https://book.gtoolkit.com/what-is-glamorous-toolkit--2tbpqa98apus4jnjk6bt9r8k8)
- [Rewilding Software Engineering — Chapter 1](https://medium.com/feenk/rewilding-software-engineering-25ba0e141e69)
- [Rewilding Software Engineering — Chapter 3: Questions and answers](https://medium.com/feenk/rewilding-software-engineering-f758ec97ddb2)
- [Rewilding Software Engineering — Chapter 6: Myths we tell ourselves](https://medium.com/feenk/rewilding-software-engineering-ca3ad1e612d8)
- [Glamorous Toolkit source](https://github.com/feenkcom/gtoolkit)

**Core idea**

Moldable Development treats software understanding as an active engineering activity. Instead of
depending on a fixed set of generic tools, developers create inexpensive **contextual micro-tools**
that answer a specific question about a specific system. Glamorous Toolkit (GT) is the environment
built around that methodology.

The important unit is therefore not a generic browser or diagram. It is:

```text
question about this system
        ↓
purpose-built deterministic analysis
        ↓
contextual representation
        ↓
understanding / decision
        ↓
next question
```

*Rewilding Software Engineering* makes the connection to AI especially concrete. Chapter 6 reports
an experiment in which direct LLM answers to a dependency question looked impressive but missed a
material fraction of the real dependencies across runs. Asking the model to construct a
deterministic tool for the question changes the epistemic shape of the task: the model may help
create the tool, but the answer comes from executable analysis of the system rather than from the
model's reconstruction.

This yields a principle that is directly relevant to AIP:

> **When an architecture question can be answered deterministically, capture the answer mechanism
> as a reusable tool instead of repeatedly asking an agent to infer the answer.**

#### Moldable Architecture Knowledge

AIP can generalize this idea from software reading to architecture knowledge.

```text
raw repositories / APIs / manifests / telemetry / configuration
                         ↓
                 source-specific evidence
                         ↓
          reconciliation + qualification
                         ↓
                Architecture Knowledge
                         ↓
            question-specific projection
                         ↓
         contextual architecture micro-tool
                         ↓
                 human / AI agent
```

What is molded is the **question-specific projection and representation of Architecture
Knowledge**, not the underlying evidence, qualification, provenance, or claim meaning. A dependency
view, deployment-identity view, evidence drill-down, unresolved-identity view, locality view, future
Intent assessment, or change-impact view can each be a different bounded projection over the same
underlying evidence-qualified knowledge.

Examples include:

```text
Which services does this service depend on?
Why does AIP believe this relation exists?
Which evidence conflicts with this claim?
Where is this service deployed?
Which deployment identities remain unresolved?
What changed between two qualified snapshots?
Which architectural constraints apply to this proposed change?
```

Each question may require a different projection, but the projection must preserve the guarantees of
the underlying knowledge.

#### What AIP adds

Moldable Development and AIP address different layers.

```text
Moldable Development
system-specific question
        ↓
contextual deterministic tool
        ↓
explainable system understanding

AIP
heterogeneous architecture evidence
        ↓
qualified Architecture Knowledge
        ↓
contextual deterministic architecture tool
        ↓
explainable architecture understanding for humans and agents
```

AIP therefore adds requirements that a generic contextual tool does not necessarily provide:

- **source semantics** — Kubernetes selection, OpenTelemetry communication, OpenAPI declaration,
  configuration, and future Intent remain distinct;
- **evidence and provenance** — every supported claim remains traceable to the evidence that
  supports it;
- **qualification** — unresolved, conflicting, insufficient, and unsupported outcomes remain
  explicit;
- **snapshot and observation context** — the answer states which qualified system state and time
  context it belongs to;
- **determinism** — equivalent qualified inputs produce equivalent supported answers;
- **bounded public contracts** — agent-facing tools expose a deliberately small semantic surface
  rather than arbitrary graph access;
- **epistemic separation** — an LLM can formulate questions, compose tools, and interpret results,
  but it does not become the source of Architecture Knowledge.

This is especially relevant to AIP's MCP direction. The goal should not be to expose the entire
architecture graph and rely on the agent to reconstruct meaning. Instead, AIP can expose a growing
set of small, deterministic, evidence-qualified architecture questions whose results are directly
inspectable and reusable.

```text
more architecture data
        ≠
better agent context

the right deterministic projection
of qualified Architecture Knowledge
        ↓
better bounded context
```

#### Agent-ready API products as a moldable-view example

Recent work on agent-ready API products provides a concrete example of why Architecture Knowledge
should not be flattened into one large context representation. Discovery metadata, agent guidance,
executable contracts, workflows, runtime affordances, observed behavior, deployment evidence, and
authorization each answer different questions and may carry different authority.

Conceptually, a consumer exploring one API product or architecture component may need several
question-specific views:

```text
API product / architecture component
        ├── capability / intent view
        ├── executable-contract view
        ├── workflow view
        ├── runtime-evidence view
        ├── deployment view
        └── provenance / conflict / limitation view
```

This is a natural fit for Moldable Architecture Knowledge. Glamorous Toolkit can make these
responsibilities inspectable through different contextual views rather than forcing them into one
agent-context blob. AIP still owns only the architecture knowledge it can establish and qualify;
moldability changes the question and representation, not the semantic role or authority of the
underlying source.

This is a design connection, not a claim that the current AIP × GT reference integration ingests
`apis.json`, `AGENTS.md`, Arazzo, hypermedia, or policy artifacts.

#### Relationship to the validated AIP × GT reference integration

The [AIP × Glamorous Toolkit reference integration](reference-integrations/glamorous-toolkit/README.md)
has now exercised this idea across both moldable inspection and agentic use.

The validated flow is:

```text
architecture question
        ↓
GT-hosted agent chooses AIP capability
        ↓
AIP negotiated MCP
        ↓
evidence-qualified, snapshot-bound Architecture Knowledge
        ↓
agent follows provenance / composes a sharper question
        ↓
GT renders a bounded ephemeral micro-tool
        ↓
developer decides whether the idea becomes permanent
```

PoC 3 validated agent-selected tool use and multi-step evidence chaining. PoC 4 validated bounded
agent-derived micro-tools whose snapshot, tool, and claim lineage remain explicit. The agent proposes
the lens; AIP remains the Architecture Knowledge authority; the developer controls permanence.

The important result is therefore not a GT visualization and not an MCP transport trick. It is the
feedback loop:

```text
qualified AIP answer
        ↓
agent/human discovers a sharper recurring question
        ↓
bounded deterministic projection / micro-tool
        ↓
inspection and reuse
        ↓
optional human-controlled promotion
```

This gives Moldable Architecture Knowledge a concrete agentic meaning: an agent may mold **how
qualified knowledge is questioned and inspected** without molding the underlying evidence or
qualification.

#### AIP stance

The existing reference integration (including negotiated MCP, snapshot-bound evidence drill-down,
GT-hosted agent exploration, and bounded ephemeral micro-tools) is supporting validation of the
consumer boundary, not a reason to add GT as an AIP dependency. An API exposure/consumption view
would be another question-specific view over AIP knowledge, not a separate source of truth.

**Moldable Architecture Knowledge is now a core AIP product concept.** Glamorous Toolkit remains a
reference integration and design influence, not AIP's implementation platform and not a reason to
expand a release's semantic scope.

The product implication is:

> **AIP should make Architecture Knowledge moldable: small, question-specific, deterministic,
> evidence-qualified projections should be inexpensive to create, inspect, verify, compose, and
> expose to humans and agents.**

The hard boundary remains:

> **The question, projection, and representation may be molded; the evidence, qualification,
> provenance, and semantic meaning are not consumer-moldable.**

That principle can guide future AIP tool design without weakening the rule that agents may reason
over Architecture Knowledge but must never become its source.

### TypeSafe AI — Jev and Typed Probabilistic Judgment

**Sources**

- [TypeSafe AI](https://typesafe.ai/)
- [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev)

**Core idea**

Jev is a decision-oriented model that takes shared state plus bounded typed questions and returns
typed probabilistic judgments rather than free-form text. Its public interface emphasizes a small
set of question/answer shapes, calibrated probabilities, and composition in ordinary software so
uncertain judgments can be thresholded, combined, or escalated without turning every decision into
an open-ended language-generation task.

**Why this matters to AIP**

Jev provides a useful adjacent reasoning model for bounded questions that are genuinely
probabilistic rather than deterministically derivable from AIP's evidence model:

```text
AIP
KNOW
what architecture claims the evidence supports

Jev
JUDGE
a bounded semantic question probabilistically

GT
EXPLORE / MOLD / EXPLAIN
turn questions and results into contextual tools
```

Atomic typed judgments are especially interesting at the consumer/orchestration boundary for
classification, routing, prioritization, or other bounded decisions whose result can then be
composed deterministically in code.

**AIP distinction**

> **Model confidence is not evidence qualification.**

A calibrated probability can express uncertainty in a probabilistic judgment; it does not establish
an architecture fact, reconcile an identity, qualify source evidence, determine applicability, or
establish Intent. Jev therefore belongs beside AIP as a possible reasoning primitive, not inside
AIP's knowledge-establishment authority.

This is a landscape reference, not an AIP dependency or roadmap commitment. For API-aware
questions as elsewhere, a confident model classification of a consumer/API relationship cannot
replace independently qualified configuration, identity, and runtime evidence.

### Davletiyarov, Khan, and Bartolini — Symbolic Separation

**Source**

- [Symbolic Separation: Grounding Deep Agents in Knowledge Graphs for Trustworthy Operational Data Analytics](https://arxiv.org/abs/2609.17107)

**Core idea**

The paper argues that a deep agent should be free to reason probabilistically while access to
operational data is constrained by a symbolic semantic layer. Its implementation uses an
ontology-constrained Virtual Knowledge Graph plus deterministic pre-execution validation so the
model does not have to invent joins or relationships between heterogeneous sources at query time.

The important separation is:

```text
probabilistic agent reasoning
        ↓
semantic request
        ↓
symbolic / ontology-constrained knowledge layer
        ↓
deterministically validated access to data
```

This addresses a failure mode that is highly relevant to AIP: an agent can understand all the
individual fields or tools and still hallucinate **how they relate**.

**Why this matters to AIP**

This gives strong theoretical support to AIP's own epistemic boundary:

```text
agent reasoning
        ≠
source of Architecture Knowledge

agent
        ↓ asks a question
AIP's qualified semantic layer
        ↓
evidence-backed architecture result
        ↓
agent interprets or acts
```

AIP's problem is narrower but also more explicit about the knowledge contract. Architecture
Knowledge must preserve source semantics, provenance, qualification, snapshot identity,
observation context, and unresolved/conflicting cases. A symbolic graph is therefore not enough by
itself; the graph's claims must still be justified by the underlying evidence.

**AIP distinction**

Symbolic Separation shows why domain semantics should not be reconstructed probabilistically on
every request. AIP adds architecture-specific evidence qualification and a stronger rule about
epistemic authority:

> **The agent may reason freely over Architecture Knowledge, but neither the agent nor an
> unqualified graph becomes the source of that knowledge.**


### Enola — Deterministic Architecture Context and Regression Testing

**Sources**

- [Enola](https://github.com/enola-labs/enola)
- [Enola architecture](https://github.com/enola-labs/enola/blob/main/ARCHITECTURE.md)
- [Enola — architectural regression testing for AI-assisted development](https://enola.tech/)

**Core idea**

Enola builds a deterministic graph from source repositories and exposes structural architecture
context to developers, coding agents, CLI workflows, MCP clients, and CI. It supports cross-
repository relationships, snapshots and deltas, impact analysis, architecture constraints, and
regression checks without requiring an LLM or embeddings to establish the graph.

Its basic loop is close to a problem AIP also cares about:

```text
before change
deterministic architecture context
        ↓
coding agent / developer
        ↓
change
        ↓
deterministic structural re-analysis
        ↓
delta / regression verdict
```

**Why this matters to AIP**

Enola is one of the closest current concrete product comparisons for agent-facing deterministic
architecture context. It demonstrates that coding agents benefit from a precomputed structural
model rather than repeatedly rediscovering dependencies from raw files, and that the same model can
feed both pre-change context and post-change verification.

The overlap with AIP is meaningful:

```text
deterministic graph
snapshot identity
change impact
agent-facing queries / MCP
architecture constraints
CI verification
```

**AIP distinction**

AIP's center of gravity is broader than code-derived structure. It reconciles heterogeneous sources
whose semantics must remain distinct:

```text
OpenAPI declaration
Kubernetes configuration / capture
OpenTelemetry observation
configured identity mappings
future Intent
        ↓
not interchangeable evidence
```

AIP therefore emphasizes evidence identity, provenance, source-specific semantics, observation
context, conflict/unresolved outcomes, and qualification before an architectural claim becomes
public Architecture Knowledge.

Enola is consequently an important comparison and potential interoperability neighbor, not evidence
that AIP should reduce its model to static code structure or duplicate Enola's regression-analysis
surface.


### Christian Posta — Agent API Profile

**Source**

- [Christian Posta — recent writing and discussion on agent APIs](https://www.linkedin.com/in/christian-posta/recent-activity/posts/)

**Core idea**

Posta argues that if agents return to ordinary APIs rather than MCP-specific interfaces, they still
need a constrained **Agent API Profile** so models are not forced to infer routine integration
semantics on every call.

The proposed deterministic surface includes concerns such as:

```text
capability discovery
operation identity
input / output schemas
error semantics
retry and idempotency behavior
async behavior
side effects
authorization discovery / acquisition
```

The point is not that every API must use MCP. The point is that agent-facing integration needs more
semantic regularity than "here is an arbitrary HTTP API; let the model work it out."

**Why this matters to AIP**

This complements Moldable Architecture Knowledge and AIP's MCP work:

```text
Architecture Knowledge semantics
        ↓
bounded deterministic AIP operation
        ↓
stable agent-facing contract
        ↓
MCP or another sufficiently constrained API profile
        ↓
agent
```

AIP should not make its architecture semantics depend on one transport protocol. MCP is currently a
useful delivery mechanism, but the durable requirement is that operations remain explicit,
discoverable, typed, bounded, deterministic, and safe to invoke without probabilistic reconstruction
of basic protocol behavior.

**AIP distinction**

An Agent API Profile answers **how an agent can reliably invoke a capability**. AIP answers **what
Architecture Knowledge that capability may safely return and why**. Transport determinism does not
replace evidence qualification, and architecture semantics should remain stable if the transport
changes.


### Model Context Protocol (MCP)

**Source**

- [MCP specification](https://modelcontextprotocol.io/specification/2025-06-18)

**Why this matters to AIP**

MCP gives AIP a standard mechanism for exposing architecture knowledge to agents and tools. This directly relates to the v0.4 goal:

> **Trusted Architecture Context for Agents**

AIP's differentiated value is not merely an MCP server. It is the evidence-backed semantics behind each tool result.

```text
Evidence
   ↓
Canonical Architecture Model
   ↓
ArchitectureIntelligenceService
   ↓
structured evidence-backed result
   ↓
MCP / agent
```

An agent must remain downstream of the deterministic architecture model and must not become the source of canonical architectural truth.

### Lu et al. — Procedural Graphs

**Source**

- [Procedural Graphs: Self-Evolving Execution Structures for LLM Agents](https://arxiv.org/abs/2609.09153)

**Core idea**

A knowledge graph organizes facts for *what-is* questions; a Procedural Graph organizes steps,
conditions, guidance, and pitfalls for *what-to-do* questions. The proposed graph is frozen during
inference, while later edits are accepted only when they preserve or improve held-out evaluation.

**Why this matters to AIP**

This defines a useful boundary for agent-facing architecture context:

```text
AIP knowledge projection
answers what the evidence supports
        ↓
procedural or coding agent
decides what to do next
```

AIP may supply qualified context to a procedure, but procedural guidance, successful trajectories,
or an agent's chosen action must not become canonical architecture truth. If procedural knowledge is
ever linked to AIP, its evidence, validation state, version, and authority need to remain distinct
from the Current-State graph.

### Daniel Kocot — Agent-Ready APIs, Traceability, and Preserved Intent

**Sources**

- [Agent-Ready APIs Start Before an Agent Sees the API](https://www.linkedin.com/pulse/agent-ready-apis-start-before-agent-sees-api-daniel-kocot-twnbe/)
- [Context Is Not More Information. It Shapes the Conditions for Interpretation and Action](https://www.linkedin.com/pulse/context-more-information-shapes-conditions-action-daniel-kocot-z55ze/)
- [What Does an Agent Actually Need to Use an API Product?](https://www.linkedin.com/pulse/what-does-agent-actually-need-use-api-product-daniel-kocot-bvcke)
- [What Gets Lost Between API Design and OpenAPI](https://www.linkedin.com/pulse/what-gets-lost-between-api-design-openapi-daniel-kocot-ispqe)
- [Looking at Arazzo from the Business Side](https://www.linkedin.com/pulse/looking-arazzo-from-business-side-daniel-kocot-mqvke)

**Core idea**

Kocot frames agent-readiness as a traceability problem that starts before OpenAPI, MCP, retrieval,
or the context window. Purpose, capability, semantics, constraints, design rationale, workflows,
runtime state, and authority originate in different places and should not be collapsed into one
artifact.

His recent API-product work makes the separation concrete:

```text
apis.json   -> discovery
AGENTS.md   -> possible agent-facing guidance
OpenAPI     -> executable HTTP contract
Arazzo      -> interaction workflow
Hypermedia  -> runtime affordance
telemetry   -> observed behavior
policy      -> execution authority
```

The useful distinctions are therefore:

```text
guidance != contract
intent != operation
workflow != capability
protocol != outcome
runtime affordance != authorization
graph != authority
inference != explicit intent
```

A capability or design decision that existed upstream should not have to be reconstructed later
from paths, schemas, runtime frequency, or agent guesses. At the same time, an explicit workflow
such as Arazzo remains a description of interactions toward an outcome; it does not automatically
become the business capability, observed Current State, or authorization decision.

**Why this matters to AIP**

This aligns closely with AIP's source-specific semantics and future separation of Current State,
Intent, and assessment:

```text
source-specific artifact / observation
        ↓
provenance + identity + qualification
        ↓
bounded Architecture Knowledge
```

AIP should preserve what each source actually establishes rather than manufacture a universal
"source of truth." OpenAPI may establish executable interface structure, telemetry may establish
observed interaction, Kubernetes may establish deployment evidence, and future explicit artifacts
may carry attributable Intent. Where sources disagree, the disagreement should remain inspectable
instead of being delegated to an agent to choose the most convenient interpretation.

The same discipline applies to workflow and intent. Arazzo is a plausible future carrier of
explicit interaction-sequence intent, but:

```text
declared workflow
        !=
observed runtime path
        !=
business outcome
```

The related [adorsys API-landscape research](#adorsys--understanding-api-landscapes-not-just-managing-them)
adds a Current-State dimension: an API interface is not automatically a business, deployment, or
authorization boundary. API discovery, executable contracts, configured access, observed invocation,
and execution authority are different claims. Agent discoverability does not grant execution
permission, and a configured gateway consumer does not prove observed usage. This sharpens the
existing v0.7 identity/claim-kind boundaries without adding policy enforcement or business
capability inference to that release.

Kocot's work also reinforces the boundary between storage and context:

```text
connected artifacts / knowledge graph
        ≠
evidence-qualified answer for this question
```

The graph connects potentially relevant material. AIP's differentiating work is establishing which
architecture claims that material supports, under which context, with which provenance,
qualification, conflicts, and limits.

> **The graph is infrastructure. The qualified answer is the context.**

**AIP stance**

Strong landscape reference for agent-facing context and future Intent/assessment semantics, but not
a roadmap commitment to ingest `AGENTS.md`, Arazzo, `apis.json`, hypermedia, or policy engines.
The carrier must not become the semantic model, and execution authorization remains outside AIP's
Architecture Knowledge core.

### BootUI — Runtime Context for Coding Agents

**Source**

- [BootUI on GitHub](https://github.com/jdubois/boot-ui)

**Core idea**

BootUI exposes deterministic, application-local runtime diagnostics through a shared registry and
bounded UI, CLI, REST, and opt-in MCP interfaces. Coding agents can inspect a running Spring Boot or
Quarkus application without making the agent itself the diagnostic authority.

**Why this matters to AIP**

```text
deterministic core
      ↓
bounded result contract
      ↓
UI / CLI / MCP
      ↓
agent
```

BootUI mainly asks what is happening inside one running application. AIP asks which cross-service,
cross-source architecture claims the available evidence supports. It is a useful boundary reference
for deciding which runtime-derived context belongs in AIP and which diagnostics should remain in
application-local tools.

> **MCP is the interface, not the intelligence.**

### Kin Lane — Agents Should Write Code to Integrate, Not Infer It at Runtime

**Source**

- [Agents Should Write Code to Integrate, Not Infer It at Runtime](https://apievangelist.com/2026/09/01/agents-should-write-code-to-integrate-not-infer/)

**Core idea**

Lane argues for a clear division between probabilistic and deterministic work: an agent is useful for ambiguous tasks like discovering capabilities and deciding what integration to build, but once a contract is understood, repeated production integration should be deterministic, reviewed, and testable — not re-interpreted by an LLM at runtime on every call.

```text
ambiguity
   ↓
inference

known contract + repeated operation
   ↓
deterministic implementation
```

**Why this matters to AIP**

The same rule applies to architecture, and is already implicit in how AIP's MCP tools above are built:

```text
sources
   ↓
deterministic evidence processing
   ↓
qualified architecture claims
   ↓
agent reasoning
```

AIP does not expose raw OpenAPI, telemetry, or arbitrary graph access and ask an LLM to infer their architectural meaning on each call — the deterministic architecture layer sits behind MCP, not inside it:

> **Do not spend probabilistic reasoning on facts and relationships that can be established deterministically.**

### UI Atlas — AI Successors

**Sources**

- [UI Atlas — GitHub repository](https://github.com/AI-Successors/ui-atlas)
- [UI Atlas — architecture documentation](https://github.com/AI-Successors/ui-atlas/blob/main/docs/architecture.md)
- [Interaction Trace documentation](https://github.com/AI-Successors/ui-atlas/blob/main/docs/interaction-trace.md)

**Core idea**

UI Atlas builds a persistent, evidence-linked representation of desktop software for computer-use agents, transforming raw observations deterministically through four retained layers:

```text
Raw Data Streams → Raw World → Semantic World → UI Knowledge Graph
```

Canonical identities deliberately exclude volatile properties (process IDs, window handles, timestamps). Its interaction model only links an observed action to an observed result state — a merely possible UI affordance never receives an invented destination, and failed, timed-out, or no-change interactions remain explicit evidence rather than being discarded.

**Why this matters to AIP**

At a different system layer, UI Atlas implements almost the same grounding discipline:

```text
UI Atlas
UI evidence → persistent evidenced UI map → computer-use agent

AIP
architecture evidence → qualified architecture model → software agent
```

The shared principle — **do not invent a relationship simply because it is plausible** — is one AIP already applies to `CALLS`/`SENDS` edges, and UI Atlas's layered raw-to-semantic transformation with retained lineage is a useful external reference for AIP's own evidence-to-claim derivation chain (Section 2).

**AIP distinction**

UI Atlas models UI states, controls, and transitions; AIP models architectural relationships and additionally reconciles distinct evidence classes (declared vs. observed). The two are complementary rather than competing.

### Thoughtworks AI/works

**Sources**

- [AI/works](https://www.thoughtworks.com/en-us/ai/works)
- [AI/works Technical Guide](https://www.thoughtworks.com/ai/works/technical-guide)
- [August 2026 V2 release](https://www.thoughtworks.com/ai/works/release/august-2026-V2-release)

**Relevant concepts**

- Code to Spec
- Dynamic / SuperSpec
- Spec to Code
- enterprise context / Knowledge Fabric
- evaluations
- Control Plane
- Runtime Operations
- continuous modernization

**Why this matters to AIP**

AI/works is a close large-scale example of an agentic development platform combining system understanding, context, modernization, generation, governance, and continuous evolution.

A useful distinction is directionality:

```text
AI/works
Code → Spec → enriched future-state context → Code

AIP
Evidence → qualified Current State
                    ↓
          trusted context for agents
```

The particularly relevant question for AIP is **reverse propagation**: after agents or developers change an implementation, how is higher-level architectural knowledge updated from real evidence without assuming the generated intent became reality?

A useful AIP distinction is:

> Context is useful. Evidence makes architecture context trustworthy.

### Nicole Königstein — AI Agents: The Definitive Guide

**Source**

- [AI Agents — The Definitive Guide repository](https://github.com/Nicolepcx/ai-agents-the-definitive-guide)

**Relevant concepts**

The open repository accompanying the O'Reilly book spans agent architectures and planning through production tool contracts, MCP, secure execution, evaluation, observability, memory, cost, and threat modeling. Particularly relevant to AIP are the examples around MCP/tool contracts, governed execution, production reliability, and deterministic evaluation harnesses.

**Why this matters to AIP**

The guide describes the engineering environment in which AIP's architecture context will be consumed:

```text
Agent system
planning · tools · MCP · governance · evaluation
                         ▲
                         │
                architecture context
                         │
                        AIP
```

Its production focus reinforces that architecture context exposed to agents needs explicit contracts, bounded tool behavior, failure semantics, evaluation, and provenance. AIP remains narrower: the agent framework determines **how an agent acts**, while AIP determines **which architecture claims are supported by evidence and how they are qualified**.

The repository is therefore useful both as an integration reference and as a source of agent-side evaluation scenarios, without making its agent architecture part of AIP itself.

### Tim O'Reilly — Why Open Source Matters for AI

**Source**

- [Why Open Source Matters for AI](https://oreillyradar.substack.com/p/why-open-source-matters-for-ai)

**Core idea**

O'Reilly argues that durable openness comes not only from licenses but from **composable architecture**: small replaceable components connected by standard interfaces and protocols. In AI, this means keeping models, agent harnesses, context, tools, memory, and skills sufficiently unbundled that one component can be replaced without rewriting the whole system. MCP is cited as an example of protocol-centric composition.

**Why this matters to AIP**

This supports an important architectural boundary for AIP:

```text
Model
  ≠
Agent harness
  ≠
Architecture context
  ≠
Tools / evidence sources
```

AIP should be useful across model and agent-framework choices. Its durable interface should be evidence-backed architecture semantics exposed through open, replaceable integration boundaries rather than coupling architectural truth to one model vendor or agent runtime.

This makes composability relevant to AIP's architecture, but not an argument for adding every adjacent agent capability. The stronger design goal is that models, harnesses, discovery adapters, and protocols can evolve independently while AIP's evidence and qualification guarantees remain explicit.

### Google Cloud — Gemini Enterprise for Financial Services

**Sources**

- [Gemini Enterprise for Financial Services](https://cloud.google.com/ai/financial-services)
- [Introducing Gemini Enterprise for Financial Services](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-for-financial-services)

**Relevant concepts**

- purpose-built reusable skills;
- secure MCP connectors to licensed and enterprise data;
- a Google-managed Financial Research agent exposed through UI and A2A APIs;
- confidence scores, explicit methodologies, auditable data snapshots, and precise source citations;
- verifiable data lineage;
- centralized governance and policy enforcement.

**Why this matters to AIP**

Gemini Enterprise for Financial Services is a concrete example of an enterprise agent platform treating **trusted context, lineage, snapshotting, source citation, and governance** as architectural capabilities rather than prompt-level concerns.

The domain differs, but the trust pattern is close:

```text
Google financial services
trusted financial data
      ↓
lineage + snapshots + citations
      ↓
agent workflows

AIP
architecture evidence
      ↓
provenance + qualification + snapshot context
      ↓
trusted architecture context for agents
```

The important distinction is semantic scope: Google is grounding financial workflows in governed domain data; AIP is concerned with what architectural claims can be supported from declared and observed software-system evidence.

Confidence scores or standardized skills should also not be confused with deterministic verification. AIP should preserve a hard boundary between probabilistic agent reasoning and evidence-backed architectural claims.

---

## 4. Architectural Intent and Governance

### Andreas Toth — AI Shouldn't Guess What We Mean. It Should Ask.

**Source**

- [AI Shouldn't Guess What We Mean. It Should Ask.](https://www.linkedin.com/pulse/ai-shouldnt-guess-what-we-mean-should-ask-andreas-toth-dsn5f/)

**Core idea**

Toth distinguishes a likely interpretation from confirmed intent. That distinction becomes
important if AIP later relates evidence-qualified Current State to architectural intent,
constraints, ADRs, or Desired State.

```text
inferred intent
    ≠
confirmed intent
```

**Why this matters to AIP**

AIP may eventually preserve or qualify explicit intent, but it should not establish intent from
runtime behavior, code structure, naming, or an LLM's interpretation. Inference may propose an
interpretation for confirmation; only explicit evidence can establish architectural intent.

> **Inference may propose architectural intent; only explicit evidence may establish it.**

### ArchiMate and Intent Interchange

**Sources**

- [ArchiMate](https://www.opengroup.org/archimate-forum/archimate-overview)
- [Requirements Interchange Format (ReqIF)](https://www.omg.org/spec/ReqIF/1.2)
- [Open Services for Lifecycle Collaboration (OSLC)](https://open-services.net/specifications/)
- [Capella](https://eclipse.dev/capella/)

**Core idea**

ArchiMate provides an enterprise-architecture language spanning motivation, strategy, business,
application, technology, and implementation views. ReqIF exchanges requirements, OSLC links
lifecycle resources across tools, and Capella/Arcadia provides model-based system-architecture
artifacts. Together they form a useful research cluster for explicit architectural intent and its
links to requirements and engineering models.

**Why this matters to AIP**

These artifacts could eventually supply authored intent, assumptions, constraints, and trace links.
They do not by themselves establish Current State:

```text
ArchiMate relationship
ReqIF requirement
OSLC lifecycle link
Capella model element
        ↓
versioned, source-bound intent evidence
        !=
observed architecture relation
```

Any future adapter must preserve source authority, version, context, native identifiers, and mapping
loss. AIP should support an explicitly qualified semantic subset rather than claim generic,
lossless import of each metamodel.

This is a bundled post-v0.5 research direction, not four immediate adapters and not a roadmap
commitment.

### Mneme HQ

**Sources**

- [Mneme HQ](https://mnemehq.com/)
- [Architecture](https://mnemehq.com/architecture/)
- [Governance Benchmark](https://mnemehq.com/benchmark/)

**Core idea**

Mneme focuses on architectural governance before generation: engineering decisions and constraints are represented in a form coding agents can retrieve and enforce.

```text
Mneme
Architectural Intent
      ↓
Constraints
      ↓
GUIDE / WARN / BLOCK
      ↓
Coding Agent
```

**Relationship to AIP**

The current boundary is clean:

```text
Mneme
Intent → constraints → governance

AIP
Evidence → Current State → trusted architecture context
```

This makes Mneme especially interesting as a potentially complementary layer rather than a direct competitor.

AIP should not turn v0.4 into an architecture-governance release. First make trusted Current State safely consumable. Intent and governance can be added later or integrated with dedicated governance systems.

### O'Reilly — Architectural Guardrails for AI-Generated Code

**Source**

- [Architectural Guardrails for AI-Generated Code](https://www.oreilly.com/radar/architectural-guardrails-for-ai-generated-code/)

**Why this matters to AIP**

The article reinforces the need for architectural decisions to become machine-readable, retrievable, traceable, and enforceable when AI participates in implementation.

For AIP this suggests a future two-sided model:

```text
WHAT IS TRUE?
Evidence → Current State

WHAT SHOULD BE TRUE?
Intent → Decisions / Constraints

             ↓

Current State + Intent
             ↓
Architecture assessment / drift / governance
```

This is a future direction, not v0.4 scope.

### Ankur Agnihotri — Architecture Drift Reduction with LLMs

**Sources**

- [Architecture Drift Reduction with LLMs: Fighting Entropy in the Age of AI Coding Agents](https://www.linkedin.com/pulse/architecture-drift-reduction-llms-fighting-entropy-age-agnihotri-csjwf/)
- [Thoughtworks Technology Radar — Architecture drift reduction with LLMs](https://www.thoughtworks.com/radar/techniques/architecture-drift-reduction-with-llms)

**Core idea**

AI-assisted development can reproduce and amplify existing architectural patterns without knowing
whether those patterns express deliberate design or accumulated compromise. As generation speeds
up, architectural drift can compound more quickly, increasing the value of deterministic analysis
and an independent verification loop.

**Why this matters to AIP**

```text
Before change
  bounded, evidence-qualified architecture context

After change
  independently re-establish the resulting architecture state
```

The sources give LLMs a role in identifying or evaluating drift. AIP should maintain a stricter
truth boundary: an LLM may interpret or discuss intent, but explicit evidence must establish it, and
AIP must not turn inferred intent into architectural truth.

> **AI agents amplify the architecture they infer. AIP should help establish the architecture they
> are actually entitled to assume.**

### Alireza Rahmani Khalili — AI Did Not Eliminate Software Design

**Source**

- [AI Did Not Eliminate Software Design](https://nidly.substack.com/p/ai-did-not-eliminate-software-design)

**Core idea**

Rahmani Khalili argues that AI separates implementation from design — "design chooses constraints, implementation expresses them" — and that as implementation gets cheaper, architecture increasingly moves toward constraints, authority, boundaries, and verification. AI can produce locally coherent systems whose global architecture is worse; passing tests do not establish architectural correctness, which the article treats as a distinct concern from behavioral verification.

**Why this matters to AIP**

This supports AIP's core split between probabilistic reasoning and deterministic verification (Section 5), and explains why architecture intelligence becomes more valuable as generation gets cheaper:

```text
faster generation
      ↓
more architectural change
      ↓
less human ability to inspect every change
      ↓
explicit context + constraints + verification
```

The article's distinction between intelligence and authority mirrors AIP's own stance:

> An agent may reason about architecture, but must not become the source of architectural truth.

**AIP distinction**

The article reaches into future concepts — architectural intent, domain authority, enforceable constraints — that should stay separate from AIP's present evidence-backed Current State rather than being folded prematurely into the Canonical Model.

### Raghunandan E. Srinivasan — From Architectural Debt to Architectural Fitness

**Source**

- [From Architectural Debt to Architectural Fitness: Making Enterprise Architecture Observable](https://www.linkedin.com/pulse/from-architectural-debt-fitness-making-enterprise-srinivasan-zmxvc/)

**Core idea**

Architecture debt should not be inferred from technology age or deviation alone. The relevant
question is whether an architecture still satisfies the NFRs, assumptions, and constraints that
justify it. Decisions can therefore be connected to explicit fitness criteria and reassessed against
operational evidence as their context changes.

**Why this matters to AIP**

This provides a concrete framing for the future Current-State-to-Intent assessment:

```text
architectural promise / decision
        + assumptions and NFRs
        + applicability context
        ↓
fitness criteria
        + qualified current evidence
        ↓
supported / violated / inconclusive assessment
```

A changed system is not automatically in debt, and a non-observation is not proof that a fitness
criterion failed. AIP would need versioned intent, bounded observation windows, qualification rules,
and explicit decision authority before producing such an assessment.

**AIP stance**

Strong input for the later Intent and Assessment releases, not for v0.5 Current-State discovery.
Fitness results should remain contextual assessments rather than timeless properties of a system.

### Matthew Skelton — Bounded Agency and the AI-native Operating Model

**Source**

- [Bounded — AI-native operating model](https://matthewskelton.com/bounded-ai-native-operating-model)

**Core idea**

Bounded treats deliberate limits to agency, auditability, traceability, curated context, and
high-fidelity feedback from live systems as foundations for AI-native work. Autonomy is enabled
inside designed boundaries rather than treated as unrestricted delegation.

**Why this matters to AIP**

AIP can supply one part of that operating environment: qualified architecture context with explicit
evidence, identity, observation scope, conflicts, and unsupported cases.

```text
Bounded
who or what may act, within which boundary and authority

AIP
what the available architecture evidence supports in that context
```

These responsibilities should not collapse. AIP does not grant authority, enforce organizational
policy, or infer accountability from technical topology. Conversely, an authorization boundary does
not establish that the architecture context supplied to an agent is correct.

**AIP stance**

A strategic neighbor and potential integration context. Bounded sharpens the consumer-side need for
AIP without expanding AIP into a general agent-governance or operating-model product.

### Matthew Skelton — Reframing the AI-native SDLC in Terms of Stewardship Boundaries

**Source**

- [Reframing the AI-native SDLC in terms of stewardship boundaries](https://www.linkedin.com/pulse/reframing-ai-native-sdlc-terms-stewardship-boundaries-matthew-skelton-vrfpe)

**Core idea**

Skelton proposes shifting from *construction boundaries* (who builds what) to *stewardship boundaries*: which long-lived human teams remain accountable for the ongoing health, outcomes, and risk of a value flow. He draws an analogy between human cognitive load and agent context windows — both become less reliable given large, loosely bounded information — and argues reliable agentic engineering needs narrow, well-defined context and platform capabilities, illustrated by a case combining agent-assisted development with deterministic guardrails rather than prompting alone.

**Why this matters to AIP**

The context argument fits AIP's own MCP design (Section 3) directly:

```text
more architecture information
        ≠
better agent context

bounded + relevant + trustworthy architecture information
        ↓
better reasoning
```

The stewardship concept is more future-facing but relevant to this section:

```text
architecture relationship + ownership/responsibility + constraints
                    ↓
            stewardship boundary
```

> **More autonomous implementation requires stronger boundaries and independently verifiable context.**

**AIP distinction**

Organizational accountability must not be inferred from runtime connectivity. `Service`, Bounded Context, deployment unit, team, and stewardship boundary are distinct concepts; any future relationship between them needs explicit evidence or intent, echoing the same caution already stated for Strategic DDD (Section 1).

### Rachel Laycock — Expert Governance and Code Review in an AI-heavy SDLC

**Sources**

- [Citizens Build, Agents Execute, Experts Govern](https://martinfowler.com/rachels-ramblings/citizens-agents-experts.html)
- [Maybe We Shouldn't Be Reviewing All This Code](https://martinfowler.com/rachels-ramblings/code-review.html)

**Core idea**

As agents make implementation abundant, experienced engineering judgment becomes more rather than
less valuable. Citizens can express needs and create useful software, agents can execute at high
speed, and experts define what production-worthy means through architecture, security, resilience,
operability, compliance, cost, guardrails, platforms, and feedback loops. At the same time, human
line-by-line review cannot remain the universal assurance mechanism when generated code volume
grows.

**Why this matters to AIP**

```text
citizens express needs
        ↓
experts define intent, boundaries, and fitness criteria
        ↓
AIP supplies qualified architecture context
        ↓
agents plan and execute
        ↓
evidence qualifies the resulting Current State
```

AIP can make expert knowledge more reusable by exposing evidence-backed context, explicit
limitations, and deterministic checks before and after implementation. It does not replace expert
judgment or grant decision authority to an agent.

**AIP distinction**

`Experts govern` must not imply a centralized architecture approval queue. AIP's bottom-up
direction is better expressed through qualified local promises, explicit decision boundaries, and
context-specific authority. Agents execute within those boundaries; evidence shows whether the
resulting system still keeps its promises.

> **Agents need qualified architectural constraints before execution and evidence afterwards that
> the resulting system still satisfies them.**


---

## 5. Verification, reliability, and observability

**AIP verification boundary**

AIP should preserve an important distinction as agent-facing features grow:

```text
AI judgment
     ≠
deterministic verification
```

Probabilistic reasoning may help formulate or interpret a question, while supported architecture claims should remain independently traceable to deterministic model state and evidence.

Mneme's benchmark methodology is relevant here because it similarly emphasizes structured outputs, reproducibility, explicit scope, and avoiding subjective LLM-as-judge grading where deterministic checks are possible.


### Davis et al. — Agentic AI and Code Reviews

**Source**

- Zach Davis, Michelle Gill, Elisabeth Hendrickson, Angie Jones, Sha Ma, Randy Shoup, and James
  Wickett, *Agentic AI and Code Reviews: Toward a Pattern Language for Code Reviews in the Age of
  Agentic AI*, IT Revolution, *Enterprise Technology Leadership Journal*, Fall 2026.

**Core idea**

The paper proposes layered verification for increasingly agent-generated changes: small changes,
shift-left deterministic checks, design for verification, context engineering, ongoing feedback,
independent/adversarial and specialist reviews, spec-driven development, and selective human
judgment. Its **Context Engineering** pattern identifies architecture constraints, dependencies,
API compatibility, ownership, incidents, previous decisions, and policies as context a reviewer
needs beyond the PR diff.

This directly articulates AIP's customer problem: code repositories alone do not provide all
the architectural knowledge an authoring or reviewing agent needs. AIP addresses the
architecture-specific part through reusable, evidence-qualified knowledge and bounded
projections; the broader organizational knowledge and historical decisions remain adjacent
domains.

**Why this matters to AIP**

This is a concrete downstream use case for AIP's customer proposition. An authoring and an
independent reviewing agent can consume the same evidence-qualified, snapshot-bound architecture
answer rather than reconstruct system context separately. A bounded question such as *What should
be inspected before editing this service?* can evolve with independently qualified locality,
API-aware, Intent, and Assessment capabilities. Shared provenance makes premises inspectable;
it does not guarantee that the review agent's judgment is correct.

**AIP stance**

AIP supplies architectural knowledge, not a PR reviewer, policy-enforcement engine, or merge gate.
Deterministic checks, review findings, acceptance decisions, and reviewer confidence remain
external and do not automatically become canonical architectural facts. The paper supports a
workflow-value pilot, not another capability release or expansion of v0.6–v0.9.

### Rush Shahani — Building Reliable AI Systems

**Source**

- [Building Reliable AI Systems: Applications and Agents You Can Trust](https://www.manning.com/books/building-reliable-ai-systems)

**Core idea**

Shahani organizes AI reliability into three layers:

```text
Reliable Outputs
      ↓
Reliable Agents
      ↓
Reliable Operations
```

The book covers grounding and hallucination reduction, agent architectures, tool integration and MCP, multi-agent coordination, evaluation, performance, deployment, monitoring, and responsible AI.

**Why this matters to AIP**

The book is a useful reference for the reliability requirements surrounding systems that consume AIP context. In particular, chapters 7–10 connect tool interfaces, agent workflows, evaluation, failure handling, deployment, and observability.

AIP occupies a narrower layer:

```text
Reliable agent
      +
reliable architecture context
      ↓
more trustworthy agent reasoning
```

The book's emphasis on grounding, graceful failure, source-backed answers, continuous evaluation, and monitoring aligns strongly with AIP's conservative semantics. A system should be able to say that it cannot establish an answer instead of filling gaps with plausible output.

**AIP distinction**

AIP should preserve a sharper distinction between:

```text
probabilistic evaluation
        ≠
deterministic verification
```

An LLM judge may help assess usefulness, relevance, or faithfulness. A supported architecture claim should still be reconstructable from deterministic model state, evidence, provenance, and qualification.

The book is therefore complementary rather than an architectural blueprint for AIP: it addresses AI-system reliability broadly, while AIP focuses specifically on the trustworthiness of architecture knowledge supplied to humans and agents.

### Google — Agent Evaluation and trajectory metrics

**Source**

- [agents-cli Evaluation Guide](https://google.github.io/agents-cli/guide/evaluation/)

**Core idea**

Agent evaluation should inspect the full multi-turn execution trajectory rather than only the final answer. Google's evaluation tooling exposes dedicated metrics for:

- `multi_turn_task_success` — whether the user's goal was fulfilled across the conversation;
- `multi_turn_trajectory_quality` — whether the execution path was logical, efficient, and resilient;
- `multi_turn_tool_use_quality` — technical and semantic correctness of tool calls across turns;
- hallucination and grounding checks against tool-returned or supplied context.

This separates several failure modes that can be invisible in a superficially correct final response: wrong tool selection, malformed parameters, incomplete execution, incorrect handling of tool output, or an inefficient trajectory.

**Why this matters to AIP**

Agent evaluation and AIP qualification answer complementary questions:

```text
Agent evaluation
Did the agent behave correctly?

AIP
Was the architecture context it consumed
supported by evidence and correctly qualified?
```

For v0.4, this is useful input for deterministic tool evaluation. An AIP tool result should make it possible to reconstruct which snapshot was queried, which claims were returned, what evidence supports them, and where the model returned unsupported or insufficiently evidenced results.

AIP should still distinguish trajectory evaluation from architectural verification. An LLM-as-judge metric may assess whether an agent used context well; it must not become the authority that decides whether an architecture claim is true.

### Zhao et al. — Failure as a Process

**Source**

- [Failure as a Process: An Anatomy of CLI Coding Agent Trajectories](https://arxiv.org/abs/2607.09510)

**Core idea**

Zhao et al. study coding-agent failure as a trajectory rather than only a final outcome. Their
results identify epistemic errors as a major source of failure and show that failures often begin
early, remain hidden, and become difficult to recover from later in the trajectory.

**Why this matters to AIP**

AIP addresses a bounded subset of premise quality: architectural premises.

```text
unsupported architecture premise
        ↓
agent reasoning
        ↓
plausible but wrong implementation path
```

AIP can move one class of premise checking before or alongside reasoning by supplying
evidence-qualified architecture context with explicit limitations. The agent still decides what to
do; AIP determines what the available architecture evidence supports.

> **Reliable agent reasoning starts before the reasoning step — with trustworthy premises.**

### Agentic Software: How AI Agents Are Restructuring the Software Paradigm

**Source**

- [Agentic Software: How AI Agents Are Restructuring the Software Paradigm](https://arxiv.org/html/2606.05608)

**Core idea**

The paper examines context drift and verification fidelity across long-running, agent-driven software evolution, and argues for shared, observable context that multiple agents and humans can rely on across sessions rather than each agent re-deriving its own working picture of the system.

**Why this matters to AIP**

```text
single-session working context
      ↓
context drift across sessions / agents / time

evidence-backed architecture context
      ↓
stable reference point, re-derived from evidence on each import
rather than accumulated in any one agent's session state
```

AIP's graph is a candidate for exactly this durable, shared context layer: a system whose state does not drift with conversation history, because it is re-derived from declared and observed evidence on each import rather than carried forward as accumulated agent memory.

### Zhou et al. — ADMET-EvO and Evidence-Gated Self-Evolution

**Source**

- [ADMET-EvO: a self-evolving scientific agent for sustained research across heterogeneous tasks](https://arxiv.org/abs/2609.10121)

**Core idea**

ADMET-EvO formalizes endpoints, generates falsifiable hypotheses, tests interventions, and carries
supported, rejected, and inconclusive outcomes into later cycles. The agent can adapt what it
investigates while evidence gates constrain what is retained as an established result.

**Why this matters to AIP**

The domain is different, but the separation of proposal from judgment closely matches AIP's
epistemic boundary:

```text
agent proposes or investigates
        ↓
independent evidence gate
        ↓
supported / rejected / inconclusive
```

For AIP, an agent may formulate architecture questions or candidate interpretations, but it must not
promote its own inference into canonical architecture truth. Qualification needs fixed contracts,
declared evidence classes, reproducible evaluation, and a frozen candidate before certification.

**AIP stance**

A verification-pattern reference, not a proposal for self-modifying AIP semantics. Qualification
rules and release evidence remain independently reviewable and must not evolve during certification.

### Martien de Jong — The Light Factory

**Source**

- [The Light Factory: Autonomous Software Development With the Lights On](https://martiendejong.nl/light-factory-autonomous-software-development/)

**Core idea**

Autonomy and transparency are independent. An autonomous delivery system remains governable when
requirements, tasks, agents, branches, commits, pull requests, tests, reviews, approvals, and
deployments form a traceable chain. Consequential actions are gated by risk, and review shifts from
reading every line toward verifying decisions, boundaries, evidence, and authority.

**Why this matters to AIP**

The article describes a transformation chain complementary to AIP's architecture evidence chain:

```text
intent → task → change → validation → approval → deployment
                                      ↓
                    resulting architecture evidence
                                      ↓
                  qualified Current-State projection
```

AIP currently explains what architecture claims the available evidence supports. A future
Transformation Lineage could connect those claims to why a change existed, how it was validated,
and under whose authority it shipped without making the agent or an audit log the source of
architectural truth.

**AIP stance**

Strong future reference for transformation lineage and decision review. It does not add autonomous
delivery, approval workflows, or agent-memory features to the present roadmap.

### OrcaReplay — Record, Replay, and Fork Agent Runs

**Source**

- [OrcaReplay](https://github.com/Continuum-AI-Corp/OrcaReplay)

**Core idea**

OrcaReplay records interactions between agents and model APIs so a run can be inspected, replayed
offline, or forked from an earlier point. It treats the execution trajectory as a reproducible
debugging artifact rather than leaving it only in transient terminal output.

**Why this matters to AIP**

Recorded agent runs could strengthen qualification of AIP's downstream consumption:

- preserve which AIP tool result and snapshot an agent received;
- reproduce transport, parsing, and reconnect behavior without spending new model tokens;
- compare agent behavior after changing the model, prompt, or client;
- inspect whether evidence references and snapshot identity remain continuous through the run.

**AIP distinction**

A replay establishes what a recorded agent execution consumed and did. It does not prove that the
recorded architecture answer is still current, that the original evidence was sufficient, or that a
forked trajectory is semantically correct. AIP's own deterministic qualification remains the
authority for supported architecture claims.

### Lucas F. Costa — Backpressure Is All You Need

**Source**

- [Backpressure Is All You Need](https://www.lucasfcosta.com/blog/backpressure-is-all-you-need)

**Core idea**

Costa argues for shifting feedback left: deterministic, automated checks applied at planning/generation time act as backpressure on agents, catching problems before they compound, rather than relying on downstream review to catch them after the fact.

**Why this matters to AIP**

```text
agent proposes a change
      ↓
deterministic check against evidence-backed Current State
      ↓
accept / block — before the change compounds
```

This is close to AIP's own emphasis on deterministic Cypher analyses over LLM judgment (see "Deterministic verification" above). AIP's Current State graph is itself a natural backpressure signal: an agent's plan can be checked against it before code is written, not only reviewed against it afterwards.

### Agent observability

Agent observability and architecture observability are complementary but different concerns:

```text
Agent observability
What did the agent do?

Architecture observability / intelligence
What does the software system actually look like,
and what evidence supports that conclusion?
```

---

## 6. AIP's emerging position

### The customer problem: agent-ready architectural context

The Fall 2026 IT Revolution papers converge on a practical need that makes AIP's customer
proposition concrete. Davis et al.'s **Context Engineering** pattern calls for engineering
environments to move beyond repositories of code toward accessible operational knowledge,
architectural intent, and historical decision context. Cochran et al. identify repeated
knowledge dependencies and coordination as delivery bottlenecks. Cockcroft et al. describe
persistent, attributable context as part of the substrate beneath agent decisions.

These are complementary external perspectives, not proof that one product must provide
all engineering context. AIP's deliberately bounded contribution is:

> **Help coding agents work across multi-service systems without reconstructing architecture.**

Code and search results are source material; they are not themselves qualified architectural
answers. AIP establishes evidence-qualified Architecture Knowledge once and makes recurring,
question-specific context available to authoring agents, reviewers, humans, and contextual tools.

### Product hierarchy and integration boundary

```text
CUSTOMER PROBLEM
Agent-ready engineering needs reusable architectural context,
not repeated inference from code and fragmented sources
                          │
                          ▼
CUSTOMER VALUE
Work across multi-service systems without reconstructing architecture
                          │
                          ▼
PRODUCT CONCEPT
Moldable Architecture Knowledge
                          │
                          ▼
CORE DOMAIN
Establish Evidence-Qualified Architecture Knowledge
applicability · identity/reconciliation · qualification
provenance/lineage · conflict handling · bounded uncertainty
                          ▲
                          │
HETEROGENEOUS EVIDENCE
contracts · manifests · configuration · deployment · telemetry
                          │
                 qualified knowledge
                          ▼
PRODUCT-LEVEL CAPABILITY
Bounded, deterministic, question-specific projections
                          │
            ┌─────────────┴──────────────┐
            ▼                            ▼
     Authoring agent              Independent reviewer
     Human / GT lens              Other contextual consumer
            └─────────────┬──────────────┘
                          ▼
EXTERNAL WORKFLOW / DECISION AUTHORITY
implementation · testing · review · approval · policy · action
```

The diagram separates where knowledge is established from where it is consumed. Graph
storage, visualization, and MCP/REST transport remain implementation/integration mechanisms;
public claim meaning, evidence, qualification, applicability, and context are product contracts.
Consumers may mold the question and representation, not the underlying architectural meaning.

### Separate epistemic and authority paths

Current State is qualified from source-specific evidence. Explicit, attributable Intent has its
own independent path. An assessment compares the two separately established projections; an
external review or decision record does not retroactively change either. Decision History linkage
remains an unscheduled future candidate, not the authority to approve or execute changes.
Technical architecture topology must not be confused with organizational decision topology.

```text
Current-State evidence ──> Qualified Current State ──┐
                                                       ├──> Qualified Assessment (planned)
Explicit attributable Intent ─> Applicable Intent ───┘
                                                       │
                                              downstream consumers
                                                       │
                                         review / decision / action
                                         (externally authoritative)
```

The papers suggest a useful **workflow-value hypothesis**: a bounded, supported AIP answer
should reduce repeat cross-source investigation and expert clarification for a coding or
reviewing agent. Validate that alongside answer correctness, explicit unresolved outcomes,
setup and maintenance cost; do not claim proven business outcomes from conceptual convergence.

AIP's differentiating epistemic question remains:

> **What architecture can we support from available evidence, and what are the limits of that knowledge?**

Its customer-facing product-design question is:

> **Which recurring architecture question can AIP answer reproducibly so that an agent does
> not have to reconstruct those premises, and can inspect their evidence and limits?**

Four durable principles follow:

1. **Evidence before inference.**
2. **Correct but incomplete is better than complete-looking but wrong.**
3. **Non-observation is not absence; missing context is not permission to invent facts.**
4. **An agent may reason over architecture, but must not become its source or approval authority.**

**Roadmap impact:** This strengthens the existing product proposition and validation wedge;
it does not add scope or reorder v0.6 Locality, v0.7 API-Aware Current State, v0.8 Intent, or
v0.9 Assessment. AIP is not a general context repository, PR reviewer, CDI platform, or
organizational governance engine.

---

## 7. How to use this document

When a source appears relevant to AIP:

1. Identify the concrete AIP problem it helps illuminate.
2. Separate conceptual similarity from actual semantic equivalence.
3. Record what the source does **not** solve.
4. Test whether adopting the idea would strengthen AIP's evidence and correctness guarantees.
5. Do not add roadmap scope merely because an adjacent platform contains a feature.
6. Prefer integration boundaries over duplicated functionality when another layer already has a strong, well-defined responsibility.
7. Turn an external idea into an AIP feature only after its semantics and validation criteria can be stated independently.

The landscape should remain a **research map**, not a feature checklist.
