"""
Tests for the hallucination detection and escalation layer.

Verifies:
- Fabricated regulatory references are flagged
- Invented claim fields are caught
- Approval-without-evidence is detected
- Confidence/rationale mismatches are flagged
- Hallucination risk triggers escalation
- Clean results pass through untouched
"""
import json
import pytest
from pathlib import Path

from app.models.ai_validation_models import AIValidationResult, AIValidationIssue
from app.services.hallucination_detector import (
    check_for_hallucinations,
    apply_hallucination_escalation,
    HallucinationCheckResult,
    KNOWN_CLAIM_FIELDS,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"


def _load_eval(name: str) -> dict:
    with open(EVAL_DIR / name) as f:
        data = json.load(f)
    data.pop("_meta", None)
    return data


def _clean_claim_data() -> dict:
    return _load_eval("clean_claim.json")


def _empty_claim_data() -> dict:
    return _load_eval("missing_required_fields.json")


# ── Unsupported reference detection ──────────────────────────────────


class TestUnsupportedReferences:

    def test_fabricated_section_reference(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.95,
            needs_human_review=False,
            rationale="Approved per Section 42B of Medicare guidelines.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        assert check.hallucination_risk_detected
        assert any("unsupported_reference" in f for f in check.flags)

    def test_fabricated_ncd_reference(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.95,
            needs_human_review=False,
            rationale="Verified against NCD-999.99 coverage determination.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        assert check.hallucination_risk_detected

    def test_fabricated_cfr_reference(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.92,
            needs_human_review=False,
            rationale="Compliant with CFR 422.100 regulation.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        assert check.hallucination_risk_detected

    def test_fabricated_federal_act_reference(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.93,
            needs_human_review=False,
            rationale="Covered under the Federal Extended Benefits Act.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        assert check.hallucination_risk_detected

    def test_clean_rationale_no_flag(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.95,
            needs_human_review=False,
            rationale="All data present and consistent. Coverage active.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        assert not check.hallucination_risk_detected


# ── Invented field detection ─────────────────────────────────────────


class TestInventedFields:

    def test_references_known_field_no_flag(self):
        result = AIValidationResult(
            status="needs_review",
            issues=[
                AIValidationIssue(
                    type="missing_field", field="coverage.policy_id",
                    severity="medium", explanation="Missing",
                ),
            ],
            confidence=0.6, needs_human_review=True, rationale="Issue found.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        invented = [f for f in check.flags if "invented_field" in f]
        assert len(invented) == 0

    def test_references_unknown_field_flagged(self):
        result = AIValidationResult(
            status="needs_review",
            issues=[
                AIValidationIssue(
                    type="inconsistency", field="patient.ssn",
                    severity="high", explanation="SSN mismatch",
                ),
            ],
            confidence=0.6, needs_human_review=True, rationale="Check SSN.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        assert check.hallucination_risk_detected
        assert any("invented_field" in f for f in check.flags)

    def test_multiple_invented_fields(self):
        result = AIValidationResult(
            status="needs_review",
            issues=[
                AIValidationIssue(
                    type="missing_field", field="diagnosis.code",
                    severity="medium", explanation="x",
                ),
                AIValidationIssue(
                    type="inconsistency", field="provider.npi",
                    severity="low", explanation="y",
                ),
            ],
            confidence=0.5, needs_human_review=True, rationale="Problems.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        invented = [f for f in check.flags if "invented_field" in f]
        assert len(invented) == 2


# ── Approval without evidence ────────────────────────────────────────


class TestApprovalWithoutEvidence:

    def test_approve_empty_policy_flagged(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.95,
            needs_human_review=False, rationale="Looks good.",
        )
        check = check_for_hallucinations(result, _empty_claim_data())
        assert check.hallucination_risk_detected
        assert any("approval_without_evidence" in f for f in check.flags)

    def test_approve_valid_claim_no_flag(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.95,
            needs_human_review=False, rationale="Looks good.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        evidence_flags = [f for f in check.flags if "approval_without_evidence" in f]
        assert len(evidence_flags) == 0

    def test_low_confidence_approval_not_flagged(self):
        """approval_without_evidence only fires on high confidence (>=0.8)."""
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.6,
            needs_human_review=True, rationale="Maybe.",
        )
        check = check_for_hallucinations(result, _empty_claim_data())
        evidence_flags = [f for f in check.flags if "approval_without_evidence" in f]
        assert len(evidence_flags) == 0


# ── Confidence / rationale mismatch ──────────────────────────────────


class TestConfidenceRationaleMismatch:

    def test_high_confidence_with_hedging_flagged(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.96,
            needs_human_review=False,
            rationale="We are unsure about the coverage dates but approve.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        assert any("confidence_rationale_mismatch" in f for f in check.flags)

    def test_high_confidence_without_hedging_no_flag(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.96,
            needs_human_review=False,
            rationale="All data verified. Dates consistent.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        mismatch = [f for f in check.flags if "confidence_rationale_mismatch" in f]
        assert len(mismatch) == 0

    def test_low_confidence_with_hedging_no_flag(self):
        """Below 0.9 confidence, hedging is expected and not flagged."""
        result = AIValidationResult(
            status="needs_review", issues=[], confidence=0.5,
            needs_human_review=True,
            rationale="Uncertain about the billing codes.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        mismatch = [f for f in check.flags if "confidence_rationale_mismatch" in f]
        assert len(mismatch) == 0


# ── Escalation behavior ─────────────────────────────────────────────


class TestHallucinationEscalation:

    def test_flagged_result_escalated(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.95,
            needs_human_review=False,
            rationale="Approved per Section 42B.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        assert check.hallucination_risk_detected
        result = apply_hallucination_escalation(result, check)
        assert result.needs_human_review is True
        assert result.status == "needs_review"
        assert "HALLUCINATION GUARDRAIL" in result.rationale

    def test_clean_result_not_modified(self):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.95,
            needs_human_review=False,
            rationale="All clear.",
        )
        check = check_for_hallucinations(result, _clean_claim_data())
        assert not check.hallucination_risk_detected
        original_status = result.status
        result = apply_hallucination_escalation(result, check)
        assert result.status == original_status
        assert result.needs_human_review is False

    def test_hallucinated_fixture_triggers_escalation(self):
        with open(FIXTURES_DIR / "hallucinated_ai_output.json") as f:
            data = json.load(f)
        result = AIValidationResult(**data)
        check = check_for_hallucinations(result, _clean_claim_data())
        assert check.hallucination_risk_detected
        result = apply_hallucination_escalation(result, check)
        assert result.status == "needs_review"
        assert result.needs_human_review is True


# ── Known fields set is correct ──────────────────────────────────────


class TestKnownFields:

    def test_known_fields_match_claim_schema(self):
        expected = {
            "patient.id", "patient.date_of_birth",
            "coverage.policy_id", "coverage.start_date", "coverage.end_date",
            "care_event.service_date", "care_event.location",
            "billing.codes",
        }
        assert KNOWN_CLAIM_FIELDS == expected
