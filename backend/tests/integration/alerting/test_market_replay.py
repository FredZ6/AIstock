import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Lock
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.engine import Connection, Engine, make_url
from stock_platform.application.alerting.features import GapContext
from stock_platform.application.alerting.outbox import (
    AlertContext,
    BarPersistence,
    NotificationChannel,
    OutboxDispatcher,
    OutboxMessage,
    PostgresAlertContextResolver,
    PostgresAlertStore,
)
from stock_platform.application.alerting.rules import AlertRule, RuleThresholds
from stock_platform.infrastructure.db.models.tables import (
    alert_event,
    alert_explanation,
    alert_metric,
    alert_thesis_link,
    derived_metric,
    evidence_item,
    investment_thesis,
    market_bar,
    normalized_record,
    notification_outbox,
    raw_data_object,
    thesis_evidence_link,
)
from stock_platform.infrastructure.messaging.market_stream import RedisMarketStream
from stock_platform.infrastructure.providers.alpaca_stream import AlpacaStreamNormalizer
from stock_platform.infrastructure.providers.object_store import MinioRawObjectStore
from stock_platform.settings import Settings
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
            "fixture_suffix": suffix,
        },
        separators=(",", ":"),
    ).encode()


def add_research_context(
    connection: Connection,
    *,
    symbol: str,
    as_of: datetime,
    created_at: datetime,
    suffix: str,
) -> tuple[UUID, UUID]:
    raw_id = uuid4()
    normalized_id = uuid4()
    metric_id = uuid4()
    evidence_id = uuid4()
    thesis_id = uuid4()
    connection.execute(
        insert(raw_data_object).values(
            id=raw_id,
            provider="FIXTURE",
            feed_type="company_facts",
            event_time=created_at - timedelta(minutes=1),
            available_at=created_at,
            ingested_at=created_at,
            content_hash=(suffix * 64)[:64],
            raw_object_key=f"fixture/context/{suffix}.json",
            created_at=created_at,
        )
    )
    connection.execute(
        insert(normalized_record).values(
            id=normalized_id,
            raw_data_object_id=raw_id,
            record_type="company_fact",
            record_key=symbol,
            normalization_version="fixture-v1",
            payload={"symbol": symbol},
            created_at=created_at,
        )
    )
    connection.execute(
        insert(derived_metric).values(
            id=metric_id,
            normalized_record_id=normalized_id,
            metric_name="fixture_metric",
            metric_value=Decimal("1"),
            algorithm_version="fixture-v1",
            created_at=created_at,
        )
    )
    connection.execute(
        insert(evidence_item).values(
            id=evidence_id,
            derived_metric_id=metric_id,
            provider="FIXTURE",
            coverage=Decimal("1"),
            conflict=False,
            content={"symbol": symbol},
            created_at=created_at,
        )
    )
    connection.execute(
        insert(investment_thesis).values(
            id=thesis_id,
            symbol=symbol,
            as_of=as_of,
            direction="BULLISH",
            summary=f"{suffix} thesis",
            catalysts=[],
            risks=[],
            invalidation_conditions=[f"{suffix} invalidation"],
            horizon="20_TRADING_DAYS",
            confidence=Decimal("0.60"),
            created_at=created_at,
        )
    )
    connection.execute(
        insert(thesis_evidence_link).values(
            thesis_id=thesis_id,
            evidence_id=evidence_id,
            relation="SUPPORTS",
            weight=Decimal("1"),
            rationale="fixture evidence",
            created_at=created_at,
        )
    )
    return thesis_id, evidence_id


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


@pytest.fixture(scope="module")
def minio_raw_store() -> MinioRawObjectStore:
    return MinioRawObjectStore.from_settings(Settings(environment="test"))


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
    minio_raw_store: MinioRawObjectStore,
) -> None:
    connection, stream, group = alert_runtime
    thesis_id, evidence_id = add_research_context(
        connection,
        symbol="NVDA",
        as_of=START - timedelta(days=1),
        created_at=START - timedelta(days=1),
        suffix="m",
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
        context_resolver=PostgresAlertContextResolver(connection),
        explainer=None,
        channels=(
            NotificationChannel.TELEGRAM,
            NotificationChannel.FEISHU,
            NotificationChannel.EMAIL,
        ),
    )
    normalizer = AlpacaStreamNormalizer(raw_store=minio_raw_store)
    for context_bar in (
        normalizer.normalize(
            raw_bar(-1111, close="99", volume="100"),
            received_at=START - timedelta(minutes=1111) + timedelta(seconds=2),
        ),
        normalizer.normalize(
            raw_bar(-60, close="100", volume="100", open_="100"),
            received_at=START - timedelta(minutes=60) + timedelta(seconds=2),
        ),
    ):
        assert store.persist_bar(context_bar) is BarPersistence.NEW
    store.commit()
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
            select(alert_thesis_link.c.evidence_id).where(
                alert_thesis_link.c.alert_event_id == alert_id
            )
        ).scalar_one()
        == evidence_id
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
    minio_raw_store: MinioRawObjectStore,
) -> None:
    _connection, stream, group = alert_runtime
    normalizer = AlpacaStreamNormalizer(raw_store=minio_raw_store)
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
    minio_raw_store: MinioRawObjectStore,
) -> None:
    connection, _stream, _group = alert_runtime
    normalizer = AlpacaStreamNormalizer(raw_store=minio_raw_store)
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


def test_updated_bar_is_point_in_time_canonical_and_preserves_conflict(
    alert_runtime: tuple[Connection, RedisMarketStream, str],
    minio_raw_store: MinioRawObjectStore,
) -> None:
    connection, _stream, _group = alert_runtime
    normalizer = AlpacaStreamNormalizer(raw_store=minio_raw_store)
    store = PostgresAlertStore(connection)
    original_payload = raw_bar(30, close="100", volume="100", symbol="REV")
    corrected_payload = raw_bar(
        30, close="103", volume="120", suffix="correction", symbol="REV"
    ).replace(b'"T":"b"', b'"T":"u"')
    original = normalizer.normalize(
        original_payload,
        received_at=START + timedelta(minutes=30, seconds=2),
    )
    corrected = replace(
        normalizer.normalize(
            corrected_payload,
            received_at=START + timedelta(minutes=31),
        ),
        conflict=True,
    )

    assert store.persist_bar(original) is BarPersistence.NEW
    assert store.persist_bar(corrected) is BarPersistence.NEW
    store.commit()

    before_correction = store.recent_bars(
        symbol="REV",
        through=original.event_time,
        available_by=original.available_at,
        limit=10,
    )
    after_correction = store.recent_bars(
        symbol="REV",
        through=corrected.event_time,
        available_by=corrected.available_at,
        limit=10,
    )
    assert before_correction == (original,)
    assert after_correction == (corrected,)
    assert after_correction[0].conflict is True
    assert (
        connection.execute(
            select(func.count()).select_from(market_bar).where(market_bar.c.symbol == "REV")
        ).scalar_one()
        == 2
    )


def test_out_of_order_bar_still_has_complete_database_lineage(
    alert_runtime: tuple[Connection, RedisMarketStream, str],
    minio_raw_store: MinioRawObjectStore,
) -> None:
    connection, _stream, _group = alert_runtime
    normalizer = AlpacaStreamNormalizer(raw_store=minio_raw_store)
    store = PostgresAlertStore(connection)
    newest = normalizer.normalize(
        raw_bar(41, close="101", volume="100", symbol="LATE"),
        received_at=START + timedelta(minutes=41, seconds=2),
    )
    late = normalizer.normalize(
        raw_bar(40, close="99", volume="100", symbol="LATE", suffix="late"),
        received_at=START + timedelta(minutes=42),
    )

    assert store.persist_bar(newest) is BarPersistence.NEW
    assert store.persist_bar(late) is BarPersistence.OUT_OF_ORDER
    store.commit()

    raw_id = connection.execute(
        select(raw_data_object.c.id).where(raw_data_object.c.content_hash == late.content_hash)
    ).scalar_one()
    assert (
        connection.execute(
            select(func.count())
            .select_from(normalized_record)
            .where(normalized_record.c.raw_data_object_id == raw_id)
        ).scalar_one()
        == 1
    )
    assert (
        connection.execute(
            select(func.count())
            .select_from(market_bar)
            .where(market_bar.c.raw_data_object_id == raw_id)
        ).scalar_one()
        == 1
    )
    assert connection.execute(
        select(market_bar.c.coverage, market_bar.c.session).where(
            market_bar.c.raw_data_object_id == raw_id
        )
    ).one() == ("IEX", "REGULAR")


def test_alpaca_raw_bytes_exist_in_minio_before_database_lineage(
    minio_raw_store: MinioRawObjectStore,
) -> None:
    from minio import Minio

    settings = Settings(environment="test")
    raw = raw_bar(50, close="101", volume="100", symbol="OBJ")
    item = AlpacaStreamNormalizer(raw_store=minio_raw_store).normalize(
        raw,
        received_at=START + timedelta(minutes=50, seconds=2),
    )
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    response = client.get_object(settings.minio_bucket, item.raw_object_key)
    try:
        assert response.read() == raw
    finally:
        response.close()
        response.release_conn()


def test_gap_context_uses_true_regular_session_open_and_previous_close(
    alert_runtime: tuple[Connection, RedisMarketStream, str],
    minio_raw_store: MinioRawObjectStore,
) -> None:
    connection, _stream, _group = alert_runtime
    normalizer = AlpacaStreamNormalizer(raw_store=minio_raw_store)
    store = PostgresAlertStore(connection)
    previous_close = normalizer.normalize(
        raw_bar(-1111, close="100", volume="100", symbol="GAP"),
        received_at=START - timedelta(minutes=1111) + timedelta(seconds=2),
    )
    session_open = normalizer.normalize(
        raw_bar(-60, close="101", volume="100", open_="101", symbol="GAP"),
        received_at=START - timedelta(minutes=60) + timedelta(seconds=2),
    )
    intraday = normalizer.normalize(
        raw_bar(0, close="102", volume="100", symbol="GAP"),
        received_at=START + timedelta(seconds=2),
    )
    for item in (previous_close, session_open, intraday):
        assert store.persist_bar(item) is BarPersistence.NEW
    store.commit()

    assert store.gap_context(
        symbol="GAP",
        through=intraday.event_time,
        available_by=intraday.ingested_at,
    ) == GapContext(session_open=Decimal("101"), previous_close=Decimal("100"))


def test_context_resolver_selects_latest_cutoff_safe_thesis_and_evidence(
    alert_runtime: tuple[Connection, RedisMarketStream, str],
) -> None:
    connection, _stream, _group = alert_runtime

    eligible_thesis, eligible_evidence = add_research_context(
        connection,
        symbol="CTX",
        as_of=START - timedelta(minutes=2),
        created_at=START - timedelta(minutes=2),
        suffix="a",
    )
    add_research_context(
        connection,
        symbol="CTX",
        as_of=START + timedelta(minutes=1),
        created_at=START + timedelta(minutes=1),
        suffix="b",
    )
    add_research_context(
        connection,
        symbol="OTHER",
        as_of=START - timedelta(minutes=1),
        created_at=START - timedelta(minutes=1),
        suffix="c",
    )
    connection.commit()

    context = PostgresAlertContextResolver(connection)("CTX", START)

    assert context == AlertContext(
        thesis_id=eligible_thesis,
        invalidation_condition="a invalidation",
        evidence_id=eligible_evidence,
    )


def test_concurrent_dispatchers_claim_one_outbox_row_once(alert_engine: Engine) -> None:
    alert_id = uuid4()
    alert_key = f"CONCURRENT:{alert_id}"
    with alert_engine.begin() as connection:
        connection.execute(
            insert(alert_event).values(
                id=alert_id,
                alert_key=alert_key,
                symbol="LOCK",
                event_time=START,
                rule_id="fixture-rule",
                rule_version="fixture-v1",
                severity="HIGH",
                materiality=Decimal("0.8"),
                conditions=["fixture"],
                metrics={},
                data_quality={},
            )
        )
        connection.execute(
            insert(notification_outbox).values(
                id=uuid4(),
                alert_id=alert_id,
                alert_key=alert_key,
                payload={"alert_key": alert_key},
                channels=["EMAIL"],
                channel_states={"EMAIL": {"status": "PENDING", "attempts": 0, "last_error": None}},
                status="PENDING",
                attempts=0,
                next_attempt_at=START,
            )
        )

    barrier = Barrier(2)
    lock = Lock()
    delivery_calls = 0

    class BarrierStore(PostgresAlertStore):
        def due(self, now: datetime) -> tuple[OutboxMessage, ...]:
            messages = super().due(now)
            barrier.wait(timeout=5)
            return messages

    class ConcurrentAdapter:
        def send(self, payload: dict[str, object]) -> None:
            nonlocal delivery_calls
            assert payload["alert_key"] == alert_key
            with lock:
                delivery_calls += 1

    adapter = ConcurrentAdapter()

    def dispatch() -> int:
        with alert_engine.connect() as connection:
            return OutboxDispatcher(
                store=BarrierStore(connection),
                adapters={NotificationChannel.EMAIL: adapter},
                clock=lambda: START + timedelta(minutes=1),
            ).dispatch_due()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _index: dispatch(), range(2)))

    assert sum(results) == 1
    assert delivery_calls == 1
