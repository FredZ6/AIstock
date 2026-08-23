from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st
from stock_platform.application.market_data.repositories import is_visible_at

aware_datetimes = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 1, 1),
    timezones=st.just(UTC),
)


@given(event_time=aware_datetimes, available_at=aware_datetimes, decision_time=aware_datetimes)
def test_visibility_requires_both_event_and_availability_cutoffs(
    event_time: datetime, available_at: datetime, decision_time: datetime
) -> None:
    assert is_visible_at(
        event_time=event_time,
        available_at=available_at,
        decision_time=decision_time,
    ) is (event_time <= decision_time and available_at <= decision_time)


def test_visibility_includes_exact_boundaries() -> None:
    cutoff = datetime(2026, 8, 23, 14, tzinfo=UTC)

    assert is_visible_at(event_time=cutoff, available_at=cutoff, decision_time=cutoff)
