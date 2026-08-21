from datetime import UTC, datetime
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, update
from stock_platform.api.dependencies import get_settings
from stock_platform.api.main import app
from stock_platform.application.events.sse import stream_events
from stock_platform.infrastructure.db.models.tables import agent_event, agent_run
from stock_platform.settings import Settings


def test_sse_orders_redacts_and_resumes_from_postgres_without_redis(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    event_ids = [uuid4(), uuid4(), uuid4()]
    now = datetime(2026, 8, 21, 21, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="RESEARCH",
                idempotency_key=f"sse-{run_id}",
                request_hash="a" * 64,
                request_payload={},
                symbol="NVDA",
                decision_time=now,
                data_cutoff=now,
                status="COMPLETED",
            )
        )
        connection.execute(
            insert(agent_event),
            [
                {
                    "id": event_ids[2],
                    "run_id": run_id,
                    "sequence": 3,
                    "event_type": "run.completed",
                    "payload": {"status": "COMPLETED"},
                },
                {
                    "id": event_ids[0],
                    "run_id": run_id,
                    "sequence": 1,
                    "event_type": "run.started",
                    "payload": {"authorization": "Bearer hidden"},
                },
                {
                    "id": event_ids[1],
                    "run_id": run_id,
                    "sequence": 2,
                    "event_type": "tool.completed",
                    "payload": {"items": [{"api_key": "hidden", "records": 2}]},
                },
            ],
        )
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url=isolated_database_url,
        redis_url="redis://127.0.0.1:1/0",
    )
    try:
        with TestClient(app) as client:
            full = client.get(f"/api/v1/events?run_id={run_id}")
            resumed = client.get(
                f"/api/v1/events?run_id={run_id}",
                headers={"Last-Event-ID": str(event_ids[1])},
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert full.status_code == 200
    assert full.headers["content-type"].startswith("text/event-stream")
    assert [line for line in full.text.splitlines() if line.startswith("id:")] == [
        f"id: {event_id}" for event_id in event_ids
    ]
    assert "Bearer hidden" not in full.text
    assert '"api_key":"[REDACTED]"' in full.text
    assert resumed.text.count("id:") == 1
    assert f"id: {event_ids[2]}" in resumed.text


def test_last_event_id_must_belong_to_the_requested_run(isolated_database_url: str) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    other_run_id = uuid4()
    other_event_id = uuid4()
    now = datetime(2026, 8, 21, 21, tzinfo=UTC)
    with engine.begin() as connection:
        for item in (run_id, other_run_id):
            connection.execute(
                insert(agent_run).values(
                    id=item,
                    run_type="RESEARCH",
                    idempotency_key=f"sse-{item}",
                    request_hash="b" * 64,
                    request_payload={},
                    symbol="NVDA",
                    decision_time=now,
                    data_cutoff=now,
                    status="COMPLETED",
                )
            )
        connection.execute(
            insert(agent_event).values(
                id=other_event_id,
                run_id=other_run_id,
                sequence=1,
                event_type="run.completed",
            )
        )
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", database_url=isolated_database_url
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/events?run_id={run_id}",
                headers={"Last-Event-ID": str(other_event_id)},
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_LAST_EVENT_ID"


def test_sse_polls_postgres_until_a_running_run_becomes_terminal(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    event_id = uuid4()
    now = datetime(2026, 8, 21, 21, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="RESEARCH",
                idempotency_key=f"sse-{run_id}",
                request_hash="c" * 64,
                request_payload={},
                symbol="NVDA",
                decision_time=now,
                data_cutoff=now,
                status="RUNNING",
            )
        )

    def finish(_seconds: float) -> None:
        with engine.begin() as writer:
            writer.execute(
                insert(agent_event).values(
                    id=event_id,
                    run_id=run_id,
                    sequence=1,
                    event_type="run.completed",
                )
            )
            writer.execute(
                update(agent_run).where(agent_run.c.id == run_id).values(status="COMPLETED")
            )

    with engine.connect() as reader:
        chunks = list(stream_events(reader, run_id, sleeper=finish))
    engine.dispose()

    assert len(chunks) == 1
    assert f"id: {event_id}" in chunks[0]
