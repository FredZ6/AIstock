"""Opt-in real HTTP/browser checks; all writes stay in an isolated test database."""

import os
import socket
import subprocess
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, select
from stock_platform.infrastructure.db.models.tables import agent_event, agent_run
from stock_platform.infrastructure.db.security_seed import seed_security_master
from stock_platform.workers.research_tasks import execute_research_run


def _free_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.mark.skipif(os.getenv("RUN_API_BROWSER") != "1", reason="Opt-in real API browser suite")
def test_isolated_api_browser_runtime(isolated_database_url: str) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    as_of = datetime(2026, 8, 16, tzinfo=UTC)
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
                    decision_time=as_of,
                    data_cutoff=as_of,
                    status="QUEUED",
                )
            )
        assert execute_research_run(isolated_database_url, str(run_id), completed_at=as_of)
        with engine.connect() as connection:
            event_ids = (
                connection.execute(
                    select(agent_event.c.id)
                    .where(agent_event.c.run_id == run_id)
                    .order_by(agent_event.c.sequence)
                )
                .scalars()
                .all()
            )
        assert len(event_ids) > 2
        api_port = _free_loopback_port()
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
                "API_BASE_URL": f"http://127.0.0.1:{api_port}",
                "BROWSER_API_PORT": str(api_port),
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
