# AIP v0.6.0 I1 — Locality and Evidence Applicability Contract

**Status:** Accepted I1 increment specification — normative semantic scope and completion contract. I1 deliverables are complete; see [`i1-completion-record.md`](i1-completion-record.md) (PRs #307–#311; closure `7a949cd`). I2 implementation is not claimed.  
**Release:** `v0.6.0` — Locality-Aware Current State  
**Increment:** I1  
**Repository path:** `docs/specifications/0.6.0/i1-locality-and-evidence-applicability.md`  
**Governing parent:** [Accepted v0.6.0 specification](specification.md), merged in [PR #278](https://github.com/michaelegner/architecture-intelligence-platform/pull/278), merge `be26edcd133edc8576a85d301be33b836335c41b`  
**Entry baseline:** Published and post-release-verified `v0.5.1`.  
**Output:** reviewed, versioned semantic contract, independent conformance cases and controlled capture plan. I2 implements the scoped ingress, persistence and assessment.

---

## 1. Purpose

The release asks **“Where is this dependency established?”** and **“Does this relation differ by supported locality?”** I1 defines exactly which evidence can license those answers before a new read model or public endpoint is built. It freezes caller-locality vocabulary, individual interaction attribution, a versioned **v2 caller-scoped observed-evidence contract alongside the existing v1 Service-level daily evidence**, capture/time applicability, refusals and an early real-capture acquisition plan. Here v1/v2 name evidence-identity generations, not AIP releases or REST/MCP API versions (§2.1).

> A positive caller-local `CALLS` is established from the Resource of the **actual CLIENT interaction**, matched to a time-compatible captured Pod/owner chain in one selected snapshot—not inferred from the Service's general deployment association or a same-Service Pod observation.

I1 SHALL provide testable contractual inputs and independently authored expected results. I1 does **not** implement or release the v2 persistence, local assessment, public relation-localities API, or the real I5 capture. Those are owned by I2, I3 and I5 respectively.

## 2. Normative authority and baseline

MUST, MUST NOT, SHALL, SHALL NOT, SHOULD and MAY are normative. The [accepted parent](specification.md), especially §§3–9, 11, 15–16, 20–24, 30, 33–34, controls the outcome. This accepted I1 specification fixes the semantic choices and review boundaries for its subsequent deliverables. Exact schema/serialization vectors, capture acquisition artifacts and independently expected conformance results must still be frozen and verified in I1 before I2 implementation; any amendment to an implementation-level spelling cannot weaken the accepted parent. Independent expected facts shall be authored **before** running AIP, not copied from implementation output.

| Baseline mechanism | Proven current behaviour / consequence |
|---|---|
| `app/canonical/ids.py::observed_evidence_id` | v1 evidence buckets distinguish environment, UTC day and subject/relation/object, **not caller Pod UID**. |
| `app/telemetry/adapter.py` | Paired HTTP CALLS uses v0.5 operation resolution; route/method and accepted fact timestamp are SERVER-sourced. Preserve this baseline. |
| `app/telemetry/correlation_buffer.py::PendingHttpSpan` | Bounded transient CLIENT/SERVER carrier currently lacks Kubernetes Resource attributes; I2 must preserve the original CLIENT's allowlisted identity across POSTs. |
| `app/telemetry/runtime_identity.py` | Per-Service/Pod observations are independent of individual relationship evidence. Same-Service co-occurrence cannot attribute one CALLS. |
| v0.5 `CAPTURED_RESOURCE` and Path C | Pod UID plus exact current captured owner chain can support bounded DEPLOYED_AS; this is not a blanket rule locating every Service interaction. |
| `app/qualification/declared_observed.py` / ADR 0010 | One declared-vs-observed status owner, with inclusive window matching. I1 specifies evidence applicability, not a second qualification algorithm. |
| `app/architecture_intelligence/repository.py` | One canonical snapshot fingerprint, currently canonicalization version 3. No-v2 v0.5 fingerprints must stay byte-identical. |
| [ADR 0012](../../adr/0012-observed-evidence-retention.md) | Proposed, not implemented. Scoped per-Pod evidence increases cardinality; compaction is not implicitly authorized. |

### 2.1 Terminology: observed-evidence v1 and v2

In this specification, **v1** and **v2** mean *generations of observed relationship-evidence identity and aggregation*. They do **not** mean AIP product releases (`v0.5.1`/`v0.6.0`), a public REST/MCP schema, or a replacement for the shared qualification rule. The `V1` suffix of proposed types such as `LocalityDayContextV1` independently names the first version of *that internal type*, not the v1 observed-evidence bucket.

| Term | Meaning | Identity / attribution boundary |
|---|---|---|
| **v1 — existing, unscoped observed evidence** | A daily Service-level evidence bucket that AIP already produces for an accepted relationship, including `CALLS`. | Its key identifies environment, UTC day, canonical subject Service, relation type and target entity. The individual caller Pod UID is **not** in this evidence identity; its relation cannot retrospectively be assigned to a Workload by joining independent same-Service Pod observations. |
| **v2 — proposed caller-scoped observed evidence** | An additional, separately isolated daily evidence representation for an accepted HTTP `CALLS` when its *original CLIENT interaction* carries admissible caller identity. | The proposed key also distinguishes CLIENT `k8s.cluster.uid` and `k8s.pod.uid` (§7). It establishes the original **Pod** attribution; a positive **Workload** locality still requires time-compatible captured Pod/owner-chain resolution in the selected snapshot (§9). |

Concrete example, for one UTC day and one environment (actual canonical `CALLS` targets are **Operations**, not provider Services):

```text
OrderService / distinct Deployment W1 / caller Pod P1
    --CALLS--> Operation pricing:GET /prices     (owned by PricingService)
OrderService / distinct Deployment W2 / caller Pod P2
    --CALLS--> Operation pricing:GET /prices     (owned by PricingService)

v1: one Service-level OrderService CALLS Operation(pricing:GET /prices) daily bucket
v2: two scoped buckets for that same Operation, one for CLIENT P1 and one for CLIENT P2
```

Two Pod-level v2 buckets do **not** necessarily mean two Workload localities: if P1 and P2 belong to two ReplicaSets of the *same* Deployment, the v0.5 owner chain resolves both to one Workload. The positive two-locality capture (§12) must instead use **two distinct Deployment objects**. The logical provider Service shown in parentheses is derived from the canonical Operation owner for the later dependency projection (§5.1); it is **not** proof of the provider's target runtime locality. Operation names shown in examples are descriptive placeholders, not a new literal canonical-ID grammar; independently pinned source inputs must supply the exact accepted canonical Operation IDs.

**Coexistence, not replacement:** every newly accepted interaction continues to contribute according to existing v1 semantics. If its original CLIENT identity satisfies the scoped rules, it *also* contributes to one isolated v2 bucket. These are two representations of the **same interaction**, not two observed calls: v2 MUST NOT be counted again in existing v0.5 relation qualification, coverage, observation counts or legacy evidence arrays. Historical v1-only aggregates remain valid *unscoped* evidence; Pod attribution cannot be reconstructed from them without independently replayable original per-interaction input (§7.2). I1 freezes this contract; I2 implements it.

Immutable semantic boundaries:

```text
caller event provenance != same-Service Pod co-occurrence
Service != Kubernetes Service != Workload != Pod
source/capture scope != caller scope != target scope != claim applicability
DEPLOYED_AS != proof of CALLS from every associated Workload
local observation != globally established relation
not observed locally != verified local absence
Current-State evidence != Architecture Intent
v2 representation of an event != another v1 observation contribution
```

## 3. Increment boundary

**I1 SHALL freeze:** exact role-specific scopes/dimensions, source/claim applicability matrix, admissible OTel CLIENT attributes and correlation preservation, deterministic scoped v2 evidence key, v1/v2 transition/no-double-count rule, date-window and capture/Pod-churn guards, refusal taxonomy, independent conformance dossier, and the I5 two-Workload capture plan (including owner and I2 rehearsal).

**I2 SHALL implement:** the CLIENT Resource carrier and fact provenance before aggregation, isolated v2 storage/replay/reachability, local assessment read model, conditional unified snapshot inputs and shared qualification integration. **I3 SHALL implement:** bounded evidenced-locality enumeration, question-specific REST/negotiated MCP exposure and snapshot-bound evidence drill-down. I4/I5/I6 qualify, demonstrate and release the exact candidate.

No new source family, live Kubernetes polling/admission, inferred Service-mesh topology, generic graph API, region/tenant/service-version locality, local messaging, historical snapshot store, local telemetry-coverage source, distributed assessor, Intent, policy engine or agent-generated canonical claims enters I1. Public route/tool count remains an I3 decision.

## 4. Locality scope and role-specific representation

### 4.1 Independent roles

The contract SHALL distinguish even coincident values:

| Role | Meaning | Proof boundary |
|---|---|---|
| `RequestedScope` | Question, explicit observation context and optional later I3 locality selection | Request is not evidence. |
| `SourceCaptureScope` | Source instance/revision, admitted resource inventory, evidence mode and `capturedAt` | Capture is not timeless presence. |
| `CallerRuntimeScope` | CLIENT Resource attached to the *individual* accepted CALLS candidate | Requires exact event association. |
| `TargetRuntimeScope` | Independently evidenced target **runtime placement**, if known | Never copied from the caller or logical Operation owner. The Operation's canonical provider Service may identify the logical dependency target, not where that provider ran. |
| `ClaimApplicabilityScope` | Scope under which that precise assertion is supported | Derived no more broadly than its inputs and rule. |
| `ProjectionSelectionScope` | Later I3 evaluated/included/excluded candidate localities | Filtering is not source evidence. |

**Internal contract identifier to freeze in I1 artifacts:** `locality-contract/1`. This is an internal semantic-contract version, *not* the future public I3 JSON schema version.

### 4.2 Minimum positive dimensions

One positive caller-Workload-local HTTP CALLS requires exact:

```text
environment              <- accepted deployment.environment.name
complete UTC day window  <- date-based selection, no partial-day promise
caller cluster UID       <- actual CLIENT k8s.cluster.uid == captured envelope clusterUid
caller Pod UID           <- actual CLIENT k8s.pod.uid
caller namespace         <- exact resolved captured Pod / owner-chain namespace
caller Workload ref      <- unique supported Workload in selected captured state
capture revision/time    <- identified, time-compatible CAPTURED_RESOURCE
```

Pod UID is retained at ingestion as **attribution identity**, not itself a proven Workload locality. Cluster UID is exact; display names, labels and namespace proximity cannot substitute for it. Optional CLIENT `k8s.namespace.name`, `k8s.pod.name`, deployment/statefulset/daemonset names and service version are only bounded consistency/source metadata when present, not positive identity from names. Two Workloads in **one cluster and namespace** count as two distinct supported localities if their captured owner chains are independently established.

Region, tenant, version-locality and messaging-locality are **unsupported in the minimum release slice**, notwithstanding the ROADMAP's broader candidates. `service.version` does not mint a new canonical Service. Other existing v0.5 relations retain their old query semantics; only the new relation-locality surface reports unsupported locality-specific qualification.

### 4.3 Internal contract types

Illustrative type/field freeze for review, not new public API or storage labels:

```text
LocalityDayContextV1:
  environment: exact_nonempty_string
  first_utc_day: ISO_DATE
  last_utc_day: ISO_DATE              # inclusive observation-day range; NOT an Intent effective interval
  requested_dimensions: typed_map     # admitted dimensions only
  selected_snapshot_ref: opaque_ref

CallerAttributionV1:
  subject_service_id: canonical_id
  relation_type: CALLS
  object_operation_id: canonical_id
  accepted_fact_environment: string
  accepted_fact_timestamp: UTC_instant
  client_environment: string
  client_timestamp: UTC_instant
  client_cluster_uid: exact_uid
  client_pod_uid: exact_uid
  optional_consistency: admitted_allowlist
  normalization_rule: id_and_version

ResolvedCallerLocalityV1:
  attribution_ref: opaque_ref
  selected_snapshot_ref: opaque_ref
  capture_source_revision: opaque_ref
  captured_at: UTC_instant
  cluster_uid: exact_uid
  namespace: exact_string
  workload_ref: canonical_workload_ref
  disposition: LocalityDisposition
  reasons: sorted_distinct_reason_codes
```

Caller attribution is retained independently of the **query-time** Pod-to-Workload resolution; neither target locality nor a resolved Workload is added to the observed event's immutable key. `LocalityDayContextV1` denotes an **observed Current-State evidence window**. A future v0.7 Intent effective interval is a *different type and semantic timeline*, cannot substitute for `first_utc_day/last_utc_day`, and does not participate in Current-State qualification. I1 must preserve that distinction in typed normalization, examples and the exit evidence.

## 5. Evidence applicability and qualification boundary

I1 freezes the following minimum claim-kind × source matrix; other kinds need separate reviewed scope/rules and independent tests.

| Evidence | May support | Cannot support alone |
|---|---|---|
| Accepted OpenAPI Service/Operation declaration | Source/Service-scoped declared Operation; may match an independently observed local CALLS | Event executed in a particular Workload; region-local declaration. |
| Resolved OTel HTTP CLIENT with actual bounded Resource | Per-interaction Pod/cluster caller identity | Unique owner Workload or target placement without captured evidence. |
| Correlated HTTP SERVER | Existing resolved provider method/route and fact timestamp | CLIENT caller locality from SERVER Resource. |
| Existing v1 daily CALLS evidence | Existing Service-level observed relation and coverage/counts | Retrospective Pod/Workload attribution by Service/time join. |
| Separate `RuntimeIdentityObservation` | Its independently supported Path C Service/Pod/DEPLOYED_AS inputs | Proof that a particular CALLS originated from that Pod. |
| Isolated v2 scoped CALLS record | Caller Pod/cluster-specific observed contribution | Positive Workload locality absent compatible query-snapshot capture. |
| Unique CAPTURED_RESOURCE Pod/owner chain | Exact captured resource and owner/Workload identity | A CALLS edge, timeless Pod presence or observed action inferred from placement. |
| Configured / explicit DEPLOYED_AS | Its own source-qualified identity association | Location of all Service interactions. |
| Operator-authored AsyncAPI overlay | Source-attributable declared messaging claim under v0.5 | Observed Kafka behaviour or local messaging qualification. |

**Declared evidence:** an accepted matching Service/Operation declaration may contribute *as source/Service-scoped evidence* to an independently observed scoped CALLS. Shared v0.5 qualification then yields `CONFIRMED` for both or `OBSERVED_ONLY` for local observation alone. The declaration is not Workload-authored/exclusive. Declared-only Service relation does not establish positive Workload-local CALLS.

**No Workload-level coverage:** no admitted minimum v0.6 input independently establishes it. Therefore local `NOT_OBSERVED_IN_WINDOW` is **unreachable and forbidden**; a missing eligible local event must be reported as *not established from available local evidence*, with unknown/insufficient local coverage, never as absence. Unscoped v0.5 qualification and coverage remain unchanged.

### 5.1 Operation-granular qualification and later Service dependency projection

AIP's canonical observed relation is `caller Service --CALLS--> provider Operation`; the v2 `object_id` remains the **Operation ID**. The parent asks a user-facing Service dependency question, but that is a **derived projection**, not a different observed fact or a claim that the target Service was placed in the caller's locality.

I1 freezes these constraints for I3's public roll-up: qualify each eligible local `CALLS` against its exact canonical Operation and source/Service-level declaration through the existing qualification owner; resolve the Operation's **unique canonical owning provider Service** using accepted source/identity state, never its display name or an inferred deployed target; group supported positive Operation assessments by *(caller Service, resolved caller Workload locality, provider Service, selected observation context/snapshot)*. Deduplicate and sort the **union of those qualifying per-Operation evidence and claim references** with Operation-level status/provenance retained. No provider Service dependency is minted when Operation ownership is missing/ambiguous, no `CONFIRMED` is inferred by pooling declared evidence from one Operation with observed evidence from a different Operation, and no global/absent/exclusive or target-runtime-locality claim is derived from that group.

**I3 SHALL freeze** the exact Service-level response shape, bounded Operation membership/evidence union, canonical ordering, group-level qualification presentation and incomplete/ambiguous-owner disposition in its reviewed public projection specification. I1 does not introduce a second aggregation-status algorithm. Add distinct-Operation/same-provider and missing-owner scenarios to I3's acceptance matrix; the present I1 examples refer to Operations explicitly.

## 6. Ingestion-time HTTP CALLS attribution contract

### 6.1 Field provenance and correlation

An eligible v2 contribution is made **only after an existing v0.5 CALLS is accepted**. Freeze origins rather than re-deriving relation semantics:

```text
canonical caller Service       existing v0.5 CLIENT Service resolution
canonical provider Operation   existing v0.5 operation matching
HTTP method/route              existing v0.5 source (SERVER for paired path)
fact environment/timestamp     existing accepted v0.5 path
caller Resource identity       actual corresponding CLIENT span
caller event timestamp         that same CLIENT span
Pod/owner-to-Workload           current selected captured-resource snapshot, at query time
```

The transient cross-batch carrier must preserve the actual CLIENT's environment, Pod UID, cluster UID, CLIENT event timestamp and bounded admitted consistency attributes regardless of CLIENT-first or SERVER-first arrival. SERVER Resource, `peer.service`, a Service-level `DEPLOYED_AS`, a separately stored same-Service identity observation or tracing parentage alone may not replace caller identity. Preserve existing correlation-buffer TTL/size and never retain raw spans/unbounded attributes in Neo4j.

`CLIENT_ONLY` may be scoped **only if** the existing v0.5 rules resolved a real CALLS candidate and its original CLIENT Resource survived correlation expiry. `SERVER_ONLY` has no CLIENT locality evidence and cannot create caller-scoped v2. All observations accepted by v0.5 still follow their existing v1 route.

### 6.2 Exact acceptance guards

**Ingestion-time guards** can inspect only the accepted v0.5 CALLS and the **same original CLIENT** Resource/carrier: (1) exact canonical subject/Operation IDs of the accepted v1 CALLS; (2) nonempty CLIENT `deployment.environment.name`, `k8s.pod.uid`, `k8s.cluster.uid`; (3) exact CLIENT environment equality with the accepted fact environment, no alias/case-fold/wildcard; (4) accepted fact and CLIENT event timestamps both valid UTC instants in the **same UTC day bucket**; and (5) bounded CLIENT-internal consistency of values actually present in that Resource/carrier. Only an actual contradiction known from these inputs can refuse scoped-v2 creation. Paired calls crossing midnight may retain their original v1 meaning, but must not be forced into a fictitious same-day v2 bucket without a separately accepted rule. Do not store raw span data or arbitrary Resource fields.

**Query-time guards** require the selected CAPTURED_RESOURCE snapshot: exact captured cluster/Pod UID, namespace, owner chain, supported Workload and `capturedAt`. They compare any optional CLIENT Pod/namespace/Workload-name consistency fields against the *captured* values. An incompatibility learned only at query time (for example `LOCALITY_NAMESPACE_CONFLICT` or cluster/owner mismatch) produces a scoped assessment limitation; it MUST NOT suppress, rewrite or delete the original valid v2 Pod-bound evidence. The ingestion path cannot check an as-yet-unselected captured namespace/owner and must not guess it from a same-Service Pod observation.

I1 conformance must cover paired/in-batch, CLIENT-first and SERVER-first cross-batch, qualified CLIENT_ONLY and SERVER_ONLY, missing caller UID, contradictory environment, cross-day facts, conflicting cluster UID and name-only attribution. I2 implements the actual propagation.

## 7. Deterministic scoped observed-evidence v2 identity and transition

### 7.1 Scoped bucket key contract

I1 fixes these **logical canonical identity inputs**, with byte-exact encoding and independent golden vectors to be frozen in its supporting artifacts:

```text
contract_version: 2
source_type: OPENTELEMETRY
evidence_type: OBSERVED
relation_type: CALLS
environment: <exact accepted fact environment>
bucket_utc_day: YYYY-MM-DD
subject_id: <canonical caller Service ID>
object_id: <canonical provider Operation ID>
caller_cluster_uid: <exact CLIENT k8s.cluster.uid>
caller_pod_uid: <exact CLIENT k8s.pod.uid>
```

Use one frozen typed UTF-8 canonical JSON representation (specified field order independent; sorted keys and fixed separators), a **full** lowercase SHA-256, and proposed opaque ID `evidence:otel:calls-scoped:v2:<64-character-sha256>`. The literal name/serialization is subject to I1 review; the input distinctions are mandated by the parent. No trace/span ID, Workload label, Service version, capture time, source display name or selected snapshot is a bucket identity field. A Pod replacement produces a distinct record even if the eventual Workload name is identical. Same Pod UID text in another cluster also differs.

Store key/normalization rule IDs and versions in lineage. I1 publishes independently authored golden vectors for field reordering, distinct Pod UID and distinct cluster UID. Source timestamps, first/last observed, aggregate count, correlation mode and bounded sanitized trace samples are metadata, not additional identity dimensions.

### 7.2 Dual representation without double-counting

As defined in §2.1, v1 is the existing Service-level daily evidence and v2 is the proposed independently identified caller-Pod-scoped evidence; neither is an AIP release or API version. A newly admitted event retains exactly the normal v1 contribution and, **when caller identity qualifies**, an *isolated* v2 contribution. These are two representations of one event. A v2 record must not be appended as an ordinary second evidence ID to the legacy CALLS edge or counted again in v0.5 relation qualification, coverage, observations or evidence arrays. I2 freezes v2 persistence/read/reachability before implementation; a separate scoped label/read model is permitted but must not introduce a second semantic owner or unrestricted public evidence exposure.

Historical v1 aggregates cannot be backfilled with Pod locality from independent `RuntimeIdentityObservation`. Only independently replayable original per-interaction input can regenerate scoped evidence; record its source/revision. Migration reports distinguish `LEGACY_UNSCOPED`, eligible v2, and refused scoped attribution while preserving v1 meaning.

Clean-state replay of one pinned source corpus must reproduce the same identities/normalized results; same input batch must not create duplicate *representations*. Do not misstate this as an existing exactly-once OTLP transport guarantee: the current v0.5 aggregator can count a repeated live POST. I2 shall freeze its retry/replay transaction semantics explicitly without silently changing v1 behaviour or counting v2 twice in legacy answers.

## 8. Whole-UTC-day observation window

The first positive scoped CALLS selector accepts **complete UTC days only**, proposed as a typed, inclusive *date* range:

```text
ScopedDayWindowV1(first_day: YYYY-MM-DD, last_day: YYYY-MM-DD)
first_day <= last_day
internal start = first_day at 00:00:00.000000 UTC
internal end   = (last_day + 1 day) at 00:00:00.000000 UTC - 1 microsecond
```

This proposal retains the existing shared v0.5 **inclusive** timestamp predicate while excluding an event occurring precisely at the following day's midnight from the selected complete days. I1 freezes the timestamp precision, UTC parser, leap/day-range validation, canonical serialization and midnight boundary with golden examples. I3 may choose a date-oriented public representation but may not change the semantics. Existing v0.5 date-time request/window behaviour is untouched.

The CLIENT's original timestamp and accepted CALLS fact timestamp must each be attributable to the same v2 UTC day. For **query-time** capture compatibility, reuse Path C's exact inclusive predicate (currently `app/architecture_intelligence/deployment_projection.py::_observation_context_limitation`): `window_start <= observed.last_seen <= window_end` and `window_start <= capturedAt <= window_end`, after exact environment matching. The `observed.last_seen` input for this scoped check is **the selected v2 bucket's own `last_seen`**, not the separate Service-level `RuntimeIdentityObservation.last_seen` or the v1 aggregate's `last_seen`. The `capturedAt` is the real timestamp of the matching selected Pod's captured envelope. The bounds are the complete-UTC-day normalized bounds defined above. An entire bucket is not continuous Pod-presence evidence. No nearby timestamp, arbitrary skew allowance, implicit timezone, missing `capturedAt` substitution or unverified source-clock repair is admitted.

Example: v2 `last_seen` on day D with a Pod captured on D+1 and a request selecting only D **cannot** establish a positive D locality: the capture is known temporally inapplicable (`INAPPLICABLE`, `LOCALITY_CAPTURE_TEMPORAL_MISMATCH`). Missing `capturedAt` instead gives insufficient evidence (`LOCALITY_CAPTURE_TIMESTAMP_MISSING`). This scoped rule leaves the v0.5 Path C input/predicate and existing v0.5 query semantics unchanged.

Sub-day/partial-day requests, cross-day forced bucket matches and a later coarsened retention bucket whose original day membership cannot be proved yield an explicit unsupported/insufficient temporal-resolution result. They must not silently widen the scope or assert local `NOT_OBSERVED_IN_WINDOW`. ADR 0012 is still Proposed and is not enacted by this contract.

## 9. Selected-snapshot Pod/Workload resolution and churn

**The v2 observed event retains its actual CLIENT Pod UID at ingestion.** Its Workload is resolved **at query time against the time-compatible Pod/owner-chain capture in the one selected canonical, revision-fenced snapshot**, under the existing v0.5 Path C guards and this contract's interaction-specific attribution:

```text
scoped v2 CALLS (caller cluster UID, caller Pod UID)
    -> exact selected CAPTURED_RESOURCE contribution with matching envelope clusterUid
    -> exact captured Pod UID and namespace
    -> unique supported owner chain (e.g. Pod -> ReplicaSet -> Deployment)
    -> unique canonical Workload
    -> caller Workload-local applicability only
```

A positive scoped Workload claim requires the correct evidence mode, accepted source inventory/revision, the **§8 exact v2-last_seen and capturedAt predicates**, exact cluster UID and Pod UID, supported owner chain, consistent present optional Resource attributes checked **at query time** against the selected capture, and no same-snapshot owner conflict. `DECLARED_MANIFEST`, label selection, name-only Pod matching, co-location, nearest timestamp and generic Service-level `DEPLOYED_AS` are insufficient. The target locality is independently unknown unless separately evidenced.

**Capture replacement:** If an authoritative later selected capture no longer includes the observed Pod/valid chain, the original event remains attributable to its original Pod in v2, but its Workload locality becomes `UNRESOLVED`. It is not absent, deleted, automatically historical, reattached to the replacement Pod, or inferred to have occurred at every current Workload. If two current owner paths disagree, retain the Path C distinction: multiple admissible candidate Workloads with no established contradictory evidence are `AMBIGUOUS`; contradictory known identity/owner evidence is `CONFLICT`. Do not choose the latest/friendliest. Source/capture revision and timestamp belong in the assessment lineage, and a changed selected capture must be reflected in its current result/snapshot.

No historical snapshot store is introduced. A file kept externally after its contribution disappears from the **selected** canonical snapshot cannot by itself make yesterday's Workload resolution queryable again. This matters to the I5 canary scenario: capture during the overlap when both Pod incarnations are present and evaluate that capture before a later authoritative import drops the old Pod.

## 10. Applicability dispositions and diagnostics

The following is the **I1 internal taxonomy**; I3 subsequently maps query-time dispositions to its versioned public answer schema. Ingestion-only diagnostic codes and query-visible limitations have different reachability (§10.2). A scoped query result is machine-visible, stable under ordering and carries one disposition, ordered distinct reasons and bounded sanitized source/capture references.

| Disposition | Meaning | Example |
|---|---|---|
| `APPLICABLE` | Directly attributable evidence and selected context justify the scoped statement | CLIENT UID + matching, time-compatible captured Pod owner chain. |
| `INAPPLICABLE` | A known evidence source or timestamp does not apply to the requested exact selection | Wrong environment or outside selected source/window. |
| `INSUFFICIENT_EVIDENCE` | Required proof is missing, with no established contradictory value | No CLIENT Pod UID; legacy v1 only; no Workload-level coverage. |
| `UNRESOLVED` | Required selected-snapshot identity/capture path is absent or incomplete and cannot establish a requested locality | Old Pod missing from selected capture; incomplete owner chain. |
| `AMBIGUOUS` | More than one admissible Path C candidate remains and the evidence cannot choose uniquely, without a known contradiction | One Pod resolves to multiple otherwise admissible Workloads under existing Path C status rules. |
| `CONFLICT` | Known compatible identity inputs disagree | CLIENT cluster UID and captured envelope cluster UID differ. |
| `UNSUPPORTED` | Dimension, relation, source interpretation or temporal precision is not admitted | Region/tenant, local messaging or sub-day window. |

Internal diagnostic codes (subject to the §10.2 visibility boundary):

```text
LOCALITY_CLIENT_IDENTITY_MISSING
LOCALITY_SERVER_ONLY_NO_CLIENT
LOCALITY_CLIENT_INTERNAL_CONFLICT
LOCALITY_CLIENT_FACT_ENVIRONMENT_MISMATCH
LOCALITY_CLIENT_FACT_DAY_MISMATCH
LOCALITY_CLUSTER_UID_MISSING
LOCALITY_CLUSTER_UID_CONFLICT
LOCALITY_POD_UID_MISSING
LOCALITY_CAPTURE_MISSING_POD
LOCALITY_CAPTURE_MODE_UNSUPPORTED
LOCALITY_CAPTURE_TEMPORAL_MISMATCH
LOCALITY_CAPTURE_TIMESTAMP_MISSING
LOCALITY_OBSERVATION_TEMPORAL_MISMATCH
LOCALITY_POD_OWNER_UNRESOLVED
LOCALITY_POD_OWNER_AMBIGUOUS
LOCALITY_POD_OWNER_CONFLICT
LOCALITY_NAMESPACE_CONFLICT
LOCALITY_LEGACY_V1_UNSCOPED
LOCALITY_UNSUPPORTED_DIMENSION
LOCALITY_UNSUPPORTED_RELATION
LOCALITY_UNSUPPORTED_TEMPORAL_RESOLUTION
LOCALITY_NO_ELIGIBLE_LOCAL_OBSERVATION
LOCALITY_LOCAL_COVERAGE_UNAVAILABLE
```

### 10.1 Phase-gated cause-to-disposition contract

`LOCALITY_NO_ELIGIBLE_LOCAL_OBSERVATION` is *not an absence claim*. Use existing v0.5 public deployment-resolution codes unchanged on existing surfaces. The following cause mapping binds the I1 contract; individual ingestion-only reasons are recorded in diagnostics/reports but are not reconstructed by an unrelated read-side v1 bucket (§10.2):

| Phase and exact cause | Locality disposition | Stable reason / treatment |
|---|---|---|
| Request asks for an unadmitted dimension/relation or sub-day resolution | `UNSUPPORTED` | `LOCALITY_UNSUPPORTED_DIMENSION`, `LOCALITY_UNSUPPORTED_RELATION` or `LOCALITY_UNSUPPORTED_TEMPORAL_RESOLUTION`; request preflight, never fall back to wildcard. |
| `SERVER_ONLY` or no corresponding CLIENT identity carrier at all | `INSUFFICIENT_EVIDENCE` | `LOCALITY_SERVER_ONLY_NO_CLIENT` for SERVER_ONLY; `LOCALITY_CLIENT_IDENTITY_MISSING` for other absent carrier; v1 handling unchanged. |
| CLIENT carrier exists, but Pod UID and/or cluster UID is missing | `INSUFFICIENT_EVIDENCE` | Specific `LOCALITY_POD_UID_MISSING` and/or `LOCALITY_CLUSTER_UID_MISSING`; **do not also** emit generic CLIENT-identity-missing. |
| CLIENT environment is missing | `INSUFFICIENT_EVIDENCE` | `LOCALITY_CLIENT_IDENTITY_MISSING`; preserve accepted v1 semantics. |
| CLIENT environment is present but differs from the accepted fact environment **at ingestion** | `INAPPLICABLE` (ingestion diagnostic only) | `LOCALITY_CLIENT_FACT_ENVIRONMENT_MISMATCH`; no v2 minted; v1 unchanged (§10.2). |
| Valid persisted v2 environment differs from exact query environment **at read time** | `INAPPLICABLE` (phase 3) | Exact environment mismatch limitation; no candidate identity/owner evaluation or widening by alias. |
| CLIENT/fact event timestamps cannot inhabit the same UTC day | `INAPPLICABLE` | `LOCALITY_CLIENT_FACT_DAY_MISMATCH`; v1 unchanged. |
| Two known values contradict *within the same CLIENT Resource/carrier* | `CONFLICT` | `LOCALITY_CLIENT_INTERNAL_CONFLICT`; do not store positive v2; no comparison against an as-yet-unselected capture at ingestion. |
| Legacy v1-only evidence, no original replayable CLIENT interaction | `INSUFFICIENT_EVIDENCE` | `LOCALITY_LEGACY_V1_UNSCOPED`; never infer Pod locality. |
| Selected Kubernetes contribution is `DECLARED_MANIFEST`, not an admissible captured source | `UNSUPPORTED` | `LOCALITY_CAPTURE_MODE_UNSUPPORTED` for observed Workload-local claims. |
| Captured source has no matching original Pod UID/current owner chain | `UNRESOLVED` | `LOCALITY_CAPTURE_MISSING_POD` or `LOCALITY_POD_OWNER_UNRESOLVED`; old v2 event remains intact. |
| Selected capture has no parseable real `capturedAt` | `INSUFFICIENT_EVIDENCE` | `LOCALITY_CAPTURE_TIMESTAMP_MISSING`; preserve existing v0.5 temporal limitation on its own surface. |
| Known v2 bucket `last_seen` or known capture `capturedAt` falls outside the exact selected full-day window | `INAPPLICABLE` | `LOCALITY_OBSERVATION_TEMPORAL_MISMATCH` or `LOCALITY_CAPTURE_TEMPORAL_MISMATCH` respectively. |
| Exact CLIENT cluster/namespace or present optional consistency attributes contradict the selected captured Pod/owner chain | `CONFLICT` | `LOCALITY_CLUSTER_UID_CONFLICT` / `LOCALITY_NAMESPACE_CONFLICT` / applicable bounded Path C contradiction; **query-time only**, retained v2 evidence unchanged. |
| Multiple admissible current captured Pod/owner candidates with no proved contradictory identity | `AMBIGUOUS` | `LOCALITY_POD_OWNER_AMBIGUOUS`; preserve the distinct v0.5 Path C `AMBIGUOUS` meaning, no arbitrary candidate. |
| Contradictory current owner paths / known identity assertions | `CONFLICT` | `LOCALITY_POD_OWNER_CONFLICT`; do not collapse into `AMBIGUOUS` or `UNRESOLVED`. |
| No eligible local CALLS / no admitted Workload-level coverage | `INSUFFICIENT_EVIDENCE` | `LOCALITY_NO_ELIGIBLE_LOCAL_OBSERVATION` / `LOCALITY_LOCAL_COVERAGE_UNAVAILABLE`; never local `NOT_OBSERVED_IN_WINDOW`. |

**Evaluation is phase-gated and short-circuits.** First evaluate the original CLIENT/accepted-CALLS input at **ingestion** (which may refuse v2 and emit an ingestion diagnostic under §10.2). For each later **query-time** candidate with independently retained v2 evidence, evaluate in this strict order:

1. **Request preflight:** an unsupported requested relation, locality dimension or time resolution terminates the request as `UNSUPPORTED`.
2. **Selected source/evidence mode:** for that candidate, `DECLARED_MANIFEST` rather than an admissible `CAPTURED_RESOURCE` terminates as `UNSUPPORTED` / `LOCALITY_CAPTURE_MODE_UNSUPPORTED`. This is a **per-candidate terminal disposition**, not solely a request-level preflight.
3. **Exact environment and temporal applicability:** evaluate available accepted-v2 environment, scoped bucket `last_seen`, real selected capture `capturedAt` and whole-day bounds. Known mismatch terminates as `INAPPLICABLE`; missing required temporal proof terminates as `INSUFFICIENT_EVIDENCE`. Do **not** continue to assess owner identity after a candidate has failed this phase.
4. **Matching captured Pod and owner identity:** only a candidate passing phases 1–3 can be resolved as `APPLICABLE`, `UNRESOLVED`, `AMBIGUOUS` or `CONFLICT` under the exact §9/Path C guards.

**Primary disposition is taken from the first terminating phase**, never from a global cross-phase severity ranking. Within that reached phase, retain every independently established diagnostic reason, deduplicate and sort lexicographically; if several causes in **that same phase** require a primary choice, use `CONFLICT > AMBIGUOUS > INAPPLICABLE > UNRESOLVED > INSUFFICIENT_EVIDENCE > APPLICABLE`. `UNSUPPORTED` is terminal in phase 1 or 2, so it is never missing from or overridden by a severity ranking for phase 3/4. A day-D v2 observation with an explicitly selected day-D+1 capture and a day-D-only query yields temporal `INAPPLICABLE`, **even if that capture's owner chain is contradictory**; no in-scope `CONFLICT` is asserted. Other excluded candidates remain separately visible with their phase, limitations and enumeration coverage, not hidden by the primary outcome. Never invent reasons for later phases that were not evaluated. I3 owns the public mapping but not permission to reorder these semantic gates.

### 10.2 Ingestion-refusal visibility and query abstention

**Selected contract: ingestion-only specific diagnostics; no new persisted refusal-fact family.** If the original CLIENT/accepted-CALLS ingress fails its v2 eligibility checks (SERVER_ONLY, missing CLIENT carrier/Pod UID/cluster UID, CLIENT/fact environment or UTC-day mismatch, CLIENT-internal contradiction), the accepted interaction retains its existing v1 handling and **no v2 record is written**. Emit the specific §10.1 reason code in bounded, sanitized ingestion diagnostics and a versioned per-source import/migration report with reason/count/source revision. Those diagnostics/reports are operational artifacts, **not** extra canonical architecture evidence, public per-interaction refusal records or snapshot inputs. I2 SHALL specify their bounds/retention and report availability without introducing a second refusal persistence model by implication.

At query time, an unscoped v1 bucket **cannot establish which individual events were refused or why**. The new locality answer reports `INSUFFICIENT_EVIDENCE` with generic `LOCALITY_NO_ELIGIBLE_LOCAL_OBSERVATION` and, as relevant, `LOCALITY_LOCAL_COVERAGE_UNAVAILABLE`; `LOCALITY_LEGACY_V1_UNSCOPED` may be included **only where legacy-only source/inventory status is independently known**. It MUST NOT expose any specific ingress rejection code as if reconstructed from the aggregate, imply that every v1 contribution was refused, or silently invent a positive locality. The import/migration report can disclose the specific ingestion cause **in its own reporting surface**, without promoting that report to architecture evidence. If v2 exists for some events in a mixed v1 bucket, only those separately retained v2 records license local positive answers; the rest remain unscoped without a fabricated per-event explanation.

Query-time failures **after** a valid v2 record exists (selected source mode, capture time, namespace/cluster/owner ambiguity or contradiction) retain v2 Pod evidence unchanged and produce the specific §10.1 query disposition/reasons where known.

A Path C `AMBIGUOUS`, `CONFLICT` or `UNRESOLVED` status shall retain its source-specific evidence and reason, including when the new locality projection abstains. No Service identity is ever changed by name matching or by extracting a narrower scope, and an existing v0.5 refusal cannot be converted to positive locality. The independent dossier tests missing carrier versus specific missing fields, ingestion-report visibility versus generic read-side v1 abstention, and known ingestion versus capture-time contradictions.

## 11. Provenance, source lifecycle, conditional snapshot identity and cost

I1 freezes these cross-increment invariants:

1. **One canonical snapshot.** When no v2 scoped evidence exists, preserve the exact current v0.5 canonical input bytes, canonicalization version, `snapshot_id` and `model_revision`, including the pinned `examples/release-golden-path/expected.json` demo `expected_snapshot_id`. Do not unconditionally add empty v2 keys or bump version. When eligible v2 records exist, their sorted canonical inputs/rules are conditionally added to this **same** fingerprint used by old and new service/REST/MCP answers—not a second locality hash.
2. **Snapshot-bound drill-down.** Scoped assessment/evidence resolution uses the same stable selected revision fence and captured-source state. New evidence/capture changes that affect applicability must be captured in the assessment's derivation and snapshot. No silent newest-snapshot substitution.
3. **Existing inventory authority.** Reimport, capture revision and authorized removal follow v0.5 source authority. An incomplete inventory or missing old Pod never authorizes deletion of observed event evidence or a negative local relation.
4. **Bounded and sanitized retention.** Store only the admitted CLIENT allowlist, canonical relation/bucket/correlation metadata, bounded first/last timestamps/counts and sanitized provenance. No raw trace store, unbounded labels, secrets, host/IP identity or arbitrary Resource payload. Public reachability must be explicit before a scoped evidence ref is exposed.
5. **Cost grows with Pod churn.** Include `(relation × day × distinct caller Pod UID/cluster)` cardinality and test repeated replacement at constant Workload count, graph/fingerprint/read costs, limitation rate and v1/v2 migration overhead. ADR 0012 remains Proposed; do not compact, discard, silently truncate or coarsen scoped evidence under this I1 authorization.
6. **Separate sources of proof.** Original v1 relation evidence, v2 CLIENT event attribution, captured Pod/owner chain, applicable source-scoped declaration and later local qualification/projection must retain distinct derivation links. No synthetic combined source is permitted to erase those distinctions.

I2 shall prove the no-v2 golden fingerprint before enabling conditional v2 projection. If a pin cannot be retained, a separately reviewed parent compatibility amendment and independently regenerated expectations are required—not an unexplained fixture edit.

## 12. Controlled real two-Workload capture: mandatory I1 plan

I5 must qualify an **actual controlled execution**, not just generated telemetry. I1 SHALL deliver its reproducible acquisition plan, identify an owner or record the pending owner decision as an **I1 blocker**, specify source/artifact pins and provide early I2 rehearsal instructions.

Minimum permitted scenario (two clusters are *not* required, but **two distinct supported Workload objects are**):

```text
one canonical caller AIP Service: service:orders
cluster K / namespace N
  old/base Deployment "orders"         = distinct Workload W1, Pod UID P1
  new/canary Deployment "orders-canary" = distinct Workload W2, Pod UID P2
  both CLIENT Resources resolve to canonical caller service:orders

actual CLIENT from P1:
  service:orders --CALLS--> Operation pricing:GET /prices
  (canonical Operation owner: service:pricing)
actual CLIENT from P2:
  service:orders --CALLS--> Operation legacy-pricing:GET /prices
  (canonical Operation owner: service:legacy-pricing)

Operation labels here are illustrative; the runbook pins actual canonical Operation IDs
and separately established provider ownership from accepted sources.

selected captured-resource revision during rollout overlap:
  source.clusterUid == each CLIENT Resource k8s.cluster.uid
  P1 and P2 are both present with distinct captured UIDs
  P1 -> unique Pod -> ReplicaSet -> Deployment "orders"         (W1)
  P2 -> unique Pod -> ReplicaSet -> Deployment "orders-canary"  (W2)
  each v2 bucket.last_seen and capturedAt match the full-UTC-day window
```

**Do not use one Deployment rolling from ReplicaSet R1 to R2 as the two-locality positive fixture.** Both Pod owner chains would resolve to that *same* Deployment/Workload under admitted v0.5 semantics. Even when v2 emits two distinct per-Pod identities, a Workload-level projection must not count them as two Workload localities. Adding ReplicaSet-local granularity would require a separately reviewed parent-scope amendment and is outside this accepted I1 contract. The provider Service in parentheses above is a **logical** Operation owner for I3's dependency roll-up (§5.1), never evidence of target runtime placement.

The acquisition runbook must document the **two distinct Deployment identities and one canonical caller AIP Service binding**, exact canonical target Operation IDs/owners, reference deployment revision, authentic CLIENT Resource emission/collection method, cluster identity provenance, capture envelope/owner-chain extraction, `capturedAt`, environment mapping, source revisions and SHA-256 pins, independently authored expected results **before** AIP evaluation, clean offline replay and teardown. Capture the **old/new overlap before a later authoritative capture replaces either old resource**. Include a later post-promotion captured revision to test that old Pod Workload locality becomes `UNRESOLVED`, not absent or transferred.

Label distinctly (a) actual independently recorded controlled reference, (b) independently authored expected answers, (c) any synthetic negative-test fixture, (d) the frozen upstream Quarkus/Airflow dossiers, and (e) any future external product pilot. A controlled run is not automatically a production observation or a pilot. Do not rewrite upstream truth to make it suitable for locality.

**Schedule gate:** I1 delivers the acquisition plan and owner; I2 rehearses CLIENT retention and artifact-format validation before I5; I5 obtains and qualifies the real pinned capture. A live deployment is necessary only to **record** the reference, not to add live Kubernetes admission to AIP or to run the eventual frozen offline demonstration.

## 13. Independently authored conformance matrix

Before I2 implementation, I1 SHALL freeze source evidence and expected result for every row, including disposition/reason codes, accepted v1/v2 keys, captured-source context, evidence lineage and prohibited conclusions. The following scenario IDs specify required independently expected cases; they are not claims that tests have run.

| ID | Input situation | Expected I1 outcome / forbidden claim |
|---|---|---|
| L01 | Same canonical v2 key with reordered input fields | Byte-identical key; one v2 bucket identity. |
| L02 | Same caller Service, relation and **Operation ID** in one UTC day, observed from two Pod UIDs | Distinct v2 keys; one original v1 caller-Service → Operation relation bucket under legacy key; no automatic second Workload locality. |
| L03 | Same Pod UID text in two different cluster UIDs | Distinct scoped v2 keys; no cross-cluster alias. |
| L04 | One cluster/namespace, **two distinct Deployment Workloads** bound to one caller Service; each Pod calls a different canonical Operation | Independently supported caller-Workload → Operation results; logical provider Service is the Operation owner, never inferred target placement or exclusivity. |
| L05 | Existing v1-only CALLS plus separately persisted same-Service Pod identity | Unscoped v1 only; no positive local backfill. |
| L06 | CLIENT lacks Pod UID / cluster UID | v1 path unaffected; no positive scoped v2; explicit missing-identity disposition. |
| L07 | Paired CLIENT/SERVER in same batch | CLIENT Resource attributed; SERVER-derived route/fact timestamp preserved. |
| L08 | Cross-batch CLIENT first and SERVER first | Original CLIENT identity retained in both arrival orders, bounded carrier only. |
| L09 | Qualified CLIENT_ONLY vs SERVER_ONLY | CLIENT_ONLY may be eligible if v0.5 CALLS and exact CLIENT proof survive; SERVER_ONLY never manufactures caller-v2. |
| L10 | CLIENT and accepted fact environment differ | No scoped v2; legacy v1 behaviour unchanged. |
| L11 | CLIENT and fact timestamps fall in different UTC days | No forced same-day v2; preserve existing v1 path. |
| L12 | Same event has v1 and v2 representations | No doubling v0.5 counts, qualification, coverage or evidence arrays. |
| L13 | No v2 in unchanged golden-path graph | Exactly frozen v0.5 `snapshot_id` and canonicalization bytes. |
| L14 | Valid new v2 records | One conditionally changed canonical fingerprint with same-snapshot provenance. |
| L15 | Exact current captured Pod, owner, cluster, time | Workload-local applicable caller path. |
| L16 | CLIENT cluster UID conflicts with captured envelope `clusterUid` | Explicit conflict; no positive locality. |
| L17 | DECLARED_MANIFEST, missing `capturedAt`, incompatible captured day | No positive observed caller-Workload locality; different `UNSUPPORTED`/`INSUFFICIENT_EVIDENCE`/`INAPPLICABLE` diagnostics per §10.1. |
| L18 | P1 replaced by P2, later snapshot lacks P1 | Original P1 event persists, P1's Workload resolution `UNRESOLVED`, never inferred at P2. |
| L19 | Multiple admissible owner Workloads without contradiction versus contradictory owner assertions | Preserve distinct `AMBIGUOUS` versus `CONFLICT` dispositions/reasons; no specificity or recency guess. |
| L20 | Caller local and target locality missing | Only caller-local CALLS; target locality unknown. |
| L21 | Applicable Service-level declaration + independently observed scoped CALLS | Source-scoped declared + caller-local observed, I2 shared owner returns `CONFIRMED`. |
| L22 | Scoped observed CALLS without applicable declaration | `OBSERVED_ONLY`; wrong Service/Operation declaration cannot confirm. |
| L23 | Declared-only Service relation or Service-level coverage but no scoped call | No positive Workload-local CALLS, no local `NOT_OBSERVED_IN_WINDOW`; insufficient local coverage. |
| L24 | Region/tenant/version-locality or messaging locality requested | Explicit unsupported category; no global fallback. |
| L25 | Sub-day range or event exactly at next-day midnight | Unsupported scoped resolution or exact UTC-day boundary; existing v0.5 window untouched. |
| L26 | Name-only, co-location, configured Service `DEPLOYED_AS` | No per-interaction caller locality inferred. |
| L27 | Overlap captures old `orders` and new `orders-canary` **distinct Deployments** (one caller AIP Service), then later authoritative capture removes old Pod | Two Workload localities only on compatible overlap snapshot; subsequently missing old Pod -> `UNRESOLVED`. |
| L28 | Many successive Pods at constant Workload count | Distinct identities; Pod-churn storage/read-cost scenario. |
| L29 | Incomplete inventory or unauthorized source removal | No inferred local absence and no widened removal authority. |
| L30 | Intent/agent narrative changes alone | Current-State observation window stays distinct from future Intent effective interval; no changed evidence/qualification. |
| L31 | Known v2 `last_seen` day D, captured Pod `capturedAt` day D+1, request exactly D | `INAPPLICABLE` / `LOCALITY_CAPTURE_TEMPORAL_MISMATCH`, no positive D locality; §8 exact inclusive predicate. |
| L32 | Two observed Operations of one canonical provider Service, plus missing/ambiguous Operation owner negative | Per-Operation qualification and deduplicated evidence refs remain distinct; I3 grouping may derive one logical provider dependency only from uniquely owned positive Operations, with no cross-Operation false `CONFIRMED`. |
| L33 | Two ReplicaSets' Pods under **one** Deployment versus two distinct Deployment objects | Two v2 Pod keys in either case; **one** Workload locality in first case, two potentially evidenced localities only in second. |
| L34 | CLIENT Resource passes ingestion guards but selected capture has contradictory namespace/cluster; versus CLIENT-internal contradiction | The first retains v2 Pod-bound evidence and gives query-time `CONFLICT`; the second refuses v2 at ingestion, with v1 unchanged. |
| L35 | SERVER_ONLY, absent CLIENT carrier, missing CLIENT Pod/cluster, known ingress environment/day mismatch or CLIENT contradiction, plus valid v2 with Path C ambiguous/conflicting owners | Specific refusal reasons appear only in ingestion diagnostics/migration reports when no v2 is written; read-side v1-only answer is generic `INSUFFICIENT_EVIDENCE`/`LOCALITY_NO_ELIGIBLE_LOCAL_OBSERVATION` (with known legacy-only tag only when independently evidenced). Valid v2 retains specific query-time `AMBIGUOUS`/`CONFLICT`. Never double-emit generic carrier-missing and specific field-missing. |
| L36 | v2 event `last_seen` day D, selected capture `capturedAt` day D+1, requested day D; captured owner chain would also conflict | Phase 3 short-circuits at `INAPPLICABLE`/`LOCALITY_CAPTURE_TEMPORAL_MISMATCH`; owner identity is not evaluated or presented as in-scope `CONFLICT`. |
| L37 | Selected candidate has only `DECLARED_MANIFEST` and contradictory-looking owner data | Phase 2 gives candidate `UNSUPPORTED`/`LOCALITY_CAPTURE_MODE_UNSUPPORTED`; no phase-4 owner assertion or invented observed locality. |

Golden ID vectors (including L01–L37) must be evaluated under input permutation and clean replays; source/mapping/reconciliation cases must be independently expected, not self-oracled. I4 later runs the exact final candidate twice from clean state and tests service/REST/MCP semantic parity. I1 shall not claim those later tests passed.

## 14. Contract deliverables and bounded slices

Planned I1 supporting deliverables under `docs/specifications/0.6.0/` (I1 may consolidate documentation without losing traceability):

```text
i1-locality-and-evidence-applicability.md    # this spec after review
i1-locality-support-matrix.md                # dimension × evidence × claim kind
i1-scoped-evidence-v2-contract.md            # key/serialization/replay/migration/snapshot
i1-conformance-dossier.md                   # independent L01–L37 truth and ID vectors
i1-capture-acquisition-runbook.md           # actual capture plan, owner, I2 rehearsal
i1-completion-record.md                     # exact revision, accepted choices and I2 handoff
```

| Slice | Required deliverable | Exit evidence |
|---|---|---|
| I1.1 | Baseline code/source and role/applicability inventory | v1 attribution gap and no-inference matrix documented. |
| I1.2 | Scope/UTC-day/CLIENT field and disposition contract | Exact normalization, allowlist and negative tests frozen. |
| I1.3 | v2 canonical key, transition, replay, conditional snapshot/retention contract | Independently authored ID vectors and no-v2 golden-pin test specification. |
| I1.4 | Real controlled reference acquisition plan | Named owner, cluster/Pod/capture fields, rollout-overlap timing, replay/teardown and I2 rehearsal steps. |
| I1.5 | Independent conformance review and handoff | L01–L37 expected dossier, parent §9 exit-gate traceability, no unresolved semantic blocker, exact completion record. |

I1 may include pure contract validators/golden-vector scripts, but SHALL NOT silently absorb I2's storage, new graph writes, public APIs, or release-demo implementation. Documentation-only PRs need no claimed application test run.

## 15. Increment-level Contract Freeze Register

The parent and this I1 semantic scope are accepted. The following implementation-level names, exact schemas/ID vectors and conformance artifacts SHALL be frozen in reviewed I1 deliverables **before corresponding I2 implementation and independent fixture execution**. This is a contract freeze register, not a claim that I1 completion checks have already run:

| Decision | Accepted semantic constraint / required I1 freeze evidence |
|---|---|
| Internal version/type naming | `locality-contract/1`, role-specific typed scope and disposition; public wire contract belongs to I3. |
| Required per-interaction Resource | Actual CLIENT environment, Pod UID, cluster UID, event timestamp; existing canonical CALLS IDs. |
| Cross-batch carrier | Extend bounded transient CLIENT carrier with original admitted Resource fields, both arrival orders; distinguish ingestion-known CLIENT contradictions from later capture inconsistencies. |
| v2 key/ID | Version 2, fact triple, environment, UTC day, caller cluster UID and Pod UID; full SHA-256 opaque ID. |
| UTC-day selector / capture predicate | Inclusive date range normalized to UTC midnight through last-day 23:59:59.999999; scoped v2 `last_seen` and matching `capturedAt` each satisfy inherited inclusive Path C check; v0.5 datetime path unchanged. |
| Capture owner mapping | Query-time reconciliation in selected current snapshot; removed historical Pod -> `UNRESOLVED`; Path C `AMBIGUOUS` distinct from `CONFLICT`. |
| v1/v2 coexistence and migration | Exactly original v1 meaning plus isolated v2 when eligible; no retroactive v1 Pod backfill or double-count. |
| Snapshot | One conditional canonical fingerprint; exact existing golden IDs on no-v2 input. |
| Cause → disposition and multiple reasons | Freeze §10.1 strict request → source mode → environment/time → owner phase gates, terminal per-candidate `UNSUPPORTED`, `AMBIGUOUS`, within-phase precedence and sorted reasons; prove L35–L37. |
| Ingestion refusal diagnostics vs query visibility | §10.2 chooses bounded ingestion diagnostics and versioned source/migration reporting only, **without new persisted refusal facts**; when only v1 remains, query abstains generically and cannot reconstruct specific ingress causes (L35). |
| Operation → Service projection | I1 preserves per-Operation status and unique canonical owning provider Service; I3 freezes bounded roll-up schema, group-level qualification display, evidence union, owner ambiguity and limits (§5.1). |
| Observation window vs Intent | `LocalityDayContextV1` records actual Current-State observation days, never future v0.7 Intent effective interval (§4.3, parent §9.5). |
| Local coverage | None admitted in this slice; local `NOT_OBSERVED_IN_WINDOW` forbidden. |
| Actual capture | One cluster and **two distinct Deployment Workloads** behind one canonical caller AIP Service; one Deployment/two ReplicaSets is invalid for the positive two-locality test; I1 plan, I2 rehearsal, I5 actual overlap. |
| Cost/retention | Account for distinct Pod UID churn; ADR 0012 still Proposed, no implicit compaction. |

Any later alternative to the accepted scope, key distinctions, phase ordering, refusal visibility, temporal precision, replay handling, storage isolation or diagnostics must preserve the parent and appear as a reviewed amendment before I2 builds against it. Do not leave semantically important choices to implementation convenience.

## 16. I1 Definition of Done and handoff

I1 is complete **only** when:

1. The versioned role/scope vocabulary and evidence/dimension/claim-kind matrix explicitly state admitted and unsupported cases, caller/target/source/claim distinction and no wildcard fallback.
2. A testable in-batch/cross-batch CLIENT attribution contract cannot assign a relation by Service/Pod co-occurrence, name-only placement, SERVER identity or configured `DEPLOYED_AS`.
3. Exact v2 key/golden vectors, v1/v2 coexistence, migration, clean replay and no-double-count legacy rules are frozen.
4. Whole UTC-day timestamp/capture compatibility, including exact v2 `last_seen`/capture `capturedAt` inclusive predicates, selected-snapshot Pod churn and **phase-gated §10.1 cause-to-disposition mapping** (including terminal per-candidate `UNSUPPORTED`, `AMBIGUOUS`, same-phase sorted reasons and L36–L37 early exits), are independently covered.
5. Matching Service-scoped declaration and local observation qualify through the existing single owner, with no Workload-local coverage/negative claim invented.
6. No-v2 legacy fingerprint and frozen golden pins, plus conditional one-snapshot v2 projection, have exact before/after expected vectors.
7. I1 has a named acquisition owner, two distinct supported Deployment Workloads of one caller Service, Operation-accurate expected facts, required CLIENT/Kubernetes capture pins, overlap timing, clean offline replay/teardown plan and I2 early rehearsal gate.
8. Independently authored L01–L37 results and the **parent §9 gate-to-I1 traceability matrix below** are reviewed; no semantic blocker is silently deferred, and the completion record identifies evidence/source revisions, decisions and actual check status (`NOT_RUN` when appropriate).
9. Ingestion-only specific refusal codes remain in sanitized reports, never fabricated from unscoped v1 at query time; I2's reporting boundaries and no-extra-evidence guarantee are reviewed (§10.2; L35).
10. Scope extraction never broadens an existing v0.5 refusal and never rewrites canonical Service or Operation ownership by display-name matching (§§2, 5.1, 6, 9–10); positive/negative vectors make these failures visible.
11. Observation-day types and documentation explicitly distinguish evidence observation windows from future Intent effective intervals; Intent cannot enter local Current-State qualification (§4.3, L30).

### 16.1 Traceability to accepted parent §9 exit gates

| Parent I1 gate | Contract location | Required I1 completion evidence |
|---|---|---|
| 1. Exact versioned dimension/evidence contract | §§4–5, 7, 10, 15; DoD 1/3 | Frozen support matrix, v2 ID vectors, admissibility/disposition contract. |
| 2. Distinct caller, target, source and claim examples | §§2.1, 4–5, 12–13; DoD 1/7/8 | Operation-accurate two-Deployment case and negative target-placement tests. |
| 3. No broader v0.5 refusal or name-based Service reidentity | §§2, 5.1, 6, 9–10, L05/L20/L26/L32; DoD 2/10 | Independent identity/refusal tests; no guessed Service/Operation owner. |
| 4. Machine-visible missing/conflict/unsupported/time dispositions | §§8–10.2, 13/15; DoD 4/8/9 | Phase-gated cause/reason table incl. `AMBIGUOUS`, phase-2 source-mode `UNSUPPORTED`, day-D/day-D+1 early exit, and ingestion-report versus generic read-side visibility. |
| 5. Observation window differs from future Intent effective interval | §4.3, §8, L30; DoD 11 | Separate typed semantics, never Current-State derivation from Intent. |
| 6. Runtime identity positive versus name/co-location negative | §§6, 9, 12–13, L15/L26/L33; DoD 2/7/8 | Actual CLIENT + capture path and one-Deployment/ReplicaSet rejection. |
| 7. v1/v2 identity/migration/replay/cross-batch/day/retention | §§6–8, 11, 13/15; DoD 3/4/6/8 | Golden v2 IDs, frozen no-v2 fingerprint, coexistence, ADR 0012/cardinality handoff. |
| 8. Selected-snapshot Pod churn and executable real capture plan | §§9, 12–13, L18/L27/L31; DoD 4/7/8 | Distinct Deployment overlap, matching CLIENT/capture cluster UID, capturedAt, revision pins and I2 rehearsal plan. |

**I2 handoff:** implement the frozen CLIENT carrier, isolated v2 evidence, v1/v2 migration/replay, query-snapshot locality assessment, one fingerprint and shared qualification reuse. **I3 handoff:** enumerate bounded evidenced candidates and expose only admitted, scope-qualified answers with same-snapshot drill-down and unchanged v0.5 routes. This I1 spec does not itself claim the new public capability, actual I5 capture, product pilot, v0.6 qualification or release publication.

---

## References

- [Accepted v0.6.0 release specification](specification.md), §§3–9, 11, 15–16, 20–24, 30, 33–34.
- [ROADMAP](../../../ROADMAP.md), v0.6 and product-validation gates; [Product Doctrine](../../product-doctrine-and-strategic-direction.md), evidence-qualified local assessment and separation from Intent.
- [v0.5.0 I2 Kubernetes Discovery](../0.5.0/i2-kubernetes-discovery-vertical-slice.md) and [v0.5.0 I3 Runtime Identity Reconciliation](../0.5.0/i3-runtime-identity-reconciliation.md).
- [ADR 0010 — single qualification rule](../../adr/0010-single-qualification-rule.md); [ADR 0011 — snapshot identity/read cost](../../adr/0011-snapshot-identity-read-cost.md); [ADR 0012 — observed evidence retention (Proposed)](../../adr/0012-observed-evidence-retention.md).
- Current code: `app/canonical/ids.py`, `app/telemetry/{adapter,model,runtime_identity,correlation_buffer}.py`, `app/provenance/model.py`, `app/qualification/declared_observed.py`, `app/architecture_intelligence/{repository,deployment_reconciliation}.py`, `examples/release-golden-path/expected.json`.
