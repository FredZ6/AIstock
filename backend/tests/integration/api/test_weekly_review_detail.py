from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select
from sqlalchemy.engine import Connection, Engine
from stock_platform.api.dependencies import get_connection, get_settings
from stock_platform.api.main import app
from stock_platform.infrastructure.db.models.tables import (
    agent_run,
    candidate_lesson,
    lesson_approval,
    replay_run,
    weekly_review_run,
)
from stock_platform.settings import Settings
from stock_platform.workers.research_tasks import execute_research_run
from stock_platform.workers.review_tasks import execute_weekly_review_run


def _client(database_url: str) -> tuple[TestClient, Engine]:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)

    def connection_override() -> Iterator[Connection]:
        with engine.begin() as connection:
            yield connection

    app.dependency_overrides[get_connection] = connection_override
    app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
        environment="test", _env_file=None
    )
    return TestClient(app), engine


def test_weekly_review_detail_exposes_normalized_learning_facts(
    isolated_database_url: str,
) -> None:
    client, engine = _client(isolated_database_url)
    research_id = uuid4()
    review_run_id = uuid4()
    research_time = datetime(2026, 8, 13, 21, tzinfo=UTC)
    review_time = datetime(2026, 8, 21, 21, tzinfo=UTC)
    try:
        with engine.begin() as connection:
            connection.execute(
                insert(agent_run),
                [
                    {
                        "id": research_id,
                        "run_type": "RESEARCH",
                        "idempotency_key": f"weekly-detail-source-{research_id}",
                        "request_hash": "6" * 64,
                        "request_payload": {"symbol": "NVDA"},
                        "symbol": "NVDA",
                        "decision_time": research_time,
                        "data_cutoff": research_time,
                        "created_at": research_time,
                        "status": "QUEUED",
                    },
                    {
                        "id": review_run_id,
                        "run_type": "WEEKLY_REVIEW",
                        "idempotency_key": f"weekly-detail-{review_run_id}",
                        "request_hash": "7" * 64,
                        "request_payload": {"scheduled": True},
                        "symbol": None,
                        "decision_time": review_time,
                        "data_cutoff": review_time,
                        "created_at": review_time,
                        "status": "QUEUED",
                    },
                ],
            )

        assert execute_research_run(
            isolated_database_url,
            str(research_id),
            completed_at=research_time,
        )
        assert execute_weekly_review_run(isolated_database_url, str(review_run_id))
        with engine.connect() as connection:
            review_id = connection.execute(
                select(weekly_review_run.c.id).where(
                    weekly_review_run.c.run_key == str(review_run_id)
                )
            ).scalar_one()
            lesson_id = connection.execute(select(candidate_lesson.c.id)).scalar_one()

        read_time = datetime.now(UTC) + timedelta(minutes=1)
        future_time = read_time + timedelta(days=1)
        future_approval_id = uuid4()
        future_replay_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                insert(lesson_approval).values(
                    id=future_approval_id,
                    lesson_id=lesson_id,
                    actor_id="future-reviewer",
                    action="APPROVE",
                    rationale="not visible before its audit time",
                    created_at=future_time,
                )
            )
            connection.execute(
                insert(replay_run).values(
                    id=future_replay_id,
                    lesson_id=lesson_id,
                    decision_ids=[],
                    baseline_score="0",
                    candidate_score="0",
                    delta="0",
                    data_cutoff=future_time,
                    created_at=future_time,
                )
            )
        response = client.get(
            f"/api/v1/weekly-reviews/{review_id}",
            params={"decision_time": read_time.isoformat()},
        )

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "decision_time",
            "review",
            "outcomes",
            "attributions",
            "lessons",
            "approvals",
            "replays",
            "calibration",
        }
        assert body["review"]["id"] == str(review_id)
        assert body["review"]["decision_ids"]
        assert body["outcomes"]
        assert body["calibration"]
        assert str(future_approval_id) not in {item["id"] for item in body["approvals"]}
        assert str(future_replay_id) not in {item["id"] for item in body["replays"]}
        assert all(item["computed_at"] <= body["decision_time"] for item in body["outcomes"])
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
