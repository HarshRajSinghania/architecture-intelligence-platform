# AIP v0.6.0 I1 — Completion Record

**Status:** **COMPLETE.** Closed by PR #311, merge `7a949cd3046e91ddd6ea67036b6bf47c241ed037` (2026-09-28T21:44:54Z). The closure SHA was written into this record after that merge (the two-step closure pattern).

I1 completion is a **contract** freeze. It does not claim that any v0.6 capability is implemented, qualified or released. I2 implements, I3 exposes, I4/I5 qualify and demonstrate, and I6 releases (parent §5).

This record covers the accepted I1 specification [`i1-locality-and-evidence-applicability.md`](i1-locality-and-evidence-applicability.md), merged in PR #283 (merge `aafb03d5735d78b2741a3dc8a2d0336079535ed6`), under the accepted parent [`specification.md`](specification.md), merged in PR #278 (merge `be26edcd133edc8576a85d301be33b836335c41b`). Neither governing text changed during I1 deliverable work. It was re-checked against `origin/main` before every slice PR, and the last I1 spec commit is still `aafb03d`. Apart from its status line, which this PR updates, the I1 spec is unamended.

## Run identity

| Slice | Deliverable | PR | Merge commit | Merged (UTC) |
|---|---|---|---|---|
| I1.1 | [`i1-locality-support-matrix.md`](i1-locality-support-matrix.md) §§1–9 | #307 | `15995ab373a356a42bb331c313245c03ab7b9f33` | 2026-09-28T19:09:12Z |
| I1.2 | Matrix §§10–16, [`i1-vectors/utc-day-window.json`](i1-vectors/utc-day-window.json), vector test | #308 | `b9f10250634a4a7e61579639f5a082d6935beb43` | 2026-09-28T19:57:11Z |
| I1.3 | [`i1-scoped-evidence-v2-contract.md`](i1-scoped-evidence-v2-contract.md), [`i1-vectors/v2-evidence-id.json`](i1-vectors/v2-evidence-id.json) | #309 | `5b3b3b7cf9802d7603a089556ea621f06d50a4d3` | 2026-09-28T20:40:02Z |
| I1.4 | [`i1-capture-acquisition-runbook.md`](i1-capture-acquisition-runbook.md) | #310 | `c8667d52371dee84c19c7e99310fa8c2abe0dd93` | 2026-09-28T21:00:19Z |
| I1.5 | [`i1-conformance-dossier.md`](i1-conformance-dossier.md), [`i1-vectors/conformance-expected.json`](i1-vectors/conformance-expected.json), this record, I1 status line | #311 | `7a949cd3046e91ddd6ea67036b6bf47c241ed037` | 2026-09-28T21:44:54Z |

The merge commits above were read from `gh pr view --json mergeCommit`, not typed from memory. Planning started at `2026-09-28T17:28:36Z`; the value is recorded in each slice PR's hidden metadata marker.

## Decisions frozen in I1 deliverables

Every decision below was left open to I1 by the accepted spec (I1 §15; parent §33), and none weakens a parent or I1 constraint. Each was taken by the owner and recorded in the named deliverable.

| # | Decision | Where frozen | Origin |
|---|---|---|---|
| D1 | Internal contract ID `locality-contract/1`; the role vocabulary and internal types as listed | Matrix §§2–3 | I1 §4 transcription |
| D2 | CLIENT allowlist and rule `otel-client-caller-attribution`/1. Admissible value = non-empty string, compared exactly; anything else counts as missing. | Matrix §10 | Owner, during I1.2 |
| D3 | The only CLIENT-internal contradiction is `CLIENT_MULTIPLE_WORKLOAD_KINDS` | Matrix §10.3 | Owner, during I1.2 |
| D4 | The CLIENT event instant is the CLIENT span `end_time`. The v1 and v2 bucket day and v2 `first_seen`/`last_seen` use the accepted fact timestamp. Precision is the receiver's microsecond instant, with float rounding disclosed. | Matrix §12, including §12.6 | I1.2 plus the review of #308 |
| D5 | `ScopedDayWindowV1`: strict `YYYY-MM-DD`, inclusive bounds `00:00:00.000000Z`–`23:59:59.999999Z`, overflow-safe end | Matrix §13 plus vectors | I1.2 |
| D6 | v2 key encoding follows the `canonical_json.py` convention (not RFC 8785), full SHA-256, as `evidence:otel:calls-scoped:v2:<hex>` | v2 contract §2 | Owner, during planning |
| D7 | Optional consistency attributes are kept with a conflict list. A flagged attribute gives a phase-4 `CONFLICT` / `LOCALITY_POD_OWNER_CONFLICT`. | v2 contract §3 | Owner, during I1.3 |
| D8 | Absorbing-conflict merge rule, deliberately diverging from order-dependent v0.5; trace samples are sorted and capped at 5 | v2 contract §3 | Review of #309, plus I1.3 |
| D9 | Conditional snapshot key `scoped_observed_calls_v2`, absent when there are no v2 records; `_CANONICALIZATION_VERSION` stays 3 | v2 contract §8 | Owner, during planning |
| D10 | Transition report `aip-scoped-evidence-transition-report/1` with categories `LEGACY_UNSCOPED`, `SCOPED_V2_WRITTEN` and `SCOPED_V2_REFUSED` | v2 contract §6 | I1.3 |
| D11 | Acquisition owner: Michael Egner. Authentic CLIENT emission is SDK instrumentation plus the Downward API Pod UID plus the `kube-system` cluster UID. The replay wire path is pinned as JSON → Collector → protobuf, with no processors, queue or retries. | Runbook §§1, 3, 6 | Owner, during planning, plus the review of #310 |

## I1 Definition of Done (I1 §16)

| DoD | Status | Evidence |
|---|---|---|
| 1. Versioned role/scope vocabulary; evidence × dimension × claim-kind matrix; admitted and unsupported cases; no wildcard | **Met** | Matrix §§2–5 |
| 2. CLIENT attribution cannot assign a relation by co-occurrence, name, SERVER identity or `DEPLOYED_AS` | **Met (contract)** | Matrix §6, §§10–11, §14; L05, L07–L09, L26 |
| 3. v2 key and golden vectors, coexistence, migration, clean replay, no double count | **Met (contract plus executable vectors)** | v2 contract §§1–7; `V01`–`V07`, `U01`–`U02`, `MP01`–`MP02` |
| 4. Whole-UTC-day and capture predicates, Pod churn, phase-gated disposition mapping, L36–L37 early exits | **Met (contract plus executable vectors)** | Matrix §§12–15; window vectors; L17, L18, L27, L31, L35–L37 |
| 5. Matching declaration plus local observation through the single owner; no local coverage or negative claim | **Met (contract)** | Matrix §4.1; L21–L23 |
| 6. No-v2 fingerprint and golden pin; conditional one-snapshot v2 with before/after vectors | **Met, split disclosed** | v2 contract §8. The no-v2 pin and v2 fragment vector are frozen. **The full after-`snapshot_id` vector is an explicit I2 pre-enablement obligation** (plan Q2). |
| 7. Named owner, two distinct Deployments, one caller Service, Operation-accurate expected facts, capture pins, overlap timing, replay and teardown, I2 rehearsal gate | **Met (plan)** | Runbook. The actual capture is `NOT_RUN` (I5), and the rehearsal is `NOT_RUN` (I2). |
| 8. Independent L01–L37 results and parent §9 traceability reviewed; no silently deferred blocker | **Met on merge of this PR** | Dossier and JSON; traceability below |
| 9. Ingestion-only codes stay in reports and are never reconstructed from v1 | **Met (contract)** | Matrix §5, §15.1–15.3; L06, L35; enforced by the dossier consistency test |
| 10. No broadened v0.5 refusal; no display-name Service or Operation reidentity | **Met (contract)** | Matrix §6–7; L05, L20, L26, L32 |
| 11. Observation window distinct from Intent effective interval | **Met (contract)** | Matrix §8; L30 |

## Parent §9 exit gates → I1 evidence

| Parent gate | I1 evidence |
|---|---|
| 1. Exact versioned scope/applicability contract | Matrix §§2–5, §15; `locality-contract/1` |
| 2. Positive/negative examples of caller, target, source and claim scope | Matrix §§2, 4, 6; L04, L20, L26 |
| 3. No broadened refusal, no name-based Service reidentity | Matrix §6; L05, L26, L32 |
| 4. Deterministic machine-visible missing/conflict/unsupported/temporal dispositions | Matrix §15; dossier; consistency test |
| 5. Observation window vs Intent in types and docs | Matrix §3, §8; L30 |
| 6. Runtime-identity attribution case and name/co-location rejection | L15, L26, L33 |
| 7. v1/v2 identity, migration, coexistence, replay, reachability, cross-batch, UTC day, ADR 0012 cost | v2 contract; matrix §§11–13; L07, L08, L11–L14, L28 |
| 8. Query-time snapshot-pinned capture selection, Pod churn, executable capture-harness plan | Matrix §15.2; L18, L27; runbook |

## Check status

| Check | Status | Result |
|---|---|---|
| `tests/unit/test_v060_i1_contract_vectors.py` (stdlib only, no `app/` import): window, timestamp-role, v2/v1 ID, merge-permutation, snapshot-fragment and pin vectors, dossier consistency and drift, and the rejected-envelope selectability guard | **RUN** | 120 passed, as part of the full unit suite in PR #311 |
| Mutation proofs: a corrupted v2 hash; a wrong L36 disposition; an ingestion code leaked into L05's answer | **RUN** | Each failed as expected and passed again once restored |
| Full local gate on the I1.5 branch (`ruff format`, `ruff check`, `pyright`, `lint-imports`, unit, integration) | **RUN** | See PR #311's description |
| I2 implementation tests against the dossier | `NOT_RUN` | I2 |
| I2 capture rehearsal (runbook §9) | `NOT_RUN` | I2 |
| Real two-Workload capture (runbook §§4–8) | `NOT_RUN` | I5 |
| Permutation, clean-replay and surface-parity qualification of the candidate | `NOT_RUN` | I4 |

## Reconciliation against the retained plan (approved plan, verbatim in PR #307)

**Completed as planned.**
- Five slice PRs, I1.1 → I1.5, each merged by the owner before the next slice started.
- All six planned documents.
- The three planned vector files, plus the stdlib-only test.
- Owner decisions 1–5 from planning, recorded here as D6, D9, D11 and the PR cadence.
- `docs/specifications/README.md` was not changed. As the plan anticipated, the index lists release directories, not increment documents.

**Deviations and justification.**
- **Extra owner decisions (D2, D3, D7):** implementation exposed three choices the spec left open. Each went to the owner rather than being picked silently (AGENTS.md).
- **Review-driven corrections:**
  - #307 split ingestion and query codes and added the capture row.
  - #308 separated the CLIENT and fact timestamp roles.
  - #309 replaced the order-dependent v0.5 merge rule with the absorbing rule.
  - #310 pinned the protobuf replay wire path.
  - The #311 review made L17 and L29 reachable. An envelope without `capturedAt`, or one that is not `COMPLETE`, is rejected by v0.5 validation (`REJECTED_INVALID`) and is never a selected capture, and the prior committed capture is preserved. L17e and L29a/b now record this, and a guard test prevents a query from selecting a rejected envelope.

  None changes an accepted I1 semantic.
- **Merge vectors:** `merge_permutation_vectors` were not in the plan. They were added to prove the §7.2 permutation invariance the #309 review required.
- **Dossier rendering:** the case tables are rendered from the JSON, and a drift test checks them. This goes beyond the plan's structure-only test.

**Specification questions discovered, and their resolution.**
- **Plan Q1:** receiver float rounding is disclosed as a baseline property (matrix §12.1).
- **Plan Q2:** the after-snapshot split is disclosed (v2 contract §8) as an I2 obligation.
- **v0.5 findings recorded, not changed:**
  - `merge_runtime_identity_observation` is order-dependent (v2 contract §3).
  - Size-evicted correlation-buffer spans are dropped silently (matrix B3).
  - Duplicate Resource keys take the last value (matrix §10.2).
- **Dossier interpretations** (dossier §4), reviewed in PR #311 and accepted with its merge. No reviewer objected:
  - every no-eligible answer carries the coverage code;
  - a missing environment and a missing UID each emit their own code;
  - a read-time environment mismatch carries no `LOCALITY_*` code.

**Deferred work.** Nothing I1 owns is deferred. The following are handed off (next section): the full after-`snapshot_id` vector, retry/replay semantics, report bounds and retention, v2 storage label, harness build and rehearsal, and the actual capture.

**Remaining limitations.**
- The vectors prove the contract's internal consistency and independent hashing. They do not prove AIP behaviour.
- The Path C `AMBIGUOUS` and `CONFLICT` fixtures (`CAP-AMB`, `CAP-CONF`) are specified abstractly. I2 must build them concretely under the existing Path C rules.

## Handoff

**To I2** (parent §12; I1 §16 handoff). Before enabling v2 projection:
- implement the matrix §§10–15 carrier, guards and dispositions;
- implement v2 records exactly per the v2 contract §§1–5, storing them where no existing evidence read (`_EVIDENCE_QUERY`, `read_evidence_rows`) can see them;
- freeze retry and replay transaction semantics (v2 contract §7);
- freeze the transition report's bounds, retention and availability (v2 contract §6);
- prove the no-v2 pin, then add an independently expected full after-`snapshot_id` vector (v2 contract §8);
- turn every dossier variant into an implementation test;
- build the capture harness and pass the runbook §9 rehearsal gate.

**To I3:**
- the Service-level roll-up shape, the Operation membership and evidence union, and the missing- or ambiguous-owner disposition (matrix §7; L32);
- the public mapping of the internal dispositions and reasons, without reordering the phase gates;
- snapshot-bound v2 evidence drill-down;
- bounded evidenced-locality enumeration.

**To I5:** execute the runbook §§4–8 with the named owner.

## I1 exit statement

I1 freezes a versioned, reviewable and partly executable locality contract for the minimum v0.6 slice. That slice is HTTP `CALLS` with an environment, a whole UTC-day window and cluster/namespace/Workload caller locality, taken from an actual CLIENT Pod attribution resolved against a time-compatible selected capture.

No semantic blocker is open. I1 is closed at `7a949cd`, and I2 may begin.
