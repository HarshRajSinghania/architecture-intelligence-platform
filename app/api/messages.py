import neo4j
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_read_session
from app.graph import read_models

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("")
def list_messages(session: neo4j.Session = Depends(get_read_session)) -> list[dict]:
    return read_models.list_messages(session)


@router.get("/{message_id}")
def get_message(message_id: str, session: neo4j.Session = Depends(get_read_session)) -> dict:
    message = read_models.get_message(session, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail=f"message not found: {message_id}")
    return message
