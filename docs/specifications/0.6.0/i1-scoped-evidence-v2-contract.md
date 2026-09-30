# AIP v0.6.0 I1 — Scoped Observed-Evidence v2 Contract

**Status:** I1 supporting deliverable, slice I1.3 (v2 canonical key, v1/v2 transition, replay, conditional snapshot and retention contract). This is a contract freeze artifact under review. It claims no implementation and no executed conformance.  
**Release / increment:** `v0.6.0` — Locality-Aware Current State / I1  
**Governing specification:** [I1 — Locality and Evidence Applicability Contract](i1-locality-and-evidence-applicability.md) §§2.1, 7, 11 and 15, accepted in [PR #283](https://github.com/michaelegner/architecture-intelligence-platform/pull/283) (merge `aafb03d5735d78b2741a3dc8a2d0336079535ed6`), under the [accepted v0.6.0 parent](specification.md) §§7, 33.  
**Builds on:** [I1 Locality Support Matrix](i1-locality-support-matrix.md). §10 there fixes the CLIENT allowlist and normalization, and §12 the timestamp roles.  
**Code baseline:** `main` at `b9f1025`. The `file:line` references are to that commit.  
**Contract identifier:** `locality-contract/1`.

As in the I1 generations terminology (I1 §2.1), **v1** is the existing Service-level daily observed-evidence bucket and **v2** is the new, separately isolated caller-Pod-scoped daily evidence for an accepted HTTP `CALLS`. Neither name refers to an AIP release or an API version. Where this document and the I1 specification disagree, the I1 specification wins. Owner decisions taken for this slice are marked **[owner decision, I1.3]**. The I1 spec left each of them to I1, and none weakens it.

---

## 1. v2 key: logical identity (I1 §7.1)

A v2 record's identity is exactly these ten fields. No other field is an identity input.

| Field | JSON type | Value |
|---|---|---|
| `contract_version` | integer | `2` |
| `source_type` | string | `OPENTELEMETRY` |
| `evidence_type` | string | `OBSERVED` |
| `relation_type` | string | `CALLS` |
| `environment` | string | The accepted fact environment. The CLIENT environment is exactly equal to it by guard I-3. |
| `bucket_utc_day` | string `YYYY-MM-DD` | The UTC day of the accepted fact timestamp. It equals the CLIENT's UTC day by guard I-4, and the v1 bucket day (matrix §12.3, §12.6). |
| `subject_id` | string | The canonical caller Service ID of the accepted v1 CALLS, e.g. `service:orders` |
| `object_id` | string | The canonical provider **Operation** ID of the accepted v1 CALLS, e.g. `operation:pricing:GET:/prices` |
| `caller_cluster_uid` | string | The exact CLIENT `k8s.cluster.uid` (matrix §10.2) |
| `caller_pod_uid` | string | The exact CLIENT `k8s.pod.uid` (matrix §10.2) |

**Not identity** (I1 §7.1): trace or span IDs, the Workload (never resolved at ingestion), namespace, Pod or Workload names, service version, capture time, the source display name, the selected snapshot, `first_seen`/`last_seen`, the count, the correlation mode, and samples.

As a consequence:
- A replacement Pod gets a distinct record, even when its eventual Workload name is identical.
- The same Pod UID text in another cluster gets a distinct record (L03).
- Two Pods of one caller Service calling one Operation on one day get two v2 records but only **one** v1 bucket (L02; vector `U01`).

## 2. Encoding and ID (I1 §7.1) **[owner decision, I1.3]**

| Step | Frozen rule |
|---|---|
| Canonical form | The §1 object as JSON with sorted keys, separators `(",", ":")` and no ASCII escaping, so non-ASCII text is written as raw UTF-8 (vector `V05`). This is the same convention as the snapshot fingerprint and observation-context ID ([`canonical_json.py`](../../../app/architecture_intelligence/canonical_json.py):14). It is **not** RFC 8785 (`app/sources/jcs.py`), whose docstring forbids interchanging the two. |
| Bytes | UTF-8 encoding of that JSON text |
| Hash | SHA-256 over the bytes, **full** 64-character lowercase hex, not truncated as v1 is (B1) |
| ID | `evidence:otel:calls-scoped:v2:<64 hex>`. The environment and day appear only inside the hash, never in clear text in the ID. |

Field order in the input is irrelevant (L01; vector `V02`). All values are compared and hashed exactly as normalized under matrix §10.2, with no trimming or case-folding.

Worked example (`V01`). The canonical bytes are:

```text
{"bucket_utc_day":"2026-09-28","caller_cluster_uid":"7f3c2a10-1b2d-4e5f-8a9b-0c1d2e3f4a5b","caller_pod_uid":"11111111-aaaa-4bbb-8ccc-000000000001","contract_version":2,"environment":"production","evidence_type":"OBSERVED","object_id":"operation:pricing:GET:/prices","relation_type":"CALLS","source_type":"OPENTELEMETRY","subject_id":"service:orders"}
```

The resulting ID is:

```text
evidence:otel:calls-scoped:v2:54533826895d5eb1fc4a81e0b5ec153266218218b103b49b7fd171ce03f6f3d1
```

## 3. v2 record: non-identity fields and merge rules

A v2 record is created or merged only for an accepted v0.5 CALLS whose original CLIENT passes ingestion guards I-1 to I-5 (matrix §14). Each such interaction contributes **one seed** to exactly one v2 record. Merging seeds into a record must be **order-independent**, so that any permutation of the same interactions yields the same record (I1 §7.2, §13).

| Field | Seed value | Merge rule | Order-independent because |
|---|---|---|---|
| `first_seen` / `last_seen` | The accepted fact timestamp (matrix §12.6) | min / max, as v1 does (`aggregator.py`:102–103) | min and max are commutative |
| `observation_count` | 1 | sum | Commutative. Replay caveats are in §7. |
| `correlation_mode` | `CLIENT_SERVER` or `CLIENT_ONLY` (`SERVER_ONLY` never yields v2) | The stronger mode under v1's `_CORRELATION_MODE_STRENGTH` (`aggregator.py`:27), i.e. `CLIENT_SERVER` over `CLIENT_ONLY` | max over a total order |
| `sample_trace_ids` | `[trace_id]` | **[owner decision, I1.3]** The distinct union, sorted ascending by code point and truncated to the first **5**. v1 keeps first-arrival order (`_cap_trace_ids`, `aggregator.py`:85), which is not permutation-invariant. v2 must be, so it sorts. | Sorting followed by a prefix of the sorted set is order-independent |
| `k8s_namespace_name`, `k8s_pod_name`, `k8s_deployment_name`, `k8s_statefulset_name`, `k8s_daemonset_name` | The admissible CLIENT value, or `null` (matrix §10.1–10.2) | **[owner decision, I1.3]** An **absorbing-conflict** rule, applied per field. (1) If the field is already flagged in the record, it stays `null` and flagged, whatever the seed carries. (2) Otherwise, a `null` on either side never erases a known value. (3) Two different non-null values set the field to `null` and flag it. Equivalently, over all seeds of the record, the final value is the single distinct non-null value if there is exactly one, and `null` if there are none. If there are two or more, the value is `null` and the field is flagged. | The final value and flag are a function of the **set** of non-null values seen, so any order gives the same result (vectors `MP01`, `MP02`). |
| `conflicting_consistency_attributes` | `[]` | Sorted, distinct union | Set union |
| `key_rule_id` / `key_rule_version` | `otel-calls-scoped-evidence-v2-key` / `1` | Constant | — |
| `normalization_rule_id` / `normalization_rule_version` | `otel-client-caller-attribution` / `1` (matrix §10) | Constant | — |

**Deliberate divergence from v0.5.** The v0.5 `merge_runtime_identity_observation` (`aggregator.py`:124) keeps the flag monotonic but not the value. A later seed refills a flagged field's `null` from the non-null side. For `k8s_pod_name` seeds `A, B, A`, v0.5 ends with `A` (flagged), while `A, A, B` ends with `null` (flagged). That is order-dependent, so equal input sets could yield different v2 bytes and snapshot IDs. v2 therefore uses the absorbing rule above. v0.5's runtime identity merge is **unchanged** by this contract. Its order dependence is recorded here as a baseline observation, and the vector test demonstrates it.

**Query-time effect of a flagged attribute [owner decision, I1.3].** A non-empty `conflicting_consistency_attributes` means that CLIENT evidence for this one Pod contradicts itself. It mirrors v0.5 Path C, where a non-empty list is a contradiction (`_consistency_attributes_agree`, B10). The record stays valid and Pod-bound. When a candidate reaches phase 4, the result is `CONFLICT` / `LOCALITY_POD_OWNER_CONFLICT`. Phases 1–3 still short-circuit first (matrix §15.2).

Workload-name seeds of different kinds, e.g. one seed with `k8s.deployment.name` and another with `k8s.statefulset.name`, do not conflict **per field**. Each seed individually passed the §10.3 single-Resource check. The merged record then carries two kind names, and phase 4 treats that as a contradiction under Path C's kind rule (B10, matrix §15.2).

## 4. Lineage (I1 §7.1, §11.6)

Every v2 record carries, in the fields above, its key rule ID/version and its normalization rule ID/version. Derivation links remain distinct:
- the v1 relation evidence (unchanged);
- the v2 CLIENT event attribution (this record);
- the captured Pod/owner chain (query time);
- the source-scoped declaration;
- the later local qualification or projection.

No synthetic combined source is created. When v2 is regenerated from a replayable original per-interaction corpus (§6), the transition report records that corpus's source identity and revision.

## 5. v1/v2 coexistence: two representations of one interaction (I1 §7.2)

| Invariant | Rule |
|---|---|
| v1 untouched | Every accepted interaction contributes to v1 exactly as today: same ID (B1), same counts, same samples, same `evidence_ids` on the CALLS edge. v2 eligibility never changes v1 acceptance. |
| v2 isolated | A v2 ID is **never** appended to a legacy CALLS relation's `evidence_ids`. It never appears in v0.5 relation qualification, coverage, observation counts, legacy evidence arrays, or any existing evidence read, in particular the snapshot state's `evidence` array (`_EVIDENCE_QUERY`, `repository.py`:86) and `read_evidence_rows` (`repository.py`:526). |
| Storage choice | I2 chooses the label and read model (I1 §7.2) under the invariant above. A v2 record stored as a node matched by `_EVIDENCE_QUERY` would break both this invariant and the no-v2 pin, which is a blocker. |
| One semantic owner | v2 feeds only the new locality assessment. Qualification still goes through `app/qualification/declared_observed.py` (ADR 0010), with v2 as the observed input for a **local** assessment and never as a second v0.5 contribution (L12). |
| Public reachability | A v2 ID is **not** publicly resolvable until I3 freezes an explicit, snapshot-bound evidence drill-down (I1 §11.4). No existing REST/MCP route returns it. |

## 6. Transition and migration report vocabulary (I1 §7.2, §10.2)

A versioned per-source report classifies accepted observed CALLS evidence. The report name is `aip-scoped-evidence-transition-report/1`. It is an operational artifact, **not** architecture evidence and not a snapshot input (I1 §10.2).

| Category | Meaning | Count unit |
|---|---|---|
| `LEGACY_UNSCOPED` | A v1 bucket that predates v2 ingestion, or whose interactions cannot be replayed from original per-interaction input. It keeps its unscoped meaning, and Pod locality is never backfilled from `RuntimeIdentityObservation` (L05). | v1 buckets |
| `SCOPED_V2_WRITTEN` | An accepted interaction that produced a v2 seed | interactions |
| `SCOPED_V2_REFUSED` | An accepted interaction with v1 but no v2, broken down by exactly one of the matrix §15.1 primary reasons, plus the sorted full reason list | interactions per reason |

Each report entry carries the source identity and revision, the environment, the UTC day and the reason. It never carries raw spans, Resource payloads or secrets. I2 freezes the report's bounds, retention and availability (I1 §10.2). Existing historical v1 aggregates are reported as `LEGACY_UNSCOPED` and never re-scoped. Only a replayable original per-interaction corpus, with its source and revision recorded, can regenerate v2 (I1 §7.2).

## 7. Replay and retry (I1 §7.2)

| Situation | Contract |
|---|---|
| Clean-state replay of one pinned corpus | It must reproduce identical v2 IDs **and** identical normalized records under any permutation of the interactions (§3; I1 §13). |
| Same interaction seen twice in one ingestion unit | One representation per interaction: no duplicate v2 record and no second v2 ID for the same interaction. |
| Repeated live OTLP POST of the same payload | **Disclosed gap.** The current v0.5 aggregator can count a repeated POST twice in v1 (`observation_count`, samples). This contract does not claim exactly-once OTLP transport. **I2 must freeze** the retry and replay transaction semantics before implementation. Whatever it chooses may not silently change v1 behaviour, and may not make a v2 contribution count in any legacy answer. |

## 8. Snapshot identity: one conditional fingerprint (I1 §11.1; parent §33 I2 row)

| Rule | Frozen value |
|---|---|
| No-v2 pin | With **zero** v2 records the canonical state, `_CANONICALIZATION_VERSION = 3` (`repository.py`:53) and every snapshot ID are byte-identical to today. This includes `aip:snapshot:v1:0bfcbdeda363876559bb78f53e432f1a73c368e9fbd4d21c37f8f4335ecdbd5f` in [`examples/release-golden-path/expected.json`](../../../examples/release-golden-path/expected.json) (L13). |
| Conditional key **[owner decision, I1.3]** | When at least one v2 record exists, the state gains **one** top-level key, `scoped_observed_calls_v2`. Its value is the list of v2 records sorted by `id`. When there are none, the key is **absent**: never `[]` and never `null`. **Amended in I2.1a (reviewed, [I2 decision record D5](i2-decision-record.md#d5--capture-scope-under-the-fence-and-in-the-fingerprint-i2-81-stop-condition-amendment)):** the same conditional rule also admits a second key, `scoped_capture_scopes_v2`, which is likewise absent with zero v2 records. The fragment vector is unchanged. |
| Version | `_CANONICALIZATION_VERSION` stays `3` **[owner decision, planning]**. The no-v2 bytes are unchanged by construction, and the key's presence is itself the discriminator. |
| Entry fields | Exactly: the ten §1 identity fields, `id`, and every §3 field (`first_seen`, `last_seen` in the `…ffffffZ` form, `observation_count`, `correlation_mode`, `sample_trace_ids`, the five `k8s_*` consistency fields, `conflicting_consistency_attributes`, and the key and normalization rule IDs/versions). These are the fields that can change a locality answer or its lineage, mirroring v1's snapshot evidence projection (`_EVIDENCE_QUERY` includes counts and samples). |
| One fingerprint | The same `snapshot_fingerprint` (`repository.py`:344) over the same state dict. There is no second locality hash, and old and new service/REST/MCP answers carry the same `snapshot_id` (L14). |

**"After" vector and the I1/I2 split (disclosed; plan Q2).** I1 freezes the v2 **fragment**: the canonical bytes and SHA-256 of a two-record `scoped_observed_calls_v2` value (vector `snapshot_fragment`, whose second entry shows a flagged attribute), plus the insertion rule above. A full-graph "after" `snapshot_id` depends on I2's persisted graph state, so **I2 must add an independently expected full after-`snapshot_id` vector before enabling v2 projection.** I1 does not claim one. Separately, I2 must prove the no-v2 pin before enabling v2 (I1 §11). If the pin cannot be retained, that requires a reviewed parent amendment, not a fixture edit.

## 9. Retention and cardinality (I1 §11.4–11.5)

**Record count:**
- v2 records per environment per UTC day = Σ over (caller Service, Operation) of the distinct `(caller_cluster_uid, caller_pod_uid)` pairs that called it that day.
- At a constant Workload count W with R replicas each and k rollouts per day, the distinct Pods per day are roughly W·R·(k+1). v2 grows with **Pod churn**, not with the number of Workloads (L28).

**Per-record bound:** the ten identity strings, two timestamps, one count, one mode, at most 5 trace IDs, five optional strings, a conflict list of at most 5 names, and four rule fields. There is no raw Resource, span or unbounded label.

**Obligations handed to I2/I4 (not claimed here):**
- A churn scenario: many successive Pods at a constant Workload count (L28).
- Measurement of graph size, fingerprint time and read cost against the v1-only baseline.
- The share of v2 records whose Pod is `UNRESOLVED` in the selected capture.
- The migration/report overhead.

[ADR 0012](../../adr/0012-observed-evidence-retention.md) stays **Proposed**. Nothing here authorizes compaction, discarding, silent truncation or coarsening of v2 records (I1 §11.5).

## 10. Vectors and executable check

[`i1-vectors/v2-evidence-id.json`](i1-vectors/v2-evidence-id.json) holds:
- **`key_vectors`:** `V01` base, `V02` reordered input (L01), `V03` distinct Pod (L02), `V04` same Pod UID in another cluster (L03), `V05` non-ASCII environment, `V06` other Operation (L04/L27 shape), `V07` next day.
- **`merge_permutation_vectors`:** `MP01`, three seeds whose `k8s_pod_name` values are `A, B, A` (absorbing conflict, plus min/max/sum/mode/sample merging), and `MP02`, seven distinct trace IDs in scrambled order (sorted, truncated to 5). The test folds the seeds in **every** permutation and requires the recorded result each time.
- **`v1_unchanged`:** one v1 ID shared by `V01`/`V03`, and a separate v1 ID for `V06`.
- **`snapshot_fragment`:** the conditional state value.
- **`no_v2_snapshot_pin`:** the golden pin.

The canonical bytes were written by hand and the hashes computed with the `sha256sum` CLI. `tests/unit/test_v060_i1_contract_vectors.py` recomputes every value with `json` and `hashlib` only, and imports nothing from `app/`. It also checks:
- that the vectors' `V`-IDs are pairwise distinct where L01–L03 require;
- that the fragment's entries are sorted by an `id` derived from their own identity fields and carry exactly the §8 field set;
- that the pin still matches `expected.json`.

## 11. Traceability

| I1 requirement | Section |
|---|---|
| §7.1 key inputs, full SHA-256, proposed ID, non-identity metadata, lineage rule IDs | §1, §2, §3, §4 |
| §7.1 golden vectors for reordering, distinct Pod UID, distinct cluster UID | §10, `V02`–`V04` |
| §7.2 dual representation, no double count, isolated storage, no second semantic owner | §5 |
| §7.2 no v1 backfill; `LEGACY_UNSCOPED`/eligible/refused reporting | §6 |
| §7.2 clean replay; no exactly-once overclaim; I2 freezes retry | §3 (absorbing conflict, `MP01`/`MP02`), §7 |
| §11.1 one conditional fingerprint; no-v2 pin (L13, L14); DoD 6 | §8 |
| §11.4–11.5 bounded retention; Pod-churn cost; ADR 0012 Proposed | §9 |
| §15 register rows "v2 key/ID", "v1/v2 coexistence and migration", "Snapshot", "Cost/retention" | §§1–9 |
