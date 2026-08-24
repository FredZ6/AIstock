from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, insert, select
from stock_platform.api.dependencies import get_settings
from stock_platform.api.main import app
from stock_platform.infrastructure.db.models.tables import agent_run, policy_control
from stock_platform.settings import Settings


def migrated_url(isolated_database_url: str) -> str:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    return isolated_database_url


def request(key: str) -> tuple[dict[str, str], dict[str, str]]:
    now = datetime(2026, 8, 21, 21, tzinfo=UTC).isoformat()
    return {"Idempotency-Key": key}, {
        "symbol": "NVDA",
        "decision_time": now,
        "data_cutoff": now,
    }


def post_after_barrier(
    barrier: Barrier, headers: dict[str, str], payload: dict[str, str]
) -> tuple[int, dict[str, object]]:
    barrier.wait()
    with TestClient(app) as client:
        response = client.post("/api/v1/research-runs", headers=headers, json=payload)
        return response.status_code, response.json()


def test_concurrent_admission_and_idempotency_are_serialized_in_postgres(
    isolated_database_url: str,
) -> None:
    database_url = migrated_url(isolated_database_url)
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", database_url=database_url, max_active_agent_runs=1
    )
    try:
        first = request(f"admission-{uuid4()}")
        second = request(f"admission-{uuid4()}")
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(
                pool.map(
                    lambda item: post_after_barrier(barrier, *item),
                    (first, second),
                )
            )
        assert sorted(status for status, _ in results) == [202, 429]

        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(agent_run.delete())

        same_request = request(f"idempotent-{uuid4()}")
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            replays = tuple(
                pool.map(
                    lambda item: post_after_barrier(barrier, *item),
                    (same_request, same_request),
                )
            )
        assert [status for status, _ in replays] == [202, 202]
        assert replays[0][1] == replays[1][1]
        with engine.connect() as connection:
            assert connection.execute(select(func.count()).select_from(agent_run)).scalar_one() == 1

        with engine.begin() as connection:
            connection.execute(agent_run.delete())
        now = datetime(2026, 8, 21, 21, tzinfo=UTC).isoformat()
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portfolio/rebalance-runs",
                headers={"Idempotency-Key": f"portfolio-pins-{uuid4()}"},
                json={"decision_time": now, "data_cutoff": now},
            )
        assert response.status_code == 202
        with engine.connect() as connection:
            pins = connection.execute(
                select(agent_run.c.prompt_version, agent_run.c.model_version)
            ).one()
        assert pins == ("portfolio-prompt-v1", "fixture-proposer-v1")

        with engine.begin() as connection:
            connection.execute(agent_run.delete())
            connection.execute(
                insert(policy_control).values(
                    policy_kind="RISK", active_version="risk-v2", revision=1
                )
            )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/research-runs",
                headers={"Idempotency-Key": f"active-policy-{uuid4()}"},
                json=request(f"active-policy-payload-{uuid4()}")[1],
            )
        assert response.status_code == 202
        with engine.connect() as connection:
            assert (
                connection.execute(select(agent_run.c.risk_policy_version)).scalar_one()
                == "risk-v2"
            )
        engine.dispose()
    finally:
        app.dependency_overrides.clear()


def test_paper_rest_admission_records_research_gap_and_rejects_portfolio_without_sip(
    isolated_database_url: str,
) -> None:
    database_url = migrated_url(isolated_database_url)
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="paper",
        database_url=database_url,
        max_active_agent_runs=10,
        alpaca_data_key="test-key",
        alpaca_data_secret="test-secret",
        alpaca_entitlement_coverage="IEX",
        alpaca_entitlement_version="operator-verified-v1",
    )
    try:
        headers, payload = request(f"paper-research-{uuid4()}")
        with TestClient(app) as client:
            research = client.post("/api/v1/research-runs", headers=headers, json=payload)
            portfolio = client.post(
                "/api/v1/portfolio/rebalance-runs",
                headers={"Idempotency-Key": f"paper-portfolio-{uuid4()}"},
                json={
                    "decision_time": payload["decision_time"],
                    "data_cutoff": payload["data_cutoff"],
                },
            )
        assert research.status_code == 202
        assert portfolio.status_code == 403
        assert portfolio.json()["error"]["code"] == "MARKET_DATA_NOT_ENTITLED"
        engine = create_engine(database_url)
        with engine.connect() as connection:
            stored = connection.execute(select(agent_run.c.request_payload)).scalar_one()
        assert stored["market_data_admission"]["outcome"] == "ALLOWED_WITH_GAP"
        assert stored["market_data_admission"]["gap_kind"] == "UNAVAILABLE"
        engine.dispose()
    finally:
        app.dependency_overrides.clear()
