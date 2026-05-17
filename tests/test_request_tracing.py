"""Tests for request correlation ID middleware."""
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.request_context import REQUEST_ID_HEADER


def test_request_id_auto_generated():
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers
    assert len(response.headers[REQUEST_ID_HEADER]) > 0


def test_request_id_preserved_when_supplied():
    client = TestClient(app)
    custom_id = "test-correlation-id-12345"
    response = client.get(
        "/health/live",
        headers={REQUEST_ID_HEADER: custom_id},
    )
    assert response.headers[REQUEST_ID_HEADER] == custom_id


def test_request_id_in_error_response(client):
    custom_id = "error-trace-id"
    response = client.get(
        "/claims/00000000-0000-0000-0000-000000000000",
        headers={REQUEST_ID_HEADER: custom_id},
    )
    assert response.status_code == 404
    body = response.json()
    assert body.get("request_id") == custom_id
