"""Structured audit logging for regulated workflows."""
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.middleware.request_context import get_request_id

logger = logging.getLogger("app.audit")

_SENSITIVE_KEYS = frozenset({
    "api_key", "password", "secret", "token", "authorization",
    "openai_api_key", "system_api_key", "reviewer_api_key",
})


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "***" if k.lower() in _SENSITIVE_KEYS else _scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def log_audit_event(event: str, **fields: Any) -> None:
    """
    Emit a structured audit log line.
    Automatically attaches request_id and UTC timestamp.
    """
    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": get_request_id(),
        **_scrub(fields),
    }
    logger.info(json.dumps(payload, default=str))
