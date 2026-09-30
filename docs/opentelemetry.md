# OpenTelemetry Runtime Observation

AIP is an **additional telemetry consumer, not the primary observability backend**. See the
project README's "Runtime telemetry" section and [`security-model.md`](security-model.md) for the
production failure-isolation topology this implies (a Collector should fan out to a real
observability backend *and* AIP in parallel, never to AIP alone).

## Ingestion contract

`POST /v1/traces` accepts a protobuf `ExportTraceServiceRequest`
(`Content-Type: application/x-protobuf`) — OTLP/HTTP, the standard export format any OpenTelemetry
Collector or SDK can produce. It decodes the batch, resolves each span against whatever the graph
already has declared, and persists observed facts and evidence. A malformed payload or wrong
content-type is rejected (400/415) before any Neo4j access happens, so a bad request can never
partially write.

AIP expects the OTLP protobuf body **uncompressed**: `POST /v1/traces` does not negotiate
`Content-Encoding`, so gzip-compressed exports are rejected during protobuf decoding. The
Collector's `otlphttp` exporter uses gzip by default; disable compression on the AIP leg:

```yaml
exporters:
  otlphttp/aip:
    endpoint: http://<aip-host>:8000
    compression: none
```

See the [runtime demo Collector configuration](../examples/runtime-demo/otel-collector-config.yaml)
for a working example.

## Attribute allowlist

Only these OTel semantic-convention attributes are ever read — nothing else is inspected, and
nothing outside this list is ever persisted:

**Resource identity** (`app/telemetry/semconv/resources.py`): `service.name`,
`service.namespace`, `service.version`, `service.instance.id`, `deployment.environment.name`.

**Bounded Kubernetes resource identity** (`app/telemetry/semconv/resources.py`, I3 spec §9.3):
`k8s.pod.uid` (required, alongside `service.name`/`deployment.environment.name`, for a bounded
runtime identity observation to be recorded at all — see below), plus the optional consistency
attributes `k8s.pod.name`, `k8s.namespace.name`, `k8s.cluster.uid`, `k8s.deployment.name`,
`k8s.statefulset.name`, `k8s.daemonset.name`. No other Kubernetes-shaped attribute (labels,
annotations, container env/command/args, pod/host IP, Node metadata, volumes, Secrets) is ever
read.

**HTTP** (`app/telemetry/semconv/http.py`): `http.request.method`, `http.route`, `url.template`
(fallback for `http.route`), `server.address`/`server.port` (defined but never used to *resolve*
anything — see below), `peer.service` (the sole allowlisted way to identify a CLIENT-only call's
target).

**Messaging** (`app/telemetry/semconv/messaging.py`): `messaging.system`,
`messaging.destination.name`, `messaging.destination.template`, `messaging.operation.name`,
`messaging.operation.type`. `messaging.destination_kind` (v0.4.1) is read only as destination-kind
safety evidence. v0.5.0 I4 widened the destination side by exactly two keys:
- `messaging.destination.subscription.name` resolves a declared Subscription, but only within an
  already-resolved declared Topic.
- `messaging.consumer.group.name` is read only so that its refusal to act as Subscription identity is
  enforced and testable. It is never retained.

See [Pub/Sub observations](#pubsub-observations-v050-i4).

Never read, never persisted: authorization headers, cookies, request/response bodies, message
bodies, query parameters, full URLs, or any other raw span attribute. `server.address`/
`server.port` exist as constants but are deliberately never used for identity resolution — a
CLIENT-only call's target must come from `peer.service`, never guessed from a network address (the
"no guessing" rule below).

## Bounded runtime identity observations (I3)

A span carrying `service.name`, `deployment.environment.name`, and `k8s.pod.uid` also produces a
bounded runtime identity observation (`app.provenance.model.RuntimeIdentityObservation`), merged
into a deterministic daily bucket (`app.canonical.ids.runtime_identity_observation_id`,
`app.telemetry.aggregator.merge_runtime_identity_observation`) and persisted under its own
`:RuntimeIdentityObservation` Neo4j label — independent of, and never coupled to, CALLS/SENDS/
RECEIVES_FROM correlation. This is pure evidence capture at ingestion time: it produces no relation
of its own, and the `:RuntimeIdentityObservation` node itself is never reachable through
`GET /api/evidence`, `get_evidence`, or the public snapshot fingerprint (a different label than
`:Evidence` entirely).

### Scoped v2 evidence and its operational provenance (v0.6.0, off by default)

With `telemetry.scoped-evidence.enabled: true`, an accepted HTTP `CALLS` whose *original CLIENT*
carries `k8s.pod.uid`, `k8s.cluster.uid` and the accepted environment is also stored as an isolated
caller-Pod-scoped record (`:ScopedObservedCallV2`), in the same transaction as its v1 evidence. The
v1 evidence, the snapshot and every v0.5 answer are unchanged, and the record is never `:Evidence`,
has no relationships, and is not reachable through any public read or the natural-language query
path. The same transaction also maintains three kinds of bare operational node, none of which is
architecture evidence:

- `:ScopedEvidenceCutover` (one per graph) and `:ScopedEvidenceLegacyBucket` record which v1 CALLS
  buckets already existed when scoped evidence was first enabled, and mark a bucket *mixed* once a
  later enabled unit contributes to it. History is reported as **unknown**, never as legacy, whenever
  this cannot be proved (no ledger, another stream, or a membership that no longer matches it).
- `:ScopedEvidenceTransitionCounter` holds exact counts of accepted and refused interactions per
  stream, environment, UTC day and primary refusal cause.

The counters and the legacy classification are read with
`app.telemetry.scoped_ledger.read_transition_report` (`aip-scoped-evidence-transition-report/1`); there
is no public endpoint. Refusals are also logged after commit as bounded, sanitized samples (at most 20
per cause per POST, plus a suppressed count) carrying only the stream, trace ID and reason codes.

v0.5.0 I3's deployment reconciliation ("Path C", `app.architecture_intelligence.
deployment_reconciliation`) reads these observations at query time — together with a real Pod's
captured owner chain (Pod → ReplicaSet/StatefulSet/DaemonSet → Workload) and an exact Service
resolution over the same span's declared/observed CALLS identity — to produce a public
`Service -[DEPLOYED_AS]-> Workload` `DeploymentClaim` (or a non-resolved `DeploymentResolution` when
the evidence conflicts, is ambiguous, or doesn't reach a single Service) through
`get_service_dependencies`/`GET /api/services/{id}/deployments`. That public claim's own
`evidence_refs` never point at a raw `:RuntimeIdentityObservation` node directly; a bounded,
sanitized `EvidenceRecord` (source type `OPENTELEMETRY`) is synthesized from it on read, carrying
only the same allowlisted attributes already described above, and only when the current snapshot
makes it reachable from a public claim or resolution (see [`evidence.md`](evidence.md)).

### Observation-context compatibility (I3)

Path C never treats a persisted observation as applicable just because its identity resolves — it
first checks the observation against the caller's own `(environment, window_start, window_end)`
Observation Context, using the *persisted* `last_seen` and the owning Pod's real I2
`CAPTURED_RESOURCE` `capturedAt` (never an undefined synthetic "observation timestamp", and never
the daily bucket treated as a continuous interval):

| Check | Outcome when it fails |
|---|---|
| `environment` present and exactly equal to the context's `environment` | `UNRESOLVED` / `DEPLOYMENT_EVIDENCE_INCOMPLETE` (absent) or `DEPLOYMENT_ENVIRONMENT_MISMATCH` (present but different) |
| `last_seen` present and inside `[window_start, window_end]` (inclusive) | `UNRESOLVED` / `DEPLOYMENT_TEMPORAL_MISMATCH` |
| the owning Pod's real `capturedAt` present and inside `[window_start, window_end]` (inclusive) | `UNRESOLVED` / `DEPLOYMENT_TEMPORAL_MISMATCH` |

`last_seen` is the decisive runtime timestamp for window applicability — `first_seen` and
`observation_count` are evidence metadata only and never independently satisfy the window check. An
environment mismatch is not a contradictory Service↔Workload identity claim; it just means the
observation doesn't apply to the requested context. This rule deliberately has no arbitrary "N hours
of skew" constant — a future historical/locality release may introduce richer temporal continuity,
I3 does not. Relatedly, the `k8s.namespace.name`/`k8s.cluster.uid` consistency attributes above are
correlation inputs only, checked for agreement against the resolved Workload's own values — never a
locality claim in their own right.

## Correlation modes

An HTTP call observation's `correlation_mode` records how confidently it was correlated:

| Mode | Meaning |
|---|---|
| `CLIENT_SERVER` | Strongest signal — a matched CLIENT+SERVER span pair, whether they arrived in the same OTLP batch or were matched across two separate batches |
| `CLIENT_ONLY` | Partial instrumentation — a CLIENT span with a stable target identity (`peer.service`) whose SERVER counterpart never arrived |
| `SERVER_ONLY` | Only ever recorded when the caller's identity is reliable — since nothing in the current attribute allowlist can identify a caller from a SERVER span alone, a SERVER-only observation today always ends up `UNRESOLVED` rather than producing a fact; the mode exists in the model for when a future signal makes caller identification possible |
| `UNRESOLVED` | Not a correlation mode itself, but the outcome for any observation whose identity is insufficient — recorded as an `UnresolvedObservation` with a reason code (below), never guessed at |

Messaging observations get their own three modes (`MESSAGING_SEND`/`MESSAGING_RECEIVE`/
`MESSAGING_PROCESS`) — see [`evidence.md`](evidence.md).

### Cross-batch correlation

A real CLIENT span and its matching SERVER span very often arrive in *separate* OTLP batches — a
Collector's batch processor flushes by time/size, not trace completeness. AIP supports this: a
bounded, TTL-based `HttpCorrelationBuffer` (`app/telemetry/correlation_buffer.py`) holds a CLIENT or
SERVER span in memory, waiting for its counterpart to arrive in a *later* `POST /v1/traces` request,
and correlates them the moment it does. If the TTL expires first, the still-unmatched span is
instead evaluated as a `CLIENT_ONLY`/`SERVER_ONLY` observation rather than silently discarded. See
[`security-model.md`](security-model.md) for exactly what this buffer does and does not persist.

### No-guessing rule

Every resolution path either finds a real, stable identity signal or reports an unresolved reason —
it never fabricates one. The fixed reason-code set (`app/telemetry/adapter.py`):

| Reason | When |
|---|---|
| `no_environment` | No `deployment.environment.name` on the span |
| `no_stable_route` | No usable `http.route`/`url.template`, or the operation couldn't be resolved |
| `no_destination_name` | A messaging span with no `messaging.destination.name` |
| `missing_target_identity` | A CLIENT-only span with method+route but no `peer.service` |
| `missing_caller_identity` | A SERVER-only span — its caller can never be identified from the current allowlist |
| `correlation_expired` | A CLIENT-only span that aged out of the buffer with not even method/route present |

## Pub/Sub observations (v0.5.0 I4)

Runtime evidence can only *qualify* declared Topic and Subscription topology. It never creates an
observed-only Topic or Subscription.

**Topic resolution** (`app/telemetry/messaging_guards.py::decide_messaging_destination`, a front
guard over the unchanged v0.4.1 Queue guard). A Topic resolves only when:
- `messaging.destination.name` is present;
- exactly one declared Topic candidate matches it, using the same precedence as for Queues:
  1. an exact name plus a compatible `messaging.system`;
  2. an exact name with no conflicting namespace;
  3. a configured `telemetry.topic_aliases` entry, consulted only when there is no unique direct
     match;
- any present `messaging.destination_kind` is compatible;
- the existing Service-identity guard accepts the span.

Around that rule:
- **Aliases never cross kinds:** Queue aliases never select a Topic, Topic aliases never select a
  Queue, and Subscription aliases do not exist.
- **Ambiguity:** a bare name that matches both a declared Queue and a declared Topic is unresolved.
- **`messaging.destination_kind`:**
  - `topic` with no declared Topic keeps v0.4.1's `unsupported_destination_semantics`.
  - `subscription` is unsupported.

**Consumer spans.** A consumer span supports `Service -[RECEIVES_FROM]-> Subscription` only when all
of these hold:
- `messaging.destination.name` resolves the declared Topic;
- `messaging.destination.subscription.name` matches a declared Subscription of that Topic exactly
  (NFC, with no case folding or trimming);
- `SUBSCRIPTION_OF` links the two.

This is the Google Cloud Pub/Sub and Azure Service Bus consumer shape. A consumer group, even one
equal to a Subscription name, never resolves, creates or aliases a Subscription. That makes Kafka
consumer-group spans unresolved by design.

**Publisher spans.** A `send` to a resolved Topic attaches OBSERVED evidence to the declared
`PUBLISHES_TO`.

**Unmatched spans.** An unmatched Pub/Sub span stays an in-memory `UnresolvedObservation` on its
batch. It is never persisted, never enters the snapshot, and is never exposed publicly.

## Declared vs. observed, and coverage qualification

See [`graph-model.md`](graph-model.md) for the full `CONFIRMED`/`OBSERVED_ONLY`/
`NOT_OBSERVED_IN_WINDOW` status model this feeds. `NOT_OBSERVED_IN_WINDOW` on its own conflates two
very different situations — "we watched for this and it didn't happen" vs. "we have no real
telemetry coverage to judge by" — so it can be qualified with a coverage classification
(`app/analysis/runtime.py::_classify_coverage`):

| Coverage | Meaning |
|---|---|
| `SUFFICIENT` | The subject has observed traffic of the *same* relation kind (HTTP vs. messaging) in this environment/window — a not-observed edge of a well-covered kind is real evidence |
| `PARTIAL` | The subject emits *some* telemetry, just not of this specific kind |
| `NONE` | The subject emitted no usable telemetry at all in this environment/window |
| `UNKNOWN` | Qualification is disabled (`telemetry.coverage.qualification-enabled: false`) or there's no coverage data for the subject at all |

This is a coarse, deliberately non-numeric classification — never interpreted as `obsolete`,
`unused`, or `dead`.

Since v0.5.0 I4, "messaging" covers Pub/Sub as well as Queues. Observed `PUBLISHES_TO -> Topic`
counts toward a service's messaging coverage just like `SENDS -> Queue`, and observed
`RECEIVES_FROM -> Subscription` counts like `RECEIVES_FROM -> Queue`. A declared-only
`PUBLISHES_TO` route is qualified by the same messaging signal. There is one shared rule,
`app/analysis/runtime.py::telemetry_coverage`, so O5's `messaging_observed` is also true for a
service whose only telemetry is Pub/Sub.

## `observation_count` is not a request counter

`observation_count` (summed per evidence bucket, alongside up to 5 `sample_trace_ids`) is an
**architecture-evidence indicator**, not an exact, billing- or SLO-grade traffic count. It exists to
answer "did this happen, roughly how much, and when" for architecture-discovery purposes — never to
answer "exactly how many requests occurred."
