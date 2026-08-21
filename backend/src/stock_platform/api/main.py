from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from stock_platform.api.routes.events import router as events_router
from stock_platform.api.routes.health import router as health_router
from stock_platform.api.routes.rest import router as rest_router
from stock_platform.api.schemas.errors import ApiError, ErrorBody, ErrorEnvelope

app = FastAPI(title="AI Stock Research Platform", version="0.2.0")
app.include_router(health_router)
app.include_router(rest_router)
app.include_router(events_router)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            retryable=retryable,
            correlation_id=uuid4(),
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
