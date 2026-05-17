"""
Tests for confidence threshold and escalation behavior.

Verifies:
- Low confidence forces human review
- Auto-approve threshold works
- Boundary conditions (exactly at threshold)
- Deterministic failures override AI confidence
- Missing/conflicting outputs escalate
"""
import pytest
from app.models.ai_validation_models import AIValidationResult, AIValidationIssue
from app.services.validation.guardrails import (
    apply_guardrails,
    validate_against_deterministic,
    CONFIDENCE_THRESHOLD,
    AUTO_APPROVE_THRESHOLD,
)


def _make_result(status="approved", confidence=0.95, needs_human_review=False, issues=None):
    return AIValidationResult(
        status=status,
        issues=issues or [],
        confidence=confidence,
        needs_human_review=needs_human_review,
        rationale="Test rationale.",
    )


# ── Threshold value tests ────────────────────────────────────────────


class TestThresholdValues:

    def test_confidence_threshold_is_075(self):
        assert CONFIDENCE_THRESHOLD == 0.75

    def test_auto_approve_threshold_is_095(self):
        assert AUTO_APPROVE_THRESHOLD == 0.95


# ── Low confidence escalation ────────────────────────────────────────


class TestLowConfidenceEscalation:

    def test_below_threshold_forces_review(self):
        result = _make_result(status="needs_review", confidence=0.5)
        result = apply_guardrails(result)
        assert result.needs_human_review is True

    def test_exactly_at_threshold_no_escalation(self):
        result = _make_result(status="needs_review", confidence=0.75)
        result = apply_guardrails(result)
        assert result.needs_human_review is False

    def test_just_below_threshold_escalates(self):
        result = _make_result(status="needs_review", confidence=0.749)
        result = apply_guardrails(result)
        assert result.needs_human_review is True

    def test_zero_confidence_escalates(self):
        result = _make_result(status="unknown", confidence=0.0)
        result = apply_guardrails(result)
        assert result.needs_human_review is True

    def test_confidence_one_no_escalation(self):
        result = _make_result(status="approved", confidence=1.0)
        result = apply_guardrails(result)
        assert result.status == "approved"


# ── Approved + low confidence downgrade ──────────────────────────────


class TestApprovedLowConfidenceDowngrade:

    def test_approved_below_threshold_downgraded(self):
        result = _make_result(status="approved", confidence=0.65)
        result = apply_guardrails(result)
        assert result.status == "needs_review"
        assert result.needs_human_review is True
        assert "GUARDRAIL APPLIED" in result.rationale

    def test_approved_above_threshold_not_downgraded(self):
        result = _make_result(status="approved", confidence=0.80)
        result = apply_guardrails(result)
        assert result.status == "approved"

    def test_approved_exactly_at_threshold_not_downgraded(self):
        result = _make_result(status="approved", confidence=0.75)
        result = apply_guardrails(result)
        assert result.status == "approved"


# ── Auto-approve threshold ───────────────────────────────────────────


class TestAutoApproveThreshold:

    def test_approved_below_auto_approve_forces_review(self):
        result = _make_result(status="approved", confidence=0.90)
        result = apply_guardrails(result)
        assert result.status == "approved"
        assert result.needs_human_review is True

    def test_approved_at_auto_approve_no_review(self):
        result = _make_result(status="approved", confidence=0.95)
        result = apply_guardrails(result)
        assert result.status == "approved"
        assert result.needs_human_review is False

    def test_approved_above_auto_approve_no_review(self):
        result = _make_result(status="approved", confidence=0.99)
        result = apply_guardrails(result)
        assert result.status == "approved"
        assert result.needs_human_review is False

    def test_approved_just_below_auto_approve_forces_review(self):
        result = _make_result(status="approved", confidence=0.949)
        result = apply_guardrails(result)
        assert result.needs_human_review is True


# ── Deterministic override ───────────────────────────────────────────


class TestDeterministicOverride:

    def test_deterministic_fail_overrides_high_confidence_approval(self):
        result = _make_result(status="approved", confidence=0.99)
        det = {"status": "FAIL", "issues": [{"code": "MISSING_POLICY_ID"}]}
        result = validate_against_deterministic(result, det)
        assert result.status == "needs_review"
        assert result.needs_human_review is True

    def test_deterministic_pass_preserves_approval(self):
        result = _make_result(status="approved", confidence=0.99)
        det = {"status": "PASS", "issues": []}
        result = validate_against_deterministic(result, det)
        assert result.status == "approved"

    def test_deterministic_fail_does_not_override_rejection(self):
        result = _make_result(status="rejected", confidence=0.99)
        det = {"status": "FAIL", "issues": [{"code": "X"}]}
        result = validate_against_deterministic(result, det)
        assert result.status == "rejected"


# ── Status-driven escalation ─────────────────────────────────────────


class TestStatusEscalation:

    def test_unknown_status_always_escalates(self):
        result = _make_result(status="unknown", confidence=0.99)
        result = apply_guardrails(result)
        assert result.needs_human_review is True

    def test_rejected_status_always_escalates(self):
        result = _make_result(status="rejected", confidence=0.99)
        result = apply_guardrails(result)
        assert result.needs_human_review is True

    def test_high_severity_issue_escalates(self):
        result = _make_result(
            status="needs_review",
            confidence=0.99,
            issues=[
                AIValidationIssue(
                    type="coverage_risk", field="coverage.end_date",
                    severity="high", explanation="Critical gap.",
                ),
            ],
        )
        result = apply_guardrails(result)
        assert result.needs_human_review is True

    def test_low_severity_issue_no_escalation(self):
        result = _make_result(
            status="approved",
            confidence=0.99,
            issues=[
                AIValidationIssue(
                    type="coverage_risk", field="care_event.location",
                    severity="low", explanation="Minor.",
                ),
            ],
        )
        result = apply_guardrails(result)
        assert result.needs_human_review is False
