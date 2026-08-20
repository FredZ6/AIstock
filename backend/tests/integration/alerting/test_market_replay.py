import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.engine import Connection, Engine, make_url
from stock_platform.application.alerting.outbox import (
    AlertContext,
    NotificationChannel,
    OutboxDispatcher,
    PostgresAlertStore,
)
from stock_platform.application.alerting.rules import AlertRule, RuleThresholds
from stock_platform.infrastructure.db.models.tables import (
    alert_event,
    alert_explanation,
    alert_metric,
    alert_thesis_link,
    investment_thesis,
    notification_outbox,
)
from stock_platform.infrastructure.messaging.market_stream import RedisMarketStream
from stock_platform.infrastructure.providers.alpaca_stream import AlpacaStreamNormalizer
from stock_platform.workers.alert_worker import AlertWorker

START = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)


def raw_bar(
    minute: int,
    *,
    close: str,
    volume: str,
    open_: str = "100",
    suffix: str = "",
    symbol: str = "NVDA",
) -> bytes:
    event_time = START + timedelta(minutes=minute)
    return json.dumps(
        {
            "T": "b",
            "S": symbol,
            "t": event_time.isoformat().replace("+00:00", "Z"),
            "o": open_,
            "h": str(Decimal(close) + Decimal("0.2")),
            "l": "99.8",
            "c": close,
            "v": volume,
            "pc": "99",
            "fixture_suffix": suffix,
        },
        separators=(",", ":"),
    ).encode()


@pytest.fixture(scope="module")
def alert_engine() -> Iterator[Engine]:
    base_url = make_url(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform",
        )
    )
    database_name = f"stock_platform_alert_{uuid4().hex}"
    assert base_url.host is not None
    assert base_url.port is not None
    assert base_url.username is not None
    with psycopg.connect(
        host=base_url.host,
        port=base_url.port,
        user=base_url.username,
        password=base_url.password,
        dbname="postgres",
        autocommit=True,
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))

    database_url = base_url.set(database=database_name).render_as_string(hide_password=False)
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    instance = create_engine(database_url)
    try:
        yield instance
    finally:
        instance.dispose()
        with psycopg.connect(
            host=base_url.host,
            port=base_url.port,
            user=base_url.username,
            password=base_url.password,
            dbname="postgres",
            autocommit=True,
        ) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))


@pytest.fixture
def alert_runtime(alert_engine: Engine) -> Iterator[tuple[Connection, RedisMarketStream, str]]:
    stream_name = f"market-bars-{uuid4().hex}"
    group = f"alert-workers-{uuid4().hex}"
    stream = RedisMarketStream(
        url=os.getenv("REDIS_URL", "redis://localhost:56379/0"),
        stream_name=stream_name,
    )
    stream.create_consumer_group(group)
    with alert_engine.connect() as connection:
        try:
            yield connection, stream, group
        finally:
            stream.delete()
            stream.close()


class RecordingAdapter:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls = 0

    def send(self, payload: dict[str, object]) -> None:
        self.calls += 1
        assert payload["product_boundary"] == "research signal for a paper portfolio"
        if self.fail_first and self.calls == 1:
            raise TimeoutError("fixture notification timeout")


def test_market_replay_is_deterministic_idempotent_and_delivers_without_llm(
    alert_runtime: tuple[Connection, RedisMarketStream, str],
    alert_engine: Engine,
) -> None:
    connection, stream, group = alert_runtime
    thesis_id = uuid4()
    connection.execute(
        insert(investment_thesis).values(
            id=thesis_id,
            symbol="NVDA",
            as_of=START - timedelta(days=1),
            direction="BULLISH",
            summary="Frozen fixture thesis",
            catalysts=["Volume-backed breakout"],
            risks=["Failed breakout"],
            invalidation_conditions=["Price closes below prior range"],
            horizon="20_TRADING_DAYS",
            confidence=Decimal("0.60"),
        )
    )
    store = PostgresAlertStore(connection)
    rule = AlertRule(
        rule_id="market-anomaly-v1",
        version="alert-policy-v1",
        thresholds=RuleThresholds(
            five_minute_return=Decimal("0.04"),
            relative_volume=Decimal("3"),
            return_zscore=Decimal("1"),
            volume_zscore=Decimal("1"),
            volatility_zscore=Decimal("1"),
            gap=Decimal("0.02"),
        ),
        minimum_conditions=3,
    )
    worker = AlertWorker(
        stream=stream,
        store=store,
        rule=rule,
        context_resolver=lambda _symbol, _time: AlertContext(
            thesis_id=thesis_id,
            invalidation_condition="Price closes below prior range",
            evidence_id=None,
        ),
        explainer=None,
        channels=(
            NotificationChannel.TELEGRAM,
            NotificationChannel.FEISHU,
            NotificationChannel.EMAIL,
        ),
    )
    normalizer = AlpacaStreamNormalizer()
    payloads = (
        raw_bar(0, close="100", volume="100"),
        raw_bar(1, close="100.2", volume="110"),
        raw_bar(2, close="99.9", volume="90"),
        raw_bar(3, close="100.3", volume="105"),
        raw_bar(4, close="100.1", volume="95"),
        raw_bar(5, close="106", volume="600"),
    )
    for minute, payload in enumerate(payloads):
        item = normalizer.normalize(
            payload,
            received_at=START + timedelta(minutes=minute, seconds=2),
        )
        stream.publish(item)

    messages = stream.read(group=group, consumer="worker-a", count=20, block_ms=10)
    assert len(messages) == len(payloads)
    results = [worker.process(message, group=group) for message in messages]

    assert results[-1].alert_id is not None
    alert_id = results[-1].alert_id
    stored = connection.execute(
        select(alert_event.c.id, alert_event.c.metrics, alert_event.c.severity).where(
            alert_event.c.id == alert_id
        )
    ).one()
    first_metrics = stored.metrics
    assert stored.severity in {"HIGH", "CRITICAL"}
    assert first_metrics["five_minute_return"] == "0.06"
    assert first_metrics["relative_volume"] == "6"
    assert (
        connection.execute(
            select(func.count())
            .select_from(alert_thesis_link)
            .where(alert_thesis_link.c.alert_event_id == alert_id)
        ).scalar_one()
        == 1
    )
    assert (
        connection.execute(
            select(func.count())
            .select_from(alert_metric)
            .where(alert_metric.c.alert_id == alert_id)
        ).scalar_one()
        >= 7
    )
    assert (
        connection.execute(
            select(func.count())
            .select_from(notification_outbox)
            .where(notification_outbox.c.alert_id == alert_id)
        ).scalar_one()
        == 1
    )
    assert (
        connection.execute(
            select(alert_explanation.c.status).where(alert_explanation.c.alert_id == alert_id)
        ).scalar_one()
        == "DISABLED"
    )
    assert stream.pending_count(group=group) == 0
    with alert_engine.connect() as verifier:
        assert (
            verifier.execute(
                select(func.count()).select_from(alert_event).where(alert_event.c.id == alert_id)
            ).scalar_one()
            == 1
        )

    repeated = normalizer.normalize(
        payloads[-1], received_at=START + timedelta(minutes=5, seconds=2)
    )
    stream.publish(repeated)
    duplicate = stream.read(group=group, consumer="worker-b", count=1, block_ms=10)[0]
    duplicate_result = worker.process(duplicate, group=group)

    assert duplicate_result.alert_id == alert_id
    assert (
        connection.execute(
            select(func.count()).select_from(alert_event).where(alert_event.c.id == alert_id)
        ).scalar_one()
        == 1
    )
    assert (
        connection.execute(
            select(alert_event.c.metrics).where(alert_event.c.id == alert_id)
        ).scalar_one()
        == first_metrics
    )
    assert (
        connection.execute(
            select(func.count())
            .select_from(notification_outbox)
            .where(notification_outbox.c.alert_id == alert_id)
        ).scalar_one()
        == 1
    )

    out_of_order = normalizer.normalize(
        raw_bar(2, close="120", volume="900", suffix="late"),
        received_at=START + timedelta(minutes=6),
    )
    stream.publish(out_of_order)
    late_message = stream.read(group=group, consumer="worker-a", count=1, block_ms=10)[0]
    late_result = worker.process(late_message, group=group)
    assert late_result.outcome == "OUT_OF_ORDER"
    assert connection.execute(select(func.count()).select_from(alert_event)).scalar_one() == 1
    assert stream.pending_count(group=group) == 0

    telegram = RecordingAdapter()
    feishu = RecordingAdapter(fail_first=True)
    email = RecordingAdapter()
    dispatcher = OutboxDispatcher(
        store=store,
        adapters={
            NotificationChannel.TELEGRAM: telegram,
            NotificationChannel.FEISHU: feishu,
            NotificationChannel.EMAIL: email,
        },
        clock=lambda: START + timedelta(minutes=10),
    )
    dispatcher.dispatch_due()
    assert (
        connection.execute(
            select(notification_outbox.c.status).where(notification_outbox.c.alert_id == alert_id)
        ).scalar_one()
        == "RETRY"
    )
    dispatcher.dispatch_due()
    assert (
        connection.execute(
            select(notification_outbox.c.status).where(notification_outbox.c.alert_id == alert_id)
        ).scalar_one()
        == "DELIVERED"
    )
    assert telegram.calls == 1
    assert feishu.calls == 2
    assert email.calls == 1


def test_pending_stream_entry_is_claimed_by_replacement_consumer(
    alert_runtime: tuple[Connection, RedisMarketStream, str],
) -> None:
    _connection, stream, group = alert_runtime
    normalizer = AlpacaStreamNormalizer()
    item = normalizer.normalize(
        raw_bar(10, close="101", volume="200", symbol="AMD"),
        received_at=START + timedelta(minutes=10, seconds=2),
    )
    stream.publish(item)

    original = stream.read(group=group, consumer="worker-crashed", count=1, block_ms=10)
    reclaimed = stream.read(
        group=group,
        consumer="worker-replacement",
        count=1,
        block_ms=10,
        reclaim_idle_ms=0,
    )

    assert reclaimed == original
    assert stream.pending_count(group=group) == 1
    stream.acknowledge(group=group, message_id=reclaimed[0].id)
    assert stream.pending_count(group=group) == 0


def test_recent_bars_enforces_available_at_cutoff(
    alert_runtime: tuple[Connection, RedisMarketStream, str],
) -> None:
    connection, _stream, _group = alert_runtime
    normalizer = AlpacaStreamNormalizer()
    store = PostgresAlertStore(connection)
    visible = normalizer.normalize(
        raw_bar(20, close="100", volume="100", symbol="CUT"),
        received_at=START + timedelta(minutes=20, seconds=2),
    )
    future_available = normalizer.normalize(
        raw_bar(21, close="105", volume="500", symbol="CUT"),
        received_at=START + timedelta(minutes=30),
    )
    store.persist_bar(visible)
    store.persist_bar(future_available)
    store.commit()

    records = store.recent_bars(
        symbol="CUT",
        through=future_available.event_time,
        available_by=START + timedelta(minutes=25),
        limit=10,
    )

    assert records == (visible,)
