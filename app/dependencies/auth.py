"""Role-based authorization dependencies."""
from fastapi import Depends, HTTPException

from app.core.auth import Principal, get_current_principal
from app.core.config import settings
from app.core.security import Role


def require_system(principal: Principal = Depends(get_current_principal)) -> Principal:
    if settings.AUTH_DISABLED:
        return principal
    if principal.role != Role.SYSTEM:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "message": "This endpoint requires the system role",
            },
        )
    return principal


def require_reviewer(principal: Principal = Depends(get_current_principal)) -> Principal:
    if settings.AUTH_DISABLED:
        return principal
    if principal.role != Role.REVIEWER:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "message": "This endpoint requires the reviewer role",
            },
        )
    return principal


def require_authenticated(
    principal: Principal = Depends(get_current_principal),
) -> Principal:
    """Any valid authenticated role (system or reviewer)."""
    return principal
