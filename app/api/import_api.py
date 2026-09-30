from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_driver, get_settings
from app.graph import read_models
from app.graph.import_runs import ImportConfigurationError, run_all_configured_sources
from app.graph.repository import open_session
from app.ingestion.import_report import (
    ConfiguredRun,
    ImportReport,
    ServiceImportReport,
    build_import_report,
)
from app.settings import Settings

router = APIRouter(prefix="/api/import", tags=["import"])


def _run_all_configured_sources(settings: Settings, driver) -> tuple[str, list[ConfiguredRun]]:
    try:
        return run_all_configured_sources(
            settings.config.sources, driver=driver, database=settings.config.graph.database
        )
    except ImportConfigurationError as exc:
        # A broken operator configuration fails the whole request loudly (I1 spec §5.1.1).
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("", response_model=ImportReport)
def import_all(
    settings: Settings = Depends(get_settings), driver=Depends(get_driver)
) -> ImportReport:
    """POST /api/import - imports every configured source (I1 spec §14). Each configured
    directory is its own atomic discovery run (I1 spec §6): one run's PARTIAL/FAILED status never
    blocks another's commit. The response is the versioned I1 §10 import report
    (`app.ingestion.import_report`)."""
    import_id, run_results = _run_all_configured_sources(settings, driver)
    return build_import_report(import_id, run_results)


@router.post("/service/{service_id}", response_model=ServiceImportReport)
def import_one_service(
    service_id: str, settings: Settings = Depends(get_settings), driver=Depends(get_driver)
) -> ServiceImportReport:
    """POST /api/import/service/{serviceId} reimports every configured source and reports the
    resulting stats, then confirms the requested canonical Service ID (e.g. "service:order-
    service") now exists. Under I1, a service may be declared by more than one source and a source
    may declare more than one service (ADR 0009), so a single-source-scoped reimport is no longer
    a meaningful unit - the whole configured scope is always reimported."""
    import_id, run_results = _run_all_configured_sources(settings, driver)
    report = build_import_report(import_id, run_results)

    with open_session(driver, database=settings.config.graph.database) as session:
        exists = read_models.service_exists(session, service_id)
    if not exists:
        raise HTTPException(status_code=404, detail=f"no known service: {service_id}")

    return ServiceImportReport(**report.model_dump(), service_id=service_id)
