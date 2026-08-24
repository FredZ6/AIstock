from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st
from stock_platform.application.market_data import repositories
from stock_platform.application.market_data.repositories import is_visible_at
from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.providers.base import FeedType, ProviderRecord

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


@given(
    first_delay=st.integers(min_value=0, max_value=10),
    revision_delay=st.integers(min_value=0, max_value=10),
    cutoff_delay=st.integers(min_value=0, max_value=20),
)
def test_latest_revision_is_selected_only_after_it_becomes_visible(
    first_delay: int,
    revision_delay: int,
    cutoff_delay: int,
) -> None:
    selector = getattr(repositories, "select_latest_visible_revisions", None)
    assert selector is not None, "point-in-time queries need deterministic revision selection"
    event_time = datetime(2026, 8, 23, 14, tzinfo=UTC)
    first_available = event_time + timedelta(minutes=first_delay)
    revised_available = first_available + timedelta(minutes=revision_delay + 1)
    decision_time = event_time + timedelta(minutes=cutoff_delay)
    records = (
        ProviderRecord(
            symbol=Symbol("NVDA"),
            feed_type=FeedType.PRICE_BARS,
            provider="FIXTURE",
            event_time=event_time,
            available_at=first_available,
            ingested_at=first_available,
            content_hash="a" * 64,
            raw_object_key="fixture/original.json",
            payload={"close": "100.00"},
        ),
        ProviderRecord(
            symbol=Symbol("NVDA"),
            feed_type=FeedType.PRICE_BARS,
            provider="FIXTURE",
            event_time=event_time,
            available_at=revised_available,
            ingested_at=revised_available,
            content_hash="b" * 64,
            raw_object_key="fixture/revised.json",
            payload={"close": "101.00"},
        ),
    )

    selected = selector(records, decision_time=decision_time)

    if decision_time < first_available:
        assert selected == ()
    elif decision_time < revised_available:
        assert tuple(item.content_hash for item in selected) == ("a" * 64,)
    else:
        assert tuple(item.content_hash for item in selected) == ("b" * 64,)
