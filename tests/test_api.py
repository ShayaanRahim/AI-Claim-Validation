"""Tests for API endpoints"""
from datetime import date, timedelta
from fastapi.testclient import TestClient


def create_valid_claim_data():
    """Helper to create valid claim data"""
    today = date.today()
    return {
        "patient": {
            "id": "patient123",
            "date_of_birth": str(today - timedelta(days=365*30))
        },
        "coverage": {
            "policy_id": "POL123",
            "start_date": str(today - timedelta(days=30)),
            "end_date": str(today + timedelta(days=30))
        },
        "care_event": {
            "service_date": str(today),
            "location": "Hospital A"
        },
        "billing": {
            "codes": ["99213", "87070"]
        }
    }


def test_create_claim(client: TestClient):
    """Test POST /claims endpoint"""
    claim_data = create_valid_claim_data()
    
    response = client.post("/claims", json=claim_data)
    
    assert response.status_code == 201
    data = response.json()
    assert "claim_id" in data
    assert data["claim_id"] is not None


def test_get_claim(client: TestClient):
    """Test GET /claims/{claim_id} endpoint"""
    # First create a claim
    claim_data = create_valid_claim_data()
    create_response = client.post("/claims", json=claim_data)
    claim_id = create_response.json()["claim_id"]
    
    # Now get the claim
    response = client.get(f"/claims/{claim_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["claim_id"] == claim_id
    assert data["status"] == "DRAFT"
    assert "raw_claim" in data
    assert "validations" in data
    assert len(data["validations"]) == 0  # No validations yet


def test_get_nonexistent_claim(client: TestClient):
    """Test GET /claims/{claim_id} with nonexistent claim"""
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/claims/{fake_uuid}")
    
    assert response.status_code == 404


def test_validate_claim_deterministic(client: TestClient):
    """Test POST /claims/{claim_id}/validate/deterministic endpoint"""
    # Create a claim
    claim_data = create_valid_claim_data()
    create_response = client.post("/claims", json=claim_data)
    claim_id = create_response.json()["claim_id"]
    
    # Validate it
    response = client.post(f"/claims/{claim_id}/validate/deterministic")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PASS"
    assert data["confidence"] == 1.0
    assert data["needs_human_review"] is False
    assert "issues" in data
    assert len(data["issues"]) == 0


def test_validate_claim_with_errors(client: TestClient):
    """Test validation of claim with errors"""
    # Create a claim with missing policy_id
    claim_data = create_valid_claim_data()
    claim_data["coverage"]["policy_id"] = ""
    
    create_response = client.post("/claims", json=claim_data)
    claim_id = create_response.json()["claim_id"]
    
    # Validate it
    response = client.post(f"/claims/{claim_id}/validate/deterministic")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "FAIL"
    assert len(data["issues"]) >= 1
    
    # Check for specific issue
    codes = [issue["code"] for issue in data["issues"]]
    assert "MISSING_POLICY_ID" in codes


def test_validation_updates_claim_status(client: TestClient):
    """Test that validation updates claim status"""
    # Create and validate a valid claim
    claim_data = create_valid_claim_data()
    create_response = client.post("/claims", json=claim_data)
    claim_id = create_response.json()["claim_id"]
    
    # Validate
    client.post(f"/claims/{claim_id}/validate/deterministic")
    
    # Get claim and check status
    response = client.get(f"/claims/{claim_id}")
    data = response.json()
    assert data["status"] == "READY_FOR_AI"
    
    # Now test with failing validation
    claim_data_bad = create_valid_claim_data()
    claim_data_bad["coverage"]["policy_id"] = ""
    create_response = client.post("/claims", json=claim_data_bad)
    claim_id_bad = create_response.json()["claim_id"]
    
    client.post(f"/claims/{claim_id_bad}/validate/deterministic")
    
    response = client.get(f"/claims/{claim_id_bad}")
    data = response.json()
    assert data["status"] == "NEEDS_FIXES"


def test_multiple_validations_create_multiple_records(client: TestClient):
    """Test that running validation multiple times creates multiple DB records"""
    # Create a claim
    claim_data = create_valid_claim_data()
    create_response = client.post("/claims", json=claim_data)
    claim_id = create_response.json()["claim_id"]
    
    # Run validation twice
    client.post(f"/claims/{claim_id}/validate/deterministic")
    client.post(f"/claims/{claim_id}/validate/deterministic")
    
    # Get claim and check validations
    response = client.get(f"/claims/{claim_id}")
    data = response.json()
    
    assert len(data["validations"]) == 2
    # Both should have the same result but different timestamps
    assert data["validations"][0]["source"] == "deterministic"
    assert data["validations"][1]["source"] == "deterministic"
    # Timestamps should be ordered
    assert data["validations"][0]["created_at"] <= data["validations"][1]["created_at"]
