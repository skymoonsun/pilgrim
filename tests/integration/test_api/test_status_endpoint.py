import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_status_endpoint():
    """Test GET /api/v1/status returns 200 and expected JSON."""
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert data["service"] == "pilgrim"


def test_status_response_model():
    """Test response model has required fields."""
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "service" in data
