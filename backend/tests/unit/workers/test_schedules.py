from datetime import UTC, date, datetime, time

import pytest
from stock_platform.workers import ingestion_tasks
from stock_platform.workers.celery_app import celery_app
from stock_platform.workers.schedules import (
    beat_schedule,
    is_market_cutoff,
    is_market_session,
    schedule_key,
)


def test_market_session_uses_new_york_boundaries_and_explicit_closures() -> None:
    before_open = datetime(2026, 8, 17, 13, 29, tzinfo=UTC)
    at_open = datetime(2026, 8, 17, 13, 30, tzinfo=UTC)
    before_close = datetime(2026, 8, 17, 19, 59, tzinfo=UTC)
    at_close = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)

    assert is_market_session(before_open) is False
    assert is_market_session(at_open) is True
    assert is_market_session(before_close) is True
    assert is_market_session(at_close) is False
    assert is_market_session(datetime(2026, 8, 16, 15, tzinfo=UTC)) is False
    assert is_market_session(at_open, closures={date(2026, 8, 17)}) is False
    with pytest.raises(ValueError, match="timezone-aware"):
        is_market_session(datetime(2026, 8, 17, 13, 30))


def test_schedule_keys_are_stable_per_job_and_cutoff() -> None:
    cutoff = datetime(2026, 8, 17, 20, 15, tzinfo=UTC)

    assert schedule_key("daily-research", cutoff, symbol="nvda") == (
        "daily-research:NVDA:2026-08-17T20:15:00+00:00"
    )
    assert schedule_key("portfolio", cutoff) == "portfolio:2026-08-17T20:15:00+00:00"


def test_market_cutoffs_follow_new_york_daylight_saving_time() -> None:
    assert is_market_cutoff(datetime(2026, 8, 17, 20, 15, tzinfo=UTC), time(16, 15))
    assert not is_market_cutoff(datetime(2026, 1, 20, 20, 15, tzinfo=UTC), time(16, 15))
    assert is_market_cutoff(datetime(2026, 1, 20, 21, 15, tzinfo=UTC), time(16, 15))


def test_celery_is_at_least_once_without_authoritative_result_backend() -> None:
    assert celery_app.conf.task_ignore_result is True
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.task_routes[
        "stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job"
    ] == {"queue": "ingestion-low"}
    assert set(beat_schedule) == {
        "daily-research-after-close",
        "intraday-market-monitor",
        "portfolio-fixed-cutoff",
        "weekly-review-after-maturity",
        "recover-queued-runs",
    }
    assert beat_schedule["daily-research-after-close"]["schedule"].hour == {20, 21}
    assert beat_schedule["portfolio-fixed-cutoff"]["schedule"].hour == {20, 21}
    assert 21 in beat_schedule["intraday-market-monitor"]["schedule"].hour
    assert celery_app.conf.beat_schedule["report-minio-orphans"] == {
        "task": "stock_platform.workers.ingestion_tasks.report_minio_orphans",
        "schedule": 3600.0,
    }
    assert celery_app.conf.beat_schedule["dispatch-alpaca-ingestion-jobs"] == {
        "task": "stock_platform.workers.ingestion_tasks.dispatch_alpaca_ingestion_jobs",
        "schedule": 15.0,
    }
    assert celery_app.conf.beat_schedule["schedule-alpaca-watchlist-ingestion"] == {
        "task": "stock_platform.workers.schedules.schedule_alpaca_watchlist_ingestion",
        "schedule": 60.0,
    }
    assert celery_app.conf.beat_schedule["schedule-alpaca-daily-ingestion"]["task"] == (
        "stock_platform.workers.schedules.schedule_alpaca_daily_ingestion"
    )
    assert (
        celery_app.tasks["stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job"]
        is not None
    )
    assert celery_app.tasks["stock_platform.workers.ingestion_tasks.persist_alpaca_stream_event"]
    assert celery_app.tasks[
        "stock_platform.workers.ingestion_tasks.reconcile_alpaca_stream_archive"
    ]
    assert celery_app.tasks["stock_platform.workers.schedules.schedule_alpaca_reconnect_ingestion"]
    assert celery_app.tasks["stock_platform.workers.schedules.schedule_alpaca_bounded_backfill"]


def test_documented_worker_consumes_the_low_priority_ingestion_queue() -> None:
    recovery = open("scripts/verify-recovery.sh", encoding="utf-8").read()
    runbook = open("docs/runbooks/stuck-run.md", encoding="utf-8").read()

    assert "--queues=celery,ingestion-low" in recovery
    assert "--queues=celery,ingestion-low" in runbook


def test_alpaca_stream_has_managed_operator_entrypoint() -> None:
    makefile = open("Makefile", encoding="utf-8").read()
    runbook = open("docs/runbooks/provider-outage.md", encoding="utf-8").read()

    assert "alpaca-stream:" in makefile
    assert "scripts/run_alpaca_stream.py" in makefile
    assert "restart-on-failure" in runbook
    assert "stream.data.alpaca.markets/v2/{iex|sip}" in runbook


def test_orphan_reporting_uses_one_bounded_summary() -> None:
    reporter = getattr(ingestion_tasks, "record_orphan_inventory", None)
    assert reporter is not None, "orphan reporting must aggregate and bound log volume"
    orphaned = tuple(f"raw/{index:02d}.json" for index in range(25))
    warnings: list[tuple[str, tuple[object, ...]]] = []

    assert (
        reporter(
            orphaned,
            warning=lambda message, *args: warnings.append((message, args)),
        )
        == 25
    )

    assert len(warnings) == 1
    message, arguments = warnings[0]
    assert message == "unreferenced MinIO raw objects: count=%d sample=%s"
    assert arguments[0] == 25
    assert arguments[1] == orphaned[:20]
