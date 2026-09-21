from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, select
from stock_platform.application.market_data.repositories import PostgresMarketDataRepository
from stock_platform.infrastructure.db.models.tables import (
    agent_event,
    agent_run,
    claim,
    confidence_policy_version,
    decision_snapshot,
    derived_metric,
    evidence_gap,
    evidence_item,
    execution_policy_version,
    investment_thesis,
    market_bar,
    normalized_record,
    raw_data_object,
    research_opinion,
    research_scoring_policy_version,
    risk_policy_version,
    security,
    thesis_evidence_link,
    tool_call,
    watchlist_item,
)
from stock_platform.settings import Settings
from stock_platform.workers.research_tasks import execute_research_run
from stock_platform.workers.schedules import schedule_daily_research


def test_watchlist_research_population_is_pit_safe_complete_and_idempotent(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    cutoff = datetime(2026, 9, 18, 20, 15, tzinfo=UTC)
    completed_at = datetime(2026, 9, 20, 8, tzinfo=UTC)
    settings = Settings(
        environment="paper",
        database_url=isolated_database_url,
        max_active_agent_runs=20,
        alpaca_data_key="test-key",
        alpaca_data_secret="test-secret",
        alpaca_entitlement_coverage="IEX",
        alpaca_entitlement_version="operator-verified-test",
    )
    dispatched: list[tuple[str, str]] = []

    original_as_of = PostgresMarketDataRepository.as_of

    def legacy_checkpoint_as_of(self, **kwargs):
        response = original_as_of(self, **kwargs)
        return replace(
            response,
            records=tuple(
                replace(record, normalized_record_id=None) for record in response.records
            ),
        )

    monkeypatch.setattr(PostgresMarketDataRepository, "as_of", legacy_checkpoint_as_of)

    with engine.begin() as connection:
        for index, symbol in enumerate(("MSFT", "NVDA"), start=1):
            security_id = uuid4()
            raw_id = uuid4()
            connection.execute(
                insert(security).values(id=security_id, instrument_type="COMMON_STOCK")
            )
            connection.execute(
                insert(watchlist_item).values(security_id=security_id, symbol=symbol)
            )
            source_time = cutoff - timedelta(days=1, minutes=index)
            connection.execute(
                insert(raw_data_object).values(
                    id=raw_id,
                    provider="SEC",
                    feed_type="company_facts",
                    event_time=source_time,
                    available_at=source_time + timedelta(seconds=1),
                    ingested_at=source_time + timedelta(seconds=2),
                    content_hash=f"{index:064x}",
                    raw_object_key=f"test/sec/{symbol}/company-facts.json",
                )
            )
            connection.execute(
                insert(normalized_record),
                [
                    {
                        "raw_data_object_id": raw_id,
                        "record_type": "company_facts",
                        "record_key": f"{symbol}:revenue:2026-Q1",
                        "normalization_version": "sec-company-facts-v1",
                        "payload": {"symbol": symbol, "revenue": str(index * 900_000)},
                    },
                    {
                        "raw_data_object_id": raw_id,
                        "record_type": "company_facts",
                        "record_key": f"{symbol}:revenue:2026-Q2",
                        "normalization_version": "sec-company-facts-v1",
                        "payload": {"symbol": symbol, "revenue": str(index * 1_000_000)},
                    },
                ],
            )
            bar_raw_id = uuid4()
            bar_normalized_id = uuid4()
            bar_hash = f"{index + 10:064x}"
            bar_key = f"test/alpaca/{symbol}/bars.json"
            connection.execute(
                insert(raw_data_object).values(
                    id=bar_raw_id,
                    provider="ALPACA",
                    feed_type="price_bars",
                    event_time=source_time,
                    available_at=source_time + timedelta(seconds=1),
                    ingested_at=source_time + timedelta(seconds=2),
                    content_hash=bar_hash,
                    raw_object_key=bar_key,
                )
            )
            connection.execute(
                insert(normalized_record).values(
                    id=bar_normalized_id,
                    raw_data_object_id=bar_raw_id,
                    record_type="price_bars",
                    record_key=symbol,
                    normalization_version="alpaca-bars-v1",
                    payload={
                        "symbol": symbol,
                        "bars": [{"c": str(index * 100), "t": source_time.isoformat()}],
                    },
                )
            )
            connection.execute(
                insert(market_bar).values(
                    symbol=symbol,
                    raw_data_object_id=bar_raw_id,
                    normalized_record_id=bar_normalized_id,
                    provider="ALPACA",
                    feed_type="price_bars",
                    coverage="IEX",
                    session="REGULAR",
                    content_hash=bar_hash,
                    raw_object_key=bar_key,
                    event_time=source_time,
                    available_at=source_time + timedelta(seconds=1),
                    ingested_at=source_time + timedelta(seconds=2),
                    open=Decimal(index * 100),
                    high=Decimal(index * 100),
                    low=Decimal(index * 100),
                    close=Decimal(index * 100),
                    volume=Decimal("1000"),
                    payload={"timeframe": "1Day"},
                )
            )

        first = schedule_daily_research(
            connection,
            settings,
            cutoff,
            dispatch=lambda task, run_id: dispatched.append((task, run_id)),
        )
        replay = schedule_daily_research(
            connection,
            settings,
            cutoff,
            dispatch=lambda task, run_id: dispatched.append((task, run_id)),
        )

    assert replay == first
    assert len(first) == 2
    assert len(dispatched) == 2
    for run_id in first:
        assert execute_research_run(
            isolated_database_url,
            run_id,
            completed_at=completed_at,
            fixture_mode=False,
        )
        assert not execute_research_run(
            isolated_database_url,
            run_id,
            completed_at=completed_at,
            fixture_mode=False,
        )

    lineage = (
        select(
            decision_snapshot.c.id,
            raw_data_object.c.id.label("raw_id"),
        )
        .select_from(
            decision_snapshot.join(
                investment_thesis,
                decision_snapshot.c.thesis_id == investment_thesis.c.id,
            )
            .join(
                thesis_evidence_link,
                thesis_evidence_link.c.thesis_id == investment_thesis.c.id,
            )
            .join(evidence_item, evidence_item.c.id == thesis_evidence_link.c.evidence_id)
            .join(claim, claim.c.evidence_id == evidence_item.c.id)
            .join(derived_metric, derived_metric.c.id == evidence_item.c.derived_metric_id)
            .join(
                normalized_record,
                normalized_record.c.id == derived_metric.c.normalized_record_id,
            )
            .join(
                raw_data_object,
                raw_data_object.c.id == normalized_record.c.raw_data_object_id,
            )
        )
    )
    with engine.connect() as connection:
        decisions = connection.execute(
            select(
                decision_snapshot.c.id,
                decision_snapshot.c.data_cutoff,
                decision_snapshot.c.available_at,
                decision_snapshot.c.prompt_version,
                decision_snapshot.c.model_version,
                research_scoring_policy_version.c.version.label("research_version"),
                risk_policy_version.c.version.label("risk_version"),
                execution_policy_version.c.version.label("execution_version"),
                confidence_policy_version.c.version.label("confidence_version"),
            )
            .join(
                research_scoring_policy_version,
                research_scoring_policy_version.c.id
                == decision_snapshot.c.research_scoring_policy_version_id,
            )
            .join(
                risk_policy_version,
                risk_policy_version.c.id == decision_snapshot.c.risk_policy_version_id,
            )
            .join(
                execution_policy_version,
                execution_policy_version.c.id == decision_snapshot.c.execution_policy_version_id,
            )
            .join(
                confidence_policy_version,
                confidence_policy_version.c.id == decision_snapshot.c.confidence_policy_version_id,
            )
            .order_by(decision_snapshot.c.id)
        ).mappings().all()
        assert len(decisions) == 2
        assert all(row["data_cutoff"] == cutoff for row in decisions)
        assert all(row["available_at"] == completed_at for row in decisions)
        assert all(
            (
                row["research_version"],
                row["risk_version"],
                row["execution_version"],
                row["confidence_version"],
                row["prompt_version"],
                row["model_version"],
            )
            == (
                "research-v1",
                "risk-v1",
                "execution-v1",
                "confidence-v1",
                "prompt-v1",
                "fixture-v1",
            )
            for row in decisions
        )
        assert {row.raw_id for row in connection.execute(lineage)} == set(
            connection.execute(select(raw_data_object.c.id)).scalars()
        )
        assert (
            connection.execute(select(func.count()).select_from(research_opinion)).scalar_one()
            == 2
        )
        gaps = connection.execute(
            select(evidence_gap.c.run_id, evidence_gap.c.kind, evidence_gap.c.reason)
            .where(evidence_gap.c.field == "price_bars")
            .order_by(evidence_gap.c.run_id)
        ).all()
        assert len(gaps) == 2
        assert all(kind == "UNAVAILABLE" for _, kind, _ in gaps)
        assert all(reason == "SIP entitlement unavailable" for _, _, reason in gaps)
        assert connection.execute(select(func.count()).select_from(agent_run)).scalar_one() == 2
        assert connection.execute(select(func.count()).select_from(agent_event)).scalar_one() > 0
        assert connection.execute(select(func.count()).select_from(tool_call)).scalar_one() > 0

    engine.dispose()
