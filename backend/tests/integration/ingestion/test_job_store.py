from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.exc import DBAPIError
from stock_platform.application.ingestion.jobs import IngestionJobSpec
from stock_platform.domain.ingestion.models import (
    DataPurpose,
    FeedType,
    IngestionErrorClass,
    IngestionRequest,
)
from stock_platform.infrastructure.db.models.tables import (
    ingestion_attempt,
    ingestion_cursor,
    ingestion_dead_letter,
    ingestion_job,
)
from stock_platform.infrastructure.ingestion.job_store import IngestionJobStore

NOW = datetime(2026, 8, 23, 13, tzinfo=UTC)


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _spec() -> IngestionJobSpec:
    request = IngestionRequest(
        {
            "provider": "ALPACA",
            "dataset": FeedType.PRICE_BARS,
            "symbols": ["NVDA"],
            "start": NOW - timedelta(days=1),
            "end": NOW,
        }
    )
    return IngestionJobSpec(
        request=request,
        provider="ALPACA",
        dataset=FeedType.PRICE_BARS,
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
        purpose=DataPurpose.RESEARCH,
        policy_version="ingestion-v1",
        max_attempts=3,
    )


def test_concurrent_enqueue_and_claim_have_one_winner(isolated_database_url: str) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)

    with ThreadPoolExecutor(max_workers=4) as pool:
        job_ids = list(pool.map(lambda _: store.enqueue(_spec(), now=NOW), range(4)))

    assert len(set(job_ids)) == 1
    job_id = job_ids[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(
            pool.map(
                lambda worker: store.claim(
                    job_id,
                    worker_id=f"worker-{worker}",
                    now=NOW,
                    lease_for=timedelta(minutes=5),
                ),
                range(2),
            )
        )

    assert sum(lease is not None for lease in leases) == 1
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(ingestion_job)).scalar_one() == 1
    engine.dispose()


def test_active_job_identity_includes_purpose_policy_and_window(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)
    base = _spec()

    job_ids = {
        store.enqueue(base, now=NOW),
        store.enqueue(replace(base, purpose=DataPurpose.PAPER_EXECUTION), now=NOW),
        store.enqueue(replace(base, policy_version="ingestion-v2"), now=NOW),
        store.enqueue(replace(base, window_start=base.window_start - timedelta(days=1)), now=NOW),
    }

    assert len(job_ids) == 4
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(ingestion_job)).scalar_one() == 4
    engine.dispose()


def test_store_rejects_unknown_error_class(isolated_database_url: str) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)
    job_id = store.enqueue(_spec(), now=NOW)
    lease = store.claim(job_id, worker_id="worker-a", now=NOW, lease_for=timedelta(minutes=5))
    assert lease is not None

    with pytest.raises(ValueError, match="not a valid IngestionErrorClass"):
        store.fail(
            lease,
            error_class="RATE_LIMITED",
            error_detail={"reason": "typo"},
            now=NOW + timedelta(minutes=1),
        )

    assert store.fail(
        lease,
        error_class=IngestionErrorClass.INVALID_AUTH,
        error_detail={"reason": "credential_rejected"},
        now=NOW + timedelta(minutes=1),
    )
    engine.dispose()


def test_database_rejects_unknown_attempt_error_class(isolated_database_url: str) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)
    job_id = store.enqueue(_spec(), now=NOW)
    lease = store.claim(job_id, worker_id="worker-a", now=NOW, lease_for=timedelta(minutes=5))
    assert lease is not None

    with engine.connect() as connection, pytest.raises(DBAPIError):
        connection.execute(
            insert(ingestion_attempt).values(
                job_id=job_id,
                attempt_number=1,
                lease_generation=lease.generation,
                worker_id="worker-a",
                started_at=NOW,
                finished_at=NOW + timedelta(seconds=1),
                outcome="FAILED",
                error_class="RATE_LIMITED",
                error_detail={},
            )
        )
    engine.dispose()


def test_retry_dead_letter_cancel_and_cursor_are_durable(isolated_database_url: str) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)

    retry_job = store.enqueue(_spec(), now=NOW)
    lease = store.claim(retry_job, worker_id="worker-a", now=NOW, lease_for=timedelta(minutes=5))
    assert lease is not None
    assert store.heartbeat(lease, now=NOW + timedelta(minutes=1), lease_for=timedelta(minutes=5))
    assert store.schedule_retry(
        lease,
        error_class="RATE_LIMIT",
        error_detail={"provider_status": "429"},
        next_attempt_at=NOW + timedelta(minutes=10),
        now=NOW + timedelta(minutes=2),
    )
    assert store.requeue_due(now=NOW + timedelta(minutes=9)) == 0
    assert store.requeue_due(now=NOW + timedelta(minutes=10)) == 1

    second_lease = store.claim(
        retry_job,
        worker_id="worker-b",
        now=NOW + timedelta(minutes=10),
        lease_for=timedelta(minutes=5),
    )
    assert second_lease is not None
    assert not store.complete(lease, now=NOW + timedelta(minutes=11))
    assert store.dead_letter(
        second_lease,
        error_class="SCHEMA_DRIFT",
        error_detail={"field": "unexpected"},
        now=NOW + timedelta(minutes=11),
    )

    cancelled_job = store.enqueue(
        IngestionJobSpec(
            request=IngestionRequest({"provider": "SEC", "dataset": "filings", "cik": "1045810"}),
            provider="SEC",
            dataset=FeedType.FILINGS,
            window_start=NOW - timedelta(days=1),
            window_end=NOW,
            purpose=DataPurpose.RESEARCH,
            policy_version="ingestion-v1",
            max_attempts=2,
        ),
        now=NOW,
    )
    assert store.cancel(cancelled_job, now=NOW)

    assert store.advance_cursor(
        provider="ALPACA",
        dataset=FeedType.PRICE_BARS,
        scope_key="NVDA",
        expected_generation=0,
        cursor={"page_token": "page-1"},
        watermark=NOW,
        now=NOW,
    )
    assert not store.advance_cursor(
        provider="ALPACA",
        dataset=FeedType.PRICE_BARS,
        scope_key="NVDA",
        expected_generation=0,
        cursor={"page_token": "stale"},
        watermark=NOW,
        now=NOW,
    )

    with engine.connect() as connection:
        assert (
            connection.execute(select(func.count()).select_from(ingestion_attempt)).scalar_one()
            == 2
        )
        assert (
            connection.execute(select(func.count()).select_from(ingestion_dead_letter)).scalar_one()
            == 1
        )
        cursor_row = connection.execute(
            select(ingestion_cursor.c.generation, ingestion_cursor.c.cursor_payload)
        ).one()
        assert cursor_row == (1, {"page_token": "page-1"})
    engine.dispose()


def test_expired_leases_recover_or_dead_letter_at_the_attempt_budget(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)

    retry_job = store.enqueue(_spec(), now=NOW)
    assert (
        store.claim(
            retry_job,
            worker_id="lost-worker",
            now=NOW,
            lease_for=timedelta(minutes=1),
        )
        is not None
    )
    exhausted_job = store.enqueue(
        IngestionJobSpec(
            request=IngestionRequest({"provider": "SEC", "dataset": "filings", "cik": "1045810"}),
            provider="SEC",
            dataset=FeedType.FILINGS,
            window_start=NOW - timedelta(days=1),
            window_end=NOW,
            purpose=DataPurpose.RESEARCH,
            policy_version="ingestion-v1",
            max_attempts=1,
        ),
        now=NOW,
    )
    assert (
        store.claim(
            exhausted_job,
            worker_id="lost-worker",
            now=NOW,
            lease_for=timedelta(minutes=1),
        )
        is not None
    )

    assert store.recover_expired(now=NOW + timedelta(minutes=2)) == 2

    with engine.connect() as connection:
        state_rows = (
            connection.execute(
                select(ingestion_job.c.id, ingestion_job.c.state).where(
                    ingestion_job.c.id.in_((retry_job, exhausted_job))
                )
            )
            .mappings()
            .all()
        )
        states: dict[UUID, str] = {
            cast(UUID, row["id"]): cast(str, row["state"]) for row in state_rows
        }
        assert states == {retry_job: "RETRY_SCHEDULED", exhausted_job: "DEAD_LETTER"}
        assert (
            connection.execute(select(func.count()).select_from(ingestion_attempt)).scalar_one()
            == 2
        )
        assert (
            connection.execute(select(func.count()).select_from(ingestion_dead_letter)).scalar_one()
            == 1
        )

    with engine.connect() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(text("DELETE FROM ingestion_attempt"))
    engine.dispose()


def test_terminal_failure_is_audited_and_cannot_be_completed_again(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)
    job_id = store.enqueue(_spec(), now=NOW)
    lease = store.claim(
        job_id,
        worker_id="worker-a",
        now=NOW,
        lease_for=timedelta(minutes=5),
    )
    assert lease is not None

    assert store.fail(
        lease,
        error_class="INVALID_AUTH",
        error_detail={"reason": "credential_rejected"},
        now=NOW + timedelta(minutes=1),
    )
    assert not store.complete(lease, now=NOW + timedelta(minutes=2))

    with engine.connect() as connection:
        assert (
            connection.execute(
                select(ingestion_job.c.state).where(ingestion_job.c.id == job_id)
            ).scalar_one()
            == "FAILED"
        )
        attempt = connection.execute(
            select(ingestion_attempt.c.outcome, ingestion_attempt.c.error_class)
        ).one()
        assert attempt == ("FAILED", "INVALID_AUTH")
    engine.dispose()


def test_retry_request_dead_letters_when_attempt_budget_is_exhausted(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)
    spec = _spec()
    job_id = store.enqueue(
        IngestionJobSpec(
            request=spec.request,
            provider=spec.provider,
            dataset=spec.dataset,
            window_start=spec.window_start,
            window_end=spec.window_end,
            purpose=spec.purpose,
            policy_version=spec.policy_version,
            max_attempts=1,
        ),
        now=NOW,
    )
    lease = store.claim(
        job_id,
        worker_id="worker-a",
        now=NOW,
        lease_for=timedelta(minutes=5),
    )
    assert lease is not None

    assert store.schedule_retry(
        lease,
        error_class="RATE_LIMIT",
        error_detail={"provider_status": "429"},
        next_attempt_at=NOW + timedelta(minutes=10),
        now=NOW + timedelta(minutes=1),
    )

    with engine.connect() as connection:
        state, next_attempt_at = connection.execute(
            select(ingestion_job.c.state, ingestion_job.c.next_attempt_at).where(
                ingestion_job.c.id == job_id
            )
        ).one()
        assert (state, next_attempt_at) == ("DEAD_LETTER", None)
        assert (
            connection.execute(select(func.count()).select_from(ingestion_dead_letter)).scalar_one()
            == 1
        )
    engine.dispose()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ingestion_job SET lease_generation = -1",
        "UPDATE ingestion_job SET lease_token = gen_random_uuid()",
        "UPDATE ingestion_job SET completed_at = now() WHERE state = 'QUEUED'",
    ],
)
def test_job_table_rejects_contradictory_control_state(
    isolated_database_url: str, statement: str
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    store = IngestionJobStore(engine)
    store.enqueue(_spec(), now=NOW)

    with engine.connect() as connection, pytest.raises(DBAPIError):
        connection.execute(text(statement))
    engine.dispose()
