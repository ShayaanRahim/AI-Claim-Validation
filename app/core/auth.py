"""Authentication primitives."""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import settings
from app.core.security import Role, resolve_role_from_api_key

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class Principal:
    role: Role


async def get_current_principal(
    api_key: str | None = Security(API_KEY_HEADER),
) -> Principal:
    """
    Resolve the caller from X-API-Key.
    When AUTH_DISABLED=true (test/legacy), returns a system principal.
    """
    if settings.AUTH_DISABLED:
        return Principal(role=Role.SYSTEM)

    role = resolve_role_from_api_key(api_key)
    if role is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Invalid or missing API key"},
        )
    return Principal(role=role)
