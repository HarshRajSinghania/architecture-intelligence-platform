"""App-level exception handlers, registered once from `create_app` (`register_exception_handlers`).

Route-specific, spec-frozen error tables (the evidence 503/409/404 table, the deployments 404) stay
with their routes; this module holds only the handlers that apply app-wide.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.ai.semantic_query_validator import SemanticValidationError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SemanticValidationError)
    def handle_semantic_validation_error(request: Request, exc: SemanticValidationError):
        """Spec §5.10: structurally invalid generated Cypher (e.g. wrong relationship direction)
        never reaches Neo4j and is reported as 422 with the violated relation's domain/range."""
        return JSONResponse(
            status_code=422,
            content={
                "code": "SEMANTIC_QUERY_INVALID",
                "message": str(exc),
                "relation": exc.relation,
                "expectedSource": sorted(exc.expected_source),
                "expectedTarget": sorted(exc.expected_target),
            },
        )
