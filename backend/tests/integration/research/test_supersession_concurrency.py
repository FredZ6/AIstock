from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, local
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, select
from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.application.research.persistence import PostgresResearchStore
from stock_platform.application.research.supersession import record_decision_supersession
from stock_platform.infrastructure.db.models.tables import decision_diff
from stock_platform.infrastructure.providers.base import FeedType
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog


@pytest.mark.parametrize("different_replacement", [False, True])
def test_concurrent_supersession_has_one_winner_without_aborting_transactions(
    isolated_database_url: str, different_replacement: bool
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    try:
        with engine.begin() as connection:
            catalog = FixtureCatalog.load_default()
            catalog.seed_database(connection)
            graph = DailyResearchGraph(
                provider=catalog.provider(), store=PostgresResearchStore(connection)
            )
            specification = TaskSpecification(
                objective="Concurrent correction regression",
                symbols=("NVDA",),
                decision_time=datetime(2026, 8, 16, tzinfo=UTC),
                data_cutoff=datetime(2026, 8, 16, tzinfo=UTC),
                allowed_tools=frozenset(feed.value for feed in FeedType),
                budgets=BudgetLimits(),
                output_schema="research-decision-v1",
                completion_rules=frozenset({"decision_persisted", "citations_verified"}),
                policy_versions=PolicyVersions(
                    "research-v1",
                    "risk-v1",
                    "execution-v1",
                    "confidence-v1",
                    "prompt-v1",
                    "fixture-v1",
                ),
            )
            ids: list[UUID] = []
            for _ in range(3):
                decision_id = graph.run(
                    run_id=str(uuid4()), specification=specification
                ).decision_id
                assert decision_id is not None
                ids.append(decision_id)
        barrier = Barrier(2)
        state = local()

        def synchronize_reads(
            conn: object,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            if statement.startswith("SELECT decision_diff.decision_id") and not getattr(
                state, "read", False
            ):
                state.read = True
                barrier.wait(timeout=10)

        event.listen(engine, "after_cursor_execute", synchronize_reads)

        def record(index: int) -> bool | str:
            result: bool | str
            with engine.begin() as connection:
                try:
                    result = record_decision_supersession(
                        connection,
                        previous_decision_id=ids[0],
                        replacement_decision_id=ids[2 if different_replacement and index else 1],
                        reason="CORRECTION",
                        recorded_at=datetime.now(UTC) + timedelta(seconds=1),
                    )
                except ValueError as error:
                    result = str(error)
                assert connection.execute(select(1)).scalar_one() == 1
                return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(record, range(2)))
        assert results.count(True) == 1
        assert (
            results.count(
                "decision already has a different replacement" if different_replacement else False
            )
            == 1
        )
        with engine.connect() as connection:
            assert (
                connection.execute(
                    select(func.count())
                    .select_from(decision_diff)
                    .where(decision_diff.c.previous_decision_id == ids[0])
                ).scalar_one()
                == 1
            )
    finally:
        engine.dispose()
