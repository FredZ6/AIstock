from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, select
from stock_platform.application.market_data.policy import EntitlementSnapshot, PolicyOutcome
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    FeedType,
    MarketDataCoverage,
    MarketSession,
)
from stock_platform.infrastructure.db.models.tables import ingestion_job, security, watchlist_item
from stock_platform.infrastructure.ingestion.job_store import IngestionJobStore
from stock_platform.workers.ingestion_tasks import (
    BackfillPriority,
    BarTimeframe,
    plan_alpaca_backfill,
    plan_reconnect_gap_fill,
    resume_alpaca_page,
)
from stock_platform.workers.schedules import (
    schedule_alpaca_backfills,
    schedule_alpaca_daily_jobs,
    schedule_alpaca_reconnect_gap_fill,
    schedule_alpaca_watchlist_jobs,
)

NOW = datetime(2026, 8, 24, 16, tzinfo=UTC)


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.mark.parametrize(
    ("dataset", "timeframe", "start", "maximum", "chunk"),
    (
        (
            FeedType.PRICE_BARS,
            BarTimeframe.DAY,
            NOW - timedelta(days=365),
            timedelta(days=365),
            timedelta(days=30),
        ),
        (
            FeedType.PRICE_BARS,
            BarTimeframe.MINUTE,
            NOW - timedelta(days=90),
            timedelta(days=90),
            timedelta(days=5),
        ),
        (
            FeedType.COMPANY_NEWS,
            None,
            NOW - timedelta(days=365),
            timedelta(days=365),
            timedelta(days=30),
        ),
    ),
)
def test_backfills_are_bounded_low_priority_and_cover_the_window_once(
    dataset: FeedType,
    timeframe: BarTimeframe | None,
    start: datetime,
    maximum: timedelta,
    chunk: timedelta,
) -> None:
    slices = plan_alpaca_backfill(dataset=dataset, timeframe=timeframe, start=start, end=NOW)

    assert slices[0].start == start
    assert slices[-1].end == NOW
    assert all(item.priority is BackfillPriority.LOW for item in slices)
    assert all(item.end - item.start <= chunk for item in slices)
    assert sum((item.end - item.start for item in slices), timedelta()) == maximum
    assert all(left.end == right.start for left, right in zip(slices, slices[1:], strict=False))


def test_backfill_rejects_unbounded_and_naive_windows() -> None:
    with pytest.raises(ValueError, match="bounded"):
        plan_alpaca_backfill(
            dataset=FeedType.PRICE_BARS,
            timeframe=BarTimeframe.MINUTE,
            start=NOW - timedelta(days=90, seconds=1),
            end=NOW,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        plan_alpaca_backfill(
            dataset=FeedType.COMPANY_NEWS,
            timeframe=None,
            start=datetime(2026, 8, 23),
            end=NOW,
        )


def test_pagination_resume_keeps_the_same_window_and_records_cursor() -> None:
    first = plan_alpaca_backfill(
        dataset=FeedType.COMPANY_NEWS,
        timeframe=None,
        start=NOW - timedelta(hours=1),
        end=NOW,
    )[0]
    resumed = resume_alpaca_page(first, next_page_token="opaque-page-2")

    assert resumed.start == first.start
    assert resumed.end == first.end
    assert resumed.page_token == "opaque-page-2"


def test_disconnect_recovery_uses_bounded_rest_gap_fill() -> None:
    recent = plan_reconnect_gap_fill(
        last_event_at=NOW - timedelta(minutes=4),
        reconnected_at=NOW,
    )
    assert recent.start == NOW - timedelta(minutes=4)
    assert recent.end == NOW

    old = plan_reconnect_gap_fill(
        last_event_at=NOW - timedelta(hours=2),
        reconnected_at=NOW,
    )
    assert old.start == NOW - timedelta(minutes=30)
    assert old.end == NOW
    assert old.truncated is True


def test_entitlement_aware_schedule_is_durable_idempotent_and_purpose_safe(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)
    entitlement = EntitlementSnapshot(
        provider="ALPACA",
        coverage=frozenset({MarketDataCoverage.IEX}),
        overnight=False,
        sip_delay=None,
        observed_at=NOW,
        version="alpaca-entitlement-v1",
    )

    research = schedule_alpaca_backfills(
        store,
        symbol="NVDA",
        dataset=FeedType.PRICE_BARS,
        timeframe=BarTimeframe.MINUTE,
        start=NOW - timedelta(hours=2),
        end=NOW,
        purpose=DataPurpose.RESEARCH,
        required_coverage=MarketDataCoverage.SIP,
        session=MarketSession.REGULAR,
        entitlement=entitlement,
        now=NOW,
    )
    replayed = schedule_alpaca_backfills(
        store,
        symbol="NVDA",
        dataset=FeedType.PRICE_BARS,
        timeframe=BarTimeframe.MINUTE,
        start=NOW - timedelta(hours=2),
        end=NOW,
        purpose=DataPurpose.RESEARCH,
        required_coverage=MarketDataCoverage.SIP,
        session=MarketSession.REGULAR,
        entitlement=entitlement,
        now=NOW,
    )
    denied = schedule_alpaca_backfills(
        store,
        symbol="NVDA",
        dataset=FeedType.PRICE_BARS,
        timeframe=BarTimeframe.MINUTE,
        start=NOW - timedelta(hours=2),
        end=NOW,
        purpose=DataPurpose.PAPER_EXECUTION,
        required_coverage=MarketDataCoverage.SIP,
        session=MarketSession.REGULAR,
        entitlement=entitlement,
        now=NOW,
    )

    assert research.decision.outcome is PolicyOutcome.ALLOWED_WITH_GAP
    assert research.job_ids == replayed.job_ids
    assert len(research.job_ids) == 1
    assert denied.decision.outcome is PolicyOutcome.DENIED_NO_ACTION
    assert denied.job_ids == ()
    with engine.connect() as connection:
        rows = connection.execute(
            select(ingestion_job.c.request_payload, ingestion_job.c.purpose).order_by(
                ingestion_job.c.window_start
            )
        ).all()
    assert len(rows) == 1
    assert all(row.purpose == "RESEARCH" for row in rows)
    assert all(row.request_payload["request"]["coverage"] == "IEX" for row in rows)
    assert all(
        row.request_payload["request"]["entitlement"]["version"] == "alpaca-entitlement-v1"
        for row in rows
    )
    assert all(row.request_payload["request"]["gap_kind"] == "UNAVAILABLE" for row in rows)
    engine.dispose()


def test_stream_reconnect_enqueues_bounded_rest_gap_fill(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    entitlement = EntitlementSnapshot(
        provider="ALPACA",
        coverage=frozenset({MarketDataCoverage.IEX}),
        overnight=False,
        sip_delay=None,
        observed_at=NOW,
        version="alpaca-entitlement-v1",
    )

    scheduled = schedule_alpaca_reconnect_gap_fill(
        IngestionJobStore(engine),
        symbol="NVDA",
        last_event_at=NOW - timedelta(hours=2),
        reconnected_at=NOW,
        purpose=DataPurpose.REALTIME_CONTEXT,
        required_coverage=MarketDataCoverage.IEX,
        session=MarketSession.REGULAR,
        entitlement=entitlement,
    )

    assert scheduled.recovery.truncated is True
    assert scheduled.recovery.start == NOW - timedelta(minutes=30)
    assert len(scheduled.scheduled.job_ids) == 1
    with engine.connect() as connection:
        row = connection.execute(select(ingestion_job)).mappings().one()
    assert row["window_start"] == NOW - timedelta(minutes=30)
    assert row["window_end"] == NOW
    engine.dispose()


def test_watchlist_scheduler_creates_runtime_jobs_only_from_explicit_entitlement(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    with engine.begin() as connection:
        security_id = connection.execute(
            insert(security).values(instrument_type="EQUITY").returning(security.c.id)
        ).scalar_one()
        connection.execute(
            insert(watchlist_item).values(
                security_id=security_id,
                symbol="NVDA",
                daily_research=True,
                intraday_monitoring=True,
                thresholds={},
                updated_at=NOW,
            )
        )
    entitlement = EntitlementSnapshot(
        provider="ALPACA",
        coverage=frozenset({MarketDataCoverage.IEX}),
        overnight=False,
        sip_delay=None,
        observed_at=NOW,
        version="operator-verified-v1",
    )

    assert schedule_alpaca_watchlist_jobs(engine, entitlement=entitlement, now=NOW) == 1
    refreshed_entitlement = EntitlementSnapshot(
        provider="ALPACA",
        coverage=entitlement.coverage,
        overnight=False,
        sip_delay=None,
        observed_at=NOW + timedelta(seconds=30),
        version=entitlement.version,
    )
    assert (
        schedule_alpaca_watchlist_jobs(
            engine,
            entitlement=refreshed_entitlement,
            now=NOW + timedelta(seconds=30),
        )
        == 1
    )
    with engine.connect() as connection:
        rows = connection.execute(select(ingestion_job)).mappings().all()
    assert len(rows) == 1
    assert rows[0]["purpose"] == "REALTIME_CONTEXT"
    assert rows[0]["request_payload"]["request"]["coverage"] == "IEX"
    assert rows[0]["request_payload"]["request"]["entitlement"]["version"] == "operator-verified-v1"
    engine.dispose()


def test_daily_scheduler_admits_bars_and_news_from_daily_research_watchlist(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    with engine.begin() as connection:
        security_id = connection.execute(
            insert(security).values(instrument_type="EQUITY").returning(security.c.id)
        ).scalar_one()
        connection.execute(
            insert(watchlist_item).values(
                security_id=security_id,
                symbol="NVDA",
                daily_research=True,
                intraday_monitoring=False,
                thresholds={},
                updated_at=NOW,
            )
        )
    entitlement = EntitlementSnapshot(
        provider="ALPACA",
        coverage=frozenset({MarketDataCoverage.IEX}),
        overnight=False,
        sip_delay=None,
        observed_at=NOW,
        version="operator-verified-v1",
    )

    assert schedule_alpaca_daily_jobs(engine, entitlement=entitlement, now=NOW) == 2
    assert (
        schedule_alpaca_daily_jobs(
            engine,
            entitlement=entitlement,
            now=NOW + timedelta(minutes=30),
        )
        == 2
    )
    with engine.connect() as connection:
        jobs = connection.execute(select(ingestion_job)).mappings().all()
    assert {job["dataset"] for job in jobs} == {"price_bars", "company_news"}
    assert len(jobs) == 2
    assert {job["request_payload"]["request"]["timeframe"] for job in jobs} == {
        "1Day",
        None,
    }
    engine.dispose()
