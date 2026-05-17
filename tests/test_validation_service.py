"""
Expanded deterministic validation tests using the golden evaluation dataset.

Verifies:
- Required field handling
- Logical consistency rules
- Format checks
- Repeatability/stability
- Edge cases from eval/ fixtures
"""
import json
import pytest
from pathlib import Path
from datetime import date, timedelta

from app.models.claim_models import ClaimInput, Patient, Coverage, CareEvent, Billing
from app.services.validation.engine import run_validation


EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"


def _load_fixture(name: str) -> dict:
    with open(EVAL_DIR / name) as f:
        data = json.load(f)
    data.pop("_meta", None)
    return data


def _claim_from_fixture(name: str) -> ClaimInput:
    return ClaimInput(**_load_fixture(name))


def _make_claim(**overrides) -> ClaimInput:
    today = date.today()
    defaults = dict(
        patient=Patient(id="p1", date_of_birth=today - timedelta(days=365 * 30)),
        coverage=Coverage(
            policy_id="POL-1",
            start_date=today - timedelta(days=60),
            end_date=today + timedelta(days=60),
        ),
        care_event=CareEvent(service_date=today, location="Clinic A"),
        billing=Billing(codes=["99213"]),
    )
    defaults.update(overrides)
    return ClaimInput(**defaults)


# ── Golden-set fixture tests ────────────────────────────────────────


class TestGoldenSetDeterministic:

    def test_clean_claim_passes(self):
        claim = _claim_from_fixture("clean_claim.json")
        result = run_validation(claim)
        assert result.status == "PASS"
        assert len(result.issues) == 0

    def test_missing_required_fields_fails(self):
        claim = _claim_from_fixture("missing_required_fields.json")
        result = run_validation(claim)
        assert result.status == "FAIL"
        codes = [i.code for i in result.issues]
        assert "MISSING_POLICY_ID" in codes
        assert "MISSING_BILLING_CODES" in codes

    def test_conflicting_coverage_fails(self):
        claim = _claim_from_fixture("conflicting_coverage.json")
        result = run_validation(claim)
        assert result.status == "FAIL"
        codes = [i.code for i in result.issues]
        assert "SERVICE_AFTER_COVERAGE" in codes

    def test_ambiguous_claim_passes_deterministic(self):
        claim = _claim_from_fixture("ambiguous_claim.json")
        result = run_validation(claim)
        assert result.status == "PASS"

    def test_malformed_claim_fails_multiple(self):
        claim = _claim_from_fixture("malformed_claim.json")
        result = run_validation(claim)
        assert result.status == "FAIL"
        codes = [i.code for i in result.issues]
        assert "INVALID_BILLING_CODE" in codes
        assert "SERVICE_BEFORE_BIRTH" in codes


# ── Deterministic stability ─────────────────────────────────────────


class TestDeterministicStability:

    def test_same_input_same_output_100_times(self):
        """Identical input must always produce identical output."""
        claim = _claim_from_fixture("clean_claim.json")
        baseline = run_validation(claim)
        for _ in range(100):
            result = run_validation(claim)
            assert result.status == baseline.status
            assert result.confidence == baseline.confidence
            assert len(result.issues) == len(baseline.issues)

    def test_failing_claim_stable(self):
        claim = _claim_from_fixture("missing_required_fields.json")
        baseline = run_validation(claim)
        for _ in range(50):
            result = run_validation(claim)
            assert result.status == baseline.status
            assert set(i.code for i in result.issues) == set(i.code for i in baseline.issues)


# ── Extended edge cases ─────────────────────────────────────────────


class TestEdgeCases:

    def test_whitespace_only_policy_id_fails(self):
        claim = _make_claim(
            coverage=Coverage(
                policy_id="   ",
                start_date=date.today() - timedelta(days=30),
                end_date=date.today() + timedelta(days=30),
            ),
        )
        result = run_validation(claim)
        assert result.status == "FAIL"
        assert any(i.code == "MISSING_POLICY_ID" for i in result.issues)

    def test_service_date_equals_coverage_start(self):
        today = date.today()
        claim = _make_claim(
            coverage=Coverage(policy_id="P1", start_date=today, end_date=today + timedelta(days=30)),
            care_event=CareEvent(service_date=today, location="Clinic"),
        )
        result = run_validation(claim)
        assert result.status == "PASS"

    def test_service_date_equals_coverage_end(self):
        today = date.today()
        claim = _make_claim(
            coverage=Coverage(policy_id="P1", start_date=today - timedelta(days=30), end_date=today),
            care_event=CareEvent(service_date=today, location="Clinic"),
        )
        result = run_validation(claim)
        assert result.status == "PASS"

    def test_service_one_day_after_coverage_fails(self):
        today = date.today()
        claim = _make_claim(
            coverage=Coverage(
                policy_id="P1",
                start_date=today - timedelta(days=60),
                end_date=today - timedelta(days=1),
            ),
            care_event=CareEvent(service_date=today, location="Clinic"),
        )
        result = run_validation(claim)
        assert result.status == "FAIL"
        assert any(i.code == "SERVICE_AFTER_COVERAGE" for i in result.issues)

    def test_service_one_day_before_coverage_fails(self):
        today = date.today()
        claim = _make_claim(
            coverage=Coverage(
                policy_id="P1",
                start_date=today + timedelta(days=1),
                end_date=today + timedelta(days=60),
            ),
            care_event=CareEvent(service_date=today, location="Clinic"),
        )
        result = run_validation(claim)
        assert result.status == "FAIL"
        assert any(i.code == "SERVICE_BEFORE_COVERAGE" for i in result.issues)

    def test_multiple_empty_billing_codes(self):
        claim = _make_claim(billing=Billing(codes=["", "  ", "99213", ""]))
        result = run_validation(claim)
        assert result.status == "FAIL"
        invalid = [i for i in result.issues if i.code == "INVALID_BILLING_CODE"]
        assert len(invalid) == 3

    def test_confidence_always_one(self):
        for fixture in ["clean_claim.json", "missing_required_fields.json", "malformed_claim.json"]:
            claim = _claim_from_fixture(fixture)
            result = run_validation(claim)
            assert result.confidence == 1.0

    def test_needs_human_review_always_false(self):
        for fixture in ["clean_claim.json", "missing_required_fields.json"]:
            claim = _claim_from_fixture(fixture)
            result = run_validation(claim)
            assert result.needs_human_review is False

    def test_errors_are_never_silently_swallowed(self):
        """A claim with 3 distinct errors must report all 3."""
        today = date.today()
        claim = _make_claim(
            coverage=Coverage(
                policy_id="",
                start_date=today + timedelta(days=10),
                end_date=today + timedelta(days=30),
            ),
            care_event=CareEvent(service_date=today, location="X"),
            billing=Billing(codes=[]),
        )
        result = run_validation(claim)
        assert result.status == "FAIL"
        assert len(result.issues) >= 3
