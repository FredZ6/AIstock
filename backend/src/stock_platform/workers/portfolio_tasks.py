from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, func, insert, select
from sqlalchemy.engine import RowMapping

from stock_platform.agents.checkpointing import postgres_checkpointer
from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.portfolio.graph import PortfolioDecisionGraph
from stock_platform.agents.portfolio.state import FrozenResearchDecision
from stock_platform.application.portfolio.accounting import (
    PostgresPaperAccountingStore,
    initial_funding,
)
from stock_platform.application.portfolio.allocation import MarketContextSnapshot, MarketRegime
from stock_platform.application.portfolio.execution import ExecutionPolicy
from stock_platform.application.portfolio.risk import RiskPolicy
from stock_platform.application.research.supersession import decision_is_active_at
from stock_platform.application.runs import RunControl, RunInputUnavailable, execute_run
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.portfolio.fill import ExecutionBar
from stock_platform.domain.research.claims import ResearchOpinionValue
from stock_platform.infrastructure.db.models.tables import (
    confidence_policy_version,
    decision_snapshot,
    evidence_item,
    execution_policy_version,
    investment_thesis,
    market_bar,
    market_context_snapshot,
    paper_portfolio_config,
    portfolio_action,
    research_opinion,
    research_scoring_policy_version,
    risk_policy_version,
    thesis_evidence_link,
)
from stock_platform.infrastructure.providers.base import FeedType
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from stock_platform.settings import Settings
from stock_platform.workers.celery_app import celery_app


def load_paper_execution_bars(
    connection: Connection,
    *,
    symbols: tuple[str, ...],
    decision_time: datetime,
    observed_at: datetime,
) -> tuple[ExecutionBar, ...]:
    require_aware(decision_time)
    observation = require_aware(observed_at).astimezone(UTC)
    visible_rows = connection.execute(
        select(market_bar)
        .where(
            market_bar.c.symbol.in_(symbols),
            market_bar.c.coverage == "SIP",
            market_bar.c.session == "REGULAR",
            market_bar.c.event_time <= observation,
            market_bar.c.available_at <= observation,
            market_bar.c.open.is_not(None),
            market_bar.c.volume.is_not(None),
        )
        .order_by(
            market_bar.c.symbol,
            market_bar.c.event_time,
            market_bar.c.available_at,
            market_bar.c.ingested_at,
        )
    ).mappings()
    revisions: dict[tuple[str, datetime, str, str, str], RowMapping] = {}
    for row in visible_rows:
        key = (
            str(row["symbol"]),
            row["event_time"],
            str(row["provider"]),
            str(row["coverage"]),
            str(row["session"]),
        )
        current = revisions.get(key)
        if current is None or (
            row["available_at"],
            row["ingested_at"],
            row["content_hash"],
        ) > (
            current["available_at"],
            current["ingested_at"],
            current["content_hash"],
        ):
            revisions[key] = row
    return tuple(
        ExecutionBar(
            Symbol(str(row["symbol"])),
            row["event_time"],
            row["available_at"],
            Decimal(row["open"]),
            Decimal(row["volume"]),
            str(row["content_hash"]),
        )
        for _, row in sorted(revisions.items())
    )


@celery_app.task(name="stock_platform.workers.portfolio_tasks.run_portfolio")  # type: ignore[untyped-decorator]
def run_portfolio(run_id: str) -> bool:
    settings = Settings()
    return execute_portfolio_run(
        settings.database_url,
        run_id,
        fixture_mode=settings.fixture_mode,
        observed_at=datetime.now(UTC),
    )


def execute_portfolio_run(
    database_url: str,
    run_id: str,
    *,
    fixture_mode: bool = True,
    observed_at: datetime | None = None,
) -> bool:
    run_uuid = UUID(run_id)
    execution_observed_at = require_aware(observed_at or datetime.now(UTC)).astimezone(UTC)

    def work(connection: Connection, row: RowMapping, control: RunControl) -> None:
        config = connection.execute(select(paper_portfolio_config)).mappings().one()
        context_row = (
            connection.execute(
                select(market_context_snapshot)
                .where(
                    market_context_snapshot.c.as_of <= row["decision_time"],
                    market_context_snapshot.c.available_at <= row["data_cutoff"],
                )
                .order_by(
                    market_context_snapshot.c.as_of.desc(),
                    market_context_snapshot.c.available_at.desc(),
                )
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if context_row is None:
            raise RunInputUnavailable("portfolio run requires a visible market context snapshot")
        context = MarketContextSnapshot(
            id=context_row["id"],
            as_of=context_row["as_of"],
            available_at=context_row["available_at"],
            qqq_trend=context_row["qqq_trend"],
            qqq_volatility=context_row["qqq_volatility"],
            soxx_relative_strength=context_row["soxx_relative_strength"],
            vix=context_row["vix"],
            regime=MarketRegime(context_row["regime_label"]),
            algorithm_version=context_row["algorithm_version"],
            source_lineage=tuple(UUID(item) for item in context_row["source_lineage"]),
        )
        frozen_rows = connection.execute(
            select(
                decision_snapshot.c.id.label("decision_id"),
                decision_snapshot.c.data_cutoff,
                decision_snapshot.c.available_at,
                decision_snapshot.c.prompt_version,
                decision_snapshot.c.model_version,
                investment_thesis.c.id.label("thesis_id"),
                investment_thesis.c.symbol,
                investment_thesis.c.as_of,
                research_opinion.c.value.label("opinion"),
                research_scoring_policy_version.c.version.label("research_version"),
                risk_policy_version.c.id.label("risk_policy_id"),
                risk_policy_version.c.version.label("risk_version"),
                risk_policy_version.c.policy.label("risk_policy"),
                execution_policy_version.c.id.label("execution_policy_id"),
                execution_policy_version.c.version.label("execution_version"),
                execution_policy_version.c.policy.label("execution_policy"),
                confidence_policy_version.c.version.label("confidence_version"),
            )
            .select_from(
                decision_snapshot.join(
                    investment_thesis,
                    decision_snapshot.c.thesis_id == investment_thesis.c.id,
                )
                .join(
                    research_opinion,
                    research_opinion.c.thesis_id == investment_thesis.c.id,
                )
                .join(
                    research_scoring_policy_version,
                    decision_snapshot.c.research_scoring_policy_version_id
                    == research_scoring_policy_version.c.id,
                )
                .join(
                    risk_policy_version,
                    decision_snapshot.c.risk_policy_version_id == risk_policy_version.c.id,
                )
                .join(
                    execution_policy_version,
                    decision_snapshot.c.execution_policy_version_id
                    == execution_policy_version.c.id,
                )
                .join(
                    confidence_policy_version,
                    decision_snapshot.c.confidence_policy_version_id
                    == confidence_policy_version.c.id,
                )
            )
            .where(
                investment_thesis.c.as_of <= row["decision_time"],
                decision_snapshot.c.data_cutoff <= row["data_cutoff"],
                decision_snapshot.c.available_at <= row["data_cutoff"],
                decision_is_active_at(decision_snapshot.c.id, row["data_cutoff"]),
                research_opinion.c.created_at <= row["data_cutoff"],
                research_scoring_policy_version.c.version == row["research_scoring_policy_version"],
                risk_policy_version.c.version == row["risk_policy_version"],
                execution_policy_version.c.version == row["execution_policy_version"],
                confidence_policy_version.c.version == row["confidence_policy_version"],
            )
            .order_by(investment_thesis.c.as_of.desc(), decision_snapshot.c.id)
        ).mappings()
        latest_by_symbol: dict[str, RowMapping] = {}
        for frozen_row in frozen_rows:
            latest_by_symbol.setdefault(frozen_row["symbol"], frozen_row)
        if not latest_by_symbol:
            raise RunInputUnavailable(
                "portfolio run requires at least one frozen research decision"
            )
        selected = tuple(latest_by_symbol.values())
        first = selected[0]
        portfolio_versions = PolicyVersions(
            first["research_version"],
            first["risk_version"],
            first["execution_version"],
            first["confidence_version"],
            row["prompt_version"],
            row["model_version"],
        )
        research: list[FrozenResearchDecision] = []
        for frozen_row in selected:
            evidence_state = connection.execute(
                select(
                    func.count(thesis_evidence_link.c.evidence_id),
                    func.coalesce(func.bool_or(evidence_item.c.conflict), False),
                )
                .select_from(
                    thesis_evidence_link.join(
                        evidence_item,
                        thesis_evidence_link.c.evidence_id == evidence_item.c.id,
                    )
                )
                .where(
                    thesis_evidence_link.c.thesis_id == frozen_row["thesis_id"],
                    thesis_evidence_link.c.created_at <= row["data_cutoff"],
                    evidence_item.c.created_at <= row["data_cutoff"],
                )
            ).one()
            opinion = ResearchOpinionValue(frozen_row["opinion"])
            proposed_weight = (
                Decimal("0.50") if opinion is ResearchOpinionValue.BULLISH else Decimal("0")
            )
            research.append(
                FrozenResearchDecision(
                    decision_id=frozen_row["decision_id"],
                    thesis_id=frozen_row["thesis_id"],
                    symbol=frozen_row["symbol"],
                    opinion=opinion,
                    as_of=frozen_row["as_of"],
                    available_at=frozen_row["available_at"],
                    evidence_complete=evidence_state[0] > 0 and not evidence_state[1],
                    proposed_weight=proposed_weight,
                    rationale=(
                        "deterministic fixture proposer from frozen research opinion"
                        if fixture_mode
                        else "deterministic paper proposer from frozen research opinion"
                    ),
                    policy_versions=PolicyVersions(
                        frozen_row["research_version"],
                        frozen_row["risk_version"],
                        frozen_row["execution_version"],
                        frozen_row["confidence_version"],
                        frozen_row["prompt_version"],
                        frozen_row["model_version"],
                    ),
                    data_cutoff=frozen_row["data_cutoff"],
                )
            )
        specification = TaskSpecification(
            objective="rebalance the singleton paper portfolio",
            symbols=tuple(sorted(latest_by_symbol)),
            decision_time=row["decision_time"],
            data_cutoff=row["data_cutoff"],
            allowed_tools=frozenset(),
            budgets=BudgetLimits(
                llm_calls=3,
                tool_calls=0,
                tokens=5000,
                reflections=0,
                wall_time=timedelta(seconds=60),
            ),
            output_schema="PortfolioDecision",
            completion_rules=frozenset({"risk_decision_for_every_order"}),
            policy_versions=portfolio_versions,
        )
        if fixture_mode:
            catalog = FixtureCatalog.load_default()
            bars = tuple(
                ExecutionBar(
                    entry.symbol,
                    entry.event_time,
                    entry.available_at,
                    Decimal(str(entry.payload["open"])),
                    Decimal(str(entry.payload["volume"])),
                    entry.content_hash,
                )
                for entry in catalog.entries
                if entry.feed_type is FeedType.PRICE_BARS
                and str(entry.symbol) in latest_by_symbol
                and {"open", "volume"} <= entry.payload.keys()
                and entry.available_at <= specification.data_cutoff
            )
        else:
            bars = load_paper_execution_bars(
                connection,
                symbols=tuple(sorted(latest_by_symbol)),
                decision_time=specification.decision_time,
                observed_at=execution_observed_at,
            )
        store = PostgresPaperAccountingStore(connection)
        prior_fills = store.load_fills(config["id"], as_of=specification.decision_time)
        ledger = store.load_ledger(config["id"], as_of=specification.decision_time)
        if not ledger:
            ledger = initial_funding(
                config["id"],
                config["initial_cash"],
                config["currency"],
                specification.decision_time,
            )
        graph = PortfolioDecisionGraph(
            risk_policy=RiskPolicy(
                id=first["risk_policy_id"],
                version=first["risk_version"],
                max_position_weight=Decimal(first["risk_policy"]["max_position_weight"]),
                max_gross_exposure=Decimal(first["risk_policy"]["max_gross_exposure"]),
                min_cash_reserve=Decimal(first["risk_policy"]["min_cash_reserve"]),
                max_daily_turnover=Decimal(first["risk_policy"]["max_daily_turnover"]),
                max_drawdown=Decimal(first["risk_policy"]["max_drawdown"]),
                max_research_age=timedelta(days=int(first["risk_policy"]["max_research_age_days"])),
                earnings_blackout=timedelta(
                    days=int(first["risk_policy"]["earnings_blackout_days"])
                ),
            ),
            execution_policy=ExecutionPolicy(
                id=first["execution_policy_id"],
                version=first["execution_version"],
                spread_bps=Decimal(first["execution_policy"]["spread_bps"]),
                slippage_bps=Decimal(first["execution_policy"]["slippage_bps"]),
                fee_per_share=Decimal(first["execution_policy"]["fee_per_share"]),
                minimum_fee=Decimal(first["execution_policy"]["minimum_fee"]),
                volume_participation=Decimal(first["execution_policy"]["volume_participation"]),
            ),
            on_node_completed=control.node_completed,
            checkpointer=checkpointer,
        )
        result = graph.run(
            run_id=run_id,
            portfolio_id=config["id"],
            specification=specification,
            research=research,
            market_context=context,
            bars=bars,
            ledger=ledger,
            prior_fills=prior_fills,
        )
        store.persist_ledger(result.ledger)
        for decision in result.risk_decisions:
            store.persist_risk_decision(decision, result.market_context)
        for order in result.order_intents:
            decision = next(
                item for item in result.risk_decisions if item.id == order.risk_decision_id
            )
            store.persist(
                order,
                tuple(item for item in result.fills if item.order_id == order.id),
                result.ledger,
                risk_decision=decision,
                market_context=result.market_context,
            )
        for action in result.actions:
            connection.execute(
                insert(portfolio_action).values(
                    decision_id=action.research_decision_id,
                    value=action.value.value,
                )
            )

    with postgres_checkpointer(database_url) as checkpointer:
        return execute_run(database_url, run_uuid, "PORTFOLIO", work)
