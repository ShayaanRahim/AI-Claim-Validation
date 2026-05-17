"""Audit logging assertion tests."""
import json
import logging
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from app.models.ai_validation_models import AIValidationResult
from app.services.validation.guardrails import apply_guardrails, validate_against_deterministic
from app.services.hallucination_detector import check_for_hallucinations
from app.utils.hashing import hash_ai_validation_input, hash_ai_validation_output


def _create_and_validate(client: TestClient) -> str:
    today = date.today()
    data = {
        "patient": {"id": "p1", "date_of_birth": str(today - timedelta(days=365 * 30))},
        "coverage": {
            "policy_id": "POL-1",
            "start_date": str(today - timedelta(days=30)),
            "end_date": str(today + timedelta(days=30)),
        },
        "care_event": {"service_date": str(today), "location": "Clinic"},
        "billing": {"codes": ["99213"]},
    }
    resp = client.post("/claims", json=data)
    claim_id = resp.json()["claim_id"]
    client.post(f"/claims/{claim_id}/validate/deterministic")
    return claim_id


class TestAuditLogEvents:

    def test_claim_created_log(self, client: TestClient, caplog):
        today = date.today()
        data = {
            "patient": {"id": "p1", "date_of_birth": str(today - timedelta(days=365 * 30))},
            "coverage": {
                "policy_id": "POL-1",
                "start_date": str(today - timedelta(days=30)),
                "end_date": str(today + timedelta(days=30)),
            },
            "care_event": {"service_date": str(today), "location": "Clinic"},
            "billing": {"codes": ["99213"]},
        }
        with caplog.at_level(logging.INFO, logger="app.audit"):
            client.post("/claims", json=data)
        assert any("claim_created" in r.message for r in caplog.records)

    def test_validation_completed_has_required_fields(self, client: TestClient, caplog):
        claim_id = _create_and_validate(client)
        with caplog.at_level(logging.INFO, logger="app.audit"):
            caplog.clear()
            client.post(f"/claims/{claim_id}/validate/deterministic")
        completed = [
            json.loads(r.message) for r in caplog.records
            if "validation_completed" in r.message
        ]
        assert len(completed) >= 1
        log = completed[-1]
        assert log["claim_id"] == claim_id
        assert log["validation_type"] == "deterministic"
        assert "status" in log
        assert "request_id" in log
        assert "timestamp" in log


class TestGuardrailLogs:

    def test_low_confidence_guardrail_logged(self, caplog):
        result = AIValidationResult(
            status="needs_review", issues=[], confidence=0.5,
            needs_human_review=False, rationale="test",
        )
        with caplog.at_level(logging.INFO, logger="app.services.validation.guardrails"):
            apply_guardrails(result)
        assert any("low confidence" in r.message.lower() for r in caplog.records)

    def test_deterministic_override_logged(self, caplog):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.99,
            needs_human_review=False, rationale="test",
        )
        with caplog.at_level(logging.WARNING, logger="app.services.validation.guardrails"):
            validate_against_deterministic(result, {"status": "FAIL", "issues": []})
        assert any("overriding" in r.message.lower() for r in caplog.records)


class TestHallucinationLogs:

    def test_hallucination_risk_logged(self, caplog):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.95,
            needs_human_review=False,
            rationale="Approved per Section 42B.",
        )
        claim_data = {"coverage": {"policy_id": "P1"}, "billing": {"codes": ["99213"]}}
        with caplog.at_level(logging.WARNING, logger="app.services.hallucination_detector"):
            check_for_hallucinations(result, claim_data)
        assert any("hallucination" in r.message.lower() for r in caplog.records)


class TestHashingInAudit:

    def test_input_and_output_hashes_are_stable(self):
        claim = {"patient": {"id": "p1"}}
        det = {"status": "PASS", "issues": []}
        out = {"status": "approved", "confidence": 0.95, "issues": []}
        assert hash_ai_validation_input(claim, det) == hash_ai_validation_input(claim, det)
        assert hash_ai_validation_output(out) == hash_ai_validation_output(out)


class TestReviewAuditLogs:

    def test_review_submission_logged(self, client: TestClient, caplog):
        claim_id = _create_and_validate(client)
        with caplog.at_level(logging.INFO, logger="app.audit"):
            caplog.clear()
            client.post(f"/claims/{claim_id}/review", json={
                "reviewer_id": "rev-1",
                "decision": "APPROVED",
            })
        messages = [r.message for r in caplog.records]
        assert any("review_submitted" in m for m in messages)
        assert any("review_completed" in m for m in messages)
