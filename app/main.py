import logging

from fastapi import FastAPI

from app.api import claims, validation, ai_validation, review, health
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.timing import RequestTimingMiddleware

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(message)s",
)

app = FastAPI(
    title="AI Claim Validation",
    debug=settings.DEBUG,
)

app.add_middleware(RequestTimingMiddleware)
app.add_middleware(RequestContextMiddleware)

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(claims.router)
app.include_router(validation.router)
app.include_router(ai_validation.router)
app.include_router(review.router)


@app.get("/health")
def health_legacy():
    """Legacy health endpoint; prefer /health/live."""
    return {"status": "ok"}
