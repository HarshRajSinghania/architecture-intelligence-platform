import neo4j
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

from app.deps import get_driver, get_http_correlation_buffer, get_settings
from app.settings import Settings
from app.telemetry.correlation_buffer import HttpCorrelationBuffer
from app.telemetry.ingest import ingest_trace_spans
from app.telemetry.otlp_receiver import OtlpDecodeError, decode_export_request

router = APIRouter(tags=["telemetry"])

_OTLP_CONTENT_TYPE = "application/x-protobuf"


@router.post("/v1/traces")
async def post_traces(
    request: Request,
    driver: neo4j.Driver = Depends(get_driver),
    settings: Settings = Depends(get_settings),
    correlation_buffer: HttpCorrelationBuffer | None = Depends(get_http_correlation_buffer),
) -> Response:
    """OTLP/HTTP trace ingestion (spec §8): decode -> resolve against declared data -> persist
    observed facts/evidence (spec §36, Iteration 11E). Content-type/decode validation happens
    before any Neo4j access, so a malformed request never touches the graph."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith(_OTLP_CONTENT_TYPE):
        raise HTTPException(
            status_code=415,
            detail=f"unsupported content-type: {content_type!r}, expected {_OTLP_CONTENT_TYPE!r}",
        )

    raw = await request.body()
    try:
        spans = decode_export_request(raw)
    except OtlpDecodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ingest_trace_spans(
        spans,
        driver=driver,
        database=settings.config.graph.database,
        telemetry=settings.config.telemetry,
        correlation_buffer=correlation_buffer,
    )

    return Response(
        content=ExportTraceServiceResponse().SerializeToString(),
        media_type=_OTLP_CONTENT_TYPE,
    )
