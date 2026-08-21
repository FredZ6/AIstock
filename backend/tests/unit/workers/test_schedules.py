from datetime import UTC, date, datetime, time

import pytest
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
