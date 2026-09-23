import os
from collections.abc import Iterator
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, delete, insert, update
from sqlalchemy.engine import Engine
from stock_platform.api.dependencies import (
    get_connection,
    get_human_actor,
    get_read_connection_factory,
    get_settings,
)
from stock_platform.api.main import app
from stock_platform.application.learning.promotion import HumanActor
from stock_platform.infrastructure.db.models.tables import (
    agent_run,
    alert_event,
    eval_metric,
    eval_run,
    regression_gate_result,
)
from stock_platform.settings import Settings

LOCKED_OPERATIONS = {
    ("GET", "/api/v1/events"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/providers/health"),
    ("GET", "/api/v1/market-data/quotes"),
    ("GET", "/api/v1/market-data/bars/{symbol}"),
    ("GET", "/api/v1/data-quality"),
    ("GET", "/api/v1/watchlist"),
    ("POST", "/api/v1/watchlist"),
    ("PATCH", "/api/v1/watchlist/{symbol}"),
    ("DELETE", "/api/v1/watchlist/{symbol}"),
    ("POST", "/api/v1/research-runs"),
    ("GET", "/api/v1/research-runs/latest"),
    ("GET", "/api/v1/research-runs/{run_id}"),
    ("GET", "/api/v1/research-runs/{run_id}/report"),
    ("GET", "/api/v1/stocks/{symbol}/research"),
    ("GET", "/api/v1/alerts"),
    ("POST", "/api/v1/alerts/{alert_id}/acknowledge"),
    ("GET", "/api/v1/portfolio"),
    ("POST", "/api/v1/portfolio/initialize"),
    ("POST", "/api/v1/portfolio/rebalance-runs"),
    ("GET", "/api/v1/portfolio/orders"),
    ("GET", "/api/v1/portfolio/fills"),
    ("GET", "/api/v1/weekly-reviews"),
    ("GET", "/api/v1/weekly-reviews/{review_id}"),
    ("POST", "/api/v1/weekly-reviews/{review_id}/lessons/{lesson_id}/approve"),
    ("POST", "/api/v1/weekly-reviews/{review_id}/lessons/{lesson_id}/reject"),
    ("POST", "/api/v1/policies/{policy_id}/activate"),
    ("POST", "/api/v1/policies/{policy_id}/rollback"),
    ("GET", "/api/v1/evals/runs"),
    ("GET", "/api/v1/evals/runs/{eval_run_id}"),
}


class JsonResponse(Protocol):
    def json(self) -> Any: ...


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
        connection.execute(
            update(agent_run)
            .where(agent_run.c.status.in_(("QUEUED", "RUNNING")))
            .values(status="CANCELLED", lease_expires_at=None, updated_at=datetime.now(UTC))
        )
        app.dependency_overrides[get_connection] = lambda: connection
        app.dependency_overrides[get_read_connection_factory] = lambda: (
            lambda: nullcontext(connection)
        )
        app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
            environment="test", _env_file=None
        )
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.clear()
            transaction.rollback()


def error(response: JsonResponse) -> dict[str, object]:
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


def test_live_read_endpoints_publish_closed_response_schemas() -> None:
    document = app.openapi()

    for path in (
        "/api/v1/providers/health",
        "/api/v1/market-data/quotes",
        "/api/v1/market-data/bars/{symbol}",
        "/api/v1/data-quality",
        "/api/v1/portfolio",
        "/api/v1/research-runs/{run_id}/report",
        "/api/v1/stocks/{symbol}/research",
        "/api/v1/alerts",
        "/api/v1/portfolio/orders",
        "/api/v1/portfolio/fills",
        "/api/v1/weekly-reviews",
        "/api/v1/evals/runs",
    ):
        schema = document["paths"][path]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert "$ref" in schema, path
        component = document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
        assert component.get("additionalProperties") is False, path


def test_provider_health_inventory_matches_implemented_adapters(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
        environment="test",
        alpha_vantage_api_key=SecretStr("configured-for-contract-test"),
        _env_file=None,
    )

    response = client.get("/api/v1/providers/health")

    assert response.status_code == 200
    assert set(response.json()["providers"]) == {"sec", "alpaca", "alpha_vantage"}
    assert response.json()["providers"]["alpha_vantage"] == {
        "configured": True,
        "mode": "read_only",
        "operator_action": None,
        "status": None,
        "coverage": None,
        "latest_job_state": None,
        "latest_quality_status": None,
    }


def test_provider_health_exposes_precise_operator_actions_for_unconfigured_research_sources(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/providers/health")

    assert response.status_code == 200
    providers = response.json()["providers"]
    assert providers["sec"]["operator_action"] == (
        "Configure SEC_USER_AGENT with a monitored contact identity."
    )
    assert providers["alpha_vantage"]["operator_action"] == (
        "Configure ALPHA_VANTAGE_API_KEY to ingest the earnings calendar."
    )


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


def test_latest_research_run_is_point_in_time_bounded(
    client: TestClient,
    api_engine: Engine,
) -> None:
    cutoff = datetime.now(UTC)
    visible_id = uuid4()
    late_id = uuid4()
    with api_engine.begin() as connection:
        connection.execute(
            insert(agent_run),
            [
                {
                    "id": visible_id,
                    "run_type": "RESEARCH",
                    "idempotency_key": f"latest-visible-{visible_id}",
                    "request_hash": "a" * 64,
                    "request_payload": {"symbol": "NVDA"},
                    "symbol": "NVDA",
                    "decision_time": cutoff - timedelta(minutes=2),
                    "data_cutoff": cutoff - timedelta(minutes=2),
                    "created_at": cutoff - timedelta(minutes=1),
                },
                {
                    "id": late_id,
                    "run_type": "RESEARCH",
                    "idempotency_key": f"latest-late-{late_id}",
                    "request_hash": "b" * 64,
                    "request_payload": {"symbol": "MSFT"},
                    "symbol": "MSFT",
                    "decision_time": cutoff - timedelta(seconds=30),
                    "data_cutoff": cutoff - timedelta(seconds=30),
                    "created_at": cutoff + timedelta(minutes=1),
                },
            ],
        )
    try:
        response = client.get(
            "/api/v1/research-runs/latest", params={"decision_time": cutoff.isoformat()}
        )

        assert response.status_code == 200
        assert response.json()["run_id"] == str(visible_id)
    finally:
        with api_engine.begin() as connection:
            connection.execute(agent_run.delete().where(agent_run.c.id.in_((visible_id, late_id))))


def test_research_run_lookup_is_point_in_time_bounded(
    client: TestClient,
    api_engine: Engine,
) -> None:
    cutoff = datetime.now(UTC)
    run_id = uuid4()
    with api_engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="RESEARCH",
                idempotency_key=f"lookup-late-{run_id}",
                request_hash="c" * 64,
                request_payload={"symbol": "NVDA"},
                symbol="NVDA",
                decision_time=cutoff - timedelta(minutes=1),
                data_cutoff=cutoff - timedelta(minutes=1),
                created_at=cutoff + timedelta(minutes=1),
            )
        )
    try:
        hidden = client.get(
            f"/api/v1/research-runs/{run_id}",
            params={"decision_time": cutoff.isoformat()},
        )
        visible = client.get(
            f"/api/v1/research-runs/{run_id}",
            params={"decision_time": (cutoff + timedelta(minutes=2)).isoformat()},
        )

        assert hidden.status_code == 404
        assert visible.status_code == 200
    finally:
        with api_engine.begin() as connection:
            connection.execute(agent_run.delete().where(agent_run.c.id == run_id))


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
    decision_time = datetime(2026, 8, 21, 21, tzinfo=UTC).isoformat().replace("+00:00", "Z")
    paths = (
        "/api/v1/health",
        "/api/v1/providers/health",
        "/api/v1/watchlist",
        f"/api/v1/stocks/NVDA/research?decision_time={decision_time}",
        f"/api/v1/alerts?decision_time={decision_time}",
        f"/api/v1/portfolio?decision_time={decision_time}",
        f"/api/v1/portfolio/orders?decision_time={decision_time}",
        f"/api/v1/portfolio/fills?decision_time={decision_time}",
        f"/api/v1/weekly-reviews?decision_time={decision_time}",
        f"/api/v1/evals/runs?decision_time={decision_time}",
    )

    for path in paths:
        assert client.get(path).status_code == 200, path


def test_alerts_are_point_in_time_bounded_and_cursor_paginated(
    client: TestClient,
    api_engine: Engine,
) -> None:
    cutoff = datetime(2026, 8, 21, 21, tzinfo=UTC)
    key_prefix = f"contract-alert-{uuid4()}"
    with api_engine.begin() as connection:
        connection.execute(
            insert(alert_event),
            [
                {
                    "alert_key": f"{key_prefix}-{index}",
                    "symbol": "NVDA",
                    "event_time": cutoff - timedelta(minutes=index),
                    "rule_id": "contract-rule",
                    "rule_version": "v1",
                    "severity": "HIGH",
                    "materiality": "0.8",
                    "created_at": cutoff - timedelta(minutes=index),
                }
                for index in range(1, 4)
            ]
            + [
                {
                    "alert_key": f"{key_prefix}-future",
                    "symbol": "NVDA",
                    "event_time": cutoff + timedelta(minutes=1),
                    "rule_id": "contract-rule",
                    "rule_version": "v1",
                    "severity": "HIGH",
                    "materiality": "0.8",
                    "created_at": cutoff + timedelta(minutes=1),
                }
            ],
        )

    try:
        first = client.get(
            "/api/v1/alerts",
            params={"decision_time": cutoff.isoformat(), "limit": 2},
        )
        assert first.status_code == 200
        assert len(first.json()["items"]) == 2
        assert first.json()["next_cursor"] is not None
        assert all(item["event_time"] <= cutoff.isoformat() for item in first.json()["items"])

        second = client.get(
            "/api/v1/alerts",
            params={
                "decision_time": cutoff.isoformat(),
                "limit": 2,
                "cursor": first.json()["next_cursor"],
            },
        )
        assert second.status_code == 200
        assert len(second.json()["items"]) == 1
        assert second.json()["next_cursor"] is None
    finally:
        with api_engine.begin() as connection:
            connection.execute(
                delete(alert_event).where(alert_event.c.alert_key.like(f"{key_prefix}%"))
            )


def test_evaluation_runs_are_point_in_time_bounded_detailed_and_paginated(
    client: TestClient,
    api_engine: Engine,
) -> None:
    cutoff = datetime.now(UTC)
    run_ids = [uuid4(), uuid4(), uuid4()]
    with api_engine.begin() as connection:
        for index, run_id in enumerate(run_ids):
            created_at = cutoff - timedelta(milliseconds=index + 1)
            connection.execute(
                insert(eval_run).values(
                    id=run_id,
                    status="PASSED",
                    passed=True,
                    mode="fixture",
                    dataset_version="eval-v0.2.0",
                    case_count=200,
                    data_cutoff=created_at,
                    model_version="fixture-deterministic-v1",
                    prompt_version="offline-eval-v0.2",
                    research_scoring_policy_version="research-scoring-v0.2",
                    risk_policy_version="risk-v0.2",
                    execution_policy_version="execution-v0.2",
                    confidence_policy_version="confidence-v0.2",
                    gate_policy_version="evaluation-gates-v0.2",
                    summary_hash=f"{index + 1:064x}",
                    created_at=created_at,
                )
            )
        connection.execute(
            insert(eval_metric).values(
                eval_run_id=run_ids[0],
                metric_name="directional_accuracy",
                metric_value="0.91",
                case_ids=["research-001"],
                case_hashes=["a" * 64],
                created_at=cutoff - timedelta(milliseconds=1),
            )
        )
        connection.execute(
            insert(regression_gate_result).values(
                eval_run_id=run_ids[0],
                metric_name="directional_accuracy",
                comparison="AT_LEAST",
                threshold="0.80",
                observed="0.91",
                passed=True,
                reason="meets threshold",
                created_at=cutoff - timedelta(milliseconds=1),
            )
        )
        connection.execute(
            insert(eval_metric).values(
                eval_run_id=run_ids[0],
                metric_name="future_metric",
                metric_value="1.00",
                case_ids=["future-case"],
                case_hashes=["f" * 64],
                created_at=cutoff + timedelta(minutes=1),
            )
        )
        connection.execute(
            insert(regression_gate_result).values(
                eval_run_id=run_ids[0],
                metric_name="future_metric",
                comparison="AT_LEAST",
                threshold="0.50",
                observed="1.00",
                passed=True,
                reason="future result",
                created_at=cutoff + timedelta(minutes=1),
            )
        )
        connection.execute(
            insert(eval_run).values(
                id=uuid4(),
                status="FAILED",
                passed=False,
                mode="fixture",
                dataset_version="future",
                case_count=1,
                data_cutoff=cutoff,
                model_version="future",
                prompt_version="future",
                research_scoring_policy_version="future",
                risk_policy_version="future",
                execution_policy_version="future",
                confidence_policy_version="future",
                gate_policy_version="future",
                summary_hash="f" * 64,
                created_at=cutoff + timedelta(minutes=1),
            )
        )

    first = client.get(
        "/api/v1/evals/runs",
        params={"decision_time": cutoff.isoformat(), "limit": 1},
    )
    assert first.status_code == 200
    assert [item["id"] for item in first.json()["items"]] == [str(run_ids[0])]
    assert first.json()["next_cursor"] is not None
    second = client.get(
        "/api/v1/evals/runs",
        params={
            "decision_time": cutoff.isoformat(),
            "limit": 1,
            "cursor": first.json()["next_cursor"],
        },
    )
    assert [item["id"] for item in second.json()["items"]] == [str(run_ids[1])]
    third = client.get(
        "/api/v1/evals/runs",
        params={
            "decision_time": cutoff.isoformat(),
            "limit": 1,
            "cursor": second.json()["next_cursor"],
        },
    )
    assert [item["id"] for item in third.json()["items"]] == [str(run_ids[2])]

    detail = client.get(
        f"/api/v1/evals/runs/{run_ids[0]}", params={"decision_time": cutoff.isoformat()}
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["run"]["model_version"] == "fixture-deterministic-v1"
    assert body["metrics"] == [
        {
            "metric_name": "directional_accuracy",
            "metric_value": "0.91",
            "case_ids": ["research-001"],
            "case_hashes": ["a" * 64],
        }
    ]
    assert body["gates"][0]["passed"] is True
    hidden = client.get(
        f"/api/v1/evals/runs/{run_ids[0]}",
        params={"decision_time": (cutoff - timedelta(milliseconds=2)).isoformat()},
    )
    assert hidden.status_code == 404


def test_operator_evaluation_view_isolates_incomplete_sentinels_without_deleting_audit_history(
    client: TestClient,
    api_engine: Engine,
) -> None:
    cutoff = datetime.now(UTC)
    sentinel_id = uuid4()
    complete_failed_id = uuid4()
    with api_engine.begin() as connection:
        for run_id, dataset, created_at in (
            (sentinel_id, "future", cutoff - timedelta(milliseconds=1)),
            (complete_failed_id, "eval-v0.2.0", cutoff - timedelta(milliseconds=2)),
        ):
            connection.execute(
                insert(eval_run).values(
                    id=run_id,
                    status="FAILED",
                    passed=False,
                    mode="fixture",
                    dataset_version=dataset,
                    case_count=1,
                    data_cutoff=created_at,
                    model_version="fixture-deterministic-v1",
                    prompt_version="offline-eval-v0.2",
                    research_scoring_policy_version="research-scoring-v0.2",
                    risk_policy_version="risk-v0.2",
                    execution_policy_version="execution-v0.2",
                    confidence_policy_version="confidence-v0.2",
                    gate_policy_version="evaluation-gates-v0.2",
                    summary_hash=run_id.hex.ljust(64, "0"),
                    created_at=created_at,
                )
            )
        connection.execute(
            insert(eval_metric).values(
                eval_run_id=complete_failed_id,
                metric_name="directional_accuracy",
                metric_value="0.40",
                case_ids=["case-1"],
                case_hashes=["a" * 64],
                created_at=cutoff - timedelta(milliseconds=2),
            )
        )
        connection.execute(
            insert(regression_gate_result).values(
                eval_run_id=complete_failed_id,
                metric_name="directional_accuracy",
                comparison="AT_LEAST",
                threshold="0.80",
                observed="0.40",
                passed=False,
                reason="below threshold",
                created_at=cutoff - timedelta(milliseconds=2),
            )
        )
    audit = client.get(
        "/api/v1/evals/runs",
        params={
            "decision_time": cutoff.isoformat(),
            "limit": 100,
            "audience": "all",
        },
    )
    operator = client.get(
        "/api/v1/evals/runs",
        params={
            "decision_time": cutoff.isoformat(),
            "limit": 100,
            "audience": "operator",
        },
    )

    assert audit.status_code == 200
    assert {str(sentinel_id), str(complete_failed_id)} <= {
        item["id"] for item in audit.json()["items"]
    }
    assert operator.status_code == 200
    operator_ids = {item["id"] for item in operator.json()["items"]}
    assert str(complete_failed_id) in operator_ids
    assert str(sentinel_id) not in operator_ids


def test_missing_resources_and_actions_use_the_error_envelope(client: TestClient) -> None:
    missing = uuid4()
    action = {"rationale": "contract test", "expected_revision": 0}
    app.dependency_overrides[get_human_actor] = lambda: HumanActor(
        id="reviewer", authenticated=True
    )
    requests = (
        client.get(
            f"/api/v1/research-runs/{missing}",
            params={"decision_time": datetime.now(UTC).isoformat()},
        ),
        client.get(
            f"/api/v1/research-runs/{missing}/report",
            params={"decision_time": datetime.now(UTC).isoformat()},
        ),
        client.get(
            f"/api/v1/evals/runs/{missing}",
            params={"decision_time": datetime.now(UTC).isoformat()},
        ),
        client.get(
            f"/api/v1/weekly-reviews/{missing}",
            params={"decision_time": datetime.now(UTC).isoformat()},
        ),
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
    assert set(created.json()) == {
        "symbol",
        "daily_research",
        "intraday_monitoring",
        "thresholds",
        "updated_at",
        "created_at",
    }
    assert patched.status_code == 200
    assert patched.json()["daily_research"] is False
    nvda = next(item for item in listed.json() if item["symbol"] == "NVDA")
    assert nvda["thresholds"] == {"return_5m": "0.03"}
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
