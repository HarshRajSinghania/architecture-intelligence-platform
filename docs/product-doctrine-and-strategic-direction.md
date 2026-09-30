# AIP Product Doctrine and Strategic Direction

**Status:** Working strategy — Moldable Architecture Knowledge positioning and release doctrine integrated<br>
**Project:** Architecture Intelligence Platform (AIP)<br>
**Date:** 2026-09-21<br>
**Roadmap-alignment revision:** 2026-09-29<br>
**Product-positioning revision:** 2026-09-29 — agent-ready architectural Context Engineering<br>
**Scope:** Product doctrine, target wedge, semantic model, Moldable Architecture Knowledge, strategic direction, and roadmap alignment<br>
**Current implementation center:** Evidence-qualified Current State and read-only agent context; v0.5 broadens discovery and public Architecture Knowledge access<br>
**Important:** ROADMAP.md assigns planned themes to v0.6–v0.9; detailed scope remains subject to release-specific specifications and qualification gates.

---

## 1. Executive Summary

AIP's customer value proposition is:

> **Help coding agents work across multi-service systems without reconstructing architecture.**

The customer problem is **agent-ready architectural context**. A repository of code alone cannot
reliably provide the operational and architectural knowledge required to change multi-service
systems: contracts, configuration, deployments, observations, constraints and previous decisions
are dispersed across sources and people. Without reusable, attributable context, every authoring
or reviewing agent must reconstruct architectural premises, often without knowing which are
supported, incomplete, conflicting, or stale.

Davis et al.'s *Context Engineering* pattern in *Agentic AI and Code Reviews* (IT Revolution,
Fall 2026, pp. 17–19) states the broader need for engineering environments to make operational
knowledge, architectural intent and decision history accessible. **AIP supplies the
architecture-specific, evidence-qualified part of that environment**, not generic organizational
memory or the authority to approve decisions. Current State, future explicit Intent and external
Decision History remain distinct knowledge domains.

Its core product concept is **Moldable Architecture Knowledge**: establish qualified Architecture
Knowledge once, then make small, deterministic, question-specific projections inexpensive to
create, inspect, compose, and reuse without allowing the consumer to rewrite the underlying evidence
or qualification.

AIP's differentiation has two layers.

**Core-domain differentiation** establishes trustworthy Architecture Knowledge:

- **evidence applicability and qualification** — state what the available evidence actually supports;
- **identity reconciliation** — relate heterogeneous identities without guessing;
- **conflict-aware reconciliation** — combine potentially disagreeing sources without flattening
  disagreement;
- **provenance and derivation lineage** — preserve why a claim exists and where it came from;
- **bounded uncertainty** — keep unresolved, conflicting, unsupported, incomplete, and scoped
  outcomes explicit.

**Product-level differentiation** makes that knowledge useful repeatedly:

- **deterministic projections** — turn recurring architecture questions into reproducible,
  inspectable answers over the same qualified knowledge;
- **moldability** — allow question, selection, composition, and representation to vary without
  changing the established meaning underneath.

Its purpose is not to make agents more autonomous. Its purpose is to make architectural
understanding **reusable rather than repeatedly reconstructed**. Context delivery is the
customer-facing job; establishing precisely which claims the evidence supports is the Core Domain.
A larger prompt, generic document retrieval, or a graph visualization alone does not provide that
qualification.

The strategic hierarchy is:

```text
CUSTOMER VALUE PROPOSITION
Help coding agents work across multi-service systems
without reconstructing architecture
        ↓
PRODUCT CONCEPT
Moldable Architecture Knowledge
        ↓ enabled by
CORE DOMAIN
Establishing Evidence-Qualified Architecture Knowledge
        ↓
CORE-DOMAIN DIFFERENTIATION
applicability + identity/reconciliation + qualification
+ provenance/lineage + bounded uncertainty
        ↓ exposed as
PRODUCT-LEVEL DIFFERENTIATION
deterministic question-specific projections + moldability
        ↓
REPLACEABLE IMPLEMENTATION
graph/database layout, query language, storage technology,
transport plumbing, internal traversal and persistence details
```

The product center becomes:

```text
Architecture Evidence
        ↓
Evidence Applicability
        ↓
Qualified Architecture Facts
        ↓
Evidence-Qualified Architecture Knowledge
        ↓
Question-Specific Deterministic Projection
        ↓
Agent / Human / Contextual Micro-Tool
        ↓
Reasoning / Inspection / Next Question
```

The longer-term product thesis is now sharper, but it preserves a hard semantic separation between
Current State and Intent:

```text
CURRENT-STATE PATH

Local Evidence
      ↓
Qualified Local Evidence Assessments
      ↓
Context-Bound Current-State Projection


INTENT PATH

Explicit Attributable Intent / Promises
      ↓
Applicable Intent Projection


ASSESSMENT PATH

Current-State Projection
      +
Applicable Intent Projection
      ↓
Qualified Current ↔ Intent Assessment
```

**Intent is never an input to Current-State qualification.**

In Promise-Theory terms, AIP does not define what autonomous components should promise. It preserves
explicit, attributable promises where available and separately assesses how evidence-qualified
cooperation relates to those promises in a given locality and time.

This does **not** mean that AIP should become a central planner, policy engine, migration orchestrator,
or architecture generator.

The durable product boundary is:

> **AIP establishes what can currently be supported about architecture from available evidence,
> preserves why that conclusion was reached, relates it to explicit attributable intent where
> available, and exposes the result in a form humans and agents can safely reason from.**

AIP does not decide what an agent should do. It does not promote inferred intent into architectural
truth. It does not treat missing evidence as proof of absence. It does not prescribe a migration
procedure merely because a Current State differs from explicit intent.

### 1.1 Core concept: Moldable Architecture Knowledge

"Moldable" describes the **question, projection, composition, and representation** of Architecture
Knowledge. It does not mean that facts become user-shaped or that qualification becomes negotiable.

```text
consumer may mold:
  question
  selection
  projection
  composition
  representation
  contextual tool

consumer may not mold:
  source evidence
  claim meaning
  qualification
  provenance
  snapshot identity
  limitations
```

The product rule is:

> **Architecture Knowledge should be moldable without making its evidence, qualification,
> provenance, or semantic meaning consumer-moldable.**

A recurring architecture question should move toward this lifecycle:

```text
architecture question
        ↓
qualified Architecture Knowledge
        ↓
deterministic projection
        ↓
inspectable answer
        ↓
optional contextual micro-tool
        ↓
reuse / refinement / next question
```

The AIP × Glamorous Toolkit reference integration validates an important version of this loop:
agents can select AIP capabilities, chain evidence requests, preserve AIP snapshot/provenance
semantics, and derive bounded ephemeral micro-tools while AIP remains responsible for establishing
the qualified Architecture Knowledge exposed by its contracts and the developer controls what
becomes permanent.

This concept does not make Glamorous Toolkit an AIP dependency. GT is a reference integration that
demonstrates the interaction model. The durable product idea is portable across agent clients,
engineering tools, REST consumers, and future interfaces.

The map-derived product distinction is:

> **Customers value a reliable Architecture Knowledge capability from which recurring questions can
> be answered deterministically. They do not need AIP's internal storage representation to become
> part of that contract.**

This does **not** make the semantic model disposable. Public architectural meaning — identity,
relation semantics, qualification, provenance, context, evidence linkage, limitations, and
assessment meaning — is part of the product contract even when its internal graph/database
representation is replaceable. Before v1.0 those semantics may still evolve through explicit,
versioned contract changes; "not replaceable" means they are not mere implementation detail, not
that they are already frozen.

### 1.2 DDD framing: Core Domain and supporting capabilities

In Domain-Driven Design terms, AIP's **Core Domain** is:

> **Establishing Evidence-Qualified Architecture Knowledge from heterogeneous, incomplete, and
> potentially conflicting system evidence.**

The core domain answers:

```text
What architectural claim can be established?
From which applicable evidence?
Under which identity, locality, time, and observation context?
With what qualification?
With what conflicts, uncertainty, or limitation?
With what provenance and derivation lineage?
```

This is distinct from the mechanics around it:

```text
CORE DOMAIN
Architecture Knowledge establishment and qualification
  - evidence applicability
  - identity and reconciliation semantics
  - claim qualification
  - conflict / uncertainty semantics
  - provenance / derivation meaning

PRODUCT CAPABILITY BUILT ON THE CORE DOMAIN
Deterministic question-specific projection
  - bounded ArchitectureAnswer contracts
  - reusable architecture questions
  - moldable composition / representation

SUPPORTING
Protocol-specific source discovery / ingestion mechanics,
syntactic normalization, snapshot plumbing, evaluation harnesses,
adapter implementation

GENERIC / STANDARDIZE WHERE PRACTICAL
MCP / HTTP transport, protocol libraries, database technology,
graph query mechanics, standard source APIs
```

A new source adapter is therefore not automatically new product capability. It becomes strategically
important when it enables a materially new class of qualified Architecture Knowledge, requires new
core-domain semantics, or unlocks a materially new deterministic architecture question.

The Core Domain is not the same thing as one Bounded Context. Current State, explicit Intent, and
Current↔Intent Assessment may require distinct semantic boundaries while still contributing to AIP's
overall Architecture Knowledge domain. In particular, Intent must remain outside Current-State
establishment.


### 1.3 Architecture Intelligence Platform — Strategic Wardley Map

The Wardley map makes the strategy above spatial: it connects the primary customer need to the
capabilities required to satisfy it and positions those capabilities by their stage of evolution.

![Architecture Intelligence Platform — Strategic Wardley Map](../images/wardley/aip-strategic-wardley-map.png)

The map should be read as an **AIP strategy map**, not as an AIP × Glamorous Toolkit integration map.
Glamorous Toolkit appears as an independent reference consumer that validates the moldable,
question-driven interaction model; it is not part of AIP's core value chain.

The map reinforces four investment conclusions:

- **differentiate in the Core Domain** — evidence applicability, identity/reconciliation,
  qualification, provenance/lineage, conflict handling, bounded uncertainty, and public
  Architecture Knowledge semantics;
- **differentiate at the product level** — deterministic, reusable, question-specific projections
  over qualified Architecture Knowledge;
- **standardize or consume mature capabilities** — MCP/REST transport, OpenAPI/OpenTelemetry/
  Kubernetes/Git interfaces, persistence technology, and graph/query plumbing where practical;
- **keep external exploration separate from semantic authority** — agents, GT, and other consumers
  may select questions, compose projections, and create contextual tools without becoming the source
  of evidence, qualification, or architectural meaning.

The strategic reading is therefore:

```text
customer need
    ↓
coding agent
    ↓
question-specific architecture answer
    ↓
Evidence-Qualified Architecture Knowledge
    ↓
qualification / reconciliation
    ↓
source adapters
    ↓
enterprise evidence sources
```

This is a **chain of needs**, not a decomposition of AIP's implementation. The horizontal position
expresses evolution from Genesis to Commodity; the vertical position expresses visibility to the
customer. Dashed links indicate interaction or usage rather than value-chain dependency.

---

## 2. Primary Customer Hypothesis

The initial product audience should remain explicit enough to prioritize work.

### Primary user

> **Platform engineering and architecture teams enabling coding agents to change multi-service
> systems.**

These teams need to let agents work across service boundaries without forcing the agent to
reconstruct architecture from source code, documentation, naming conventions, stale diagrams, or
incomplete telemetry.

The primary customer need is therefore not "buy an architecture graph" or "buy more agent
autonomy." It is to obtain reliable, bounded architecture knowledge at the point where an agent must
reason across service boundaries. AIP is an architecture-specific **Context Engineering**
capability: make established knowledge reusable at the moment of development and review rather
than making each agent infer it again. Operational runbooks, incident history, policy enforcement
and organizational decision records can be relevant adjacent context without automatically
becoming AIP-owned sources or authority.

### Secondary users

- senior software architects reviewing agent-generated changes;
- developers using coding agents in distributed systems;
- platform teams exposing architecture context through MCP or other machine interfaces;
- engineering organizations building deterministic guardrails around probabilistic development;
- teams managing long-running architecture evolution across environments, regions, and deployment
  topologies.

These remain secondary until the primary workflow is validated.

---

## 3. Initial Wedge Workflow

The first high-value workflow remains:

> **Before a coding agent changes a service, provide bounded, evidence-qualified dependency context;
> after the change is deployed or otherwise observable, independently establish the resulting
> architecture state again.**

This is a question-specific context workflow: *What should be inspected before editing this
service?* An AIP answer must expose supported relationships, evidence, snapshot/observation
context and limits. An authoring agent and an independent reviewing agent can consult the same
premises, but review findings, policy judgments and decisions do not thereby become AIP
Architecture Knowledge.

Conceptually:

```text
Engineering task
     ↓
Agent identifies affected service(s)
     ↓
AIP: dependency / drift / evidence context
     ↓
Agent plans and changes software
     ↓
Tests / deployment / runtime evidence
     ↓
AIP reconstructs current architecture state
     ↓
Architect / agent inspects what is now established
```

AIP does **not** claim that the agent caused the resulting state merely because the state changed
after the agent's work.

Post-change verification establishes:

```text
what the architecture state is now
```

not automatically:

```text
why it changed
who caused it
whether the change was intentional
```

Causal attribution requires separate evidence. Independent evaluation also does not guarantee
independent evidence: re-reading an agent-edited declaration establishes what is declared, not that
the implementation behaves accordingly. The source-independence and verification-scope boundary in
§22 applies to this workflow.

The longer-term wedge extension is:

```text
Before change:
  establish Current State
  +
  retrieve applicable explicit intent
  +
  identify qualified difference

After change:
  re-observe
  +
  re-assess
  +
  establish the new qualified difference
```

This remains advisory and read-only.

---

## 4. Product Evolution Thesis

AIP should evolve by deepening the quality of architecture knowledge before broadening its authority.

The sequence is:

```text
1. Establish architecture facts from evidence.
2. Qualify those facts under explicit observation context.
3. Preserve provenance and derivation.
4. Establish facts locally before projecting them globally.
5. Extend qualified Current State to API exposure and consumption without conflating interfaces,
   technical implementation, products, consumers, and business capabilities.
6. Introduce explicit attributable intent as a separate domain.
7. Assess Current State against applicable intent.
8. Represent architecture evolution as context-bound trajectories.
9. Only then consider transformation reasoning.
```

The progression deliberately separates:

```text
KNOW
what can currently be established

from

INTEND
what has explicitly been promised / required

from

ASSESS
how Current State relates to Intent

from

TRANSFORM
how the system might safely change
```

AIP should not collapse these stages into one graph or one AI-generated answer.

Product evolution should also be visible as an expansion of the **architecture-question space**.
A capability release should be explainable in terms of a materially new recurring question that AIP
can answer safely and deterministically, not merely in terms of internal machinery added to the
platform.

```text
v0.5  Where is this service deployed?
      Which deployment identities are unresolved?

v0.6  Where is this dependency established?
      Does this relation differ by supported locality?

v0.7  How are APIs exposed and consumed, and what can the available evidence establish
      about those relationships?

v0.8  What explicit architecture intent applies here?

v0.9  Where does Current State differ from applicable Intent?
```

The technical model remains essential, but the product roadmap should explain **what new question
becomes safely answerable** because of that model.

---

## 5. Customer Outcome Hypotheses

AIP should be evaluated against customer outcomes, not only internal semantic elegance.

The current hypotheses are:

1. **Reduce unsupported architectural assumptions before implementation.**
2. **Reduce senior-engineer time spent reconstructing cross-service architecture during review.**
3. **Make architecture questions reproducible across humans, agents, and tools.**
4. **Surface uncertainty early instead of allowing agents to convert missing context into plausible
   architecture.**
5. **Provide an independent post-change architecture check without relying on the agent's own report
   of success.**
6. **Reduce ambiguity between expected evolution and unintended architecture drift.**
7. **Allow teams to express partial architectural intent without maintaining a complete target-state
   blueprint.**
8. **Make locality- and time-specific differences visible instead of flattening them into one global
   architecture view.**
9. **Reduce the cost of turning a recurring architecture question into a reusable deterministic
   projection or contextual tool.**
10. **Allow agents to derive useful architecture lenses without allowing agent-generated content to
    become Architecture Knowledge.**
11. **Let REST, MCP, and external moldable tools consume the same semantic knowledge without
    duplicating qualification logic.**
12. **Reduce repeated manual cross-source investigation and dependence on individual experts for
    recurring architecture questions, without concealing unresolved evidence.**
13. **Enable authors and independent reviewers to inspect the same qualified architecture premises
    without treating either agent's review judgment as an established architecture fact.**

These are hypotheses to validate, not claims that AIP has already demonstrated these business
outcomes.

---

## 6. Product Success Measures

AIP needs both semantic-quality metrics and workflow-value metrics.

### 6.1 Semantic quality

Examples:

```text
false supported-claim rate
qualification disagreement rate
unresolved-identity rate
unsupported-relation rate
deterministic replay equality
evidence/provenance resolution rate
snapshot reproducibility
cross-context projection consistency
local-assessment reconciliation consistency
```

Desired direction:

```text
false supported claims -> zero in qualified scenarios
cross-surface semantic mismatches -> zero
unexplained nondeterminism -> zero
silent locality/context loss -> zero
```

### 6.2 Agent-context quality

Measure:

```text
percentage of returned claims with:
- qualification
- applicable evidence
- snapshot identity
- observation context where relevant
- locality/context scope where relevant
- explicit limitations

context truncation frequency
context completeness status
excluded/unresolved claim count
```

### 6.3 Workflow value

For pilot users, measure:

```text
time to answer "what does this service depend on?"
time spent reconstructing architecture during review
repeated cross-source searches and expert clarification for the same architecture question
author/reviewer ability to resolve the same evidence and understand unresolved limitations
unsupported assumptions surfaced before implementation
post-change discrepancies surfaced independently
architecture-sensitive agent tasks that query AIP before acting
time to identify Current ↔ Intent differences
time to distinguish local deviation from system-wide deviation
time from recurring architecture question to deterministic reusable projection
reuse frequency of promoted architecture questions / projections
recurring questions answered from deterministic Architecture Knowledge rather than agent reconstruction
```

Metrics should remain small enough to support actual product decisions.

### 6.4 Pilot decision gate

Validate the initial workflow on a bounded set of representative architecture tasks with and without
AIP, using comparable source access and independently authored expected results. Record the task
set, baseline, and success/stop thresholds before evaluating the pilot.

Measure jointly:

- supported-claim correctness and the proportion of questions answered usefully;
- unresolved and unsupported outcomes, including whether abstention was justified;
- total engineering time, including setup, source maintenance, identity mapping, and clarification;
- independently detected post-change discrepancies and false alarms.

A lower false-claim rate achieved only by returning more unresolved answers does not establish product
value. Reduced investigation/review time must be evaluated against the added maintenance burden.
Compare workflows with equivalent source access, measuring both time to a useful qualified answer
and the proportion of questions that remain unresolved. A faster but misleading answer is not
product success.

Pilot criteria must support an explicit continue, narrow, defer, or stop decision. Planned releases
remain subject to these product-value gates as well as semantic and implementation qualification;
failed gates require a documented scope or roadmap decision. This doctrine does not claim that a
pilot has already passed or prescribe unvalidated numerical thresholds.

---

## 7. Core Product Question

AIP's current core epistemic question remains:

> **What architecture can we currently support from available evidence, and what are the limits of
> that knowledge?**

The longer-term question becomes:

> **What architecture is currently established here and now, what explicit intent applies here and
> now, and what does the evidence support about the difference?**

This is intentionally weaker and more defensible than claiming a universal architecture "truth
layer."

The preferred product concept is:

> **Moldable Architecture Knowledge**

with the semantic foundation:

> **evidence-qualified Architecture Knowledge**

not:

> technical-architecture truth layer

A complementary product-design question is:

> **Which recurring architecture question can AIP make deterministic next, while preserving the
> evidence, qualification, context, and limits of the answer?**

---

## 8. Durable Principles

1. **Evidence before inference.**
2. **Correct but incomplete is better than complete-looking but wrong.**
3. **Non-observation is not absence.**
4. **An agent may reason over architecture, but must not become the source of architectural truth.**
5. **A relationship being present in a graph does not by itself qualify an architecture claim.**
6. **Traceability proves that a chain exists; qualification determines what that chain supports.**
7. **Different evidence modes must not be collapsed into one generic notion of truth.**
8. **Intent, declaration, and observation are distinct semantic domains.**
9. **Architectural intent is established only by explicit, attributable intent artifacts.**
10. **Inferred intent is a hypothesis, never an instruction or authoritative intent source.**
11. **Explicit promises and observed cooperation are distinct: observing cooperation does not prove
    that the cooperation was promised or intended.**
12. **A promise assessment is context-bound: whether evidence supports a promise depends on locality,
    time, observation context, applicable evidence, and the assessment rule.**
13. **Current State must be derivable entirely from current-state evidence and qualification rules;
    Intent must never be an input to Current-State establishment.**
14. **AIP establishes architecture locally before projecting it globally.**
15. **System-level Current-State views are context-bound projections of qualified evidence
    assessments. Claims about cross-boundary interactions require their own evidence and
    qualification rules. Intent and alignment assessments remain separate knowledge domains.**
16. **Locality and connectivity are independent: WHERE something is does not establish HOW it
    interacts.**
17. **Service identity, Bounded Context, deployment unit, and team boundary are distinct concepts.
    They may align, but that alignment is itself an architectural claim requiring evidence or
    explicit intent. API product, API contract, operation, gateway route/service, application
    service, consumer, and business capability also retain distinct meanings; an association is
    not automatically identity.**
18. **Emergent behavior may establish Current State; it does not establish Intent.**
19. **Current State and Intent may both be partial, local, and time-bound.**
20. **Desired architecture should be declarative and partial rather than encoded as a migration
    script.**
21. **Assessment must preserve evidence, context, time, rule version, provenance, and limitations.**
22. **Agent-facing convenience must not weaken deterministic semantics.**
23. **Advisory, read-only architecture intelligence is preferred over policy enforcement in the AIP
    core.**
24. **AIP's semantic contracts should remain portable across model vendors, agent frameworks, coding
    agents, and integration transports.**
25. **Transformation planning is downstream from qualified Current State, explicit Intent, and
    qualified difference.**
26. **Architecture Knowledge may be molded in question, projection, composition, and representation;
    evidence, qualification, provenance, and semantic meaning are not consumer-moldable.**
27. **When a recurring architecture question can be answered deterministically, prefer a reusable
    projection/tool over repeatedly asking an agent to reconstruct the answer.**
28. **Differentiate where Architecture Knowledge is established; standardize where it is transported
    and sourced.**
29. **Internal representation is replaceable; public architectural meaning is a versioned semantic
    contract, not an implementation detail.**
30. **The product is neither the graph nor a bag of fixed answers: it is a reliable Architecture
    Knowledge capability whose qualified semantics support reusable deterministic projections.**

---

## 9. Epistemic Model

AIP should keep Current State, Intent, and Current↔Intent assessment on separate semantic paths.

### 9.1 Current-state evidence modes

Current State may be established only from evidence modes that describe or support the system as it
is currently declared, implemented, deployed, or observed:

```text
DECLARED
OBSERVED
SOURCE_DERIVED / IMPLEMENTATION_DERIVED
INFRASTRUCTURE_DERIVED
```

These modes may differ in authority and applicability, but all belong to the **Current-State path**.

### 9.2 Intent artifacts are a separate normative source domain

Explicit intent artifacts do **not** participate in Current-State qualification.

Examples may include:

```text
OpenAPI Overlay
AsyncAPI-compatible explicit intent artifact / extension
standalone AIP intent artifact
OpenSpec
machine-readable ADR assertion
other attributable normative specification
```

They establish candidate **Intent Assertions**, not Current-State facts.

The separation is:

```text
Current-State Evidence
        ↓
Current-State Assessment / Projection

Explicit Intent Artifact
        ↓
Intent Assertion / Intent Projection
```

Only a later advisory assessment may compare the two.

### 9.3 Current-state observation context

Current-state evidence may be scoped by:

```text
snapshot identity
environment
observation window
source revision / source observation
region
cluster / namespace
tenant
service version
deployment identity
other explicitly supported locality dimensions
```

AIP must not expose a locality dimension unless it has evidence and semantics to support it.

### 9.4 Intent applicability

Intent has its own applicability dimensions, independently of runtime observation windows:

```text
scope
environment / region / tenant / version where explicitly stated
effective_from
effective_until
source revision
authority / provenance
```

An intent effective interval and an evidence observation window may overlap, but they are never the
same field and must never be silently substituted for one another.

### 9.5 Important distinctions

```text
observed repeatedly
    ≠
intended

declared
    ≠
observed

implemented
    ≠
organizationally approved

not observed
    ≠
absent

co-located
    ≠
dependent

globally projected
    ≠
universally true

agent-inferred target
    ≠
explicit intent

current-state evidence
    ≠
intent evidence

observation window
    ≠
intent effective interval
```

---

## 10. Qualified Local Evidence Assessment

The key semantic unit for establishing Current State should be the **Qualified Local Evidence
Assessment**.

It is intentionally independent of Intent.

A conceptual form is:

```text
EvidenceAssessment(
    subject,
    assertion,
    context,
    observation_window,
    applicable_evidence,
    rule_version,
    qualification,
    provenance,
    limitations
)
```

There is **no `applicable_intent` field** in this assessment.

The governing rule is:

> **AIP qualifies what current-state evidence establishes within an explicit scope before projecting it into a broader
> Current-State view.**

Example:

```text
EU / prod:
  OrderService -> PricingService
  ESTABLISHED

India / prod:
  OrderService -> LegacyPricingService
  ESTABLISHED
```

These evidence assessments can coexist without contradiction because their localities differ.

Any later question about whether either state conforms to explicit intent belongs to a separate
Current↔Intent assessment and must not alter these Current-State results.

---

## 11. Current-State Architecture Projection

A system-level Current-State view should be a deterministic projection over applicable **Qualified
Local Evidence Assessments only**.

Conceptually:

```text
CurrentState(context C, snapshot S)
    =
deterministic projection(
    applicable QualifiedLocalEvidenceAssessments
)
```

The projection must preserve:

```text
which evidence assessments contributed
which localities were included
which localities were excluded
which evidence was unresolved
which qualification / projection rules were used
whether the projection is complete
```

Intent assertions must not influence this projection.

A projection must not silently transform:

```text
"established in locality A"
```

into:

```text
"true everywhere"
```

The Current-State path is therefore:

```text
Current-State Evidence
          ↓
Qualified Local Evidence Assessment
          ↓
Current-State Architecture Projection
```

Intent remains on a separate path until an explicit advisory comparison is requested.

### 11.1 Composition boundary

Local means an explicit scope of applicability, not necessarily one service, team, or deployment.
An assessment may span several components when the evidence and qualification rule support that scope.

Projection may select and reconcile existing qualified claims. It must not silently create stronger
claims. Any new cross-boundary or system-level claim requires its own qualification rule, applicable
evidence, compatible identities and contexts, temporal compatibility, and explicit coverage limits.
For example, independently established `A -> B` and `B -> C` relations do not by themselves establish
one causal runtime flow `A -> B -> C`. Likewise, locally satisfied promises do not establish an
end-to-end business outcome without a rule and evidence that support that outcome.

Conflicting, excluded, stale, or unresolved inputs remain visible in the projection. Intent and
Current↔Intent assessments are not derivable from Current-State projection alone.

---

## 12. Locality, Connectivity, and Emergence

AIP should keep two structural dimensions independent:

```text
WHERE something is
        ≠
HOW it interacts
```

Examples of place/locality:

```text
region
cluster
namespace
workload
process
tenant
bounded execution context
```

Examples of connectivity/cooperation:

```text
CALLS
SENDS
RECEIVES
CONFORMS_TO
provides / accepts capability
```

AIP must not infer interaction from co-location.

AIP must not infer absence of interaction from separation.

AIP must also keep technical, semantic, deployment, and organizational boundaries distinct:

```text
Service
    ≠
Bounded Context
    ≠
Deployment Unit
    ≠
Team Boundary
```

These concepts may align in a specific system, but the alignment is not assumed. It must itself be
supported by evidence or explicit intent appropriate to that claim.

This distinction becomes especially important with Kubernetes and broader infrastructure discovery.

### Emergent behavior

Operational architecture may emerge from local interactions even when nobody explicitly declared
the resulting global topology.

Therefore:

```text
emergent observed behavior
    -> may support Current State

emergent observed behavior
    -> does not establish Intent
```

AIP may expose higher-order emergent architecture only when the aggregation semantics are
deterministic, evidence-backed, and independently testable.

Probabilistic pattern recognition may propose a hypothesis, but must not directly create canonical
architecture truth.

---

## 13. Evidence Applicability

AIP should not assign broad authority to a source category such as "OpenTelemetry" or "Kubernetes."

Applicability should be explicit at the level of:

```text
artifact type
    ×
claim kind
    ×
mapping rule/version
    ×
context/locality applicability
```

Conceptually:

```text
OpenAPI operation
    + DIRECT_HTTP_CONTRACT claim
    + openapi.operation.v2 mapping
        -> applicable declared evidence

OTel span using supported HTTP semantic conventions
    + RUNTIME_HTTP_INTERACTION claim
    + otel.http.client.v3 mapping
        -> applicable observed evidence

Kubernetes workload identity
    + WORKLOAD_LOCALITY claim
    + kubernetes.workload.v1 mapping
        -> applicable infrastructure-derived evidence

explicit intent artifact
    + PROVIDES_CAPABILITY assertion
    + intent.promise.v1 mapping
        -> applicable intent evidence
```

AIP should ask:

> **What claim kind does this specific evidence, through this mapping rule, in this context, entitle us
> to support?**

It should not infer organizational authority, business ownership, or architectural intent merely
from technical source type.

---

## 14. Qualified Current State

AIP's current strategic center remains the Current-State path:

```text
Available Current-State Evidence
       ↓
Applicability
       ↓
Canonical Architecture Facts
       ↓
Qualified Local Evidence Assessments
       ↓
Current-State Projection
       ↓
Evidence-Qualified Current State
```

This pipeline must be executable without loading, resolving, or evaluating any Intent artifact.

Current State should preserve:

- unresolved identities;
- unsupported semantics;
- conflicting evidence;
- observation context and observation window;
- locality;
- qualification;
- provenance;
- rule versions;
- limitations;
- projection completeness.

AIP should prefer returning less information over returning a plausible-looking relation that the
evidence does not justify.

The invariant is:

> **With evidence, evaluation context, identity resolution, and mapping, qualification, and projection
> rule versions held constant, adding, removing, or changing Intent must not change established
> Current State.**

---

### 14.1 API-Aware Current State — planned v0.7

AIP's planned API Landscape capability applies the **same Current-State qualification path** to
how APIs are exposed and consumed, rather than creating a vendor-specific gateway graph or a
general-purpose enterprise catalog.

> **How are APIs exposed and consumed, and what can the available evidence establish about those
> relationships?**

The first question-specific validation slice relates *configured* consumer/API access to
independently *observed* consumer-attributed usage in an explicit environment/window. A configured
registration, gateway ACL membership, or subscription establishes only what that source actually
asserts. It does not by itself establish a runtime call, an approved architectural requirement, or
business intent. No matching measurement is not proof of non-use without applicable telemetry
coverage and supported attribution.

A source-neutral semantic contract must distinguish API contract and version, API operation,
gateway route/service, application service, gateway consumer, configured-access relationship,
observed interaction, and any separately evidenced API product, business capability, owner, or
authorization boundary. Similar names, URLs, graph proximity, or shared deployment do not establish
entity equivalence or business classification. A gateway route may expose an operation and forward
to an application service while remaining a different entity from both.

The first real-source validation proposes Kong configuration and consumer-attributed measurements,
with explicit inventory/revision, provenance, snapshot/replay, identity/reconciliation, and coverage
rules. Kong source semantics must be translated into AIP's own evidence-qualified model. Other
gateways, OpenAPI/AsyncAPI, repositories, CI/CD results, architecture models, and further business
sources are subsequent **question-driven adapter candidates**, not automatic coverage claims or
requirements of the first v0.7 slice.

The initial question remains wholly within **Current State**. Canonical contract authority,
product/capability ownership, organizational accountability and authorization must be independently
evidenced where they are asserted, not inferred from technical metadata. Formal Intent remains a
separate downstream path; security-policy assessment belongs downstream of independently established
Current State and applicable Intent.

## 15. Explicit Intent

Agent-readiness creates pressure to add architectural intent. AIP should support this only with a
strict authority model. Configured API/gateway registration remains evidence of Current State;
it does not become governing Intent merely because access was granted or usage was observed.

The preferred separation is:

```text
WHAT CAN CURRENTLY BE ESTABLISHED?
Evidence -> Qualified Current State

WHAT HAS BEEN EXPLICITLY PROMISED / REQUIRED / INTENDED?
Explicit attributable intent artifacts -> Intent Assertions

Qualified Current State
        +
Applicable Explicit Intent
        ↓
Advisory Architecture Assessment
```

### 15.1 Intent authority rule

> **Inference may propose architectural intent. Explicit attributable artifacts establish candidate
> assertions; applicable authority and lifecycle evidence determine whether they are governing Intent.**

AIP should not establish intent from:

```text
runtime frequency
code structure
naming
co-location
probabilistic interpretation
agent-generated rationale
```

An inferred intent is a hypothesis, not an instruction.

Attribution identifies who authored an assertion; authority establishes whether that actor may make
that assertion for the stated scope. They must not be conflated. A requirement imposed on a service,
a capability offered by it, and a promise made by its accountable owner are distinct assertion kinds.
One does not imply the others.

Intent applicability must account for externally evidenced approval status, authority scope,
exceptions, effective intervals, revocation, and explicit supersession. A draft or an attributable
but unauthorized assertion must not silently become governing Intent. An authorized exception must
identify the assertion and scope it qualifies.

When an enterprise requirement conflicts with a local promise, AIP must preserve both and report an
unresolved authority/applicability conflict unless an explicit, attributable resolution rule or
exception establishes precedence. AIP must not invent hierarchy from source format or specificity.

AIP consumes authority and lifecycle evidence; it does not own approvals or decide who should have
authority. Exact fields and conflict outcomes require qualification in the Intent specification.

### 15.2 Promise-oriented interpretation

Promise Theory provides a useful semantic interpretation of explicit architectural intent without
making Promise Theory itself a required AIP implementation model.

The key separation is:

```text
EXPLICIT INTENT ASSERTION
an attributable requirement, capability offer, capability acceptance, constraint, or promise

        ≠

OBSERVED COOPERATION
what available evidence establishes that components actually did

        ≠

AIP ASSESSMENT
what that evidence supports about the relationship between promise and cooperation
in a given locality and time
```

A promise is a distinct Intent Assertion with an explicit promiser, promised behavior or capability,
conditions, and an identified recipient or audience where applicable. A requirement expressed by a
consumer does not establish a provider's promise to satisfy it. Offers, acceptances, and requirements
retain their own assertion kinds and attributable actors; none is silently converted into another.

AIP does not assign promises to autonomous components. It preserves explicit, attributable promise
artifacts where available, applies the authority and lifecycle rules in §15.1, and assesses how the
observed or declared cooperation relates to the applicable promises.

AIP should therefore prefer statements of the form:

```text
Under context C, during time T, using evidence E and rule R,
AIP assesses promise P as qualification Q.
```

over absolute statements such as:

```text
promise P is kept
```

unless the semantics of `kept` are themselves explicitly defined and context-bound.

The corresponding doctrine rule is:

> **AIP distinguishes explicit promises from observed cooperation. Evidence may establish how
> components cooperate; only explicit attributable artifacts may establish what they intended or
> promised.**

And the strategic formulation is:

> **AIP establishes evidence-qualified cooperation independently, then separately assesses its
> relationship to explicit promises in the locality and time where those promises apply.**

### 15.3 Source-neutral intent semantics

AIP should standardize the **meaning** of architectural intent, not require every ecosystem to author
intent using the same format.

Potential carriers may include:

```text
OpenAPI Overlay
AsyncAPI x-extensions or another explicit AsyncAPI-compatible mechanism
standalone AIP intent artifacts
OpenSpec
ADRs with machine-readable explicit assertions
other versioned intent sources
```

The durable semantic layer should normalize these into source-neutral assertions such as:

```text
promise
capability offered
capability accepted
constraint
required relationship
prohibited relationship
scope
effective_from
effective_until
provenance
```

Intent applicability is independent of Current-State observation context. An intent assertion may be
effective during an interval while the Current-State evidence used to assess it comes from a
different, explicitly recorded observation window. Recording both intervals is necessary but not
sufficient: their use together must pass an explicit temporal-compatibility rule (see §16).

OpenAPI Overlay should therefore be treated as **one carrier**, not as the AIP intent model.

The absence of a standardized AsyncAPI Overlay equivalent is not a strategic blocker if AIP keeps
intent semantics source-neutral.

### 15.4 Declarative intent

Desired architecture should answer:

```text
WHAT SHOULD HOLD?
```

not:

```text
WHICH SEQUENCE OF IMPLEMENTATION STEPS MUST BE EXECUTED?
```

AIP should not require a complete future-state graph.

> **Explicit but partial intent is better than an inferred complete target architecture.**

---

## 16. Qualified Current ↔ Intent Assessment

AIP's longer-term differentiating capability is not merely "Desired State support."

It is a **separate second-order assessment** over an already-established Current State and an
independently established Intent projection.

The dependency direction is:

```text
Current-State Evidence
        ↓
Qualified Local Evidence Assessments
        ↓
Current-State Projection
                                                   +--> Current ↔ Intent Assessment
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

A conceptual comparison form is:

```text
IntentAlignmentAssessment(
    current_state_ref,
    current_assessment_refs,
    intent_assertion_ref,
    intent_projection_ref,  // identifies the versioned applicable Intent projection
    evaluation_context,
    evaluated_at,

    current_observation_context: {
        observation_window,
        snapshot_id
    },

    intent_applicability: {
        effective_from,
        effective_until,
        scope
    },

    assessment_rule_version,
    qualification,
    provenance,
    limitations
)
```

### Temporal comparability

Assessment requires explicit temporal compatibility between evidence and Intent, including relevant
service/deployment versions. Evidence from before an Intent became effective does not by itself
establish present compliance or violation. For partially overlapping windows, an assessment may use
only a qualified overlapping portion; if the evidence cannot be separated safely, the comparison
remains inconclusive. Extrapolation requires a separately qualified rule and explicit limitations.

Incompatible, stale, or insufficient temporal coverage must produce an inconclusive assessment rather
than an assertion that a promise is kept or broken. Release-specific specifications must freeze the
compatibility and coverage rules before qualification fixtures are authored.

The two temporal dimensions remain independent:

```text
observation_window
    = when Current-State evidence was observed

effective_from / effective_until
    = when the explicit Intent applies
```

For a given evaluation context:

```text
Current(C, S)
    =
projection of applicable Qualified Local Evidence Assessments

Intent(C, t)
    =
projection of explicit Intent Assertions applicable at t

Difference(C, S, t)
    =
qualified assessment of Current(C, S) versus Intent(C, t)
```

Possible future outcomes may distinguish:

```text
intent established
intent not yet established
explicit contradiction
conflicting evidence
unexpected observed relationship
insufficient evidence
intent not applicable in this context
```

Terms such as `expected transition` require temporal/historical semantics and are therefore deferred
until trajectory support exists.

Exact public vocabulary must be frozen only after deterministic truth tables exist.

AIP must not reduce this to generic PASS / FAIL compliance.

---

## 17. Architecture Trajectories — Beyond v1.0 Under the Current Roadmap

Architecture trajectories remain a valuable long-term concept, but they are **not part of the
pre-v1.0 roadmap under the current `ROADMAP.md`**.

The current roadmap explicitly places architecture trajectories in the unscheduled future beyond
v1.0.

A trajectory also requires capabilities that current snapshot binding does not provide.

At minimum, AIP would first need a deliberate historical-state model such as:

```text
durable historical assessment / snapshot retention or import
stable identity across historical states
historical evidence and provenance retention
versioned intent history and effective intervals
deterministic temporal ordering
trajectory continuity rules
historical query semantics
retention / compaction policy
```

Current snapshot identifiers bind answers to the current qualified state; they are not by themselves
a historical architecture store.

Only after those prerequisites exist should AIP ask:

> **How is the evidence-qualified architecture evolving relative to the explicit intent that applied
> in each context and time?**

A future trajectory capability might then distinguish:

```text
unexpected drift
expected migration phase
intent not yet realized
intent changed
local deviation
system-wide deviation
```

Until then, AIP should compare Current State with the Intent applicable to the selected evaluation
time without claiming a trajectory across historical states.

---

## 18. Distributed Local Assessment — Post-v1.0 Deployment Hypothesis

If qualified local assessment becomes a core semantic unit, some evidence collection and
deterministic qualification may naturally move closer to the locality where the evidence has
meaning.

The **semantic concept** of local assessment is required before v1.0, but physically distributing assessment execution toward services/workloads is a **beyond-v1.0, unscheduled deployment hypothesis** under the current roadmap.

Conceptually:

```text
Service / Workload locality
        │
        ├── local contracts
        ├── runtime identity
        ├── telemetry
        └── deployment context
                │
                ▼
       Local Architecture Assessor
                │
                ▼
 Qualified Local Evidence Assessment
                │
                ▼
            Central AIP
                │
        reconcile / compose
                │
                ▼
    Current-State Projection

Explicit Intent remains a separate input to a later
Current ↔ Intent assessment.
```

### 18.1 Local versus global responsibility

Local assessment can answer:

```text
What can be established from evidence available here?
```

Central composition can answer:

```text
What follows when applicable local assessments are reconciled across localities?
```

The local assessor should emit assessment plus evidence lineage, not only conclusions.

### 18.2 Deployment form must remain flexible

"Local assessor" does not imply "sidecar" as the only topology.

Possible deployment forms include:

```text
sidecar
node agent
DaemonSet
OTel Collector processor / extension
local gateway
standalone local service
```

### 18.3 Failure boundary

The local assessor should not become part of the application's functional execution path.

Preferred failure mode:

```text
local assessor unavailable
    -> application continues
    -> architecture evidence / assessment for that locality degrades
```

This preserves AIP as architecture intelligence infrastructure rather than a service mesh or runtime
application dependency.

---

## 19. Derivation Lineage

Derivation lineage should be modeled as a **directed acyclic graph (DAG)** rather than a linear chain
because one result may depend on several independent evidence items, mappings, qualification rules,
contexts, and projections.

The two assessment paths must have separate lineage structures.

### 19.1 Current-State lineage

A Current-State claim or projection depends only on Current-State evidence and Current-State rules.

```text
Current-State Claim / Projection
├── Qualified Local Evidence Assessment(s)
│   ├── Assertion
│   ├── Applicable Current-State Evidence
│   │   ├── source artifact(s)
│   │   └── evidence mapping rule + version
│   ├── Observation Context / Locality
│   ├── Observation Window
│   ├── Qualification Rule + Version
│   ├── Provenance
│   └── Limitations
├── Current-State Projection Rule + Version
├── Snapshot Identity
└── Projection Completeness / Limitations
```

**Intent is not a dependency anywhere in this DAG.**

AIP should be able to reconstruct:

```text
which Current-State evidence was used
which mapping rule interpreted it
which local evidence assessment was produced
which qualification rule evaluated it
which observation context / locality / window applied
which projection rule produced the Current-State view
which snapshot the result belongs to
which limitations or unresolved items remain
```

### 19.2 Current ↔ Intent assessment lineage

A Current↔Intent assessment is a separate second-order derivation. It consumes two independently
established inputs:

```text
Current-State Projection ──────────────┐
                                       ├──► Qualified Current ↔ Intent Assessment
Applicable Intent Projection ──────────┘

Current-State Projection lineage:
  evidence-only; established independently

Applicable Intent Projection lineage:
  ├── Versioned Intent projection identity
  ├── Explicit Intent Assertion(s) + source revisions
  ├── Intent source artifact(s)
  ├── Intent mapping rule + version
  ├── Intent scope + evaluation context
  ├── effective_from / effective_until
  ├── Authority evidence + authority scope
  ├── Lifecycle evidence (approval status, exceptions, revocation, supersession)
  ├── Applicability / precedence rule identity + version
  ├── Unresolved authority / applicability conflicts and limitations
  └── Intent provenance

Qualified Current ↔ Intent Assessment
├── Current-State projection reference
├── Current-State lineage reference(s)
├── Applicable Intent projection reference
├── Intent lineage reference(s)
├── Evaluation Context
├── Assessment Rule + Version
├── Qualification
├── Provenance
└── Limitations
```

Each applicable Intent projection must have a versioned identity bound to the exact assertion
revisions, authority and lifecycle evidence, evaluation context, and mapping/applicability rule
versions used. These dependencies must be explicitly referenced in its lineage rather than left
implicit in a generic provenance field. Missing or unresolved authority evidence remains a limitation,
not an assumed approval.

A Current↔Intent assessment must reference that exact projection identity. For example, revoking an
exception must produce a distinguishable Intent projection even when the assertion text and Current
State remain unchanged. Resolving an assessment's lineage must not silently substitute the latest
authority or lifecycle status for the version used at evaluation. Historical retrieval and retention
remain governed by the roadmap; where prior dependencies are unavailable, AIP must explicitly report
that the earlier assessment cannot be reproduced rather than claim historical replay.

The assessment DAG may reference both paths, but it must never create a back-edge from Intent into
Current-State establishment.

This means:

```text
Intent ───────────────X──► Current-State Assessment

Current State ────────┐
                      ├──► Current ↔ Intent Assessment
Intent Projection ────┘
```

Stable rule identity/version is essential in both DAGs. Evidence or intent provenance alone is
insufficient to reproduce why AIP produced a specific result.

---

## 20. Agent-Ready Structured Context

**Context Engineering is the customer-facing application of AIP's Core Domain.** An agent-ready
engineering environment needs accessible architectural premises whose source, claim meaning,
applicability, qualification, and limitations remain inspectable. AIP supplies this
architecture-specific substrate as **bounded, deterministic, moldable context**, without assuming
responsibility for general agent memory, task reasoning or organizational execution governance.

The Context Engineering pattern in Davis et al., *Agentic AI and Code Reviews* (Fall 2026,
pp. 17–19) also calls for operational history, prior decisions, policies and ownership. That is
the broader engineering-context need, not evidence that AIP currently ingests every such source.
Planned explicit Intent (v0.8), separate qualified Assessment (v0.9), and unscheduled externally
sourced Decision History preserve distinct semantic and authority paths.

AIP should become more agent-ready by assembling **bounded, deterministic, moldable context**, not
by taking over task reasoning.

The agent may decide:

```text
what it needs to know
which supported question to ask
which evidence to follow
which returned facts to compose
which contextual lens would make the answer easier to inspect
```

AIP decides:

```text
what the evidence and explicit intent support
what qualification applies
which limitations remain
which snapshot/context the answer belongs to
```

Every returned claim or assessment must retain:

```text
qualification
applicable evidence references
applicable intent references where relevant
snapshot / trajectory identity
observation context
locality/context scope
rule version where relevant
limitations
```

The context envelope must expose completeness and truncation explicitly.

A generic unbounded graph-neighborhood dump is not an acceptable agent-context API. Neither is a
design in which an agent reconstructs qualification from raw graph facts.

The desired interaction is:

```text
agent chooses question
        ↓
AIP returns qualified Architecture Knowledge
        ↓
agent may follow provenance or compose a bounded lens
        ↓
external tool may render an ephemeral contextual micro-tool
        ↓
human controls permanent promotion
```

The [AIP × Glamorous Toolkit reference integration](reference-integrations/glamorous-toolkit/README.md)
has validated this interaction pattern through agent-selected MCP calls, evidence chaining, and
bounded agent-derived ephemeral micro-tools.

---

## 21. MCP and Interface Doctrine

MCP and REST are adapters, not the product.

The durable product boundary is:

```text
evidence-qualified Architecture Knowledge
        +
question-specific deterministic projections
        +
stable public architectural meaning
```

The storage representation beneath that boundary is replaceable. The semantic contract above it is
not incidental implementation detail.

The v0.5 public topology is intentionally simple:

```text
                    ArchitectureIntelligenceService
                              |
              +---------------+---------------+
              |                               |
             REST                     standard negotiated MCP
       general integrations                agent clients
```

The deterministic evaluator invokes `ArchitectureIntelligenceService` directly as the
transport-independent qualification path. No public adapter owns Architecture Knowledge semantics.

MCP should remain as stable and boring as practical. REST should remain a general deterministic
integration surface. Future product evolution should appear primarily through typed
architecture-intelligence contracts and new safely answerable questions, not repeated transport
redesign.

The strategic rule is:

> **Differentiate where Architecture Knowledge is established; standardize where it is transported
> and sourced.**

That means transport protocols, standard source interfaces, graph/database technology, and similar
plumbing should be consumed as mature capabilities wherever practical. AIP-specific investment
belongs primarily in evidence semantics, identity/reconciliation, qualification, provenance,
uncertainty handling, and deterministic projections.

### 21.1 Portability and composability

AIP should remain useful across model vendors, coding agents, agent harnesses, and integration
frameworks.

The durable boundary is:

```text
Model
  ≠
Agent Harness
  ≠
Architecture Context
  ≠
Discovery / Evidence Source
  ≠
Transport Protocol
```

AIP's architecture semantics must therefore not depend on one LLM vendor, one coding-agent product,
one agent framework, or one MCP client implementation.

Open and replaceable integration boundaries should allow:

```text
model changes
agent-framework changes
client changes
discovery-adapter changes
transport evolution
```

without weakening or redefining AIP's evidence, qualification, provenance, and assessment semantics.

Standard negotiated MCP is the primary agent-facing integration protocol, while REST is the general
integration surface for tools and deterministic HTTP consumers. AIP's semantic contracts should be
portable enough to support additional consumers without making any consumer the source of
Architecture Knowledge.

### 21.2 Semantic tool layers

Conceptually, the pre-v1.0 agent-facing semantics may evolve as:

```text
REST / standard negotiated MCP / other typed integration boundary
│
├── Current State
│   dependencies / drift / evidence
│
├── Intent
│   applicable explicit intent
│
└── Assessment
    Qualified Current ↔ Intent Assessment
```

The Current-State layer remains independent of Intent.

Architecture trajectories and trajectory-facing tools remain **beyond v1.0, unscheduled** under the
current roadmap and require historical-state foundations first.

Exact future tool names and schemas require release-specific specifications.

All agent-facing architecture-intelligence tools should remain read-only unless AIP's product
boundary is explicitly reconsidered.

---

## 22. Reverse Verification

AIP has a useful position on both sides of an agent-generated change.

```text
Before change:
AIP establishes qualified architecture context
and, where available, applicable explicit intent
          ↓
Agent reasons and changes software
          ↓
After change:
new declared / infrastructure / runtime evidence appears
          ↓
AIP establishes the post-change architecture state
          ↓
AIP re-assesses the Current ↔ Intent difference
```

This supports independent evaluation of post-change evidence within the supported claim scope.
Independent evaluation does not imply independent evidence, and neither implies complete verification
of a change.

If an agent changes both code and an API contract, re-importing that contract establishes a new
DECLARED state. It does not independently confirm implementation or runtime behavior. An assessment
must identify which aspects are supported by declarations, implementation-derived evidence,
infrastructure evidence, or observations, and disclose shared origins or dependencies where known.
Distinct source formats alone do not establish source independence; unknown independence must remain
explicit. No unsupported corroboration may be inferred from multiple representations of one assertion.

Post-change results must state what was evaluated, which sources support it, and what remains
unverified. They do not by themselves establish causality or overall change correctness.

---

## 23. Product Boundary

### AIP should own

Current and near-term core ownership:

- source-to-claim semantic interpretation and evidence-applicability rules;
- canonical architecture semantics exposed through public contracts, independent of the persistence
  representation;
- evidence applicability;
- identity reconciliation;
- declared-versus-observed qualification;
- observation-context semantics;
- snapshot-bound architecture answers;
- provenance;
- derivation lineage;
- limitations, conflicts, unsupported cases, and unresolved states;
- bounded deterministic architecture context;
- question-specific deterministic Architecture Knowledge projections;
- public semantic contracts that external moldable tools can inspect and compose without becoming
  architecture authorities.

AIP should own the **domain meaning** required for these capabilities. Standard source protocols,
transport libraries, and persistence mechanics should remain supporting or generic wherever
practical. Consumers should not depend on the internal database schema, graph layout, query
implementation, or persistence model used to realize the domain semantics.

Future, only if separately specified and validated:

- typed advisory assertion verification;
- source-neutral normalization of explicit architectural intent;
- Qualified Local Evidence Assessments as a public contract;
- locality/context applicability beyond what current evidence supports;
- advisory Current ↔ Intent assessment;
- composition of trustworthy local assessments;
- read-only agent-facing access to these semantics.

Beyond v1.0 under the current roadmap:

- historical-state persistence/import sufficient for temporal reasoning;
- architecture trajectories;
- trajectory-aware Current ↔ Intent assessment;
- distributed Local Architecture Assessor deployment (sidecar, DaemonSet, OTel extension, local
  gateway, or similar), unless the roadmap is explicitly revised.

### AIP should not own

- agent orchestration;
- coding-agent planning;
- prompt management;
- agent memory;
- generic workflow automation;
- generic enterprise knowledge graphs;
- exposing AIP's internal graph/database representation as the product contract;
- generic graph/Cypher access as a substitute for qualified architecture questions;
- business capability ownership;
- policy authoring;
- approvals;
- CI enforcement;
- migration-script execution;
- deployment orchestration;
- target-state generation by an LLM;
- automatic promotion of inferred intent into authoritative intent;
- generic runtime service invocation;
- service-mesh responsibilities;
- LLM-generated architecture truth.

---

## 24. Differentiation

### Software catalogs

```text
Catalog:
maintained system metadata and relationships

AIP:
evidence-qualified architecture knowledge
with context, provenance, derivation, qualification, and limits
```

### Observability systems

```text
Observability:
what telemetry was emitted

AIP:
what architecture claims the supported telemetry
can actually establish
```

### Static architecture discovery

```text
Static discovery:
what code appears to contain or reference

AIP:
how code-derived, declared, infrastructure, and observed evidence
combine into qualified architecture knowledge
```

### Agent platforms

```text
Agent platform:
reason, plan, execute, recover

AIP:
establish architecture premises
the agent does not have to invent
```

### Moldable development environments

```text
Moldable environment:
helps humans and agents construct contextual tools and representations

AIP:
provides evidence-qualified Architecture Knowledge
whose bounded projections can be molded without changing underlying semantics
```

The AIP × GT reference integration demonstrates that the layers compose: a GT-hosted agent can ask
AIP questions over MCP, follow evidence, and derive ephemeral micro-tools while AIP remains
responsible for the qualification semantics of the Architecture Knowledge it exposes and the
developer controls permanence.

### Governance / policy systems

```text
Governance:
intent, policy, permissions, allow/warn/block

AIP:
qualified Current State
+
applicable explicit intent
+
advisory evidence-linked assessment
```

### Desired-state / compliance tools

```text
Compliance:
compare implementation against a prescribed global target

AIP future direction:
compare context-bound established Current State
against partial, explicit, attributable intent
without requiring a complete target blueprint
```

### Knowledge graphs

```text
Knowledge graph:
connects and represents information

AIP:
establishes evidence-qualified Architecture Knowledge
with public semantic meaning, provenance, context, limitations,
and deterministic question-specific projections
```

AIP may use a graph internally, but the graph representation is not the customer contract. The
public architectural semantics are.

---

## 25. Formal and Strategic Foundations

AIP may use external theories as design lenses without adopting them as implementation models.

### Promise Theory

Useful principle:

```text
autonomous agents
+
explicit promises / capabilities
+
local cooperation
+
assessment of outcomes
```

AIP relevance:

- distinguish explicit Intent from Declared and Observed evidence;
- model offered/accepted capabilities without assuming centralized control;
- support explicit partial intent rather than a globally complete target blueprint;
- distinguish promises from observed cooperation;
- preserve the rule that observed behavior does not imply intended behavior;
- assess the relationship between independently established cooperation and independently
  established promises.

Promise Theory must not blur AIP's two semantic paths.

First, Current-State cooperation is established independently:

```text
declared / observed cooperation evidence
        +
locality / observation context
        +
Current-State qualification rule
        ↓
Qualified Local Evidence Assessment
        ↓
Current-State Projection
```

Separately, explicit promises establish Intent:

```text
explicit attributable promise
        +
scope / effective interval
        +
intent mapping rule
        ↓
Applicable Intent Projection
```

Only then may AIP compare them:

```text
Current-State Projection
        +
Applicable Intent Projection
        +
assessment rule
        ↓
Qualified Current ↔ Intent Assessment
```

AIP is the observer/assessor in this relationship, not the promise-maker and not necessarily the
promisee.

The product-facing implication is:

> **AIP establishes evidence-qualified cooperation independently, then separately assesses how that
> cooperation relates to explicit promises in the locality and time where those promises apply.**

Promise Theory should remain a semantic foundation and design lens. AIP should not require users to
adopt Promise-Theory-specific terminology or encode the Canonical Model directly as a Promise Theory
formalism unless a concrete product need justifies it.

### Semantic Spacetime

Useful principle:

```text
architecture meaning depends on:
context
locality
time
observer / evidence perspective
```

AIP relevance:

- qualified local assessments;
- context-bound Current State;
- effective-time intent;
- architecture trajectories;
- explicit limits on global projection.

### Bigraphs

Useful principle:

```text
PLACE / LOCALITY
        ≠
LINK / CONNECTIVITY
```

AIP relevance from v0.5 onward:

- Kubernetes/locality modeling;
- clean separation between deployment structure and interaction structure;
- moving identity across locality changes;
- future architecture trajectories where place and links evolve independently, once historical-state semantics exist.

Bigraphs should remain a **design influence**, not a replacement for the Canonical Model before v1.0.

Formal Bigraphical Reactive Systems may become relevant later when AIP has a concrete transformation
problem involving valid reconfiguration and safe evolution.

### Transformation formalisms

Bigraphical Reactive Systems, process calculi, type systems, temporal logic, and confluence-related
ideas may later help answer:

```text
Given:
  Current State C
  Explicit Intent I
  Candidate Transformation T

under which conditions is T safe?
```

That is a future research problem, not a pre-v1.0 product commitment.

---

## 26. Roadmap Alignment

`ROADMAP.md` is authoritative for release sequencing and planned scope. This doctrine is strategic
guidance for the semantics and product boundaries behind that roadmap.

### 26.1 Planned pre-v1.0 sequence

```text
v0.5 — Broader Architecture Discovery
  Product questions:
  "Where is this service deployed?"
  "Which deployment identities are unresolved?"

v0.6 — Locality-Aware Current State
  Product questions:
  "Where is this dependency established?"
  "Does this relation differ by supported locality?"

v0.7 — API-Aware Current State
  Product question:
  "How are APIs exposed and consumed, and what can the available evidence establish about
   those relationships?"
  First bounded validation: configured consumer/API access versus observed usage with real
  gateway configuration, attributed measurements, coverage, and cross-source identity.

v0.8 — Explicit Architecture Intent
  Product question:
  "What explicit architecture intent applies here?"

v0.9 — Qualified Architecture Assessment
  Product question:
  "Where does Current State differ from applicable Intent?"

v1.0.0-rc.N — Contract Freeze / Production Qualification
  Freeze and production-qualify the implemented contracts intended for v1.0;
  this is a release-candidate phase, not a new architecture-question release.

v1.0 — Stable Architecture Intelligence Platform
```

The release themes still describe implementation scope. The product questions explain why each
capability release expands AIP's useful Architecture Knowledge. v0.7 remains a **validation-gated,
question-specific Current-State extension**; it must not delay, amend or implicitly widen the
accepted v0.6.0 specification.

The semantic dependency between these themes is deliberate:

```text
DISCOVER
   ↓
ESTABLISH CURRENT STATE LOCALLY
   ↓
CONNECT API EXPOSURE AND CONSUMPTION AS CURRENT STATE
   ↓
REPRESENT INTENT INDEPENDENTLY
   ↓
ASSESS CURRENT ↔ INTENT
   ↓
FREEZE / QUALIFY
```

### 26.2 v0.6 boundary: locality semantics, not distributed deployment

v0.6 requires locality-aware Current-State semantics. It does **not** require assessment execution to
run beside the service or workload.

The required semantic direction is:

```text
Current-State Evidence
        +
explicit observation context / locality
        ↓
Qualified Local Evidence Assessment
        ↓
Current-State Projection
```

This may be implemented centrally.

A sidecar, DaemonSet, OTel extension, local gateway, or other distributed Local Architecture Assessor
is explicitly **beyond v1.0, unscheduled** under the current roadmap.

This keeps:

```text
local assessment as semantics
        ≠
distributed assessor as deployment architecture
```

### 26.3 v0.7 API Landscape, v0.8 Intent and v0.9 Assessment are planned capabilities

The API Landscape addition broadens the question space within **Current State**. It needs an
independently qualified, source-neutral vocabulary for API exposure/consumption, real gateway and
consumer-attributed usage evidence, cross-source reconciliation, and explicit coverage. It is not a
commitment to model all API gateways, products, business capabilities, or ownership at once. The
initial pilot must justify the value and operating cost of its bounded question before its contracts
are accepted for v1.0. Source objects remain distinct unless equivalence is evidenced.

Explicit Intent and Qualified Current↔Intent Assessment remain separate planned capabilities, not
unallocated ideas. Planned scope, authorization to execute a release, and qualification for v1.0 are
distinct decisions. Planned status does not waive the product and qualification gates.

v0.8 must implement and qualify the independent Intent path while preserving the invariant:

> **With evidence, evaluation context, identity resolution, and mapping, qualification, and projection
> rule versions held constant, changing Intent must not change established Current State.**

v0.9 must implement and qualify the separate Current↔Intent assessment path over the two independent
projections. For example, comparing evidenced *effective* gateway configuration with an applicable
security requirement is not the same as inferring endpoint insecurity from a missing route-level
plugin, and observed usage is context rather than compliance evidence by itself.

### 26.4 v1.0 release-candidate qualification and freeze rule

After v0.9, contract freeze and production qualification should run as a `v1.0.0-rc.N` phase
rather than as another capability release solely for stabilization. That phase should stabilize
only the planned pre-v1.0 capabilities actually implemented and qualified through v0.9.

The rule is:

> **Implement and qualify the planned capability before freezing its public contract.**

If a planned v0.7, v0.8 or v0.9 capability does not satisfy its product-value, semantic,
deterministic, security, performance, or real-system qualification gates, it must not be promoted
into the stable v1.0 contract merely because it appeared on the roadmap.

Such a capability should instead be one of:

```text
deferred beyond v1.0
kept explicitly experimental / unstable
reduced in scope and re-qualified
removed from the v1.0 contract
```

No additional roadmap change is required merely to specify and implement the planned v0.7 API
Landscape, v0.8 Intent or v0.9 Assessment capabilities. The release-candidate phase must not invent
a new product question merely to justify a version number; its purpose is to freeze and qualify the
already-implemented question space. Product-value and qualification gates still apply. A failed gate
must result in a documented decision to narrow, defer, or remove scope; material changes to release
assignment or product boundary must also be reflected in ROADMAP.md.

### 26.5 Beyond v1.0, unscheduled

The current roadmap places these capabilities beyond v1.0:

```text
externally sourced architecture decision-history linkage (findings, reviews, attributable decisions,
  rationale, approved exceptions and their validity), without owning approval workflows
historical architecture-state retention/import
architecture trajectories
distributed Local Architecture Assessor deployment
safe architecture transformation research
causal runtime-flow analysis
other explicitly future integrations/capabilities
```

Decision-history linkage is distinct from historical reconstruction of architectural Current State:
an externally recorded exception or review does not prove what was deployed at that time. AIP may
eventually relate a versioned finding/assessment to that record, but must not become its approval
authority. This is an unscheduled research candidate, not an added pre-v1.0 release requirement.

Architecture trajectories require a prior historical-state foundation including temporal identity,
provenance continuity, intent history, retention/import semantics, and temporal querying.

Distributed Local Architecture Assessor deployment may be evaluated only after v1.0 unless the
roadmap is explicitly revised based on compelling qualification evidence.

### 26.6 Transformation hypothesis

Full transformation reasoning remains downstream of qualified assessment and future historical
evolution semantics:

```text
Current State
    +
Explicit Intent
    +
Qualified Difference
    +
Constraints
        ↓
Candidate Evolution / Transformation
        ↓
Safe / Unsafe / Unresolved
```

Formal Bigraphical Reactive Systems and other transformation formalisms are more likely to become
relevant here than in the current pre-v1.0 discovery, locality, intent, and assessment roadmap.

### 26.7 Release/versioning doctrine

From v0.5 onward, AIP version progression should track expansion of the safely answerable
architecture-question space rather than accumulation of internal machinery.

```text
new materially different architecture question
        ↓
0.x.0 capability release

same question space, post-release correction / maintenance
        ↓
0.x.y patch release
```

A `0.x.0` capability is not shipped merely because its semantic core exists. Its supported public
adapters, evidence drill-down, limitations, deterministic evaluation, and release qualification are
part of the same release. Planned patch releases must not be used as a place to finish incomplete
`0.x.0` scope.

Contract freeze and production qualification after the final pre-v1.0 capability release belong to
the `v1.0.0-rc.N` phase because they harden an existing question space rather than create another
one.

Historical releases before v0.5 remain historical evidence and are not renamed to fit this doctrine.

---

## 27. Prioritization Framework

A feature should not enter the roadmap merely because it improves the internal model.

Prioritize using five gates.

### Gate A — Customer value

```text
Does this solve a recurring, high-cost architecture problem
for the primary user?
```

### Gate B — Strategic fit

```text
Does it strengthen the customer value proposition
without moving differentiation into transport or storage plumbing?

Does it deepen AIP's Core Domain or Moldable Architecture Knowledge capability:
evidence applicability, identity/reconciliation, qualification, provenance,
bounded uncertainty, or deterministic projection?

If it only adds a new source or transport, what new qualified knowledge
or recurring architecture question does that unlock?
```

### Gate C — Semantic defensibility

```text
Can the resulting claim semantics, uncertainty, applicability,
locality, context, and failure modes be stated independently of an LLM?
```

### Gate D — Executable validation

```text
Can the capability be evaluated deterministically
and, where appropriate, against independently authored or real-system evidence?
```

### Gate E — Architecture question

```text
What recurring architecture question becomes safely answerable,
or materially more reusable, because this capability exists?
```

For a new capability release, inability to state that question clearly is a warning that the work is
primarily machinery or hardening rather than product-surface expansion.

---

## 28. Near-Term Priority Order

Given the current roadmap, the preferred order is:

```text
1. Preserve qualification correctness and semantic safety.
2. Complete the current agent-facing interoperability work.
3. Broaden trustworthy discovery in v0.5.
4. Preserve WHERE != HOW and the service != Bounded Context != deployment unit != team boundary rule.
5. Implement locality-aware Current-State semantics in v0.6 without requiring distributed execution.
6. Validate API exposure and consumption as a bounded, source-neutral Current-State question in
   v0.7, beginning with real gateway configuration and consumer-attributed usage evidence.
7. Implement the independent explicit-Intent path in v0.8.
8. Implement the separate Current ↔ Intent assessment path in v0.9.
9. In the v1.0 release-candidate phase, freeze only contracts that survive implementation and qualification.
10. Keep decision-history linkage, historical trajectories and distributed Local Architecture Assessor
    deployment beyond v1.0, unscheduled, unless the roadmap is explicitly revised.
```

This sequence preserves the central dependency:

```text
Current State first and independently
        ↓
Intent second and independently
        ↓
Assessment only over both established projections
```

---

## 29. Product Decision Filter

For every proposed feature, ask:

1. **Who is the primary user for this capability?**
2. **What recurring architecture question becomes safely answerable?**
3. **What concrete job or failure mode does it address?**
4. **What measurable customer outcome should improve?**
5. **What claim, assessment, or context does AIP produce?**
6. **What exact evidence can support that output?**
7. **Which artifact type × claim kind × mapping rule defines applicability?**
8. **Which locality/context/time dimensions are actually supported?**
9. **Is the claim local, projected, or intended to be global?**
10. **If intent is involved, what explicit attributable artifact establishes it?**
11. **What happens when evidence is missing, partial, conflicting, unsupported, or local-only?**
12. **Can the semantics be stated without relying on an LLM?**
13. **Can behavior be validated deterministically?**
14. **Does the capability keep AIP advisory and read-only?**
15. **Would an integration boundary be better than AIP owning the adjacent function?**
16. **Does the feature accidentally couple AIP to one authoring format or deployment topology?**
17. **What existing roadmap item should be delayed if this enters scope?**

---

## 30. Strategic Risks

### Product broadening before wedge validation

Kubernetes, Pub/Sub, derivation, intent, assessment, and local assessors may all be
useful, but without a validated primary workflow they can become parallel attractive directions.

### Core-domain dilution

AIP could become a broad integration, catalog, graph, or protocol platform if source breadth,
visualization, transport, and persistence capabilities grow faster than the evidence-applicability,
identity, reconciliation, qualification, provenance, uncertainty, and projection semantics that
differentiate the product.

### Epistemic overclaiming

Calling AIP a "truth layer" would contradict its own open-world semantics.

### Silent incompleteness

Agent context that truncates, aggregates, or projects silently would undermine the trusted-context
proposition.

### False contradiction

Non-observation must never become contradiction unless an explicit closed-world rule permits that
interpretation.

### Global-truth flattening

Local assessments must not be silently promoted into universal facts.

### Static desired-state trap

AIP should not require a complete centrally authored target graph when explicit partial intent is
sufficient.

### API boundary and vendor-model conflation

An API contract, operation, gateway route/service, application service, consumer, product, business
capability, and permission are not interchangeable objects. An adapter must not make one gateway's
terminology the source-neutral model or infer organizational authority from technical metadata.
Configured access must not be silently treated as explicit architectural Intent.

### Intent-carrier lock-in

OpenAPI Overlay, AsyncAPI extensions, OpenSpec, or another format must not become the semantic model
by accident.

### Sidecar coupling

A local-assessor architecture must not force every application to depend functionally on an AIP
sidecar.

### Governance drift

Advisory assessment must not gradually become hidden policy authoring or CI enforcement.

### Natural-language leakage into truth

Natural language may help formulate questions or hypotheses, but must not become the unverified
source of canonical facts or intent.

### Formalism creep

Promise Theory, Semantic Spacetime, Bigraphs, process calculi, and type systems are useful only when
they solve concrete AIP semantic problems.

### Transformation premature optimization

AIP should not design migration execution before Current State and any future Intent/Assessment semantics are sufficiently stable. Historical trajectory semantics remain a separate post-v1.0 prerequisite under the current roadmap.

---

## 31. Recommended Positioning

### Customer value proposition

> **Help coding agents work across multi-service systems without reconstructing architecture.**

### Product concept

> **Moldable Architecture Knowledge.**

### Core Domain

> **Establishing Evidence-Qualified Architecture Knowledge from heterogeneous, incomplete, and
> potentially conflicting system evidence.**

### Differentiation

> **Core domain:** evidence applicability, identity/reconciliation, qualification, provenance and
> lineage, conflict handling, and bounded uncertainty.  
> **Product level:** deterministic question-specific projections and moldability.

### Current short positioning

> **AIP gives coding agents evidence-qualified Architecture Knowledge they do not have to reconstruct.**

### Customer problem: agent-ready architecture context

> **Code repositories alone do not provide the architectural context agents need to change
> multi-service systems safely. AIP makes that knowledge reusable and inspectable instead of
> asking every authoring or reviewing agent to infer it again.**

This is AIP's architecture-specific contribution to Context Engineering. It does not imply that
AIP stores all operational knowledge, owns historical decisions, governs agents, or independently
proves a software change safe.

### Current product positioning

> **AIP establishes evidence-qualified Architecture Knowledge from heterogeneous system evidence and
> exposes bounded, deterministic projections for concrete architecture questions. The projections
> are moldable; the evidence, qualification, provenance, and public architectural meaning are not.**

### Primary customer framing

> **For platform engineering and architecture teams enabling coding agents across multi-service
> systems, AIP provides reliable, bounded Architecture Knowledge at the point where an agent would
> otherwise have to reconstruct architecture from code, documentation, names, and partial runtime
> evidence.**

### Boundary statement

> **AIP does not decide what an agent should do, and it does not turn inferred intent into
> architectural truth.**

### Agent-readiness statement

> **AIP is not an agent platform or general organizational memory system. It establishes the
> evidence-qualified Architecture Knowledge that authoring and reviewing agents can query and mold
> into contextual views without becoming the source of that knowledge.**

### Future product proposition — strategic hypothesis

> **Know what your architecture is, what it is explicitly intended to be, and where, when, and under
> which evidence that difference holds.**

This is a future proposition, not a claim about the current release.

### Promise-oriented strategic interpretation

Internally, the same proposition can be expressed as:

> **AIP shows which promises apply here and now, what cooperation is actually established by evidence,
> and where the two diverge.**

A more architectural formulation is:

> **AIP establishes evidence-qualified cooperation independently, then separately assesses its
> relationship to explicit promises in the locality and time where those promises apply.**

These formulations are useful for semantic design and strategy. They should not replace the primary
public positioning unless user research shows that Promise-Theory terminology is broadly understood
by the target audience.

---

## 32. Strategic Conclusion

The product direction remains sound. The Wardley-mapping exercise clarifies the strategic hierarchy:

```text
Customer value proposition:
Help coding agents work across multi-service systems
without reconstructing architecture

Product concept:
Moldable Architecture Knowledge

Core Domain:
establishing Evidence-Qualified Architecture Knowledge

Core-domain differentiation:
evidence applicability, identity/reconciliation, qualification,
provenance/lineage, conflict handling, bounded uncertainty

Product-level differentiation:
deterministic question-specific projections and moldability

Replaceable implementation:
storage, graph layout, query language, transport plumbing
```

The product center remains **Moldable Architecture Knowledge**, but it is not the customer value proposition
itself.

AIP should evolve from:

```text
Evidence
   ↓
Qualified Architecture Knowledge
   ↓
Question-Specific Deterministic Projection
   ↓
Agent / Human / Contextual Tool
```

while preserving two independent semantic paths:

```text
Local Current-State Evidence
        ↓
Qualified Local Evidence Assessments
        ↓
Context-Bound Current-State Projection

Explicit Attributable Intent
        ↓
Applicable Intent Projection

Current-State Projection + Intent Projection
        ↓
Qualified Current ↔ Intent Assessment
```

Under the current roadmap, **Architecture Trajectories remain beyond v1.0** and require a separate
historical-state foundation before they can become a product capability.

The interaction insight is:

> **AIP should establish Architecture Knowledge once and make recurring architecture questions cheap
> to express as deterministic, inspectable projections.**

The strategic investment rule is:

> **Differentiate where Architecture Knowledge is established; standardize where it is transported
> and sourced.**

And the contract rule is:

> **Internal representation is replaceable. Public architectural meaning is a versioned semantic
> contract, not an implementation detail.**

The most important semantic insight remains:

> **AIP establishes architecture locally before projecting it globally.**

And the corresponding long-term product principle is:

> **System-level Current-State views are context-bound projections of qualified evidence assessments.
> Claims about cross-boundary interactions require their own evidence and qualification rules.**

This principle applies to Current-State views; explicit Intent and alignment assessments remain
separate knowledge domains. Locality alone does not make a claim composable or establish an
enterprise outcome.

This makes locality, time, provenance, and observer context first-class without turning AIP into a
general knowledge-representation system.

It also gives a clean division of responsibility among the theoretical influences:

```text
Promise Theory
  -> explicit local intent / promises, autonomous cooperation, promise assessment

Semantic Spacetime
  -> context, locality, time, observer perspective, trajectories

Bigraphs
  -> place versus connectivity, structural evolution

AIP
  -> evidence applicability, qualification, provenance, assessment
```

Before v1.0, these ideas should influence semantics only where they solve concrete product problems; distributed Local Architecture Assessor deployment remains beyond v1.0 under the current roadmap.
The Canonical Model should not be replaced wholesale by any formal theory.

The preferred strategic journey is:

```text
Broaden what AIP can safely know.
        ↓
Qualify local Current-State assertions from evidence.
        ↓
Project those assessments into contextual Current-State views.
        ↓
Implement the planned independent Intent capability, subject to product-value and qualification gates.
        ↓
Implement the planned separate Current↔Intent assessment, subject to the same gates.
        ↓
Freeze and production-qualify only the contracts that actually exist.
        ↓
Beyond v1.0: add historical-state foundations before trajectory reasoning.
        ↓
Only later reason about safe transformation.
```

AIP should preserve one durable center:

> **Agents should reason about architecture, not reconstruct it probabilistically on every run.**

And its deeper long-term differentiator may become:

> **AIP tells agents and engineers not only what architecture is established, but where and when that
> knowledge applies, what was explicitly intended, and what evidence supports the difference.**

In Promise-Theory terms, the same long-term differentiator is:

> **AIP tells agents and engineers which explicit promises apply, what cooperation is supported by
> evidence, and where the two align or diverge in a given locality and time.**
