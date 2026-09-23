from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.exc import IntegrityError
from stock_platform.infrastructure.db.models.tables import (
    agent_run,
    cash_ledger,
    claim,
    confidence_policy_version,
    decision_snapshot,
    derived_metric,
    evidence_item,
    execution_policy_version,
    investment_thesis,
    normalized_record,
    order_intent,
    paper_fill,
    paper_order,
    portfolio_action,
    portfolio_nav,
    raw_data_object,
    research_opinion,
    research_scoring_policy_version,
    risk_decision,
    risk_policy_version,
    thesis_evidence_link,
)
from stock_platform.workers.portfolio_tasks import execute_portfolio_run


def test_iex_portfolio_run_persists_audited_cash_only_no_action(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    run_id = uuid4()
    research_run_id = uuid4()
    thesis_id = uuid4()
    decision_id = uuid4()
    raw_id = uuid4()
    normalized_id = uuid4()
    metric_id = uuid4()
    evidence_id = uuid4()
    research_policy_id = uuid4()
    risk_policy_id = uuid4()
    execution_policy_id = uuid4()
    confidence_policy_id = uuid4()
    cutoff = datetime(2026, 9, 18, 20, 30, tzinfo=UTC)
    research_cutoff = cutoff - timedelta(minutes=15)

    with engine.begin() as connection:
        connection.execute(
            insert(research_scoring_policy_version).values(
                id=research_policy_id, version="research-v1", policy={}
            )
        )
        connection.execute(
            insert(risk_policy_version).values(
                id=risk_policy_id,
                version="risk-v1",
                policy={
                    "max_position_weight": "0.20",
                    "max_gross_exposure": "1",
                    "min_cash_reserve": "0.05",
                    "max_daily_turnover": "0.25",
                    "max_drawdown": "0.20",
                    "max_research_age_days": "2",
                    "earnings_blackout_days": "1",
                },
            )
        )
        connection.execute(
            insert(execution_policy_version).values(
                id=execution_policy_id,
                version="execution-v1",
                policy={
                    "spread_bps": "0",
                    "slippage_bps": "0",
                    "fee_per_share": "0",
                    "minimum_fee": "0",
                    "volume_participation": "1",
                },
            )
        )
        connection.execute(
            insert(confidence_policy_version).values(
                id=confidence_policy_id, version="confidence-v1", policy={}
            )
        )
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="PORTFOLIO",
                idempotency_key=f"iex-no-action-{run_id}",
                request_hash="a" * 64,
                request_payload={
                    "scheduled": True,
                    "market_data_admission": {
                        "outcome": "DENIED_NO_ACTION",
                        "selected_coverage": None,
                        "gap_kind": "UNAVAILABLE",
                        "reason": "SIP entitlement required for paper execution",
                        "entitlement_version": "operator-verified-test",
                        "declared_delay_seconds": None,
                    },
                },
                decision_time=cutoff,
                data_cutoff=cutoff,
                status="QUEUED",
            )
        )
        connection.execute(
            insert(raw_data_object).values(
                id=raw_id,
                provider="SEC",
                feed_type="company_facts",
                event_time=research_cutoff - timedelta(days=1),
                available_at=research_cutoff - timedelta(hours=1),
                ingested_at=research_cutoff - timedelta(minutes=30),
                content_hash="b" * 64,
                raw_object_key="test/sec/NVDA/company-facts.json",
            )
        )
        connection.execute(
            insert(normalized_record).values(
                id=normalized_id,
                raw_data_object_id=raw_id,
                record_type="company_facts",
                record_key="NVDA:revenue",
                normalization_version="test-v1",
                payload={"symbol": "NVDA", "revenue": "1000000"},
                created_at=research_cutoff,
            )
        )
        connection.execute(
            insert(derived_metric).values(
                id=metric_id,
                normalized_record_id=normalized_id,
                metric_name="revenue",
                metric_value=Decimal("1000000"),
                algorithm_version="test-v1",
                created_at=research_cutoff,
            )
        )
        connection.execute(
            insert(evidence_item).values(
                id=evidence_id,
                derived_metric_id=metric_id,
                provider="SEC",
                conflict=False,
                content={"symbol": "NVDA"},
                created_at=research_cutoff,
            )
        )
        connection.execute(
            insert(claim).values(
                evidence_id=evidence_id,
                statement="NVDA has visible company facts",
                created_at=research_cutoff,
            )
        )
        connection.execute(
            insert(investment_thesis).values(
                id=thesis_id,
                run_id=research_run_id,
                symbol="NVDA",
                as_of=research_cutoff,
                direction="BULLISH",
                summary="PIT-safe research thesis",
                confidence=Decimal("0.8"),
                confidence_policy_version_id=confidence_policy_id,
                created_at=research_cutoff,
            )
        )
        connection.execute(
            insert(thesis_evidence_link).values(
                thesis_id=thesis_id,
                evidence_id=evidence_id,
                relation="SUPPORTS",
                weight=Decimal("1"),
                rationale="visible fact",
                created_at=research_cutoff,
            )
        )
        connection.execute(
            insert(research_opinion).values(
                thesis_id=thesis_id,
                value="BULLISH",
                created_at=research_cutoff,
            )
        )
        connection.execute(
            insert(decision_snapshot).values(
                id=decision_id,
                thesis_id=thesis_id,
                research_scoring_policy_version_id=research_policy_id,
                risk_policy_version_id=risk_policy_id,
                execution_policy_version_id=execution_policy_id,
                confidence_policy_version_id=confidence_policy_id,
                prompt_version="prompt-v1",
                model_version="fixture-v1",
                data_cutoff=research_cutoff,
                available_at=research_cutoff,
                created_at=research_cutoff,
            )
        )

    assert execute_portfolio_run(
        isolated_database_url,
        str(run_id),
        fixture_mode=False,
        observed_at=cutoff + timedelta(minutes=1),
    )
    assert not execute_portfolio_run(
        isolated_database_url,
        str(run_id),
        fixture_mode=False,
        observed_at=cutoff + timedelta(minutes=1),
    )

    with engine.connect() as connection:
        assert (
            connection.execute(
                select(agent_run.c.status).where(agent_run.c.id == run_id)
            ).scalar_one()
            == "COMPLETED"
        )
        assert connection.execute(select(portfolio_action.c.value)).scalar_one() == "NO_ACTION"
        risk = connection.execute(
            select(
                risk_decision.c.status,
                risk_decision.c.reason_codes,
                risk_decision.c.market_context_snapshot_id,
            )
        ).one()
        assert risk == ("REJECTED", ["MARKET_DATA_ENTITLEMENT"], None)
        assert connection.execute(select(func.count()).select_from(cash_ledger)).scalar_one() == 2
        assert connection.execute(
            select(func.sum(cash_ledger.c.debit - cash_ledger.c.credit)).where(
                cash_ledger.c.account == "ASSET:CASH"
            )
        ).scalar_one() == Decimal("100000")
        assert connection.execute(select(portfolio_nav.c.nav)).scalar_one() == Decimal("100000")
        assert connection.execute(select(func.count()).select_from(order_intent)).scalar_one() == 0
        assert connection.execute(select(func.count()).select_from(paper_order)).scalar_one() == 0
        assert connection.execute(select(func.count()).select_from(paper_fill)).scalar_one() == 0
        invalid_risk = dict(connection.execute(select(risk_decision)).mappings().one())
        invalid_risk.update(
            id=uuid4(),
            proposal_id=uuid4(),
            reason_codes=["MISSING_PRICE"],
            created_at=cutoff,
        )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(insert(risk_decision).values(**invalid_risk))
    engine.dispose()
