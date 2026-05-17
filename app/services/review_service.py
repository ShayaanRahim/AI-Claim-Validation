"""
Human review service layer.

Handles:
- Fetching the review queue (claims flagged for human review)
- Submitting review decisions with status transitions
- Building audit history for a claim
"""
import json
import logging
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select, col

from app.db.models import (
    Claim, Validation, Review, ClaimStatus, ReviewDecision, ValidationSource
)
from app.models.review_models import (
    ReviewRequest, ReviewResponse, ReviewQueueItem,
    ReviewQueueResponse, ClaimHistoryEntry, ClaimHistoryResponse
)


logger = logging.getLogger(__name__)


REVIEWABLE_STATUSES = {
    ClaimStatus.READY_FOR_AI,
    ClaimStatus.IN_REVIEW,
    ClaimStatus.NEEDS_FIXES,
}

DECISION_TO_STATUS = {
    ReviewDecision.APPROVED: ClaimStatus.APPROVED,
    ReviewDecision.REJECTED: ClaimStatus.REJECTED,
    ReviewDecision.ESCALATED: ClaimStatus.IN_REVIEW,
}


class ReviewServiceError(Exception):
    pass


class ClaimNotFoundError(ReviewServiceError):
    pass


class ClaimNotReviewableError(ReviewServiceError):
    pass


def get_review_queue(session: Session, limit: int = 50, offset: int = 0) -> ReviewQueueResponse:
    """
    Fetch claims that need human review, ordered by creation date (oldest first).

    Includes claims that either:
    - Have an AI validation with needs_human_review=True
    - Are in a reviewable status (READY_FOR_AI, IN_REVIEW, NEEDS_FIXES)
    """
    # Find claim IDs flagged by AI for human review
    flagged_statement = (
        select(Validation.claim_id)
        .where(Validation.needs_human_review == True)  # noqa: E712
        .distinct()
    )
    flagged_claim_ids = session.exec(flagged_statement).all()

    # Find claims in reviewable statuses or flagged by AI
    statement = (
        select(Claim)
        .where(
            (col(Claim.status).in_([s.value for s in REVIEWABLE_STATUSES]))
            | (col(Claim.id).in_(flagged_claim_ids))
        )
        .where(
            col(Claim.status).notin_([ClaimStatus.APPROVED.value, ClaimStatus.REJECTED.value])
        )
        .order_by(Claim.created_at)
        .offset(offset)
        .limit(limit)
    )
    claims = session.exec(statement).all()

    # Count total
    count_statement = (
        select(Claim)
        .where(
            (col(Claim.status).in_([s.value for s in REVIEWABLE_STATUSES]))
            | (col(Claim.id).in_(flagged_claim_ids))
        )
        .where(
            col(Claim.status).notin_([ClaimStatus.APPROVED.value, ClaimStatus.REJECTED.value])
        )
    )
    all_matching = session.exec(count_statement).all()
    total = len(all_matching)

    items = []
    for claim in claims:
        # Get latest AI validation for this claim
        ai_val_stmt = (
            select(Validation)
            .where(Validation.claim_id == claim.id)
            .where(Validation.source == ValidationSource.llm)
            .order_by(Validation.created_at.desc())
        )
        ai_val = session.exec(ai_val_stmt).first()

        # Get latest deterministic validation
        det_val_stmt = (
            select(Validation)
            .where(Validation.claim_id == claim.id)
            .where(Validation.source == ValidationSource.deterministic)
            .order_by(Validation.created_at.desc())
        )
        det_val = session.exec(det_val_stmt).first()

        ai_confidence = ai_val.confidence_score if ai_val else None
        ai_status = ai_val.result_json.get("status") if ai_val else None
        ai_rationale = ai_val.result_json.get("rationale") if ai_val else None
        det_status = det_val.result_json.get("status") if det_val else None

        issue_count = 0
        if ai_val and "issues" in ai_val.result_json:
            issue_count += len(ai_val.result_json["issues"])
        if det_val and "issues" in det_val.result_json:
            issue_count += len(det_val.result_json["issues"])

        items.append(ReviewQueueItem(
            claim_id=str(claim.id),
            claim_status=claim.status,
            created_at=claim.created_at.isoformat(),
            updated_at=claim.updated_at.isoformat(),
            ai_confidence=ai_confidence,
            ai_status=ai_status,
            ai_rationale=ai_rationale,
            deterministic_status=det_status,
            issue_count=issue_count,
        ))

    return ReviewQueueResponse(total=total, items=items)


def submit_review(
    session: Session,
    claim_id: UUID,
    review_request: ReviewRequest,
) -> ReviewResponse:
    """
    Submit a human review decision for a claim.

    Validates:
    - Claim exists
    - Claim is in a reviewable state
    - Override rationale is provided when overriding AI recommendation

    Creates an immutable Review record and transitions the claim status.
    """
    claim = session.exec(select(Claim).where(Claim.id == claim_id)).first()
    if not claim:
        raise ClaimNotFoundError(f"Claim {claim_id} not found")

    if claim.status in (ClaimStatus.APPROVED.value, ClaimStatus.REJECTED.value):
        raise ClaimNotReviewableError(
            f"Claim {claim_id} has already been finalized with status '{claim.status}'"
        )

    # Find the latest AI validation to link the review to
    ai_val = session.exec(
        select(Validation)
        .where(Validation.claim_id == claim_id)
        .where(Validation.source == ValidationSource.llm)
        .order_by(Validation.created_at.desc())
    ).first()

    # Check if this is an override of the AI recommendation
    if ai_val:
        ai_status = ai_val.result_json.get("status", "")
        decision_lower = review_request.decision.lower()
        ai_recommended_approve = ai_status == "approved"
        human_rejects = decision_lower == "rejected"
        ai_recommended_reject = ai_status == "rejected"
        human_approves = decision_lower == "approved"

        is_override = (ai_recommended_approve and human_rejects) or (
            ai_recommended_reject and human_approves
        )
        if is_override and not review_request.override_rationale:
            raise ReviewServiceError(
                "override_rationale is required when the decision contradicts the AI recommendation"
            )

    status_before = claim.status
    decision_enum = ReviewDecision(review_request.decision)
    new_status = DECISION_TO_STATUS[decision_enum]
    claim.status = new_status.value

    review = Review(
        claim_id=claim_id,
        validation_id=ai_val.id if ai_val else None,
        reviewer_id=review_request.reviewer_id,
        decision=review_request.decision,
        notes=review_request.notes,
        override_rationale=review_request.override_rationale,
        claim_status_before=status_before,
        claim_status_after=new_status.value,
    )

    session.add(review)
    session.commit()
    session.refresh(review)
    session.refresh(claim)

    logger.info(json.dumps({
        "event": "review_submitted",
        "claim_id": str(claim_id),
        "reviewer_id": review_request.reviewer_id,
        "decision": review_request.decision,
        "status_before": status_before,
        "status_after": new_status.value,
    }))

    return ReviewResponse(
        review_id=str(review.id),
        claim_id=str(review.claim_id),
        reviewer_id=review.reviewer_id,
        decision=review.decision,
        notes=review.notes,
        override_rationale=review.override_rationale,
        claim_status_before=review.claim_status_before,
        claim_status_after=review.claim_status_after,
        created_at=review.created_at.isoformat(),
    )


def get_claim_history(session: Session, claim_id: UUID) -> ClaimHistoryResponse:
    """
    Build the complete audit history for a claim: all validations and reviews ordered by time.
    """
    claim = session.exec(select(Claim).where(Claim.id == claim_id)).first()
    if not claim:
        raise ClaimNotFoundError(f"Claim {claim_id} not found")

    validations = session.exec(
        select(Validation)
        .where(Validation.claim_id == claim_id)
        .order_by(Validation.created_at)
    ).all()

    reviews = session.exec(
        select(Review)
        .where(Review.claim_id == claim_id)
        .order_by(Review.created_at)
    ).all()

    history: list[ClaimHistoryEntry] = []

    for v in validations:
        details: dict = {
            "validation_id": str(v.id),
            "result": v.result_json,
        }
        if v.model_name:
            details["model_name"] = v.model_name
        if v.prompt_version:
            details["prompt_version"] = v.prompt_version
        if v.confidence_score is not None:
            details["confidence_score"] = v.confidence_score
        details["needs_human_review"] = v.needs_human_review

        history.append(ClaimHistoryEntry(
            entry_type="validation",
            source=v.source,
            timestamp=v.created_at.isoformat(),
            details=details,
        ))

    for r in reviews:
        history.append(ClaimHistoryEntry(
            entry_type="review",
            source="human",
            timestamp=r.created_at.isoformat(),
            details={
                "review_id": str(r.id),
                "reviewer_id": r.reviewer_id,
                "decision": r.decision,
                "notes": r.notes,
                "override_rationale": r.override_rationale,
                "claim_status_before": r.claim_status_before,
                "claim_status_after": r.claim_status_after,
            },
        ))

    history.sort(key=lambda e: e.timestamp)

    return ClaimHistoryResponse(
        claim_id=str(claim.id),
        current_status=claim.status,
        history=history,
    )
