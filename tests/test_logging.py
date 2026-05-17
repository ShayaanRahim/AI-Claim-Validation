"""
Audit logging assertion tests.

Verifies that critical structured logs are emitted with required metadata
for regulated-workflow observability.

Uses capfd / capsys to capture print-based JSON logs and logging.* calls
via Python's logging module.
"""
import json
import logging
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from app.main import app
from app.db.session import get_session
from app.models.ai_validation_models import AIValidationResult, AIValidationIssue
from app.services.validation.guardrails import apply_guardrails, validate_against_deterministic
from app.services.hallucination_detector import check_for_hallucinations


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


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


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


# ── Claim creation logging ───────────────────────────────────────────


class TestClaimCreationLogs:

    def test_create_claim_emits_event(self, client: TestClient, capsys):
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
        client.post("/claims", json=data)
        captured = capsys.readouterr()
        assert "claim_created" in captured.out


# ── Deterministic validation logging ─────────────────────────────────


class TestDeterministicValidationLogs:

    def test_validation_started_event(self, client: TestClient, capsys):
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
        captured = capsys.readouterr()
        assert "validation_started" in captured.out

    def test_validation_completed_event_has_required_fields(self, client: TestClient, capsys):
        claim_id = _create_and_validate(client)
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if "validation_completed" in l]
        assert len(lines) >= 1
        log = json.loads(lines[-1])
        assert log["event"] == "validation_completed"
        assert "claim_id" in log
        assert "validation_source" in log
        assert "status" in log
        assert "num_issues" in log


# ── Guardrail logging ────────────────────────────────────────────────


class TestGuardrailLogs:

    def test_low_confidence_guardrail_logged(self, caplog):
        result = AIValidationResult(
            status="needs_review", issues=[], confidence=0.5,
            needs_human_review=False, rationale="test",
        )
        with caplog.at_level(logging.INFO, logger="app.services.validation.guardrails"):
            apply_guardrails(result)
        assert any("low confidence" in r.message.lower() for r in caplog.records)

    def test_approved_low_confidence_guardrail_logged(self, caplog):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.5,
            needs_human_review=False, rationale="test",
        )
        with caplog.at_level(logging.WARNING, logger="app.services.validation.guardrails"):
            apply_guardrails(result)
        assert any("changing status" in r.message.lower() for r in caplog.records)

    def test_deterministic_override_logged(self, caplog):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.99,
            needs_human_review=False, rationale="test",
        )
        det = {"status": "FAIL", "issues": []}
        with caplog.at_level(logging.WARNING, logger="app.services.validation.guardrails"):
            validate_against_deterministic(result, det)
        assert any("overriding" in r.message.lower() for r in caplog.records)


# ── Hallucination logging ────────────────────────────────────────────


class TestHallucinationLogs:

    def test_hallucination_risk_logged(self, caplog):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.95,
            needs_human_review=False,
            rationale="Approved per Section 42B.",
        )
        claim_data = {"patient": {"id": "p1"}, "coverage": {"policy_id": "P1"}, "billing": {"codes": ["99213"]}}
        with caplog.at_level(logging.WARNING, logger="app.services.hallucination_detector"):
            check_for_hallucinations(result, claim_data)
        assert any("hallucination" in r.message.lower() for r in caplog.records)

    def test_clean_output_no_hallucination_log(self, caplog):
        result = AIValidationResult(
            status="approved", issues=[], confidence=0.95,
            needs_human_review=False,
            rationale="All data verified.",
        )
        claim_data = {"patient": {"id": "p1"}, "coverage": {"policy_id": "P1"}, "billing": {"codes": ["99213"]}}
        with caplog.at_level(logging.WARNING, logger="app.services.hallucination_detector"):
            check_for_hallucinations(result, claim_data)
        halluc_records = [r for r in caplog.records if "hallucination" in r.message.lower()]
        assert len(halluc_records) == 0


# ── Review workflow logging ──────────────────────────────────────────


class TestReviewLogs:

    def test_review_queue_request_logged(self, client: TestClient, capsys):
        client.get("/review/queue")
        captured = capsys.readouterr()
        assert "review_queue_requested" in captured.out

    def test_review_submission_logged(self, client: TestClient, capsys):
        claim_id = _create_and_validate(client)
        _ = capsys.readouterr()  # clear buffer
        client.post(f"/claims/{claim_id}/review", json={
            "reviewer_id": "rev-1",
            "decision": "APPROVED",
        })
        captured = capsys.readouterr()
        assert "review_submitted" in captured.out

    def test_history_request_logged(self, client: TestClient, capsys):
        claim_id = _create_and_validate(client)
        _ = capsys.readouterr()
        client.get(f"/claims/{claim_id}/history")
        captured = capsys.readouterr()
        assert "history_requested" in captured.out
