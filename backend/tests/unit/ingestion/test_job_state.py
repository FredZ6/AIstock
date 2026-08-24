from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st
from stock_platform.application.ingestion.jobs import (
    IngestionLease,
    InvalidJobTransition,
    StaleIngestionLease,
    require_current_lease,
    transition_job,
)
from stock_platform.domain.ingestion.models import IngestionJobState, can_transition


@given(
    current=st.sampled_from(list(IngestionJobState)),
    target=st.sampled_from(list(IngestionJobState)),
)
def test_job_transition_validation_matches_the_frozen_state_machine(
    current: IngestionJobState, target: IngestionJobState
) -> None:
    if can_transition(current, target):
        assert transition_job(current, target) is target
    else:
        with pytest.raises(InvalidJobTransition):
            transition_job(current, target)


def test_only_the_current_unexpired_running_lease_is_accepted() -> None:
    now = datetime(2026, 8, 23, 13, tzinfo=UTC)
    lease = IngestionLease(
        job_id=uuid4(),
        token=uuid4(),
        generation=3,
        expires_at=now + timedelta(minutes=5),
    )

    assert (
        require_current_lease(
            state=IngestionJobState.RUNNING,
            stored_token=lease.token,
            stored_generation=3,
            stored_expires_at=lease.expires_at,
            presented=lease,
            now=now,
        )
        is lease
    )


@pytest.mark.parametrize("failure", ["state", "token", "generation", "expired"])
def test_stale_or_mismatched_leases_are_rejected(failure: str) -> None:
    now = datetime(2026, 8, 23, 13, tzinfo=UTC)
    lease = IngestionLease(
        job_id=uuid4(),
        token=uuid4(),
        generation=3,
        expires_at=now + timedelta(minutes=5),
    )
    state = IngestionJobState.RUNNING
    token = lease.token
    generation = lease.generation
    expires_at = lease.expires_at
    if failure == "state":
        state = IngestionJobState.QUEUED
    elif failure == "token":
        token = uuid4()
    elif failure == "generation":
        generation += 1
    else:
        expires_at = now

    with pytest.raises(StaleIngestionLease):
        require_current_lease(
            state=state,
            stored_token=token,
            stored_generation=generation,
            stored_expires_at=expires_at,
            presented=lease,
            now=now,
        )
