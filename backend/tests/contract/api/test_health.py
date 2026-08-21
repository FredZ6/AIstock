from uuid import UUID

from fastapi.testclient import TestClient
from stock_platform.api.main import app

client = TestClient(app)


def test_health_reports_fixture_mode_and_paper_only_boundary() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "fixture",
        "trading": "paper_only",
    }


def test_unknown_route_uses_locked_error_envelope() -> None:
    response = client.get("/api/v1/not-a-route")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "NOT_FOUND"
    assert payload["error"]["message"] == "Resource not found"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"] == {}
    UUID(payload["error"]["correlation_id"])
