from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from stock_platform.domain.common.time import PointInTimeRecord, require_aware


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        require_aware(datetime(2026, 8, 17, 12, 0))


def test_point_in_time_fields_are_not_substituted() -> None:
    event_time = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    available_at = event_time + timedelta(minutes=2)
    ingested_at = available_at + timedelta(seconds=30)

    record = PointInTimeRecord(
        event_time=event_time,
        available_at=available_at,
        ingested_at=ingested_at,
    )

    assert record.event_time == event_time
    assert record.available_at == available_at
    assert record.ingested_at == ingested_at


def test_point_in_time_fields_must_be_chronological() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="event_time <= available_at <= ingested_at"):
        PointInTimeRecord(event_time=now, available_at=now - timedelta(seconds=1), ingested_at=now)


@given(
    available_at=st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2035, 1, 1),
        timezones=st.timezones(),
    ),
    offset=st.integers(min_value=-86_400, max_value=86_400),
)
def test_visibility_is_exactly_available_at_lte_decision_time(
    available_at: datetime, offset: int
) -> None:
    event_time = available_at - timedelta(days=1)
    ingested_at = available_at + timedelta(days=1)
    record = PointInTimeRecord(
        event_time=event_time,
        available_at=available_at,
        ingested_at=ingested_at,
    )
    decision_time = available_at.astimezone(UTC) + timedelta(seconds=offset)

    assert record.is_visible_at(decision_time) is (offset >= 0)


def test_visibility_rejects_naive_decision_time() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    record = PointInTimeRecord(event_time=now, available_at=now, ingested_at=now)
    with pytest.raises(ValueError, match="timezone-aware"):
        record.is_visible_at(datetime(2026, 8, 17, 12, 0))
