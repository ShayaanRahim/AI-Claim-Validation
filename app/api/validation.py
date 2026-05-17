"""Validation API endpoints"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.audit_log import log_audit_event
from app.core.auth import Principal
from app.db.session import get_session
from app.db.models import Claim, Validation, ClaimStatus, ValidationSource
from app.dependencies.auth import require_system
from app.models.claim_models import ClaimInput
from app.models.validation_models import ValidationResult
from app.services.validation.engine import run_validation

router = APIRouter(prefix="/claims", tags=["validation"])


@router.post("/{claim_id}/validate/deterministic", response_model=ValidationResult)
def validate_claim_deterministic(
    claim_id: UUID,
    session: Session = Depends(get_session),
    _principal: Principal = Depends(require_system),
):
    """Run deterministic validation on a claim (system role only)."""
    log_audit_event(
        "validation_started",
        claim_id=str(claim_id),
        validation_type="deterministic",
    )

    try:
        claim = session.exec(select(Claim).where(Claim.id == claim_id)).first()
        if not claim:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Claim not found"},
            )

        try:
            claim_input = ClaimInput(**claim.raw_claim_json)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_claim", "message": str(e)},
            )

        result = run_validation(claim_input)

        validation = Validation(
            claim_id=claim_id,
            source=ValidationSource.deterministic,
            result_json=result.model_dump(mode="json"),
        )
        session.add(validation)

        claim.status = (
            ClaimStatus.READY_FOR_AI if result.status == "PASS" else ClaimStatus.NEEDS_FIXES
        )
        session.commit()
        session.refresh(validation)

        log_audit_event(
            "validation_completed",
            claim_id=str(claim_id),
            validation_type="deterministic",
            validation_id=str(validation.id),
            status=result.status,
            num_issues=len(result.issues),
            needs_human_review=result.needs_human_review,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        log_audit_event(
            "validation_failed",
            claim_id=str(claim_id),
            validation_type="deterministic",
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": str(e)},
        )
