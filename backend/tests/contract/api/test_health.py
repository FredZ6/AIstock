from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from stock_platform.api.dependencies import get_settings
from stock_platform.api.main import app
from stock_platform.settings import Settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def fixture_settings() -> Iterator[None]:
    app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
        environment="fixture", _env_file=None
    )
    try:
        yield
    finally:
        app.dependency_overrides.clear()


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
