# Security Model

## Trust boundaries

| Boundary | What crosses it | How it's handled |
|---|---|---|
| User input (NL question) | Free text | Never executed directly — routed to a fixed deterministic analysis, or turned into Cypher that must pass the validator below |
| **LLM output** | Generated Cypher, generated prose | **Always treated as untrusted input** — see below |
| Cypher validation | Generated Cypher -> validated Cypher | `app/ai/cypher_validator.py` — allowlisted read-only constructs only, known labels/relation types only, bounded traversal depth, capped result rows (see [`semantic-validation.md`](semantic-validation.md)) |
| Graph reachability | Validated Cypher -> nodes it may read | `app/ai/graph_reachability.py` — fail-closed: every node pattern must be bound to an approved public label (syntax rule), and the `EXPLAIN` plan of the final query may only read approved labels; unlabeled scans and label expressions are refused, so internal nodes are unreachable |
| Neo4j read path | Validated Cypher -> graph rows | Executed against a read-only session; the LLM layer never receives write credentials |
| OTLP input | `POST /v1/traces` protobuf body | Decoded, then only allowlisted attributes are ever read (see [`opentelemetry.md`](opentelemetry.md)) — a malformed payload is rejected before any Neo4j access |
| Bounded HTTP correlation buffer | In-memory span metadata awaiting a cross-batch match | See below — its own dedicated trust boundary |
| Filesystem imports | OpenAPI/AsyncAPI/manifest documents under `sources.directories` | Parsed, source-validated, then canonically validated before any graph write; a partial import is never left in the graph |
| MCP input (`POST /mcp`) | JSON-RPC tool calls from an MCP client | Origin/host allow-listed (`app/mcp/guard.py`, `MCPConfig`); tool arguments validated against a closed schema; every tool call is read-only (see below) |

## LLM output is untrusted input

The platform's single hard rule for the LLM layer: **LLM output = untrusted input.** Generated
Cypher is never executed as-is — it always passes through `CypherValidator` first, which enforces a
strict allowlist and rejects anything else outright (see [`semantic-validation.md`](semantic-validation.md)
for the exact rule set). The LLM is architecturally incapable of mutating the graph: it never holds
Neo4j write credentials, and even its read-only Cypher is validated before execution. This is a
permanent architectural constraint, not a temporary safeguard — the LLM's only role is translating a
question into a query and explaining the resulting rows, never acting as the knowledge base itself.

## The HTTP correlation buffer as its own trust boundary (11H)

`HttpCorrelationBuffer` (`app/telemetry/correlation_buffer.py`) is the one piece of runtime state in
this codebase that lives entirely in memory, outside the graph, and it's worth calling out
explicitly as its own trust boundary rather than folding it into "OTLP input" above:

- **Bounded** — capped at `max-pending-spans` (default 10,000); once full, further inserts evict the
  oldest pending span rather than growing unbounded.
- **TTL-based** — every pending span (`PendingHttpSpan`) is evicted once `ttl-seconds` (default 60)
  elapses, whether or not its counterpart ever arrives.
- **No raw payload persistence** — a `PendingHttpSpan` only ever holds the same already-allowlisted
  identity/routing fields the rest of the OpenTelemetry pipeline reads (trace/span ids, service
  identity, method, route, target identity, timestamp) — never a raw span attribute dump.
- **No Neo4j `Span` nodes** — this buffer is purely an in-memory waiting room for cross-batch
  correlation; nothing about an individual span is ever written to the graph. Only the *fact* a
  correlated pair produces (a `CALLS` relation plus its evidence) is ever persisted.

This is a deliberate, explicit distinction: **short-lived correlation state is not persisted
Architecture Evidence.** The buffer exists purely to bridge two OTLP requests that happen to split a
single logical call across batches; it is never an alternative raw-telemetry or trace store, and it
must never become one — see [`opentelemetry.md`](opentelemetry.md) for the full attribute allowlist
this buffer (like everything else in the OpenTelemetry pipeline) is bound by.

## MCP is local/trusted-network evaluation only (v0.4.0 I2)

The `POST /mcp` endpoint (`app/mcp/`) is **not** a public-internet-safe surface, by design and
permanently for this release — v0.4.0 does not implement authorization, tenancy, or a general audit
platform for it. `MCPConfig.allowed_origins`/`allowed_hosts` (`app/settings.py`) default to
loopback-only origins and must be overridden deliberately for any non-local deployment; a request
whose `Origin`/`Host` isn't allow-listed is rejected (`403`) before any tool executes
(`mcp.server.transport_security`).

Within that boundary, every MCP tool call is read-only by the same architectural constraint as the
LLM query layer above: the MCP adapter package (`app/mcp/`) has no graph-session or write-repository
dependency, imports no graph repository, and cannot mutate the graph on any path (success, refusal,
input error, or internal error) — it can only call `ArchitectureIntelligenceService`, which itself
opens Neo4j `READ_ACCESS` sessions exclusively.
