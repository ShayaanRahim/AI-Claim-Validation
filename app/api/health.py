"""Health check endpoints for orchestration and load balancers."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session

from app.db.session import get_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


@router.get("/health/live", response_model=HealthResponse)
def liveness():
    """Process is running."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def readiness(session: Session = Depends(get_session)):
    """Verify database connectivity."""
    session.exec(text("SELECT 1"))
    return HealthResponse(status="ok")
