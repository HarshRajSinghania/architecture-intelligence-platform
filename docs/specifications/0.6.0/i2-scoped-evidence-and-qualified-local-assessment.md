# AIP v0.6.0 I2 — Scoped Evidence Implementation and Qualified Local Evidence Assessment

**Status:** Accepted (revision 0.4, merged in PR #312, merge `6cebe35`; accepted by the owner and recorded in the [I2 decision record](i2-decision-record.md)). Not yet implemented. This document prescribes I2 work; it is not an I2 implementation or qualification completion record.  
**Release / increment:** v0.6.0 / I2, Locality-Aware Current State  
**Repository path:** `docs/specifications/0.6.0/i2-scoped-evidence-and-qualified-local-assessment.md`  
**Entry baseline inspected:** `main` at `7a949cd3046e91ddd6ea67036b6bf47c241ed037` (PR #311, I1.5 merge and closure SHA). I2.1 SHALL record that closure SHA in its entry/decision record, without editing the frozen I1 oracle.  
**Governing authority:** [Accepted v0.6.0 parent](specification.md), especially §§3–12, 15–16, 33–34; [accepted I1 specification](i1-locality-and-evidence-applicability.md), especially §§4–13, 15–16. This draft does not reopen I1 semantics.  
**Frozen supporting inputs:** [I1 support matrix](i1-locality-support-matrix.md) §§10–15; [scoped-evidence v2 contract](i1-scoped-evidence-v2-contract.md); [independent conformance dossier](i1-conformance-dossier.md) and [`i1-vectors/conformance-expected.json`](i1-vectors/conformance-expected.json); [`i1-vectors/utc-day-window.json`](i1-vectors/utc-day-window.json); [`i1-vectors/v2-evidence-id.json`](i1-vectors/v2-evidence-id.json); [controlled-capture acquisition runbook](i1-capture-acquisition-runbook.md); [I1 completion record](i1-completion-record.md).  
**Normative words:** MUST/SHALL/SHALL NOT have their parent-spec meaning. Text explicitly marked **[I2 proposal — review before implementation]** is not yet a frozen decision.

---

## 1. Purpose and exit outcome

I2 implements the first *internally usable* locality-qualified Current-State path. For an accepted HTTP `CALLS`, AIP retains the original CLIENT event's admitted caller Pod/cluster identity before aggregation, writes separately isolated v2 evidence without changing its original v1 contribution, resolves that Pod at query time through the **selected, time-compatible captured-resource revision**, and produces an independently qualified local assertion with provenance and limitations.

The minimum demonstrable result is two distinct Deployment Workloads, `orders` and `orders-canary`, associated with one canonical caller `service:orders`, whose different, individually attributable CLIENT calls resolve to their respective canonical Operations. On the compatible overlap capture, the matching declared `orders → pricing` Operation is `CONFIRMED` and the independently observed undeclared `orders-canary → legacy-pricing` Operation is `OBSERVED_ONLY`. This establishes **caller** locality, not target placement, exclusivity, a universal dependency or local absence.

I2's deliverable is an internal, deterministic assessment/read model and tests. I3 owns bounded public locality enumeration/comparison, public REST/MCP routes and versioned public response schemas. I4 owns final-candidate independent repeatability/surface qualification; I5 owns the actual pinned controlled reference. A successful I2 rehearsal must not be relabelled as I5 capture evidence.

## 2. Scope and non-goals

**In scope:** original CLIENT carrier across in-batch and cross-batch correlation; exact I1 ingestion guards; isolated v2 key, canonical record and deterministic merge; v1/v2 coexistence; bounded operational transition/refusal reporting; selected-snapshot capture and owner reconciliation; a first-class internal `QualifiedLocalEvidenceAssessment`; the one shared declared/observed qualification owner; conditional unified snapshot fingerprint; deterministic and independently authored conformance tests; early controlled-capture rehearsal and I3 handoff.

**Not in scope:** new Kubernetes/OTel source families, live Kubernetes admission or polling, broad region/tenant/version or messaging locality, Workload-level HTTP coverage, historical snapshot reconstruction, public relation-localities APIs, generic graph/Cypher exposure, inferred target runtime placement, local absence or causal flow, Intent/policy/remediation, an LLM-dependent semantic path, or ADR 0012 compaction/retention enactment. Existing dependency/drift/evidence, Pub/Sub and `DEPLOYED_AS` behavior remain v0.5-compatible.

## 3. Authority and frozen versus proposed decisions

| Area | Already frozen by I1 | Exact implementation decision I2 must record |
|---|---|---|
| CLIENT attribution | Admitted original CLIENT Resource allowlist, exact non-empty string normalization, `client_timestamp = CLIENT.end_time`; I-1–I-5 | Carrier and accepted-fact data model, bounded failure diagnostics, transaction boundary |
| Scoped identity | Ten-field v2 key, sorted-key UTF-8 JSON, full SHA-256 ID, identity/rule versions | Persisted label, indexes, model/schema and query ownership |
| Merge | Fact-timestamp min/max, sum, strongest mode, sorted smallest five trace IDs, absorbing consistency conflicts | Storage-level atomic merge and repeatable seed-fold implementation |
| Legacy isolation | Existing v1 IDs/counts/qualification unchanged; no v2 ID in legacy `evidence_ids` or `_EVIDENCE_QUERY` | Standalone v2 nodes, no `:Evidence`/relationships/`owner_source_ids`, legacy `_RELATION_QUERY` and generated NL/MCP exclusion with negative tests |
| Candidate selection | I1 candidates must reach the phase-3 environment/UTC-day checks | Exact caller/Operation v2 selection without env/day prefilter, deterministic bounded reading and explicit limits |
| Multiple captures | One selected, accepted, snapshot-bound contribution per evaluated candidate; L16 conflict vs missing Pod | Explicit-selector fidelity; implicit *covering-source* predicate using actual Pod UID or proven cluster + namespace scope; deterministic one-candidate roll-up retaining source-specific limitations |
| No selectable covering source | Never invent a captured Pod absence or new I1 reason code | Candidate `INSUFFICIENT_EVIDENCE` with existing `LOCALITY_LOCAL_COVERAGE_UNAVAILABLE` plus explicitly named bounded **no-selectable-covering-source** limitation. If no positive local CALLS exists, answer uses generic `LOCALITY_NO_ELIGIBLE_LOCAL_OBSERVATION` + `LOCALITY_LOCAL_COVERAGE_UNAVAILABLE`. Distinguish this from a covering source's actual `LOCALITY_CAPTURE_MISSING_POD` (I2.1; §8.1). |
| Legacy-only proof | `LOCALITY_LEGACY_V1_UNSCOPED` requires independently known legacy-only inventory | Frozen cutover/source ledger, mixed-history guard and stricter snapshot-bound query proof |
| Capture | One selected `CAPTURED_RESOURCE`, exact UID and environment/whole-UTC-day predicates; ordered query phases | Persisted/read-side capture representation, resolution and evidence lineage |
| Assessment | One declared/observed owner; positive only from locally applicable v2; no local `NOT_OBSERVED_IN_WINDOW` | Stable assertion vs snapshot-bound assessment-instance identity, internal projection and types |
| Snapshot | No-v2 byte-identical pin; conditional `scoped_observed_calls_v2` sorted by ID; version 3, one fingerprint | Actual graph-to-state query, independently expected full *after* ID |
| Operations | Report vocabulary and reason boundaries; exact original corpus needed for v2 regeneration | Report bounds/retention/accessibility; retry and replay guarantees; positive evidence cost |

The implementation of these decisions requires an I2 review before the corresponding semantic code is enabled. A semantic disagreement is settled through a reviewed contract amendment, not by rewriting the independent dossier to match application output.

## 4. End-to-end data flow and ownership

```text
OTLP/HTTP protobuf receiver -> decoded RuntimeSpan
 -> existing service/Operation resolution and CLIENT/SERVER correlation
 -> original CLIENT's bounded attribution carrier + accepted v0.5 CALLS fact
 -> existing v1 observation path (unchanged)
 -> I1 ingestion I-1..I-5 -> eligible v2 seed OR ingestion-only refusal
 -> separately persisted caller-Pod-scoped v2 record
 -> stable snapshot fence + selected captured Kubernetes source/revision
 -> ordered phase 1..4 locality applicability and Pod/owner reconciliation
 -> matching source/Service-scoped declaration + shared qualification owner
 -> QualifiedLocalEvidenceAssessment + derivation + limitations
 -> I3 internal handoff (I3 later adds public projection/adapters)
```

`app/architecture_intelligence/service.py` remains the sole semantic owner for the eventual public question. I2 may expose a typed internal entry point consumed by that service; it SHALL NOT introduce a second semantic engine in REST, MCP, SQL/Cypher or an agent. The v2 record describes an attributed event contribution. It does not persist a resolved Workload as an immutable event key: locality is snapshot-dependent and must be assessed at query time.

## 5. Original CLIENT carrier and ingress guards

Extend `app/telemetry/correlation_buffer.py`'s bounded `PendingHttpSpan` (default TTL 60 s and maximum 10,000 entries unchanged) and the associated `app/telemetry/adapter.py` fact path so both arrival orders retain the **original admitted CLIENT** environment, cluster UID, Pod UID, optional namespace/Pod/Deployment/StatefulSet/DaemonSet names and converted CLIENT end timestamp. Do not read these from a SERVER Resource, `peer.service`, unrelated `RuntimeIdentityObservation`, Pod name, `DEPLOYED_AS`, or an inferred matching span. The carrier is transient and shall not itself be persisted.

Only after the existing v0.5 CALLS is accepted, evaluate I1 matrix §14 guards I-1–I-5. Use the receiver-converted aware UTC microsecond instant; for paired calls the accepted fact timestamp (and v1/v2 day and v2 first/last seen) comes from the SERVER, while the CLIENT end timestamp is checked for the same UTC day. For `CLIENT_ONLY`, these timestamps coincide. `SERVER_ONLY` never mints v2. A missing CLIENT identity or known ingress mismatch does **not** change accepted v1 behavior, mint a fabricated identity or refuse the original unscoped relation.

The exact allowlist, exact string matching without trimming/normalization, single CLIENT-internal contradiction `CLIENT_MULTIPLE_WORKLOAD_KINDS`, all simultaneous ingress reasons and primary disposition follow support matrix §§10, 14–15.1. Specific ingress-only reasons remain in operational diagnostics/reporting; do not reconstruct them from v1 in an architecture answer. Preserve v0.5's known size-eviction and receiver duplicate-key behavior as disclosed by I1; do not silently change the existing transport contract.

**Required proof:** in-batch paired, CLIENT-first and SERVER-first cross-batch, CLIENT_ONLY expiry, SERVER_ONLY, field absence/type/value, mismatching environments/days, simultaneous guards and UID conflicts; compare v1 output to the baseline for each case. A size-evicted CLIENT must not be retroactively localized.


## 6. v2 storage, canonical key, merging and coexistence

The persisted v2 key is exactly I1 v2 contract `1's ten fields, with `contract_version=2`, `source_type=OPENTELEMETRY`, `evidence_type=OBSERVED`, `relation_type=CALLS`, exact fact environment/day, canonical caller Service/target **Operation** and original CLIENT cluster/Pod UID. Derive `evidence:otel:calls-scoped:v2:<64 lowercase hex>` from sorted-key compact UTF-8 JSON (`ensure_ascii=False`) and full SHA-256, **not** RFC 8785. Namespace, Workload, names, display label, trace/span ID, count, timestamps and capture are not key inputs.

**[I2 proposal — amended after PR #312 review]** Persist v2 as standalone, uniquely indexed Neo4j `ScopedObservedCallV2` nodes keyed by `id`, accessible through a dedicated I2-only repository reader. This is a provisional *internal* label, not a public contract. V2 nodes SHALL NOT carry the legacy `:Evidence` label, SHALL NOT have **any incident graph relationships** (including CALLS), and SHALL NOT carry `owner_source_ids`. Source identity/revision on v2 is provenance, not import-lifecycle ownership. The importer's generic `_OWNED_NODE_IDS_QUERY` matches any node with `owner_source_ids` and its cleanup can `DETACH DELETE`: a declaration/Kubernetes reimport/removal must not sweep, rewrite or expire retained per-event Pod attribution. A future scoped-retention/expiry rule requires separate reviewed authority; ADR 0012 remains Proposed.

**A new label alone is insufficient.** The actual v0.5 reads are `_EVIDENCE_QUERY` and `read_evidence_rows` over `:Evidence`, plus `read_public_evidence_list_rows`/`read_public_evidence_row`. The snapshot `_RELATION_QUERY` is label-agnostic (`MATCH (a)-[r]->(b)`), so any v2 incident relationship would contaminate legacy `relations` and bypass the one conditional fingerprint key. I2 SHALL enforce *zero* incident v2 relationships and test this directly; protect the legacy relation projection against any future endpoint-shape change (explicit v2 endpoint exclusion if its query/write shape changes). The conditional `scoped_observed_calls_v2` key must be the **only** new canonical-state input from v2 (amended in I2.1a: plus the equally conditional `scoped_capture_scopes_v2`, [decision record D5](i2-decision-record.md#d5--capture-scope-under-the-fence-and-in-the-fingerprint-i2-81-stop-condition-amendment)), with no v2 in legacy `evidence`, `relations`, legacy relation `evidence_ids`, or old evidence resolvers. An unchanged no-v2 graph must preserve exact old state bytes.

**Generated NL/Cypher isolation is a separate pre-enablement gate.** On the inspected baseline, `app/ai/cypher_validator.py::validate_cypher` and `SemanticQueryValidator` accept unlabeled `MATCH (n) RETURN n`; a read-only session or prompt/schema omission cannot conceal v2. Before storing queryable v2, the actual `ArchitectureQuestionService.ask` execution path SHALL enforce fail-closed graph reachability: every node pattern, including `OPTIONAL MATCH`, nested subqueries, pattern expressions and relationship endpoints, must be explicitly bound to approved existing public labels; reject unlabeled/dynamic-label patterns, generic relationship scans, direct private-label matching and any query shape that cannot be proven within this allowlist. Check the **final executed query**, not just the LLM prompt or one validator in isolation. Keep `ScopedObservedCallV2` out of `KNOWN_NODE_LABELS` and do not expose a generic graph route. If the current generated-Cypher grammar cannot enforce this soundly, isolate its database read principal/store from v2 until it can. Negative tests shall cover `MATCH (n) RETURN n`, `MATCH (a)-[r]->(b) RETURN a,b`, private-label and dynamic/label-introspection attempts, including NL/MCP execution, while preserving authorized existing questions.

Persist precisely I1 v2 contract `3's non-identity fields. Merge `first_seen=min(fact timestamps)`, `last_seen=max`, `observation_count=sum`, strongest `correlation_mode`, sorted distinct first five trace IDs, and optional fields by **absorbing conflict** (once two non-null values differ, null/flag is permanent). The `A,B,A` vs `A,A,B` and seven-trace-sample permutation vectors, Pod churn and mixed Workload-kind seeds must match the independently frozen results. Baseline `merge_runtime_identity_observation` stays unchanged.

**One atomic POST transaction [I2 proposal].** Preserve `/v1/traces` → `ObservationBatch` → `session.execute_write(_persist_batch_tx, batch)` → one `bump_revision` from `app/telemetry/aggregator.py`. Write a POST's accepted v1 facts and eligible v2 seeds in the **same** transaction; v2 failure rolls that unit back rather than committing half a pair. A CLIENT/SERVER fact correlated across POSTs contributes in the **later POST** when the pair resolves. Ineligible v2 is normal accepted-v1 processing, not an import failure. Uniqueness of a v2 ID does not imply exactly-once transport across separately repeated successful POSTs.


## 7. Retry, migration and operational reporting — decisions to freeze

**[I2 proposal — amended after review]** One successfully decoded `/v1/traces` POST and its `ObservationBatch` form the ingestion unit, including an accepted cross-batch pair or TTL-expired CLIENT processed during that POST. One `execute_write` transaction commits the unit's v1 and v2 effects and bumps revision once; retries of a failed transaction are atomic. A separately repeated *successful* live POST is another unit and can increment the existing v1 and new v2 counts: no v2-only dedup claim or silent v1 compatibility change. Fold each accepted interaction once *within* a unit. Clean-state replay of the same pinned original interaction corpus reproduces v2 IDs and normalized records under seed permutation, but not arbitrary permutations of legacy v1's first-arrival trace samples. Historical aggregated v1 cannot be backfilled as local v2.

Produce the operational `aip-scoped-evidence-transition-report/1` with I1's exact categories: `LEGACY_UNSCOPED` (**v1 buckets**), `SCOPED_V2_WRITTEN` (**interactions**) and `SCOPED_V2_REFUSED` (**interactions**, one primary cause and sorted complete causes). Include real source identity/revision, environment, UTC day and bounded sanitized diagnostics/rule identity. The report is neither architecture evidence nor snapshot input and is never served by the public evidence resolver. **[I2 proposal]** Exact aggregate counters survive example truncation; freeze diagnostic sample caps, overflow indicator, authorized ingest/report availability and retention before I2.2.

### 7.1 Independent legacy-only provenance and cutover [I2 proposal]

A missing v2 row or old v1 `first_seen` cannot establish when *all* of a v1 bucket's individual calls were ingested. I2.1 SHALL record an immutable operational **v2-enable cutover ledger** for each actual configured telemetry source/stream: source identity, enabling committed graph revision, and a frozen ID inventory/digest of its pre-enablement v1 buckets. A live OTLP POST has the real configured stream/source identity and accepted graph revision (not a fabricated file/Kubernetes revision); an offline corpus has its pinned SHA-256 revision and source/line identity. A post-cutover contribution to a listed v1 bucket makes it *mixed*; neither the report nor an answer may call the entire bucket legacy-only merely because its ID existed earlier.

`LEGACY_UNSCOPED` in the transition report is limited to independently identified pre-enablement v1 inventory / unreplayable original inputs, with **v1-bucket count unit and as-of revision** explicit; if a later report cannot prove a bucket is wholly old, disclose mixed/unknown as separate operational diagnostics (not a fourth I1 report category) rather than silently count it as legacy-only. A refused post-cutover interaction belongs to `SCOPED_V2_REFUSED`, not an invented pre-cutover category. If the cutover proof/source identity is unavailable after restart, report unknown—not legacy-by-absence. The ledger is operational provenance and SHALL NOT alter canonical evidence or the no-v2 fingerprint.

Architecture-answer `LOCALITY_LEGACY_V1_UNSCOPED` has I1 §10.2's **stricter** condition: legacy-only source/inventory status for the exact request must be independently proven *and recoverable in its selected snapshot/derivation*. The operational cutover ledger alone or merely no v2 record does **not** qualify. If the no-v2 canonical pin cannot accommodate such snapshot-bound proof, omit this optional code and emit only `LOCALITY_LOCAL_COVERAGE_UNAVAILABLE` + `LOCALITY_NO_ELIGIBLE_LOCAL_OBSERVATION`, which is already the valid I1 outcome. No answer may change with mutable report availability. Test pre-v2-only, post-cutover-mixed and unknown history, repeated import, restart without the report, and a v1-only bucket plus unrelated `RuntimeIdentityObservation`.


## 8. Snapshot-bound capture, time and owner resolution

Read retained v2 evidence with **one selected canonical, revision-fenced snapshot**, including current admitted Kubernetes source contribution identities/revisions. Never read newest state outside the fence or reconstruct C1 after C2 replaces it. The v0.5 Path C exact Pod UID → captured Pod → unique owner/ReplicaSet → Deployment/StatefulSet/DaemonSet chain is the only allowed positive caller-Workload reconciliation. Names, annotations, co-location and generic `DEPLOYED_AS` cannot substitute for original CLIENT attribution.


### 8.1 Candidate inventory, covering sources and combination [I2 proposal — amended after PR #312 review]

The internal v2 candidate read filters by exact canonical **caller Service**, `CALLS` and optional exact canonical **Operation ID** only. It MUST NOT pre-filter by query environment, UTC day/`last_seen`, caller cluster or resolved Workload: these are phase-3/4 applicability inputs, not a positive-only repository query. L10b (wrong requested environment) and L17d (day-D v2 against day-D+1 query) must reach phase 3 with retained identity and explicit `INAPPLICABLE`. Read in stable v2 `id` order under one revision fence, with bounded internal pages and visible truncation; I3 freezes public bounds/continuation.

**Each assessed pair** binds a retained v2 candidate to a currently committed, accepted Kubernetes contribution in the *same selected canonical snapshot*. Retain source instance, configured discovery scope, authoritative envelope `scope.namespaces`, current revision, evidence mode, envelope `clusterUid` and `capturedAt`. Accepted envelopes have explicit nonempty namespace lists (never wildcard) and `completeness.status=COMPLETE` **relative to that scope**, not to an entire cluster. I2.1 must prove the accepted scope/revision is available under the snapshot fence and any relevant scope change changes answer lineage/fingerprint. If not, never reconstruct scope from a latest file or assume same-cluster means complete coverage; stop for the reviewed fingerprint/representation decision.

**Explicit selection:** If a request or I1 oracle selects CAP-A/CAP-B/CAP-DM, evaluate that exact accepted, currently selected contribution regardless of the *implicit* coverage predicate. `DECLARED_MANIFEST` still terminates at phase 2 per candidate. A K2 v2/P1 explicitly evaluated against K1 CAP-A containing P1 must reach L16's phase-4 `LOCALITY_CLUSTER_UID_CONFLICT`. An absent, stale, rejected CAP-PARTIAL or externally preserved old C1 cannot silently become the selected capture. A missing explicit selection has candidate `INSUFFICIENT_EVIDENCE` and a bounded selection/coverage limitation, not a fabricated phase-4 missing-Pod reason or invented `LOCALITY_*` code.

**Implicit selection:** Enumerate accepted current sources by stable source/scope/revision order. Include a candidate/source pair only if one of these is proven from the selected snapshot:

1. The source actually contains a captured Pod with exactly the original CLIENT `caller_pod_uid`, **even when its envelope cluster UID differs** (preserves L16 and the ability to report a namespace conflict).
2. Its envelope `clusterUid` equals the v2 `caller_cluster_uid` **and** its declared complete `scope.namespaces` contains the admissible original CLIENT `client_namespace`. This admits the genuinely covering later capture that no longer contains P1, preserving L18/L27. Equal cluster UID *without matching namespace scope* is insufficient. If CLIENT namespace is missing, never infer it from Service name, Workload or unrelated observations: only rule 1 admits a source.

A non-covering source is **omitted**, not evaluated to `LOCALITY_CAPTURE_MISSING_POD`. An otherwise eligible `DECLARED_MANIFEST` source still participates and terminates at phase 2. Never prefilter environment/time or identity contradiction from a covering pair. The coverage predicate is only an implicit *source-inventory* selection; it does not alter I1's four ordered gates.

For each included pair apply phases separately, in I1 order: (1) request preflight; (2) selected source mode; (3) exact v2 environment, `last_seen` and selected real parseable `capturedAt` within the whole UTC-day window; (4) exact Pod/cluster/namespace and owner-chain/optional-attribute reconciliation. At phase 4, **same captured UID with conflicting cluster** gives `CONFLICT / LOCALITY_CLUSTER_UID_CONFLICT` (L16); a proven covering source with **no captured matching UID** gives `UNRESOLVED / LOCALITY_CAPTURE_MISSING_POD` (L18/L27). No other source supplies an unseen Pod to this pair. Preserve first-terminating-phase disposition, sorted reasons, source/capture lineage and L36/L37 early exits in every pair.

**One-candidate roll-up (after, not inside, the independent I1 phase gates):**

- **Zero covering sources:** retain the v2 candidate and return candidate `INSUFFICIENT_EVIDENCE` with `LOCALITY_LOCAL_COVERAGE_UNAVAILABLE` and the explicitly named bounded **no-selectable-covering-source** limitation from the I2.1 decision table (not a newly minted `LOCALITY_*` reason). If no positive local call is established at answer level, use I1's generic `LOCALITY_NO_ELIGIBLE_LOCAL_OBSERVATION` and `LOCALITY_LOCAL_COVERAGE_UNAVAILABLE`; optional legacy-only status still requires §7.1 proof. Never mint `LOCALITY_CAPTURE_MISSING_POD`.
- **One covering pair:** candidate disposition/reasons equal exactly that pair's result, preserving all single-source L15/L16/L18/L27 fixtures.
- **Multiple covering pairs:** keep every pair's source-specific disposition/reasons/lineage. A known pair `CONFLICT`, or two `APPLICABLE` pairs resolving the same original Pod attribution to different canonical Workloads, makes the candidate summary `CONFLICT` (the latter owner contradiction uses existing `LOCALITY_POD_OWNER_CONFLICT` with both chains). Otherwise any `AMBIGUOUS` pair yields summary `AMBIGUOUS`. Otherwise one or more `APPLICABLE` pairs for the same exact Workload yield summary `APPLICABLE`, with that one supported Workload claim and all other pairs' `UNRESOLVED`/`INAPPLICABLE`/`UNSUPPORTED`/`INSUFFICIENT_EVIDENCE` as **separate source-specific limitations**: neither silently discard them nor turn them into local absence. When none is positive/conflicting/ambiguous, use the common disposition if all pairs agree; otherwise summary `INSUFFICIENT_EVIDENCE` with every pair's unchanged result, not invented combined cause codes. Deduplicate only exact identical positive Workload identities and retain all supporting source revisions. Sort pairs by source/scope/revision and reasons lexically; import/read order cannot change the result.

This **aggregate** does not recompute any pair's first terminating phase, globally rank phase-specific reasons or convert legitimate different source scopes into an asserted architecture contradiction. If a known compatible identity conflict exists, a source-agnostic positive candidate summary is withheld while each individual source outcome remains inspectable.

**Additional two-source regression (I2-authored; the frozen I1 oracle remains unchanged):**

| Snapshot and original CLIENT for P1 | Implicit selected pairs | Summary and mandatory result |
|---|---|---|
| A: K1/`shop` complete, P1 → W1. B: K1/`billing` complete, P1 absent; CLIENT namespace `shop`. | A only | `APPLICABLE` W1. B cannot produce false missing-Pod reason. |
| A as above; B: other cluster K2 without P1. | A only | `APPLICABLE` W1. Unrelated cluster omitted. |
| A captures P1 → W1; B: K1/`shop` complete but P1 absent. | A + B | `APPLICABLE` W1 from A; preserve B's `UNRESOLVED / LOCALITY_CAPTURE_MISSING_POD` as separately attributed limitation. |
| A as above; B: K2 captures same actual Pod UID P1. | A + B | B reaches L16 `CONFLICT / LOCALITY_CLUSTER_UID_CONFLICT`; candidate summary `CONFLICT`, both outcomes preserved. |
| Only accepted C2: K1/`shop` complete; P1 removed. | C2 only | L18/L27 `UNRESOLVED / LOCALITY_CAPTURE_MISSING_POD`; v2 P1 retained. |
| No capture has P1; original CLIENT namespace missing; all captures only namespace-scoped. | None | Candidate `INSUFFICIENT_EVIDENCE / LOCALITY_LOCAL_COVERAGE_UNAVAILABLE`; no fabricated Pod absence. |

A present nonempty offset-less `capturedAt` can reach phase-3 temporal limitation; an absent required field rejects the envelope before selection (L17e). Invalid CAP-PARTIAL retains prior CAP-A (L29). Optional original CLIENT identity disagreement is phase-4 `CONFLICT`, never an ingestion rewrite. Preserve Path C `AMBIGUOUS` vs `CONFLICT`; do not infer continuous Pod presence or target placement.

## 9. Internal Qualified Local Evidence Assessment

Implement a typed result at minimum equivalent to the parent §10 semantic unit:

```text
QualifiedLocalEvidenceAssessment:
  assertion_ref: stable scoped assertion identity
  assessment_instance_ref: snapshot-/rule-bound evaluation identity
  subject_service_id: canonical Service
  assertion: CALLS -> canonical Operation
  context: exact environment + ScopedDayWindowV1
  caller_scope: evidenced cluster UID, namespace and unique Workload ref
  target_runtime_scope: UNKNOWN unless separately evidenced (not part of minimum)
  observation: distinct applicable v2 evidence refs and fact time bounds
  declared_evidence: independently applicable Service/Operation source refs, if any
  selected_capture: source instance + revision + evidence mode + real capturedAt
  derivation: v2 CLIENT attribution; selected Pod/owner chain; declaration match;
              normalization, identity and shared qualification rule IDs/versions
  applicability: I1 disposition + sorted reason codes
  qualification: shared-owner result where positive; otherwise no fabricated status
  coverage: local Workload-level coverage unavailable
  limitations: bounded, evidence-qualified and phase-specific
  snapshot_id / model_revision: the same stable canonical snapshot as the read
```

**[I2 proposal — review before implementation]** Use a pure deterministic internal read-side assessment, without a materialized `LOCAL_ASSESSMENT` graph node. Distinguish a stable **assertion ID**, derived by versioned canonical JSON/hash from canonical caller Service, canonical Operation, exact environment/window and resolved captured Workload identity (cluster UID, namespace, supported kind and UID/ref), from an **assessment instance** tied to the assertion ID, selected canonical snapshot, capture revision and applicable rule versions. Keep v2 Pod evidence IDs as lineage, not as the Workload-assertion key, so multiple actual caller Pods of one Workload can contribute without inventing multiple Workloads. Where applicability does not resolve a unique Workload, return a candidate limitation tied to the v2 attribution and snapshot; do not mint a positive Workload-scoped assertion ID. Freeze exact type names, byte encoding, version strings and expected identity vectors in a reviewed I2 slice. Neither ID is a new public I3 wire contract.

An assessment is Current State only, not Intent. A narrative/Intent-only change must not alter it. Read order, group order, reference order and limitation order must be deterministic. Return enough capture/source identity to reconstruct *why this scope* is applicable; do not synthesize an all-localities fact.

## 10. Shared qualification and local coverage boundary

Reuse `app/qualification/declared_observed.py` as the sole semantic owner of `CONFIRMED`/`OBSERVED_ONLY` logic, applied to **the exact eligible scoped Operation call** and its separately source/Service-scoped declaration. Do not implement a parallel truth table in a new service/read query, and do not pool declared evidence for Operation O1 with observed evidence for O2. With eligible v2 observation and exact applicable declaration: `CONFIRMED`. With eligible v2 and no applicable declaration: `OBSERVED_ONLY`. A declared-only v1/Service relation or unrelated Pod observation mints **no positive local CALLS**.

No admitted minimum input proves Workload-level HTTP coverage. Consequently local `NOT_OBSERVED_IN_WINDOW` is **unreachable** and SHALL NOT be emitted. Where there is no retained eligible v2, answer `INSUFFICIENT_EVIDENCE` using `LOCALITY_NO_ELIGIBLE_LOCAL_OBSERVATION` and `LOCALITY_LOCAL_COVERAGE_UNAVAILABLE`; include `LOCALITY_LEGACY_V1_UNSCOPED` only with §7.1's independent **snapshot-bound** proof for the exact source/inventory; an operational report alone or a missing v2 row cannot justify that optional code. Never leak an ingestion-only reason into the query, treat an unsupported/unresolved candidate as absence, or change unscoped v0.5 coverage and qualification.

## 11. Conditional canonical snapshot and read consistency

Use `app/architecture_intelligence/repository.py`'s one canonical state/fingerprint mechanism. With **zero** v2 records, preserve `_CANONICALIZATION_VERSION = 3`, identical state bytes, `model_revision`, all v0.5.1 pins and the golden demo snapshot `aip:snapshot:v1:0bfcbdeda363876559bb78f53e432f1a73c368e9fbd4d21c37f8f4335ecdbd5f`. The key `scoped_observed_calls_v2` must be **absent**, not `[]` or `null`. No v2 schema or rules may accidentally perturb the no-v2 semantic-config projection.

With v2 records, add only I1 contract §8's conditionally present state key (amended in I2.1a: plus the conditional `scoped_capture_scopes_v2` of [decision record D5](i2-decision-record.md#d5--capture-scope-under-the-fence-and-in-the-fingerprint-i2-81-stop-condition-amendment), also absent with zero v2 records), ordered by v2 ID, with exactly the frozen fields and `YYYY-MM-DDTHH:MM:SS.ffffffZ` timestamps; keep canonicalization version 3. V2 must not reach legacy `relations` via `_RELATION_QUERY`, `evidence` via `_EVIDENCE_QUERY` or source-import ownership via `owner_source_ids`. Hash this *one* state. Do not add a second locality fingerprint or let v2 records appear in the legacy `evidence` array. Snapshot and assessment reads use the existing stability fence; a changed selected capture/owner state changes lineage and unified snapshot even if retained v2 IDs have not changed. I3's later scoped drill-down must resolve against that same snapshot and refuse a mismatched/stale ref rather than silently switch to latest.

**Pre-enablement gates:** (a) independently prove byte-exact no-v2 golden pin against the baseline; (b) produce and freeze an **independently expected full-graph after-`snapshot_id` vector**, not only I1's already-frozen two-record fragment; (c) prove an actual v2-positive current graph yields that value; (d) verify no v2 ID leaks through `_EVIDENCE_QUERY`, `read_evidence_rows`, `_RELATION_QUERY` or any existing v0.5 relation/evidence/dependency/drift read; (e) assert zero incident v2 relationships or `owner_source_ids`, including after a declaration/Kubernetes import/removal; and (f) deny private/unlabeled Cypher on the actual NL/MCP execution path *before* enabling persistence. If an old pin cannot be preserved, stop for the parent-required compatibility amendment; never update a fixture to match an unexpected output.

## 12. Early controlled-capture harness rehearsal

Build the runbook §3 harness (real OTel SDK HTTP client/server instrumentation, two distinct `orders` Deployments sharing one canonical caller Service, `pricing` and `legacy-pricing` providers). Use the Downward API for actual Pod UID and a pinned `kube-system` namespace UID both as CLIENT cluster UID and captured envelope `clusterUid`; no collector-side `k8s.*` enrichment and no synthesized CLIENT spans. Capture C1 with both Pods and C2 after P1 removal, each with real timestamp, source revision and pinned files. Respect stop conditions and non-atomicity disclosure.

Rehearse the runbook's exact offline JSONL → replay Collector HTTP JSON → protobuf exporter → AIP `/v1/traces` path with pinned config, no replay processors/queue/retries. Assert AIP accepts every forwarded protobuf request, one line corresponds to one request, decoded Resource fields remain byte-equal, the source envelopes/digests validate, owner chains resolve uniquely, and both cross-batch arrival orders retain CLIENT identity. Evaluate C1 before selecting C2. Record the rehearsal separately and label it `rehearsal`, **not** the independently recorded I5 qualification fixture. I2's failure to pass any runbook §9 gate blocks I2 exit and I5 acquisition.

## 13. Independent conformance and compatibility evidence

Use the independently authored I1 `conformance-expected.json` (L01–L37, including L17e/L29a–b) as a **read-only oracle**, together with UTC-day (W/M/D/T), v2 key/merge (V/U/MP) and snapshot vectors. For each applicable variant, construct a concrete ingestion/source/capture/assessment test, assert the exact phase, disposition, sorted reasons, identity/ref and prohibited conclusion. Turn abstract Path C `CAP-AMB` and `CAP-CONF` into actual admissible fixture graphs and preserve the distinction between them. Test the L29 invalid-envelope import through the existing validator, not as a fictional selected capture.

Additional integration gates:

| Area | Required evidence |
|---|---|
| Attribution | Same-batch; both cross-batch orders; CLIENT_ONLY and SERVER_ONLY; no name/co-location/DEPLOYED_AS substitution; wrong/absent UID/env/day; retained ingress-only causes |
| Storage and NL isolation | Exact v2 IDs, distinct cluster/Pod/day/Operation; zero `:Evidence`, incident relationships or `owner_source_ids`; legacy `_EVIDENCE_QUERY`/`_RELATION_QUERY` no-leak plus NL/MCP unlabeled/private-label refusal; v1 single counted, per-POST atomic rollback |
| Replay and legacy provenance | Clean-state corpus replay; all v2 merge vectors; fixed-order repeated clean runs; later-POST cross-batch fact and repeated successful POST count; actual source revision and cutover-ledger pre-v2/mixed/unknown tests |
| Candidate and capture applicability | L10b/L17d without environment/day prefilter; §8.1 explicit selection versus implicit actual-UID/proven-cluster+namespace coverage; A(`shop`)/B(`billing`) two-source no-false-missing-Pod, genuinely covering B missing-Pod limitation retained, K2 same UID L16 conflict, no-cover `INSUFFICIENT_EVIDENCE`, deterministic candidate summary; all four phases, owner ambiguity/conflict, churn, rejected-source non-selectability |
| Qualification | O1 `CONFIRMED` vs O2 `OBSERVED_ONLY`; declaration provenance; no cross-Operation pooling; no local negative/coverage promotion |
| Snapshot | No-v2 exact pin, independently expected full after pin, canonical sorting, one revision-fenced snapshot, changed C1/C2 lineage, v2 absent from legacy evidence reads |
| Compatibility | Existing dependency/drift/evidence/Pub/Sub/DEPLOYED_AS semantic and contract regression; full quality, type, imports, security and integration gates |
| Capture | Runbook §9 rehearsal and provenance log; actual I5 capture remains `NOT_RUN` |

Do not assert arbitrary permutation invariance of **legacy v1 sample ordering**: I1 expressly preserves v0.5 first-arrival samples. Prove v2 normalized order independence separately and clean-run byte equality for a **fixed replay order**. I4 will repeat final-candidate qualification, not infer success from I2's development tests.

## 14. Safety, observability and cost

Store only I1-admitted bounded CLIENT metadata, source/rule provenance and at most five trace samples per v2 record; no raw spans, complete OTel Resources, credentials, inferred host/IP identity or arbitrary `k8s.*`. Diagnostics must be sanitized and bounded and never become architecture evidence. Emit operational counts for v1-only versus eligible/refused v2, resolution success/`UNRESOLVED`, cardinality by environment/day/Pod churn, graph size, fingerprint time, read latency, and report overhead. A stress case with many Pod replacements at fixed Workload count must measure these against a no-v2 baseline. Record observed values in the completion record; this draft invents no performance thresholds or successful measurements. Retention/compaction behavior remains unchanged absent a separately accepted ADR.

## 15. I2 slices and exit evidence

| Slice | Bounded delivery | Required exit artifact |
|---|---|---|
| **I2.1 — Decisions and carrier** | Freeze graph/NL isolation, unfiltered candidates, §8.1 implicit covering-source selection and per-candidate roll-up (including no-cover `INSUFFICIENT_EVIDENCE`), prove authoritative scope/revision available under snapshot fence and fingerprint-sensitive; cutover, identity, one-POST transaction/report/replay; record I1 closure SHA `7a949cd`; implement CLIENT carrier/I-1–I-5 | Reviewed I2.1 decision table naming the **no-selectable-covering-source** limitation and generic-code fallback, plus all six two-source/no-cover tests from §8.1, NL access negatives, ingestion guards and both cross-batch orders |
| **I2.2 — Isolated v2 persistence** | Canonical v2 ID, seed/merge, standalone node/index/read, per-POST transaction and cutover/transition reporting | V/U/MP vectors, `:Evidence`/`_RELATION_QUERY`/NL no-leak and source-removal tests, deterministic replay and legacy-only/mixed/unknown proof |
| **I2.3 — Selected-capture applicability** | Unfiltered caller/Operation v2 candidates, snapshot-bound explicit/candidate × proven-covering-source selection, deterministic source-aware roll-up/limitations, UTC-day phases, owner/UID and churn | L10b/L17d, L15–L20/L27/L29/L31/L34–L37 plus §8.1 six two-source/no-cover tests: unrelated namespace omitted, covering B's missing-Pod retained, same-UID K2 L16 conflict, stale source, Path C ambiguity/conflict |
| **I2.4 — Qualified assessment** | Stable scoped assertion/assessment identity, applicable declaration via shared qualification owner, typed lineage and limitations | Independent O1/O2 positive tests, declared-only and local-coverage negative tests, same-scope isolation |
| **I2.5 — One snapshot and compatibility** | Conditional v2 canonical-state input; no-v2 and full v2 after ID pins; legacy surface isolation and transaction/replay qualification | Independent full after vector, exact golden-path pin, regression results |
| **I2.6 — Harness, qualification and handoff** | Build/run early rehearsal, complete 65-variant I1 dossier mapping, measure Pod-churn cost, document internal read contract for I3 | Pinned rehearsal log, test matrix, measured bounds, I2 completion record, explicit I3 handoff |

A slice MAY be split or regrouped without moving acceptance criteria. In particular, the capture rehearsal must occur early enough to discover missing CLIENT Resource or replay-format behavior before I5; it cannot be treated as optional polish at the end. Keep PRs focused and record review-driven decisions against the frozen spec.

## 16. Definition of Done, completion record and I3 handoff

I2 is complete only when all of the following are independently supported, not just stated:

1. Original CLIENT identity survives accepted same- and cross-batch CALLS and its ingress guards; v1 semantics do not change when v2 is refused.
2. Every eligible interaction produces the exact isolated v2 ID and order-independent normalized record, with no `:Evidence`/legacy relation/NL/MCP leak, no `owner_source_ids` import-removal risk and no double-counting on existing v0.5 surfaces.
3. One-POST atomic v1/v2 transaction, retry/replay, actual transition-report source identity/revision/bounds/retention, immutable cutover proof and strict snapshot-bound legacy-only diagnostic have reviewed semantics and executable tests; no unearned exactly-once or historical backfill claim.
4. I2 reads caller/Operation candidates without environment/day prefilter (L10b/L17d); explicit source selection and §8.1 implicit *proven* coverage distinguish unrelated namespace/cluster non-pairs from real missing Pods, with deterministic candidate roll-up, retained source-specific limitations, L16 cluster conflict, C1/C2 churn and all four phase gates under one fence. All six §8.1 regression rows pass.
5. Two eligible Workload localities coexist for one canonical caller Service and yield the independently expected Operation-granular `CONFIRMED` and `OBSERVED_ONLY` assessments through the existing qualification owner; no local `NOT_OBSERVED_IN_WINDOW`.
6. The typed first-class assessment has a reviewed stable assertion/instance identity, source/CLIENT/capture/qualification derivation and Current-State-only scope; no materialized assessment is required.
7. Without v2, canonicalization version/state/fingerprint and the published golden path are byte-identical; with v2, a *new independently authored full-graph after pin* proves the conditional single snapshot and stable reads.
8. All I1 L01–L37 variants and vectors have executable implementation-test coverage (the abstract and import-rejected fixtures are made reachable), and v0.5 regression/quality gates pass. State counts, exact HEAD and failed/skipped status; never call an unrun check passed.
9. The two-Workload harness passes the runbook §9 rehearsal and is labelled as such, with digest/provenance/run record; the real I5 capture is not claimed.
10. The completion record reconciles the accepted plan, decisions, deviations, unresolved questions, deferred work, benchmark/cardinality measurements, source versions, test commands and exact merged PR SHAs. Any missing requirement is an explicit blocker or independently approved amendment, never silent deferral.

**Handoff to I3:** provide a pure internal request/result API under the one Architecture Intelligence semantic owner that enumerates caller/Operation v2 candidates *without an environment/day prefilter*, distinguishes explicit selected source from implicitly proven covering sources, exposes both the §8.1 deterministic per-candidate disposition and **all** source-specific pair dispositions/limitations (including no-cover abstention) under one snapshot, and reports bounded-scan incompleteness; I3 then sets public continuation/bounds and selected-scope comparison; supply exact assessment ID/lineage, per-Operation qualification, unqualified candidate/limitation semantics, selected-source/coverage diagnostics and stable evidence lookup hooks. I3 freezes the public Service dependency roll-up, same-snapshot evidence drill-down, REST/negotiated MCP schema/version and final route/tool count. I2's internal interface does not license a public endpoint or a second evidence-resolving hash.

## 17. Items requiring explicit owner review before implementation

The accepted parent and I1 texts do **not** resolve the following I2-level details; their proposed choices above must be reviewed and frozen before corresponding work:

1. Exact v2 graph label/index/read with **no `:Evidence`, incident relationships or `owner_source_ids`**, legacy `_RELATION_QUERY` protection and fail-closed NL/MCP explicit-public-label access checks, proven by negative tests before enablement.
2. Stable scoped assertion ID versus snapshot-bound assessment-instance ID, canonical bytes, version and the negative-candidate identity policy; read-side-only versus materialized assessment.
3. Preserve one-POST `execute_write` and later-POST cross-batch contribution, atomic v1/v2 effects, failed transaction retry and disclosed repeated-successful-POST behavior; no v2-only transport dedup.
4. Actual live OTLP source/committed-unit revision versus pinned offline replay, independent pre-v2 cutover ID inventory, mixed/unknown history and snapshot-bound `LOCALITY_LEGACY_V1_UNSCOPED` gate; report schema/count unit/cap/retention and authorized surface.
5. Independently authored full-graph positive snapshot fixture and assertion ID vectors; no-v2 pin is not negotiable by ordinary fixture updates.
6. Internal caller/Operation v2 candidate set without environment/day prefilter, explicit-source fidelity, §8.1 implicit proven coverage and deterministic one-candidate roll-up across current source revisions (including source-specific missing-Pod limitations and no-cover `INSUFFICIENT_EVIDENCE`), plus I2→I3 lineage/fence. I3 freezes public shapes and bounds.
7. Rehearsal harness image/tool digests and capture provenance; no substitution of synthetic spans for actual CLIENT emission.

**Stop condition:** if implementation leaks v2 through label-agnostic NL, legacy `evidence`/`relations` or import ownership; prefilters away L10b/L17d; treats an unrelated namespace/cluster as missing Pod, silently drops a covering source's limitation or privileges one conflicting capture; guesses between capture sources; asserts legacy-only from missing v2; infers Pod attribution from unrelated observations; changes v1; bypasses phases; selects rejected capture; fabricates local absence, a second fingerprint or weakened I1 rules, stop for a reviewed amendment, not self-confirming fixtures.