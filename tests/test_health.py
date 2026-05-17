"""Tests for health endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from app.main import app
from app.db.session import get_session


@pytest.fixture(name="client")
def client_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_liveness_always_ok(client: TestClient):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_ok_with_db(client: TestClient):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_fails_on_db_error():
    def broken_session():
        raise ConnectionError("database unavailable")
        yield  # pragma: no cover

    app.dependency_overrides[get_session] = broken_session
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health/ready")
    app.dependency_overrides.clear()
    assert response.status_code == 500
