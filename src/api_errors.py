"""Centralized FastAPI error handling for the BigFlavor backend.

Keeps raw exception detail in the server logs only and returns a consistent,
client-safe body for every error class:

    {"error": {"code": "<machine_code>", "message": "<client-safe text>"}}
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "unprocessable_entity",
    429: "too_many_requests",
}


def error_body(code: str, message: str) -> dict:
    """Build the shared error response body."""
    return {"error": {"code": code, "message": message}}


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Return expected client errors (404/400/...) in the shared error body shape."""
    code = _ERROR_CODES.get(exc.status_code, "error")
    message = exc.detail if isinstance(exc.detail, str) else "Request could not be completed."
    logger.warning(
        "HTTP %s on %s %s: %s", exc.status_code, request.method, request.url.path, message
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return request-validation failures as 422 in the shared error body shape."""
    logger.warning(
        "Validation error on %s %s: %s", request.method, request.url.path, exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content=error_body("unprocessable_entity", "Request validation failed."),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log the full exception server-side; return a generic 500 with no internal detail."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "An internal error occurred."),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register the centralized exception handlers on a FastAPI app."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
