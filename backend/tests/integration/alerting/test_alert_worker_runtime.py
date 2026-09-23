from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, func, insert, select
from stock_platform.application.alerting.features import MinuteBar
from stock_platform.application.alerting.outbox import PostgresAlertStore
from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.db.models.tables import (
    agent_event,
    agent_run,
    alert_event,
    alert_explanation,
    alert_thesis_link,
    derived_metric,
    evidence_item,
    investment_thesis,
    normalized_record,
    notification_outbox,
    raw_data_object,
    thesis_evidence_link,
)
from stock_platform.workers.research_tasks import execute_market_monitor_run


def _seed_alert_bars(connection: Connection, *, start: datetime, symbol: str = "NVDA") -> None:
    store = PostgresAlertStore(connection)
    closes = ("100", "100.2", "99.9", "100.3", "100.1", "106")
    volumes = ("100", "110", "90", "105", "95", "600")
    for minute, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
        event_time = start + timedelta(minutes=minute)
        store.persist_bar(
            MinuteBar(
                symbol=Symbol(symbol),
                event_time=event_time,
                available_at=event_time + timedelta(seconds=1),
                ingested_at=event_time + timedelta(seconds=2),
                open=Decimal("100"),
                high=Decimal(close) + Decimal("0.2"),
                low=Decimal("99.8"),
                close=Decimal(close),
                volume=Decimal(volume),
                previous_close=Decimal("99"),
                provider="ALPACA",
                content_hash=f"{symbol}{minute + 1}".encode().hex().ljust(64, "0")[:64],
                raw_object_key=f"live/alpaca/{symbol}/{event_time.isoformat()}.json",
                raw_payload={"symbol": symbol, "close": close, "volume": volume},
            )
        )


def _insert_monitor_run(
    connection: Connection, *, run_id: UUID, cutoff: datetime, index: int
) -> None:
    connection.execute(
        insert(agent_run).values(
            id=run_id,
            run_type="ALERT_MONITOR",
            idempotency_key=f"alert-runtime-{run_id}",
            request_hash=f"{index + 11:064x}",
            request_payload={"scheduled": True},
            decision_time=cutoff,
            data_cutoff=cutoff,
            status="QUEUED",
        )
    )


def test_market_monitor_persists_one_deduplicated_pit_alert_without_llm(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    start = datetime(2026, 9, 18, 14, 30, tzinfo=UTC)
    cutoff = start + timedelta(minutes=6)
    run_ids = (uuid4(), uuid4())
    thesis_id = uuid4()
    evidence_id = uuid4()

    with engine.begin() as connection:
        _seed_alert_bars(connection, start=start)

        context_raw_id = uuid4()
        context_record_id = uuid4()
        context_metric_id = uuid4()
        context_time = start - timedelta(hours=1)
        connection.execute(
            insert(raw_data_object).values(
                id=context_raw_id,
                provider="SEC",
                feed_type="company_facts",
                event_time=context_time - timedelta(days=1),
                available_at=context_time,
                ingested_at=context_time,
                content_hash="a" * 64,
                raw_object_key="live/sec/NVDA/companyfacts.json",
                created_at=context_time,
            )
        )
        connection.execute(
            insert(normalized_record).values(
                id=context_record_id,
                raw_data_object_id=context_raw_id,
                record_type="company_fact",
                record_key="NVDA:revenue",
                normalization_version="sec-v1",
                payload={"symbol": "NVDA"},
                created_at=context_time,
            )
        )
        connection.execute(
            insert(derived_metric).values(
                id=context_metric_id,
                normalized_record_id=context_record_id,
                metric_name="revenue",
                metric_value=Decimal("1"),
                algorithm_version="sec-v1",
                created_at=context_time,
            )
        )
        connection.execute(
            insert(evidence_item).values(
                id=evidence_id,
                derived_metric_id=context_metric_id,
                provider="SEC",
                conflict=False,
                content={"symbol": "NVDA"},
                created_at=context_time,
            )
        )
        connection.execute(
            insert(investment_thesis).values(
                id=thesis_id,
                symbol="NVDA",
                as_of=context_time,
                direction="BULLISH",
                summary="Persisted cutoff-safe thesis",
                invalidation_conditions=["Revenue evidence is contradicted"],
                confidence=Decimal("0.7"),
                created_at=context_time,
            )
        )
        connection.execute(
            insert(thesis_evidence_link).values(
                thesis_id=thesis_id,
                evidence_id=evidence_id,
                relation="SUPPORTS",
                weight=Decimal("1"),
                rationale="cutoff-safe evidence",
                created_at=context_time,
            )
        )
        for index, run_id in enumerate(run_ids):
            _insert_monitor_run(connection, run_id=run_id, cutoff=cutoff, index=index)

    def execute(run_id: UUID) -> bool:
        return execute_market_monitor_run(isolated_database_url, str(run_id))

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(execute, run_ids))

    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(alert_event)).scalar_one() == 1
        alert_id = connection.execute(select(alert_event.c.id)).scalar_one()
        assert (
            connection.execute(
                select(alert_thesis_link.c.thesis_id).where(
                    alert_thesis_link.c.alert_event_id == alert_id
                )
            ).scalar_one()
            == thesis_id
        )
        assert (
            connection.execute(select(func.count()).select_from(notification_outbox)).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(alert_explanation.c.status).where(alert_explanation.c.alert_id == alert_id)
            ).scalar_one()
            == "DISABLED"
        )
        completion_events = connection.execute(
            select(agent_event.c.payload)
            .where(agent_event.c.event_type == "monitor.completed")
            .order_by(agent_event.c.run_id)
        ).scalars()
        assert sorted(payload["alerts_created"] for payload in completion_events) == [0, 1]
    engine.dispose()


def test_market_monitor_records_unavailable_thesis_context_without_fabricating_alert(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    start = datetime(2026, 9, 18, 15, 30, tzinfo=UTC)
    cutoff = start + timedelta(minutes=6)
    run_id = uuid4()
    with engine.begin() as connection:
        _seed_alert_bars(connection, start=start, symbol="MSFT")
        _insert_monitor_run(connection, run_id=run_id, cutoff=cutoff, index=3)

    assert execute_market_monitor_run(isolated_database_url, str(run_id))

    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(alert_event)).scalar_one() == 0
        payload = connection.execute(
            select(agent_event.c.payload).where(
                agent_event.c.run_id == run_id,
                agent_event.c.event_type == "monitor.completed",
            )
        ).scalar_one()
        assert payload["symbols_evaluated"] == 1
        assert payload["alerts_created"] == 0
        assert payload["unavailable_context"] == 1
    engine.dispose()
