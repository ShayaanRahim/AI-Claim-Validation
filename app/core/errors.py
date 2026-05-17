"""Standardized API error responses."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.middleware.request_context import get_request_id


class ErrorBody(BaseModel):
    error: str
    message: str
    request_id: str | None = None
    details: dict | list | None = None


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            body = ErrorBody(
                error=detail.get("error", "http_error"),
                message=detail.get("message", str(detail)),
                request_id=get_request_id(),
                details=detail.get("details"),
            )
        else:
            body = ErrorBody(
                error="http_error",
                message=str(detail),
                request_id=get_request_id(),
            )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(exclude_none=True))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        body = ErrorBody(
            error="validation_error",
            message="Request validation failed",
            request_id=get_request_id(),
            details=exc.errors(),
        )
        return JSONResponse(status_code=422, content=body.model_dump(exclude_none=True))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        body = ErrorBody(
            error="internal_error",
            message="An unexpected error occurred",
            request_id=get_request_id(),
        )
        return JSONResponse(status_code=500, content=body.model_dump(exclude_none=True))
