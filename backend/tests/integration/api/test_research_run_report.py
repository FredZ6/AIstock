from contextlib import nullcontext
from datetime import UTC, datetime
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from stock_platform.api.dependencies import (
    get_connection,
    get_read_connection_factory,
    get_settings,
)
from stock_platform.api.main import app
from stock_platform.infrastructure.db.models.tables import agent_run
from stock_platform.settings import Settings
from stock_platform.workers.research_tasks import execute_research_run


def _migrate(database_url: str) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def test_completed_research_report_is_closed_and_lineage_backed(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    as_of = datetime(2026, 8, 16, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="RESEARCH",
                idempotency_key=f"report-{run_id}",
                request_hash="a" * 64,
                request_payload={"symbol": "NVDA"},
                symbol="NVDA",
                decision_time=as_of,
                data_cutoff=as_of,
                status="QUEUED",
            )
        )

    assert execute_research_run(isolated_database_url, str(run_id)) is True

    with engine.connect() as connection:
        app.dependency_overrides[get_connection] = lambda: connection
        app.dependency_overrides[get_read_connection_factory] = lambda: (
            lambda: nullcontext(connection)
        )
        app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[call-arg]
            environment="test", _env_file=None
        )
        try:
            response = TestClient(app).get(f"/api/v1/research-runs/{run_id}/report")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    report = response.json()
    assert set(report) == {
        "run_id",
        "thesis",
        "opinion",
        "decision",
        "evidence",
        "evidence_gaps",
        "decision_diff",
    }
    assert report["run_id"] == str(run_id)
    assert report["thesis"]["symbol"] == "NVDA"
    assert report["opinion"]["value"] in {"BULLISH", "NEUTRAL", "BEARISH", "ABSTAIN"}
    assert report["decision"]["data_cutoff"] == as_of.isoformat().replace("+00:00", "Z")
    assert report["decision"]["prompt_version"] == "prompt-v1"
    assert report["decision"]["model_version"] == "fixture-v1"
    assert set(report["decision"]["policy_versions"]) == {
        "research_scoring",
        "risk",
        "execution",
        "confidence",
    }
    assert report["evidence"]
    assert all(item["raw_object_key"] for item in report["evidence"])
    assert all(item["content_hash"] for item in report["evidence"])
    assert all(
        item["available_at"] <= report["decision"]["data_cutoff"] for item in report["evidence"]
    )
    assert report["decision_diff"]["generator"] == "DETERMINISTIC_CODE"
    assert all(gap["run_id"] == str(run_id) for gap in report["evidence_gaps"])
    engine.dispose()
