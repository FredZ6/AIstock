from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from stock_platform.api.routes.events import router as events_router
from stock_platform.api.routes.health import router as health_router
from stock_platform.api.routes.rest import router as rest_router
from stock_platform.api.schemas.errors import ApiError, ErrorBody, ErrorEnvelope
from stock_platform.infrastructure.observability.context import (
    CorrelationContext,
    correlation_scope,
    current_correlation,
)
from stock_platform.infrastructure.observability.metrics import platform_metrics
from stock_platform.infrastructure.observability.telemetry import operational_telemetry

app = FastAPI(title="AI Stock Research Platform", version="0.2.0")
app.include_router(health_router)
app.include_router(rest_router)
app.include_router(events_router)


@app.middleware("http")
async def correlation_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    raw_id = request.headers.get("x-correlation-id")
    try:
        correlation_id = UUID(raw_id) if raw_id else uuid4()
    except ValueError:
        correlation_id = uuid4()
        with correlation_scope(CorrelationContext(correlation_id=correlation_id)):
            invalid_response = _error_response(
                400,
                "INVALID_CORRELATION_ID",
                "x-correlation-id must be a UUID",
            )
        invalid_response.headers["x-correlation-id"] = str(correlation_id)
        return invalid_response
    context = CorrelationContext(correlation_id=correlation_id)
    with correlation_scope(context):
        with operational_telemetry.span("http.request", {"http.method": request.method}) as span:
            response = await call_next(request)
            span.set_attribute("http.status_code", response.status_code)
    response.headers["x-correlation-id"] = str(correlation_id)
    route = request.scope.get("route")
    route_name = str(getattr(route, "path", "unmatched"))
    platform_metrics.observe_request(
        service="api",
        route=route_name,
        status=str(response.status_code),
    )
    with correlation_scope(context):
        operational_telemetry.log(
            "http.request.completed",
            {"method": request.method, "route": route_name, "status": response.status_code},
        )
    return response


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(platform_metrics.render(), media_type=CONTENT_TYPE_LATEST)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    try:
        correlation_id = current_correlation().correlation_id
    except RuntimeError:
        correlation_id = uuid4()
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            retryable=retryable,
            correlation_id=correlation_id,
            details=details or {},
        )
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, exception: ApiError) -> JSONResponse:
    return _error_response(
        exception.status_code,
        exception.code,
        exception.message,
        retryable=exception.retryable,
        details=exception.details,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, exception: RequestValidationError
) -> JSONResponse:
    errors = [
        {"type": item["type"], "loc": list(item["loc"]), "message": item["msg"]}
        for item in exception.errors()
    ]
    return _error_response(
        422,
        "INVALID_REQUEST",
        "Request validation failed",
        details={"errors": errors},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, exception: StarletteHTTPException) -> JSONResponse:
    if exception.status_code == 404:
        code = "NOT_FOUND"
        message = "Resource not found"
    else:
        code = "HTTP_ERROR"
        message = str(exception.detail)
    return _error_response(exception.status_code, code, message)
