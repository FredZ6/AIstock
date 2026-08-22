from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, func, select
from sqlalchemy.engine import RowMapping

from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.application.research.persistence import PostgresResearchStore
from stock_platform.application.runs import RunControl, execute_run
from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.db.models.tables import market_bar
from stock_platform.infrastructure.providers.base import FeedType
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from stock_platform.mcp_servers.common import McpProviderGateway, PostgresMcpAuditSink
from stock_platform.settings import Settings
from stock_platform.workers.celery_app import celery_app


@celery_app.task(name="stock_platform.workers.research_tasks.run_research")  # type: ignore[untyped-decorator]
def run_research(run_id: str) -> bool:
    return execute_research_run(Settings().database_url, run_id)


def execute_research_run(
    database_url: str, run_id: str, *, completed_at: datetime | None = None
) -> bool:
    completion_time = require_aware(completed_at) if completed_at is not None else None

    def work(connection: Connection, row: RowMapping, control: RunControl) -> None:
        symbol = row["symbol"]
        if not symbol:
            raise ValueError("research run requires a symbol")
        catalog = FixtureCatalog.load_default()
        catalog.seed_database(connection)
        specification = TaskSpecification(
            objective=f"Research the frozen {symbol} fixture",
            symbols=(symbol,),
            decision_time=row["decision_time"],
            data_cutoff=row["data_cutoff"],
            allowed_tools=frozenset(feed.value for feed in FeedType),
            budgets=BudgetLimits(),
            output_schema="research-decision-v1",
            completion_rules=frozenset({"decision_persisted", "citations_verified"}),
            policy_versions=PolicyVersions(
                row["research_scoring_policy_version"],
                row["risk_policy_version"],
                row["execution_policy_version"],
                row["confidence_policy_version"],
                row["prompt_version"],
                row["model_version"],
            ),
        )
        DailyResearchGraph(
            provider=McpProviderGateway(
                catalog.provider(),
                PostgresMcpAuditSink(connection, event_emitter=control.emit),
            ),
            store=PostgresResearchStore(
                connection, available_at=completion_time, record_events=False
            ),
            on_node_completed=control.node_completed,
        ).run(run_id=run_id, specification=specification)

    return execute_run(database_url, UUID(run_id), "RESEARCH", work)


@celery_app.task(name="stock_platform.workers.research_tasks.monitor_market")  # type: ignore[untyped-decorator]
def monitor_market(run_id: str) -> bool:
    return execute_market_monitor_run(Settings().database_url, run_id)


def execute_market_monitor_run(database_url: str, run_id: str) -> bool:
    run_uuid = UUID(run_id)

    def work(connection: Connection, row: RowMapping, control: RunControl) -> None:
        visible_bars = connection.execute(
            select(func.count())
            .select_from(market_bar)
            .where(
                market_bar.c.event_time <= row["decision_time"],
                market_bar.c.available_at <= row["data_cutoff"],
            )
        ).scalar_one()
        control.emit("monitor.completed", {"visible_bars": visible_bars})

    return execute_run(database_url, run_uuid, "ALERT_MONITOR", work)
