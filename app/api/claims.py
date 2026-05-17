"""Claims API endpoints"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.audit_log import log_audit_event
from app.core.auth import Principal
from app.db.session import get_session
from app.db.models import Claim, Validation, ClaimStatus
from app.dependencies.auth import require_authenticated, require_system
from app.models.claim_models import ClaimInput

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("", response_model=dict, status_code=201)
def create_claim(
    claim_input: ClaimInput,
    session: Session = Depends(get_session),
    _principal: Principal = Depends(require_system),
):
    """Create a new claim (system role only)."""
    claim = Claim(
        raw_claim_json=claim_input.model_dump(mode="json"),
        status=ClaimStatus.DRAFT,
    )
    session.add(claim)
    session.commit()
    session.refresh(claim)

    log_audit_event(
        "claim_created",
        claim_id=str(claim.id),
        status=claim.status,
    )
    return {"claim_id": str(claim.id)}


@router.get("/{claim_id}")
def get_claim(
    claim_id: UUID,
    session: Session = Depends(get_session),
    _principal: Principal = Depends(require_authenticated),
):
    """Retrieve claim metadata and validation history."""
    claim = session.exec(select(Claim).where(Claim.id == claim_id)).first()
    if not claim:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Claim not found"})

    validations = session.exec(
        select(Validation).where(Validation.claim_id == claim_id).order_by(Validation.created_at)
    ).all()

    log_audit_event("claim_retrieved", claim_id=str(claim_id))

    return {
        "claim_id": str(claim.id),
        "status": claim.status,
        "created_at": claim.created_at.isoformat(),
        "updated_at": claim.updated_at.isoformat(),
        "raw_claim": claim.raw_claim_json,
        "validations": [
            {
                "validation_id": str(v.id),
                "source": v.source,
                "result": v.result_json,
                "created_at": v.created_at.isoformat(),
            }
            for v in validations
        ],
    }
