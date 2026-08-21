import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from stock_platform.api.dependencies import get_connection, get_human_actor
from stock_platform.api.main import app
from stock_platform.application.learning.promotion import HumanActor

LOCKED_OPERATIONS = {
    ("GET", "/api/v1/events"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/providers/health"),
    ("GET", "/api/v1/watchlist"),
    ("POST", "/api/v1/watchlist"),
    ("PATCH", "/api/v1/watchlist/{symbol}"),
    ("DELETE", "/api/v1/watchlist/{symbol}"),
    ("POST", "/api/v1/research-runs"),
    ("GET", "/api/v1/research-runs/{run_id}"),
    ("GET", "/api/v1/research-runs/{run_id}/report"),
    ("GET", "/api/v1/stocks/{symbol}/research"),
    ("GET", "/api/v1/alerts"),
    ("POST", "/api/v1/alerts/{alert_id}/acknowledge"),
    ("GET", "/api/v1/portfolio"),
    ("POST", "/api/v1/portfolio/rebalance-runs"),
    ("GET", "/api/v1/portfolio/orders"),
    ("GET", "/api/v1/portfolio/fills"),
    ("GET", "/api/v1/weekly-reviews"),
    ("POST", "/api/v1/weekly-reviews/{review_id}/lessons/{lesson_id}/approve"),
    ("POST", "/api/v1/weekly-reviews/{review_id}/lessons/{lesson_id}/reject"),
    ("POST", "/api/v1/policies/{policy_id}/activate"),
    ("POST", "/api/v1/policies/{policy_id}/rollback"),
    ("GET", "/api/v1/evals/runs"),
    ("GET", "/api/v1/evals/runs/{eval_run_id}"),
}


@pytest.fixture(scope="session")
def api_engine() -> Iterator[Engine]:
    engine = create_engine(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform",
        )
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def client(api_engine: Engine) -> Iterator[TestClient]:
    with api_engine.connect() as connection:
        transaction = connection.begin()
        app.dependency_overrides[get_connection] = lambda: connection
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.clear()
            transaction.rollback()


def error(response: Response) -> dict[str, object]:
    payload: dict[str, Any] = response.json()
    UUID(payload["error"]["correlation_id"])
    return cast(dict[str, object], payload["error"])


def research_request(symbol: str = "NVDA") -> dict[str, str]:
    decision_time = datetime(2026, 8, 21, 21, tzinfo=UTC)
    return {
        "symbol": symbol,
        "decision_time": decision_time.isoformat(),
        "data_cutoff": decision_time.isoformat(),
    }


def test_openapi_contains_the_locked_surface_and_no_live_broker() -> None:
    document = app.openapi()
    actual = {
        (method.upper(), path)
        for path, operations in document["paths"].items()
        for method in operations
        if method != "parameters"
    }

    assert LOCKED_OPERATIONS <= actual
    assert all("broker" not in path.casefold() for _, path in actual)


@pytest.mark.parametrize(
    "payload",
    [
        research_request("../../etc"),
        {
            "symbol": "NVDA",
            "decision_time": "2026-08-21T21:00:00",
            "data_cutoff": "2026-08-21T21:00:00+00:00",
        },
    ],
)
def test_research_run_rejects_invalid_symbols_and_naive_datetimes(
    client: TestClient, payload: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/research-runs",
        headers={"Idempotency-Key": f"invalid-{uuid4()}"},
        json=payload,
    )

    assert response.status_code == 422
    assert error(response)["code"] == "INVALID_REQUEST"


def test_research_run_requires_an_idempotency_key(client: TestClient) -> None:
    response = client.post("/api/v1/research-runs", json=research_request())

    assert response.status_code == 422
    assert error(response)["code"] == "INVALID_REQUEST"


def test_idempotency_replays_equal_requests_and_rejects_key_reuse(client: TestClient) -> None:
    key = f"research-{uuid4()}"
    first = client.post(
        "/api/v1/research-runs",
        headers={"Idempotency-Key": key},
        json=research_request(),
    )
    replay = client.post(
        "/api/v1/research-runs",
        headers={"Idempotency-Key": key},
        json=research_request(),
    )
    conflict = client.post(
        "/api/v1/research-runs",
        headers={"Idempotency-Key": key},
        json=research_request("MSFT"),
    )

    assert first.status_code == replay.status_code == 202
    assert first.json() == replay.json()
    assert first.headers["Idempotency-Replayed"] == "false"
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert conflict.status_code == 409
    assert error(conflict)["code"] == "IDEMPOTENCY_CONFLICT"


def test_admission_limit_is_durable_and_cancellation_releases_capacity(
    client: TestClient,
) -> None:
    first = client.post(
        "/api/v1/research-runs",
        headers={"Idempotency-Key": f"admission-a-{uuid4()}"},
        json=research_request("NVDA"),
    )
    second = client.post(
        "/api/v1/research-runs",
        headers={"Idempotency-Key": f"admission-b-{uuid4()}"},
        json=research_request("MSFT"),
    )
    rejected = client.post(
        "/api/v1/research-runs",
        headers={"Idempotency-Key": f"admission-c-{uuid4()}"},
        json=research_request("AAPL"),
    )

    assert first.status_code == second.status_code == 202
    assert rejected.status_code == 429
    assert error(rejected)["code"] == "TASK_ADMISSION_LIMIT"

    cancelled = client.post(f"/api/v1/research-runs/{first.json()['run_id']}/cancel")
    cancelled_events = client.get(f"/api/v1/events?run_id={first.json()['run_id']}")
    admitted = client.post(
        "/api/v1/research-runs",
        headers={"Idempotency-Key": f"admission-d-{uuid4()}"},
        json=research_request("AAPL"),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert "event: run.cancelled" in cancelled_events.text
    assert admitted.status_code == 202


def test_locked_read_views_are_callable(client: TestClient) -> None:
    paths = (
        "/api/v1/health",
        "/api/v1/providers/health",
        "/api/v1/watchlist",
        "/api/v1/stocks/NVDA/research",
        "/api/v1/alerts",
        "/api/v1/portfolio",
        "/api/v1/portfolio/orders",
        "/api/v1/portfolio/fills",
        "/api/v1/weekly-reviews",
        "/api/v1/evals/runs",
    )

    for path in paths:
        assert client.get(path).status_code == 200, path


def test_missing_resources_and_actions_use_the_error_envelope(client: TestClient) -> None:
    missing = uuid4()
    action = {"rationale": "contract test", "expected_revision": 0}
    app.dependency_overrides[get_human_actor] = lambda: HumanActor(
        id="reviewer", authenticated=True
    )
    requests = (
        client.get(f"/api/v1/research-runs/{missing}"),
        client.get(f"/api/v1/research-runs/{missing}/report"),
        client.get(f"/api/v1/evals/runs/{missing}"),
        client.post(f"/api/v1/alerts/{missing}/acknowledge", json=action),
        client.post(f"/api/v1/weekly-reviews/{missing}/lessons/{uuid4()}/approve", json=action),
        client.post(f"/api/v1/weekly-reviews/{missing}/lessons/{uuid4()}/reject", json=action),
        client.post(f"/api/v1/policies/{missing}/activate", json=action),
        client.post(f"/api/v1/policies/{missing}/rollback", json=action),
    )

    for response in requests:
        assert response.status_code == 404
        assert error(response)["code"] == "NOT_FOUND"


def test_mutating_review_actions_reject_self_asserted_identity(client: TestClient) -> None:
    missing = uuid4()
    action = {"actor_id": "self-asserted", "rationale": "approve", "expected_revision": 0}

    for path in (
        f"/api/v1/alerts/{missing}/acknowledge",
        f"/api/v1/weekly-reviews/{missing}/lessons/{uuid4()}/approve",
        f"/api/v1/policies/{missing}/activate",
    ):
        response = client.post(path, json=action)
        assert response.status_code == 403
        assert error(response)["code"] == "FORBIDDEN"


def test_watchlist_crud_normalizes_and_persists_symbol(client: TestClient) -> None:
    created = client.post("/api/v1/watchlist", json={"symbol": "nvda"})
    patched = client.patch(
        "/api/v1/watchlist/NVDA",
        json={"daily_research": False, "thresholds": {"return_5m": "0.03"}},
    )
    listed = client.get("/api/v1/watchlist")
    deleted = client.delete("/api/v1/watchlist/NVDA")

    assert created.status_code == 201
    assert created.json()["symbol"] == "NVDA"
    assert patched.status_code == 200
    assert patched.json()["daily_research"] is False
    assert listed.json()[0]["thresholds"] == {"return_5m": "0.03"}
    assert deleted.status_code == 204


def test_portfolio_run_uses_the_shared_durable_idempotency_path(client: TestClient) -> None:
    key = f"portfolio-{uuid4()}"
    decision_time = datetime(2026, 8, 21, 21, tzinfo=UTC).isoformat()
    request = {"decision_time": decision_time, "data_cutoff": decision_time}

    first = client.post(
        "/api/v1/portfolio/rebalance-runs",
        headers={"Idempotency-Key": key},
        json=request,
    )
    replay = client.post(
        "/api/v1/portfolio/rebalance-runs",
        headers={"Idempotency-Key": key},
        json=request,
    )

    assert first.status_code == replay.status_code == 202
    assert first.json() == replay.json()
    assert replay.headers["Idempotency-Replayed"] == "true"
