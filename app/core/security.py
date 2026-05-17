"""Role definitions and API key validation."""
from enum import Enum

from app.core.config import settings


class Role(str, Enum):
    SYSTEM = "system"
    REVIEWER = "reviewer"


def resolve_role_from_api_key(api_key: str | None) -> Role | None:
    """Map an API key to a role. Returns None if key is invalid."""
    if not api_key:
        return None
    if api_key == settings.SYSTEM_API_KEY:
        return Role.SYSTEM
    if api_key == settings.REVIEWER_API_KEY:
        return Role.REVIEWER
    return None
