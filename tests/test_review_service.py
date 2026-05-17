"""Tests for review service layer."""
import pytest
from uuid import uuid4
from datetime import datetime, timezone
from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from app.db.models import (
    Claim, Validation, ClaimStatus, ValidationSource
)
from app.models.review_models import ReviewRequest
from app.services.review_service import (
    get_review_queue, submit_review, get_claim_history,
    ClaimNotFoundError, ClaimNotReviewableError, ReviewServiceError,
)


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_claim(session: Session, status: str = ClaimStatus.READY_FOR_AI) -> Claim:
    claim = Claim(
        raw_claim_json={"patient": {"id": "p1"}},
        status=status,
    )
    session.add(claim)
    session.commit()
    session.refresh(claim)
    return claim


def _make_validation(
    session: Session,
    claim_id,
    source: str = ValidationSource.deterministic,
    needs_human_review: bool = False,
    result_json: dict | None = None,
    confidence: float | None = None,
) -> Validation:
    val = Validation(
        claim_id=claim_id,
        source=source,
        result_json=result_json or {"status": "PASS", "issues": []},
        needs_human_review=needs_human_review,
        confidence_score=confidence,
    )
    session.add(val)
    session.commit()
    session.refresh(val)
    return val


class TestGetReviewQueue:

    def test_empty_queue(self, session: Session):
        resp = get_review_queue(session)
        assert resp.total == 0
        assert resp.items == []

    def test_reviewable_claims_appear(self, session: Session):
        _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        _make_claim(session, status=ClaimStatus.NEEDS_FIXES)
        resp = get_review_queue(session)
        assert resp.total == 2

    def test_finalized_claims_excluded(self, session: Session):
        _make_claim(session, status=ClaimStatus.APPROVED)
        _make_claim(session, status=ClaimStatus.REJECTED)
        resp = get_review_queue(session)
        assert resp.total == 0

    def test_ai_flagged_claims_appear(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        _make_validation(
            session, claim.id, source=ValidationSource.llm,
            needs_human_review=True,
            result_json={"status": "needs_review", "issues": [], "rationale": "Low confidence"},
            confidence=0.6,
        )
        resp = get_review_queue(session)
        assert resp.total == 1
        assert resp.items[0].ai_confidence == 0.6

    def test_queue_includes_issue_count(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        _make_validation(
            session, claim.id, source=ValidationSource.deterministic,
            result_json={"status": "FAIL", "issues": [{"code": "A"}, {"code": "B"}]},
        )
        resp = get_review_queue(session)
        assert resp.items[0].issue_count == 2

    def test_pagination(self, session: Session):
        for _ in range(5):
            _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        resp = get_review_queue(session, limit=2, offset=0)
        assert len(resp.items) == 2
        assert resp.total == 5


class TestSubmitReview:

    def test_approve_claim(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        req = ReviewRequest(reviewer_id="rev-1", decision="APPROVED", notes="OK")
        resp = submit_review(session, claim.id, req)

        assert resp.decision == "APPROVED"
        assert resp.claim_status_before == ClaimStatus.READY_FOR_AI
        assert resp.claim_status_after == ClaimStatus.APPROVED

        session.refresh(claim)
        assert claim.status == ClaimStatus.APPROVED

    def test_reject_claim(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        req = ReviewRequest(reviewer_id="rev-1", decision="REJECTED", notes="Bad data")
        resp = submit_review(session, claim.id, req)

        assert resp.decision == "REJECTED"
        assert resp.claim_status_after == ClaimStatus.REJECTED

    def test_escalate_claim(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        req = ReviewRequest(reviewer_id="rev-1", decision="ESCALATED", notes="Need senior")
        resp = submit_review(session, claim.id, req)

        assert resp.decision == "ESCALATED"
        assert resp.claim_status_after == ClaimStatus.IN_REVIEW

    def test_cannot_review_already_approved(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.APPROVED)
        req = ReviewRequest(reviewer_id="rev-1", decision="REJECTED")
        with pytest.raises(ClaimNotReviewableError):
            submit_review(session, claim.id, req)

    def test_cannot_review_already_rejected(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.REJECTED)
        req = ReviewRequest(reviewer_id="rev-1", decision="APPROVED")
        with pytest.raises(ClaimNotReviewableError):
            submit_review(session, claim.id, req)

    def test_claim_not_found(self, session: Session):
        req = ReviewRequest(reviewer_id="rev-1", decision="APPROVED")
        with pytest.raises(ClaimNotFoundError):
            submit_review(session, uuid4(), req)

    def test_override_requires_rationale(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        _make_validation(
            session, claim.id, source=ValidationSource.llm,
            result_json={"status": "rejected", "issues": [], "rationale": "Bad"},
            confidence=0.9,
        )
        req = ReviewRequest(reviewer_id="rev-1", decision="APPROVED")
        with pytest.raises(ReviewServiceError, match="override_rationale"):
            submit_review(session, claim.id, req)

    def test_override_with_rationale_succeeds(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        _make_validation(
            session, claim.id, source=ValidationSource.llm,
            result_json={"status": "rejected", "issues": [], "rationale": "Bad"},
            confidence=0.9,
        )
        req = ReviewRequest(
            reviewer_id="rev-1",
            decision="APPROVED",
            override_rationale="Documentation confirms coverage is valid.",
        )
        resp = submit_review(session, claim.id, req)
        assert resp.decision == "APPROVED"
        assert resp.override_rationale is not None

    def test_multiple_reviews_creates_multiple_records(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        req1 = ReviewRequest(reviewer_id="rev-1", decision="ESCALATED", notes="Need more info")
        submit_review(session, claim.id, req1)

        session.refresh(claim)
        assert claim.status == ClaimStatus.IN_REVIEW

        req2 = ReviewRequest(reviewer_id="rev-2", decision="APPROVED", notes="Confirmed")
        submit_review(session, claim.id, req2)

        session.refresh(claim)
        assert claim.status == ClaimStatus.APPROVED


class TestGetClaimHistory:

    def test_history_empty_for_new_claim(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.DRAFT)
        resp = get_claim_history(session, claim.id)
        assert resp.current_status == ClaimStatus.DRAFT
        assert len(resp.history) == 0

    def test_history_includes_validations(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        _make_validation(session, claim.id, source=ValidationSource.deterministic)
        resp = get_claim_history(session, claim.id)
        assert len(resp.history) == 1
        assert resp.history[0].entry_type == "validation"
        assert resp.history[0].source == ValidationSource.deterministic

    def test_history_includes_reviews(self, session: Session):
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        _make_validation(session, claim.id, source=ValidationSource.deterministic)
        req = ReviewRequest(reviewer_id="rev-1", decision="APPROVED")
        submit_review(session, claim.id, req)

        resp = get_claim_history(session, claim.id)
        assert len(resp.history) == 2
        assert resp.history[0].entry_type == "validation"
        assert resp.history[1].entry_type == "review"
        assert resp.history[1].details["reviewer_id"] == "rev-1"

    def test_history_claim_not_found(self, session: Session):
        with pytest.raises(ClaimNotFoundError):
            get_claim_history(session, uuid4())

    def test_full_lifecycle_history(self, session: Session):
        """Test a complete claim lifecycle: create → validate → AI → review."""
        claim = _make_claim(session, status=ClaimStatus.READY_FOR_AI)
        _make_validation(session, claim.id, source=ValidationSource.deterministic,
                         result_json={"status": "PASS", "issues": []})
        _make_validation(
            session, claim.id, source=ValidationSource.llm,
            needs_human_review=True,
            result_json={"status": "needs_review", "issues": [], "rationale": "Low conf"},
            confidence=0.6,
        )
        req = ReviewRequest(reviewer_id="rev-1", decision="APPROVED", notes="Verified manually")
        submit_review(session, claim.id, req)

        resp = get_claim_history(session, claim.id)
        assert resp.current_status == ClaimStatus.APPROVED
        assert len(resp.history) == 3
        types = [e.entry_type for e in resp.history]
        assert types == ["validation", "validation", "review"]
