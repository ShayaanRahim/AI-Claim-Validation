"""Tests for review Pydantic models."""
import pytest
from pydantic import ValidationError
from app.models.review_models import ReviewRequest, ReviewResponse, ReviewQueueItem


class TestReviewRequest:

    def test_valid_approve_request(self):
        req = ReviewRequest(
            reviewer_id="reviewer-1",
            decision="APPROVED",
            notes="All looks good.",
        )
        assert req.decision == "APPROVED"
        assert req.override_rationale is None

    def test_valid_reject_request(self):
        req = ReviewRequest(
            reviewer_id="reviewer-1",
            decision="REJECTED",
            notes="Missing documentation.",
        )
        assert req.decision == "REJECTED"

    def test_valid_escalated_request(self):
        req = ReviewRequest(
            reviewer_id="reviewer-1",
            decision="ESCALATED",
            notes="Needs senior review.",
        )
        assert req.decision == "ESCALATED"

    def test_invalid_decision_rejected(self):
        with pytest.raises(ValidationError):
            ReviewRequest(
                reviewer_id="reviewer-1",
                decision="MAYBE",
            )

    def test_empty_reviewer_id_rejected(self):
        with pytest.raises(ValidationError):
            ReviewRequest(
                reviewer_id="",
                decision="APPROVED",
            )

    def test_override_rationale_accepted(self):
        req = ReviewRequest(
            reviewer_id="reviewer-1",
            decision="APPROVED",
            override_rationale="AI recommended rejection but documentation confirms coverage.",
        )
        assert req.override_rationale is not None

    def test_notes_optional(self):
        req = ReviewRequest(reviewer_id="rev-1", decision="APPROVED")
        assert req.notes is None


class TestReviewQueueItem:

    def test_minimal_queue_item(self):
        item = ReviewQueueItem(
            claim_id="abc-123",
            claim_status="READY_FOR_AI",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )
        assert item.ai_confidence is None
        assert item.issue_count == 0

    def test_full_queue_item(self):
        item = ReviewQueueItem(
            claim_id="abc-123",
            claim_status="IN_REVIEW",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T12:00:00",
            ai_confidence=0.72,
            ai_status="needs_review",
            ai_rationale="Timing issue",
            deterministic_status="PASS",
            issue_count=3,
        )
        assert item.ai_confidence == 0.72
        assert item.issue_count == 3
