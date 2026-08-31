from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, func, select
from sqlalchemy.engine import Engine, RowMapping

from stock_platform.agents.checkpointing import postgres_checkpointer
from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.application.market_data.repositories import PostgresMarketDataRepository
from stock_platform.application.research.persistence import PostgresResearchStore
from stock_platform.application.runs import RunControl, execute_run
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import MarketDataCoverage
from stock_platform.infrastructure.db.models.tables import market_bar
from stock_platform.infrastructure.providers.base import (
    FeedType,
    ProviderResponse,
    ProviderStatus,
    ResearchDataProvider,
)
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from stock_platform.mcp_servers.common import McpProviderGateway, durable_mcp_audit_sink
from stock_platform.settings import Settings
from stock_platform.workers.celery_app import celery_app


@celery_app.task(name="stock_platform.workers.research_tasks.run_research")  # type: ignore[untyped-decorator]
def run_research(run_id: str) -> bool:
    settings = Settings()
    return execute_research_run(
        settings.database_url,
        run_id,
        fixture_mode=settings.fixture_mode,
    )


class PostgresResearchProvider:
    """Point-in-time paper-mode provider over committed normalized facts."""

    name = "POSTGRES_POINT_IN_TIME"

    def __init__(
        self,
        engine: Engine,
        *,
        coverage: MarketDataCoverage | None,
        gap_reason: str | None,
    ) -> None:
        self._engine = engine
        self._coverage = coverage
        self._gap_reason = gap_reason

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        if feed_type is FeedType.PRICE_BARS and self._coverage is None:
            return ProviderResponse(
                status=ProviderStatus.UNAVAILABLE,
                provider="ALPACA",
                feed_type=feed_type,
                symbol=Symbol(symbol),
                query_as_of=require_aware(as_of),
                missingness=self._gap_reason or "market data entitlement unavailable",
            )
        with self._engine.connect() as connection:
            response = PostgresMarketDataRepository(connection).as_of(
                symbol=symbol,
                feed_type=feed_type,
                decision_time=as_of,
                coverage=self._coverage if feed_type is FeedType.PRICE_BARS else None,
            )
        alpaca_records = tuple(record for record in response.records if record.provider == "ALPACA")
        if response.records and alpaca_records != response.records:
            response = ProviderResponse(
                status=ProviderStatus.OK if alpaca_records else ProviderStatus.NOT_FOUND,
                provider="ALPACA",
                feed_type=response.feed_type,
                symbol=response.symbol,
                query_as_of=response.query_as_of,
                records=alpaca_records,
                warnings=response.warnings,
                trace_id=response.trace_id,
                missingness=None if alpaca_records else "MISSING",
            )
        if feed_type is FeedType.PRICE_BARS and self._gap_reason is not None:
            return ProviderResponse(
                status=response.status,
                provider=response.provider,
                feed_type=response.feed_type,
                symbol=response.symbol,
                query_as_of=response.query_as_of,
                records=response.records,
                warnings=response.warnings + (f"market_data_gap:UNAVAILABLE:{self._gap_reason}",),
                missingness=response.missingness,
            )
        return response


def execute_research_run(
    database_url: str,
    run_id: str,
    *,
    completed_at: datetime | None = None,
    fixture_mode: bool = True,
) -> bool:
    completion_time = require_aware(completed_at) if completed_at is not None else None

    def work(connection: Connection, row: RowMapping, control: RunControl) -> None:
        symbol = row["symbol"]
        if not symbol:
            raise ValueError("research run requires a symbol")
        request_payload = row["request_payload"] or {}
        admission = request_payload.get("market_data_admission", {})
        selected_coverage = admission.get("selected_coverage")
        gap_reason = (
            str(admission.get("reason")) if admission.get("gap_kind") == "UNAVAILABLE" else None
        )
        provider: ResearchDataProvider = PostgresResearchProvider(
            connection.engine,
            coverage=(
                MarketDataCoverage(str(selected_coverage))
                if selected_coverage is not None
                else None
            ),
            gap_reason=gap_reason,
        )
        if fixture_mode:
            catalog = FixtureCatalog.load_default()
            catalog.seed_database(connection)
            provider = catalog.provider()
        specification = TaskSpecification(
            objective=(
                f"Research the frozen {symbol} fixture"
                if fixture_mode
                else f"Research {symbol} from point-in-time provider facts"
            ),
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
        audit_sink = durable_mcp_audit_sink(database_url)
        try:
            DailyResearchGraph(
                provider=McpProviderGateway(provider, audit_sink),
                store=PostgresResearchStore(
                    connection, available_at=completion_time, record_events=False
                ),
                on_node_completed=control.node_completed,
                checkpointer=checkpointer,
            ).run(run_id=run_id, specification=specification)
        finally:
            audit_sink.close()

    with postgres_checkpointer(database_url) as checkpointer:
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
