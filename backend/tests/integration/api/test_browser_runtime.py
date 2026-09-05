"""Opt-in real HTTP/browser checks; all writes stay in an isolated test database."""

import os
import subprocess
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert
from stock_platform.infrastructure.db.models.tables import agent_event, agent_run
from stock_platform.infrastructure.db.security_seed import seed_security_master


@pytest.mark.skipif(os.getenv("RUN_API_BROWSER") != "1", reason="Opt-in real API browser suite")
def test_isolated_api_browser_runtime(isolated_database_url: str) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    event_ids = [uuid4(), uuid4(), uuid4()]
    try:
        with engine.begin() as connection:
            seed_security_master(connection)
            connection.execute(
                insert(agent_run).values(
                    id=run_id,
                    run_type="RESEARCH",
                    idempotency_key=f"browser-{run_id}",
                    request_hash="a" * 64,
                    request_payload={},
                    symbol="NVDA",
                    decision_time=datetime(2026, 8, 21, tzinfo=UTC),
                    data_cutoff=datetime(2026, 8, 21, tzinfo=UTC),
                    status="COMPLETED",
                )
            )
            for sequence, event_id in enumerate(event_ids, 1):
                connection.execute(
                    insert(agent_event).values(
                        id=event_id,
                        run_id=run_id,
                        sequence=sequence,
                        event_type="run.completed" if sequence == 3 else "node.completed",
                        payload={"test_only": True, "node": f"browser-step-{sequence}"},
                    )
                )
        result = subprocess.run(
            [
                "pnpm",
                "--dir",
                "web",
                "exec",
                "playwright",
                "test",
                "e2e/api-runtime.spec.ts",
                "--workers=1",
            ],
            env={
                **os.environ,
                "DATABASE_URL": isolated_database_url,
                "RUN_API_BROWSER": "1",
                "WEB_DATA_MODE": "api",
                "API_BASE_URL": "http://127.0.0.1:8107",
                "PLAYWRIGHT_WEB_PORT": "3107",
                "BROWSER_RUN_ID": str(run_id),
                "BROWSER_EVENT_IDS": ",".join(map(str, event_ids)),
            },
            timeout=180,
            check=False,
        )
        assert result.returncode == 0
    finally:
        engine.dispose()
