"""Human review API endpoints."""
import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db.session import get_session
from app.models.review_models import (
    ReviewRequest, ReviewResponse,
    ReviewQueueResponse, ClaimHistoryResponse,
)
from app.services.review_service import (
    get_review_queue, submit_review, get_claim_history,
    ClaimNotFoundError, ClaimNotReviewableError, ReviewServiceError,
)


router = APIRouter(tags=["review"])


@router.get("/review/queue", response_model=ReviewQueueResponse)
def list_review_queue(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    """
    List claims awaiting human review, oldest first.

    Includes claims that have been flagged by the AI layer (needs_human_review=true)
    or are in a reviewable status (READY_FOR_AI, IN_REVIEW, NEEDS_FIXES).
    Already-finalized claims (APPROVED, REJECTED) are excluded.
    """
    print(json.dumps({
        "event": "review_queue_requested",
        "limit": limit,
        "offset": offset,
    }))

    return get_review_queue(session, limit=limit, offset=offset)


@router.post("/claims/{claim_id}/review", response_model=ReviewResponse, status_code=201)
def create_review(
    claim_id: UUID,
    review_request: ReviewRequest,
    session: Session = Depends(get_session),
):
    """
    Submit a human review decision for a claim.

    - Validates the claim exists and is in a reviewable state
    - Requires override_rationale when contradicting AI recommendation
    - Creates an immutable review record
    - Transitions claim status based on the decision:
        APPROVED  → claim status = APPROVED
        REJECTED  → claim status = REJECTED
        ESCALATED → claim status = IN_REVIEW (stays in queue)
    """
    print(json.dumps({
        "event": "review_submitted",
        "claim_id": str(claim_id),
        "reviewer_id": review_request.reviewer_id,
        "decision": review_request.decision,
    }))

    try:
        return submit_review(session, claim_id, review_request)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail="Claim not found")
    except ClaimNotReviewableError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ReviewServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(json.dumps({
            "event": "review_failed",
            "claim_id": str(claim_id),
            "error": str(e),
        }))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/claims/{claim_id}/history", response_model=ClaimHistoryResponse)
def get_history(
    claim_id: UUID,
    session: Session = Depends(get_session),
):
    """
    Get the complete audit history for a claim.

    Returns all validations (deterministic and AI) and human review decisions,
    ordered chronologically. Every status transition is traceable.
    """
    print(json.dumps({
        "event": "history_requested",
        "claim_id": str(claim_id),
    }))

    try:
        return get_claim_history(session, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail="Claim not found")
    except Exception as e:
        print(json.dumps({
            "event": "history_failed",
            "claim_id": str(claim_id),
            "error": str(e),
        }))
        raise HTTPException(status_code=500, detail=str(e))
