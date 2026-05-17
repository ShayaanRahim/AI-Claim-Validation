"""Authentication and authorization tests."""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from app.main import app
from app.db.session import get_session
from app.core.config import settings


@pytest.fixture
def auth_client(session: Session, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_DISABLED", False)

    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
    monkeypatch.setattr(settings, "AUTH_DISABLED", True)


def _claim_payload():
    today = date.today()
    return {
        "patient": {"id": "p1", "date_of_birth": str(today - timedelta(days=365 * 30))},
        "coverage": {
            "policy_id": "POL-1",
            "start_date": str(today - timedelta(days=30)),
            "end_date": str(today + timedelta(days=30)),
        },
        "care_event": {"service_date": str(today), "location": "Clinic"},
        "billing": {"codes": ["99213"]},
    }


class TestAuthentication:

    def test_missing_api_key_rejected(self, auth_client: TestClient):
        response = auth_client.post("/claims", json=_claim_payload())
        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"

    def test_invalid_api_key_rejected(self, auth_client: TestClient):
        response = auth_client.post(
            "/claims",
            json=_claim_payload(),
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401


class TestAuthorization:

    def test_system_can_create_claim(self, auth_client: TestClient):
        response = auth_client.post(
            "/claims",
            json=_claim_payload(),
            headers={"X-API-Key": settings.SYSTEM_API_KEY},
        )
        assert response.status_code == 201

    def test_reviewer_cannot_create_claim(self, auth_client: TestClient):
        response = auth_client.post(
            "/claims",
            json=_claim_payload(),
            headers={"X-API-Key": settings.REVIEWER_API_KEY},
        )
        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"

    def test_system_cannot_access_review_queue(self, auth_client: TestClient):
        response = auth_client.get(
            "/review/queue",
            headers={"X-API-Key": settings.SYSTEM_API_KEY},
        )
        assert response.status_code == 403

    def test_reviewer_can_access_review_queue(self, auth_client: TestClient):
        response = auth_client.get(
            "/review/queue",
            headers={"X-API-Key": settings.REVIEWER_API_KEY},
        )
        assert response.status_code == 200

    def test_system_cannot_submit_review(self, auth_client: TestClient, session: Session):
        create = auth_client.post(
            "/claims",
            json=_claim_payload(),
            headers={"X-API-Key": settings.SYSTEM_API_KEY},
        )
        claim_id = create.json()["claim_id"]
        auth_client.post(
            f"/claims/{claim_id}/validate/deterministic",
            headers={"X-API-Key": settings.SYSTEM_API_KEY},
        )
        response = auth_client.post(
            f"/claims/{claim_id}/review",
            json={"reviewer_id": "rev-1", "decision": "APPROVED"},
            headers={"X-API-Key": settings.SYSTEM_API_KEY},
        )
        assert response.status_code == 403

    def test_reviewer_can_submit_review(self, auth_client: TestClient):
        create = auth_client.post(
            "/claims",
            json=_claim_payload(),
            headers={"X-API-Key": settings.SYSTEM_API_KEY},
        )
        claim_id = create.json()["claim_id"]
        auth_client.post(
            f"/claims/{claim_id}/validate/deterministic",
            headers={"X-API-Key": settings.SYSTEM_API_KEY},
        )
        response = auth_client.post(
            f"/claims/{claim_id}/review",
            json={"reviewer_id": "rev-1", "decision": "APPROVED"},
            headers={"X-API-Key": settings.REVIEWER_API_KEY},
        )
        assert response.status_code == 201
