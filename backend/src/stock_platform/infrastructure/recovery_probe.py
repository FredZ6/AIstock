"""Deterministic durable-state probes used by operational recovery checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert

from stock_platform.application.portfolio.accounting import (
    PostgresPaperAccountingStore,
    apply_fill,
    initial_funding,
)
from stock_platform.application.portfolio.allocation import (
    MarketContextSnapshot,
    MarketRegime,
)
from stock_platform.application.portfolio.risk import RiskDecision, RiskDecisionStatus
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.fill import PaperFill
from stock_platform.domain.portfolio.order import OrderIntent, OrderSide
from stock_platform.infrastructure.db.models.tables import (
    execution_policy_version,
    risk_policy_version,
)

PORTFOLIO_ID = UUID("10000000-0000-0000-0000-000000000001")
ORDER_ID = UUID("70000000-0000-0000-0000-000000000017")
FILL_ID = UUID("71000000-0000-0000-0000-000000000017")
RISK_DECISION_ID = UUID("72000000-0000-0000-0000-000000000017")
PROPOSAL_ID = UUID("73000000-0000-0000-0000-000000000017")
MARKET_CONTEXT_ID = UUID("74000000-0000-0000-0000-000000000017")
SOURCE_LINEAGE_ID = UUID("75000000-0000-0000-0000-000000000017")
RISK_POLICY_ID = UUID("76000000-0000-0000-0000-000000000017")
EXECUTION_POLICY_ID = UUID("77000000-0000-0000-0000-000000000017")
DECISION_TIME = datetime(2026, 8, 16, 14, 30, tzinfo=UTC)


def persist_paper_fill_probe(database_url: str) -> UUID:
    """Persist and safely replay one scoped paper fill and balanced ledger."""
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                insert(risk_policy_version)
                .values(
                    id=RISK_POLICY_ID,
                    version="task17-recovery-risk-v1",
                    policy={"purpose": "recovery-probe"},
                )
                .on_conflict_do_nothing(index_elements=[risk_policy_version.c.id])
            )
            connection.execute(
                insert(execution_policy_version)
                .values(
                    id=EXECUTION_POLICY_ID,
                    version="task17-recovery-execution-v1",
                    policy={"purpose": "recovery-probe"},
                )
                .on_conflict_do_nothing(index_elements=[execution_policy_version.c.id])
            )
            context = MarketContextSnapshot(
                id=MARKET_CONTEXT_ID,
                as_of=DECISION_TIME,
                available_at=DECISION_TIME,
                qqq_trend=Decimal("0.05"),
                qqq_volatility=Decimal("0.18"),
                soxx_relative_strength=Decimal("0.02"),
                vix=Decimal("18"),
                regime=MarketRegime.RISK_ON,
                algorithm_version="task17-recovery-v1",
                source_lineage=(SOURCE_LINEAGE_ID,),
            )
            risk = RiskDecision(
                id=RISK_DECISION_ID,
                proposal_id=PROPOSAL_ID,
                research_decision_id=None,
                portfolio_id=PORTFOLIO_ID,
                symbol=Symbol("NVDA"),
                status=RiskDecisionStatus.APPROVED,
                requested_weight=Decimal("0.001"),
                approved_weight=Decimal("0.001"),
                current_weight=Decimal("0"),
                approved_delta=Decimal("0.001"),
                reference_nav=Decimal("100000"),
                reference_price=Decimal("100"),
                max_order_quantity=Decimal("1"),
                reason_codes=(),
                risk_policy_version_id=RISK_POLICY_ID,
                decided_at=DECISION_TIME,
                market_context_snapshot_id=MARKET_CONTEXT_ID,
            )
            order = OrderIntent(
                id=ORDER_ID,
                portfolio_id=PORTFOLIO_ID,
                symbol=Symbol("NVDA"),
                side=OrderSide.BUY,
                quantity=Decimal("1"),
                decision_time=DECISION_TIME,
                execution_policy_version_id=EXECUTION_POLICY_ID,
                risk_approved=True,
                risk_decision_id=RISK_DECISION_ID,
            )
            fill = PaperFill(
                id=FILL_ID,
                order_id=ORDER_ID,
                portfolio_id=PORTFOLIO_ID,
                symbol=Symbol("NVDA"),
                side=OrderSide.BUY,
                quantity=Decimal("1"),
                price=Decimal("100"),
                fee=Decimal("1"),
                currency="USD",
                filled_at=DECISION_TIME + timedelta(minutes=1),
                source_bar_time=DECISION_TIME + timedelta(minutes=1),
                execution_policy_version_id=EXECUTION_POLICY_ID,
            )
            entries = apply_fill(
                initial_funding(PORTFOLIO_ID, Decimal("100000"), "USD", DECISION_TIME),
                fill,
            )
            PostgresPaperAccountingStore(connection).persist(
                order,
                (fill,),
                entries,
                risk_decision=risk,
                market_context=context,
            )
        return FILL_ID
    finally:
        engine.dispose()
