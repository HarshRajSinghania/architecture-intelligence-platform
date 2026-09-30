import neo4j
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_read_session
from app.graph import read_models

router = APIRouter(prefix="/api/queues", tags=["queues"])


@router.get("")
def list_queues(session: neo4j.Session = Depends(get_read_session)) -> list[dict]:
    return read_models.list_queues(session)


@router.get("/{queue_id}")
def get_queue(queue_id: str, session: neo4j.Session = Depends(get_read_session)) -> dict:
    queue = read_models.get_queue(session, queue_id)
    if queue is None:
        raise HTTPException(status_code=404, detail=f"queue not found: {queue_id}")
    return queue


@router.get("/{queue_id}/evidence")
def get_queue_evidence(
    queue_id: str, session: neo4j.Session = Depends(get_read_session)
) -> list[dict]:
    """Evidence backing every relation incident to this queue (spec §4.10, AC13)."""
    if read_models.get_queue(session, queue_id) is None:
        raise HTTPException(status_code=404, detail=f"queue not found: {queue_id}")
    return read_models.queue_evidence(session, queue_id)
