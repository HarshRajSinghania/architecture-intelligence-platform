from pathlib import Path

import neo4j
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.answer_router import LLMNotConfiguredError, answer_question
from app.api.query import QueryResponse
from app.api.ui_context import queue_page_context, service_page_context
from app.deps import build_question_service, get_read_session, get_settings
from app.graph import read_models
from app.settings import Settings

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: neo4j.Session = Depends(get_read_session)):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "services": read_models.index_services(session),
            "queues": read_models.index_queues(session),
        },
    )


@router.get("/services/{service_id}", response_class=HTMLResponse)
def service_explorer(
    request: Request,
    service_id: str,
    environment: str | None = None,
    session: neo4j.Session = Depends(get_read_session),
    settings: Settings = Depends(get_settings),
):
    context = service_page_context(
        session,
        service_id,
        environment=environment,
        runtime_analysis=settings.config.runtime_analysis,
    )
    if context is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
    return templates.TemplateResponse(request, "service.html", context)


@router.get("/queues/{queue_id}", response_class=HTMLResponse)
def queue_explorer(
    request: Request, queue_id: str, session: neo4j.Session = Depends(get_read_session)
):
    context = queue_page_context(session, queue_id)
    if context is None:
        raise HTTPException(status_code=404, detail=f"queue not found: {queue_id}")
    return templates.TemplateResponse(request, "queue.html", context)


@router.get("/query", response_class=HTMLResponse)
def query_page(
    request: Request,
    question: str | None = None,
    session: neo4j.Session = Depends(get_read_session),
):
    result = None
    if question:
        settings = get_settings(request)
        question_service = build_question_service(request)
        try:
            routed = answer_question(
                session=session,
                question=question,
                deterministic_threshold=settings.config.intent_router.deterministic_threshold,
                question_service=question_service,
                default_window_hours=settings.config.runtime_analysis.default_window_hours,
                default_environment=settings.config.runtime_analysis.default_environment,
            )
            result = QueryResponse(
                question=routed.question,
                cypher=routed.cypher,
                rows=routed.rows,
                answer=routed.answer,
                execution_mode=routed.execution_mode,
                intent=routed.intent,
            )
        except LLMNotConfiguredError:
            result = QueryResponse(
                question=question,
                cypher=None,
                rows=[],
                answer="Natural language query is not configured (missing OPENAI_API_KEY, or llm.enabled is false in config.yaml).",
            )
    return templates.TemplateResponse(
        request, "query.html", {"question": question, "result": result}
    )
