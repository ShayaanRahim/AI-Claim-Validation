"""
Strict schema enforcement tests for AI validation outputs.

Verifies that:
- Invalid AI output NEVER passes Pydantic validation silently
- Missing keys, wrong types, bad enums all raise
- Valid outputs parse correctly
- Regression fixtures remain compatible
"""
import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from app.models.ai_validation_models import AIValidationResult, AIValidationIssue


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


# ── Valid outputs parse correctly ────────────────────────────────────


class TestValidOutputsParse:

    def test_approved_fixture(self):
        data = _load_fixture("valid_ai_output_approved.json")
        result = AIValidationResult(**data)
        assert result.status == "approved"
        assert result.confidence == 0.95

    def test_needs_review_fixture(self):
        data = _load_fixture("valid_ai_output_needs_review.json")
        result = AIValidationResult(**data)
        assert result.status == "needs_review"
        assert len(result.issues) == 1

    def test_unknown_fixture(self):
        data = _load_fixture("valid_ai_output_unknown.json")
        result = AIValidationResult(**data)
        assert result.status == "unknown"
        assert result.needs_human_review is True

    def test_rejected_fixture(self):
        data = _load_fixture("valid_ai_output_rejected.json")
        result = AIValidationResult(**data)
        assert result.status == "rejected"
        assert result.issues[0].severity == "high"


# ── Invalid outputs are rejected ─────────────────────────────────────


class TestInvalidOutputsRejected:

    def test_missing_required_keys(self):
        data = _load_fixture("invalid_ai_output_missing_keys.json")
        with pytest.raises(ValidationError):
            AIValidationResult(**data)

    def test_wrong_data_types(self):
        data = _load_fixture("invalid_ai_output_wrong_types.json")
        with pytest.raises(ValidationError):
            AIValidationResult(**data)

    def test_invalid_enum_status(self):
        data = _load_fixture("invalid_ai_output_bad_enums.json")
        with pytest.raises(ValidationError):
            AIValidationResult(**data)

    def test_confidence_above_one(self):
        with pytest.raises(ValidationError):
            AIValidationResult(
                status="approved",
                issues=[],
                confidence=1.5,
                needs_human_review=False,
                rationale="test",
            )

    def test_confidence_below_zero(self):
        with pytest.raises(ValidationError):
            AIValidationResult(
                status="approved",
                issues=[],
                confidence=-0.1,
                needs_human_review=False,
                rationale="test",
            )

    def test_none_status_rejected(self):
        with pytest.raises(ValidationError):
            AIValidationResult(
                status=None,
                issues=[],
                confidence=0.5,
                needs_human_review=True,
                rationale="test",
            )

    def test_empty_string_status_rejected(self):
        with pytest.raises(ValidationError):
            AIValidationResult(
                status="",
                issues=[],
                confidence=0.5,
                needs_human_review=True,
                rationale="test",
            )

    def test_null_confidence_rejected(self):
        with pytest.raises(ValidationError):
            AIValidationResult(
                status="approved",
                issues=[],
                confidence=None,
                needs_human_review=False,
                rationale="test",
            )

    def test_invalid_issue_type_rejected(self):
        with pytest.raises(ValidationError):
            AIValidationIssue(
                type="fraud_detected",
                field="patient.id",
                severity="high",
                explanation="bad",
            )

    def test_invalid_issue_severity_rejected(self):
        with pytest.raises(ValidationError):
            AIValidationIssue(
                type="inconsistency",
                field="patient.id",
                severity="critical",
                explanation="bad",
            )


# ── Edge-case schema scenarios ───────────────────────────────────────


class TestSchemaEdgeCases:

    def test_empty_issues_list_accepted(self):
        result = AIValidationResult(
            status="approved",
            issues=[],
            confidence=0.95,
            needs_human_review=False,
            rationale="Clean.",
        )
        assert result.issues == []

    def test_confidence_exactly_zero_accepted(self):
        result = AIValidationResult(
            status="unknown",
            issues=[],
            confidence=0.0,
            needs_human_review=True,
            rationale="No data.",
        )
        assert result.confidence == 0.0

    def test_confidence_exactly_one_accepted(self):
        result = AIValidationResult(
            status="approved",
            issues=[],
            confidence=1.0,
            needs_human_review=False,
            rationale="Perfect.",
        )
        assert result.confidence == 1.0

    def test_extra_keys_in_raw_dict_ignored_by_pydantic(self):
        """Extra keys should not crash parsing (Pydantic ignores by default)."""
        data = _load_fixture("invalid_ai_output_extra_keys.json")
        result = AIValidationResult(**data)
        assert result.status == "approved"
        assert not hasattr(result, "internal_score")

    def test_round_trip_serialization(self):
        original = AIValidationResult(
            status="needs_review",
            issues=[
                AIValidationIssue(
                    type="missing_field",
                    field="coverage.policy_id",
                    severity="medium",
                    explanation="Missing",
                )
            ],
            confidence=0.65,
            needs_human_review=True,
            rationale="Needs attention.",
        )
        dumped = original.model_dump(mode="json")
        restored = AIValidationResult(**dumped)
        assert restored.status == original.status
        assert restored.confidence == original.confidence
        assert len(restored.issues) == len(original.issues)
