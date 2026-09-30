import neo4j
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_read_session
from app.graph import read_models

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("")
def list_services(session: neo4j.Session = Depends(get_read_session)) -> list[dict]:
    return read_models.list_services(session)


@router.get("/{service_id}")
def get_service(service_id: str, session: neo4j.Session = Depends(get_read_session)) -> dict:
    service = read_models.get_service(session, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
    return service


@router.get("/{service_id}/evidence")
def get_service_evidence(
    service_id: str, session: neo4j.Session = Depends(get_read_session)
) -> list[dict]:
    """Evidence backing every relation incident to this service (spec §4.10, AC13)."""
    if read_models.get_service(session, service_id) is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
    return read_models.service_evidence(session, service_id)
