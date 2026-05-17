"""Human review API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.core.audit_log import log_audit_event
from app.core.auth import Principal
from app.db.session import get_session
from app.dependencies.auth import require_reviewer
from app.models.review_models import (
    ReviewRequest,
    ReviewResponse,
    ReviewQueueResponse,
    ClaimHistoryResponse,
)
from app.services.review_service import (
    get_review_queue,
    submit_review,
    get_claim_history,
    ClaimNotFoundError,
    ClaimNotReviewableError,
    ReviewServiceError,
)

router = APIRouter(tags=["review"])


@router.get("/review/queue", response_model=ReviewQueueResponse)
def list_review_queue(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_reviewer),
):
    """List claims awaiting human review (reviewer role only)."""
    log_audit_event(
        "review_queue_requested",
        reviewer_role=principal.role.value,
        limit=limit,
        offset=offset,
    )
    return get_review_queue(session, limit=limit, offset=offset)


@router.post("/claims/{claim_id}/review", response_model=ReviewResponse, status_code=201)
def create_review(
    claim_id: UUID,
    review_request: ReviewRequest,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_reviewer),
):
    """Submit a human review decision (reviewer role only)."""
    log_audit_event(
        "review_submitted",
        claim_id=str(claim_id),
        reviewer_id=review_request.reviewer_id,
        decision=review_request.decision,
    )

    try:
        response = submit_review(session, claim_id, review_request)
        log_audit_event(
            "review_completed",
            claim_id=str(claim_id),
            review_id=response.review_id,
            reviewer_id=review_request.reviewer_id,
            decision=review_request.decision,
            previous_status=response.claim_status_before,
            new_status=response.claim_status_after,
            override_rationale=review_request.override_rationale,
        )
        return response
    except ClaimNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Claim not found"},
        )
    except ClaimNotReviewableError as e:
        raise HTTPException(
            status_code=409,
            detail={"error": "conflict", "message": str(e)},
        )
    except ReviewServiceError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "review_error", "message": str(e)},
        )
    except Exception as e:
        log_audit_event(
            "review_failed",
            claim_id=str(claim_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": str(e)},
        )


@router.get("/claims/{claim_id}/history", response_model=ClaimHistoryResponse)
def get_history(
    claim_id: UUID,
    session: Session = Depends(get_session),
    _principal: Principal = Depends(require_reviewer),
):
    """Full audit history for a claim (reviewer role only)."""
    log_audit_event("history_requested", claim_id=str(claim_id))

    try:
        return get_claim_history(session, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Claim not found"},
        )
    except Exception as e:
        log_audit_event("history_failed", claim_id=str(claim_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": str(e)},
        )
