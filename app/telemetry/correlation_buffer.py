import logging
import threading
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PendingHttpSpan(BaseModel):
    """Transient cross-batch HTTP correlation record (11H spec §15's suggested shape, extended
    with service_namespace/service_version - both already-structured identity fields this
    codebase reads from RuntimeSpan today, not raw/unbounded attribute data, so including them
    doesn't violate the "no raw payload" allowlist principle spec §6.3/§13/§14 require). Never
    persisted as a Neo4j Span node - purely an in-memory, TTL-bounded waiting record."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    span_kind: Literal["CLIENT", "SERVER"]
    service_name: str
    service_namespace: str | None = None
    service_version: str | None = None
    environment: str | None = None
    method: str | None = None
    route: str | None = None
    target_identity: str | None = None
    timestamp: datetime
    # v0.6.0 I2.1c: the original CLIENT's admitted Kubernetes identity, so it survives a
    # cross-batch wait. Bounded exact strings from the I1 allowlist only, never set for a SERVER
    # span, and (like the rest of this record) never persisted.
    k8s_pod_uid: str | None = None
    k8s_cluster_uid: str | None = None
    k8s_namespace_name: str | None = None
    k8s_pod_name: str | None = None
    k8s_deployment_name: str | None = None
    k8s_statefulset_name: str | None = None
    k8s_daemonset_name: str | None = None


class HttpCorrelationBuffer:
    """Bounded, TTL-based, thread-safe store of unpaired CLIENT/SERVER HTTP spans awaiting their
    cross-batch counterpart (11H R2/spec §6). Both maps key on the pairing identity a matching
    counterpart would look itself up under: a SERVER span is keyed by (trace_id, parent_span_id),
    which is exactly a CLIENT span's own (trace_id, span_id) - so whichever side arrives second
    finds the other already waiting under the same key, regardless of arrival order.

    Deliberately simple: no background sweep task (matches this app's fully synchronous,
    request-driven style - Neo4j calls in POST /v1/traces run directly on the event loop thread,
    confirmed in app/api/telemetry.py, so there is no true concurrent request processing here to
    defend against beyond cheap insurance). Eviction is lazy, checked at the top of every
    offer_*() call, both by TTL and by a hard max-size bound (oldest entry evicted first, via
    OrderedDict's insertion-order guarantee) - this must never become an unbounded trace store
    (spec §6.3)."""

    def __init__(self, *, ttl_seconds: int, max_pending_spans: int) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max = max_pending_spans
        self._lock = threading.Lock()
        self._pending_clients: OrderedDict[tuple[str, str], tuple[PendingHttpSpan, datetime]] = (
            OrderedDict()
        )
        self._pending_servers: OrderedDict[tuple[str, str], tuple[PendingHttpSpan, datetime]] = (
            OrderedDict()
        )
        # Lightweight diagnostics only (spec §23) - never span content.
        self.cross_batch_matches = 0
        self.expirations = 0
        self.evictions = 0

    def _pop_expired_locked(
        self, store: "OrderedDict[tuple[str, str], tuple[PendingHttpSpan, datetime]]", now: datetime
    ) -> list[PendingHttpSpan]:
        expired = []
        while store:
            _, (span, inserted_at) = next(iter(store.items()))
            if now - inserted_at <= self._ttl:
                break
            store.popitem(last=False)
            self.expirations += 1
            expired.append(span)
        return expired

    def _evict_expired_locked(
        self, store: "OrderedDict[tuple[str, str], tuple[PendingHttpSpan, datetime]]", now: datetime
    ) -> None:
        self._pop_expired_locked(store, now)

    def sweep_expired(self) -> tuple[list[PendingHttpSpan], list[PendingHttpSpan]]:
        """Evicts and returns (expired_clients, expired_servers) - TTL-expired entries a caller
        should now treat as CLIENT_ONLY/SERVER_ONLY candidates (11H-C/spec §7) rather than
        silently discarding. Safe to call every request; entries already popped by a prior sweep
        or by offer_*() are simply absent from the result."""
        now = datetime.now(UTC)
        with self._lock:
            expired_clients = self._pop_expired_locked(self._pending_clients, now)
            expired_servers = self._pop_expired_locked(self._pending_servers, now)
        return expired_clients, expired_servers

    def _enforce_bound_locked(
        self, store: "OrderedDict[tuple[str, str], tuple[PendingHttpSpan, datetime]]"
    ) -> int:
        evicted = 0
        while len(store) > self._max:
            store.popitem(last=False)
            self.evictions += 1
            evicted += 1
        return evicted

    def offer_server(self, span: PendingHttpSpan) -> PendingHttpSpan | None:
        """Offers a SERVER-kind span that had no in-batch CLIENT match. Returns the previously
        buffered CLIENT counterpart if one is waiting (and consumes it); otherwise buffers this
        SERVER span for a CLIENT that may arrive in a later batch, and returns None."""
        if span.parent_span_id is None:
            return None
        now = datetime.now(UTC)
        key = (span.trace_id, span.parent_span_id)
        with self._lock:
            self._evict_expired_locked(self._pending_clients, now)
            self._evict_expired_locked(self._pending_servers, now)
            match = self._pending_clients.pop(key, None)
            if match is not None:
                self.cross_batch_matches += 1
                return match[0]
            self._pending_servers[key] = (span, now)
            evicted = self._enforce_bound_locked(self._pending_servers)
            if evicted:
                logger.warning("HTTP correlation buffer size eviction count=%d", evicted)
            return None

    def offer_client(self, span: PendingHttpSpan) -> PendingHttpSpan | None:
        """Offers a CLIENT-kind span that had no in-batch SERVER match. Returns the previously
        buffered SERVER counterpart if one is waiting (and consumes it); otherwise buffers this
        CLIENT span for a SERVER that may arrive in a later batch, and returns None."""
        now = datetime.now(UTC)
        key = (span.trace_id, span.span_id)
        with self._lock:
            self._evict_expired_locked(self._pending_clients, now)
            self._evict_expired_locked(self._pending_servers, now)
            match = self._pending_servers.pop(key, None)
            if match is not None:
                self.cross_batch_matches += 1
                return match[0]
            self._pending_clients[key] = (span, now)
            evicted = self._enforce_bound_locked(self._pending_clients)
            if evicted:
                logger.warning("HTTP correlation buffer size eviction count=%d", evicted)
            return None
