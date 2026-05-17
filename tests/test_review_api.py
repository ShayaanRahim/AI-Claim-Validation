"""Tests for review API endpoints."""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from app.main import app
from app.db.session import get_session
from app.db.models import Claim, Validation, ClaimStatus, ValidationSource


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


def _create_claim_via_api(client: TestClient) -> str:
    today = date.today()
    data = {
        "patient": {
            "id": "patient123",
            "date_of_birth": str(today - timedelta(days=365 * 30)),
        },
        "coverage": {
            "policy_id": "POL123",
            "start_date": str(today - timedelta(days=30)),
            "end_date": str(today + timedelta(days=30)),
        },
        "care_event": {
            "service_date": str(today),
            "location": "Hospital A",
        },
        "billing": {
            "codes": ["99213", "87070"],
        },
    }
    resp = client.post("/claims", json=data)
    return resp.json()["claim_id"]


def _validate_claim(client: TestClient, claim_id: str):
    client.post(f"/claims/{claim_id}/validate/deterministic")


class TestReviewQueue:

    def test_empty_queue(self, client: TestClient):
        resp = client.get("/review/queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_validated_claim_in_queue(self, client: TestClient):
        claim_id = _create_claim_via_api(client)
        _validate_claim(client, claim_id)
        resp = client.get("/review/queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["claim_id"] == claim_id

    def test_queue_pagination(self, client: TestClient):
        for _ in range(3):
            cid = _create_claim_via_api(client)
            _validate_claim(client, cid)
        resp = client.get("/review/queue?limit=2&offset=0")
        assert len(resp.json()["items"]) == 2
        assert resp.json()["total"] == 3


class TestCreateReview:

    def test_approve_claim(self, client: TestClient):
        claim_id = _create_claim_via_api(client)
        _validate_claim(client, claim_id)

        resp = client.post(f"/claims/{claim_id}/review", json={
            "reviewer_id": "rev-1",
            "decision": "APPROVED",
            "notes": "All good",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["decision"] == "APPROVED"
        assert data["claim_status_after"] == "APPROVED"

    def test_reject_claim(self, client: TestClient):
        claim_id = _create_claim_via_api(client)
        _validate_claim(client, claim_id)

        resp = client.post(f"/claims/{claim_id}/review", json={
            "reviewer_id": "rev-1",
            "decision": "REJECTED",
            "notes": "Missing info",
        })
        assert resp.status_code == 201
        assert resp.json()["claim_status_after"] == "REJECTED"

    def test_escalate_claim(self, client: TestClient):
        claim_id = _create_claim_via_api(client)
        _validate_claim(client, claim_id)

        resp = client.post(f"/claims/{claim_id}/review", json={
            "reviewer_id": "rev-1",
            "decision": "ESCALATED",
            "notes": "Need senior review",
        })
        assert resp.status_code == 201
        assert resp.json()["claim_status_after"] == "IN_REVIEW"

    def test_review_nonexistent_claim(self, client: TestClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.post(f"/claims/{fake_id}/review", json={
            "reviewer_id": "rev-1",
            "decision": "APPROVED",
        })
        assert resp.status_code == 404

    def test_review_finalized_claim_returns_409(self, client: TestClient):
        claim_id = _create_claim_via_api(client)
        _validate_claim(client, claim_id)

        client.post(f"/claims/{claim_id}/review", json={
            "reviewer_id": "rev-1",
            "decision": "APPROVED",
        })
        resp = client.post(f"/claims/{claim_id}/review", json={
            "reviewer_id": "rev-2",
            "decision": "REJECTED",
        })
        assert resp.status_code == 409

    def test_invalid_decision_returns_422(self, client: TestClient):
        claim_id = _create_claim_via_api(client)
        _validate_claim(client, claim_id)

        resp = client.post(f"/claims/{claim_id}/review", json={
            "reviewer_id": "rev-1",
            "decision": "MAYBE",
        })
        assert resp.status_code == 422

    def test_escalate_then_approve(self, client: TestClient):
        claim_id = _create_claim_via_api(client)
        _validate_claim(client, claim_id)

        client.post(f"/claims/{claim_id}/review", json={
            "reviewer_id": "rev-1",
            "decision": "ESCALATED",
        })
        resp = client.post(f"/claims/{claim_id}/review", json={
            "reviewer_id": "rev-2",
            "decision": "APPROVED",
            "notes": "Senior approved",
        })
        assert resp.status_code == 201
        assert resp.json()["claim_status_after"] == "APPROVED"


class TestClaimHistory:

    def test_history_for_new_claim(self, client: TestClient):
        claim_id = _create_claim_via_api(client)
        resp = client.get(f"/claims/{claim_id}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["claim_id"] == claim_id
        assert len(data["history"]) == 0

    def test_history_after_validation_and_review(self, client: TestClient):
        claim_id = _create_claim_via_api(client)
        _validate_claim(client, claim_id)
        client.post(f"/claims/{claim_id}/review", json={
            "reviewer_id": "rev-1",
            "decision": "APPROVED",
        })

        resp = client.get(f"/claims/{claim_id}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_status"] == "APPROVED"
        assert len(data["history"]) == 2
        assert data["history"][0]["entry_type"] == "validation"
        assert data["history"][1]["entry_type"] == "review"

    def test_history_nonexistent_claim(self, client: TestClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(f"/claims/{fake_id}/history")
        assert resp.status_code == 404
