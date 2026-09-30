"""Template contexts for the HTML explorer pages (`app.api.ui`): the reads each page needs, in the
order it has always issued them, plus display formatting. The routes only decide the 404 and render.
"""

import neo4j

from app.analysis.blast_radius import blast_radius
from app.analysis.queues import consumers_of_queue, senders_of_queue
from app.analysis.runtime import default_since, service_runtime_profile
from app.graph import read_models
from app.settings import RuntimeAnalysisConfig


def _humanize_window_hours(hours: int) -> str:
    if hours % 24 == 0:
        days = hours // 24
        return "1 day" if days == 1 else f"{days} days"
    return f"{hours}h"


def service_page_context(
    session: neo4j.Session,
    service_id: str,
    *,
    environment: str | None,
    runtime_analysis: RuntimeAnalysisConfig,
) -> dict | None:
    """`service.html`'s context, or None when the service does not exist."""
    service = read_models.service_summary(session, service_id)
    if service is None:
        return None

    provides = read_models.service_provides(session, service_id)
    calls = read_models.service_calls(session, service_id)
    sends = read_models.service_sends(session, service_id)
    receives = read_models.service_receives(session, service_id)
    downstream = blast_radius(session, service_id, max_depth=1)

    env = environment or runtime_analysis.default_environment
    since = default_since(runtime_analysis.default_window_hours)
    observed = service_runtime_profile(session, service_id=service_id, environment=env, since=since)

    return {
        "service": service,
        "provides": provides,
        "calls": calls,
        "sends": sends,
        "receives": receives,
        "downstream": downstream,
        "observed": observed,
        "observed_window_label": _humanize_window_hours(runtime_analysis.default_window_hours),
    }


def queue_page_context(session: neo4j.Session, queue_id: str) -> dict | None:
    """`queue.html`'s context, or None when the queue does not exist."""
    queue = read_models.queue_summary(session, queue_id)
    if queue is None:
        return None

    messages = read_models.queue_messages(session, queue_id)
    dlq = read_models.queue_dead_letter(session, queue_id)

    return {
        "queue": queue,
        "senders": senders_of_queue(session, queue_id),
        "consumers": consumers_of_queue(session, queue_id),
        "messages": messages,
        "dlq": dlq,
    }
