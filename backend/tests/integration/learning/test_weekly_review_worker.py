from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, func, insert, select
from stock_platform.infrastructure.db.models.tables import (
    agent_run,
    candidate_lesson,
    confidence_policy_version,
    decision_outcome,
    decision_snapshot,
    error_attribution,
    execution_policy_version,
    investment_thesis,
    lesson_approval,
    market_bar,
    normalized_record,
    policy_candidate,
    raw_data_object,
    replay_run,
    research_opinion,
    research_scoring_policy_version,
    risk_policy_version,
    weekly_review_run,
)
from stock_platform.workers.review_tasks import execute_weekly_review_run


def _insert_decision(
    connection: Connection,
    *,
    decision_id: UUID,
    symbol: str,
    decision_time: datetime,
    policy_ids: tuple[UUID, UUID, UUID, UUID],
) -> None:
    thesis_id = uuid4()
    connection.execute(
        insert(investment_thesis).values(
            id=thesis_id,
            symbol=symbol,
            as_of=decision_time,
            direction="BULLISH",
            summary=f"{symbol} persisted thesis",
            confidence=Decimal("0.7"),
            confidence_policy_version_id=policy_ids[3],
            created_at=decision_time,
        )
    )
    connection.execute(
        insert(research_opinion).values(
            thesis_id=thesis_id,
            value="BULLISH",
            created_at=decision_time,
        )
    )
    connection.execute(
        insert(decision_snapshot).values(
            id=decision_id,
            thesis_id=thesis_id,
            research_scoring_policy_version_id=policy_ids[0],
            risk_policy_version_id=policy_ids[1],
            execution_policy_version_id=policy_ids[2],
            confidence_policy_version_id=policy_ids[3],
            prompt_version="prompt-v1",
            model_version="model-v1",
            data_cutoff=decision_time,
            available_at=decision_time,
            created_at=decision_time,
        )
    )


def _insert_price(
    connection: Connection,
    *,
    symbol: str,
    event_time: datetime,
    close: str,
    sequence: int,
) -> None:
    raw_id = uuid4()
    normalized_id = uuid4()
    available_at = event_time + timedelta(seconds=1)
    content_hash = f"{sequence:064x}"
    connection.execute(
        insert(raw_data_object).values(
            id=raw_id,
            provider="ALPACA",
            feed_type="price_bars",
            event_time=event_time,
            available_at=available_at,
            ingested_at=available_at,
            content_hash=content_hash,
            raw_object_key=f"live/alpaca/{symbol}/{event_time.isoformat()}.json",
            created_at=available_at,
        )
    )
    connection.execute(
        insert(normalized_record).values(
            id=normalized_id,
            raw_data_object_id=raw_id,
            record_type="market_bar",
            record_key=f"{symbol}:{event_time.isoformat()}",
            normalization_version="alpaca-v1",
            payload={"symbol": symbol, "close": close},
            created_at=available_at,
        )
    )
    connection.execute(
        insert(market_bar).values(
            id=uuid4(),
            event_time=event_time,
            symbol=symbol,
            raw_data_object_id=raw_id,
            normalized_record_id=normalized_id,
            provider="ALPACA",
            feed_type="price_bars",
            coverage="IEX",
            session="REGULAR",
            content_hash=content_hash,
            raw_object_key=f"live/alpaca/{symbol}/{event_time.isoformat()}.json",
            available_at=available_at,
            ingested_at=available_at,
            close=Decimal(close),
            payload={"symbol": symbol, "close": close},
        )
    )


def test_weekly_review_worker_persists_mature_outcomes_and_only_prior_validated_replay(
    isolated_database_url: str,
) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    engine = create_engine(isolated_database_url)
    cutoff = datetime(2026, 9, 18, 20, 30, tzinfo=UTC)
    mature_time = cutoff - timedelta(days=6)
    pending_time = cutoff - timedelta(hours=12)
    source_time = cutoff - timedelta(days=20)
    run_id = uuid4()
    mature_id, pending_id, source_id = uuid4(), uuid4(), uuid4()
    policy_ids = (uuid4(), uuid4(), uuid4(), uuid4())
    approved_lesson_id, future_lesson_id, unapproved_lesson_id = uuid4(), uuid4(), uuid4()

    with engine.begin() as connection:
        for table, policy_id, version in (
            (research_scoring_policy_version, policy_ids[0], "research-v1"),
            (risk_policy_version, policy_ids[1], "risk-v1"),
            (execution_policy_version, policy_ids[2], "execution-v1"),
            (confidence_policy_version, policy_ids[3], "confidence-v1"),
        ):
            connection.execute(insert(table).values(id=policy_id, version=version, policy={}))
        for decision_id, symbol, decision_time in (
            (source_id, "AMD", source_time),
            (mature_id, "NVDA", mature_time),
            (pending_id, "MSFT", pending_time),
        ):
            _insert_decision(
                connection,
                decision_id=decision_id,
                symbol=symbol,
                decision_time=decision_time,
                policy_ids=policy_ids,
            )
        sequence = 1
        for symbol, points in (
            (
                "NVDA",
                (
                    (mature_time - timedelta(minutes=1), "100"),
                    (mature_time + timedelta(days=1), "90"),
                    (mature_time + timedelta(days=5), "80"),
                ),
            ),
            (
                "MSFT",
                (
                    (pending_time - timedelta(minutes=1), "100"),
                    (pending_time + timedelta(hours=6), "101"),
                ),
            ),
            (
                "QQQ",
                (
                    (mature_time - timedelta(minutes=1), "100"),
                    (mature_time + timedelta(days=1), "101"),
                    (mature_time + timedelta(days=5), "105"),
                ),
            ),
        ):
            for event_time, close in points:
                _insert_price(
                    connection,
                    symbol=symbol,
                    event_time=event_time,
                    close=close,
                    sequence=sequence,
                )
                sequence += 1
        prior_review_id = connection.execute(
            insert(weekly_review_run)
            .values(
                run_key="prior-review",
                decision_ids=[str(source_id)],
                decision_time=cutoff - timedelta(days=11),
                data_cutoff=cutoff - timedelta(days=11),
                research_scoring_policy_version="research-v1",
                risk_policy_version="risk-v1",
                execution_policy_version="execution-v1",
                confidence_policy_version="confidence-v1",
                prompt_version="prompt-v1",
                model_version="model-v1",
                status="COMPLETED",
            )
            .returning(weekly_review_run.c.id)
        ).scalar_one()
        prior_outcome_id = connection.execute(
            insert(decision_outcome)
            .values(
                weekly_review_run_id=prior_review_id,
                decision_id=source_id,
                status="MATURED",
                maximum_favorable_excursion=Decimal("0"),
                maximum_adverse_excursion=Decimal("-0.1"),
                risk_adjusted_return=Decimal("-1"),
                calibration_error=Decimal("2"),
                computed_at=cutoff - timedelta(days=11),
            )
            .returning(decision_outcome.c.id)
        ).scalar_one()
        attribution_id = connection.execute(
            insert(error_attribution)
            .values(
                outcome_id=prior_outcome_id,
                category="THESIS_ERROR",
                rationale="prior validated miss",
                controllable=True,
            )
            .returning(error_attribution.c.id)
        ).scalar_one()
        lesson_rows = (
            (
                approved_lesson_id,
                "prior-approved",
                cutoff - timedelta(days=10),
                cutoff - timedelta(days=9),
                True,
            ),
            (
                future_lesson_id,
                "future-approved",
                cutoff + timedelta(days=1),
                cutoff + timedelta(days=1),
                True,
            ),
            (
                unapproved_lesson_id,
                "prior-unapproved",
                cutoff - timedelta(days=8),
                cutoff - timedelta(days=7),
                False,
            ),
        )
        for lesson_id, suffix, created_at, replay_cutoff, approved in lesson_rows:
            connection.execute(
                insert(candidate_lesson).values(
                    id=lesson_id,
                    attribution_id=attribution_id,
                    scope="weekly:thesis_error",
                    statement=f"Review thesis direction {suffix}",
                    duplicate_key=f"weekly:thesis_error|{suffix}",
                    evidence=[f"outcome:{prior_outcome_id}"],
                    confidence=Decimal("0.8"),
                    replay_delta=Decimal("0.1"),
                    creator="weekly-review-v1",
                    created_at=created_at,
                )
            )
            connection.execute(
                insert(replay_run).values(
                    lesson_id=lesson_id,
                    decision_ids=[str(source_id)],
                    baseline_score=Decimal("-0.1"),
                    candidate_score=Decimal("0"),
                    delta=Decimal("0.1"),
                    data_cutoff=replay_cutoff,
                    created_at=replay_cutoff,
                )
            )
            if approved:
                connection.execute(
                    insert(lesson_approval).values(
                        lesson_id=lesson_id,
                        actor_id="human-reviewer",
                        action="APPROVE",
                        rationale="validated offline",
                        created_at=created_at,
                    )
                )
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                run_type="WEEKLY_REVIEW",
                idempotency_key=f"weekly-worker-{run_id}",
                request_hash="f" * 64,
                request_payload={"scheduled": True},
                decision_time=cutoff,
                data_cutoff=cutoff,
                research_scoring_policy_version="research-v1",
                risk_policy_version="risk-v1",
                execution_policy_version="execution-v1",
                confidence_policy_version="confidence-v1",
                prompt_version="prompt-v1",
                model_version="model-v1",
                status="QUEUED",
            )
        )

    assert execute_weekly_review_run(isolated_database_url, str(run_id), fixture_mode=False)
    assert not execute_weekly_review_run(isolated_database_url, str(run_id), fixture_mode=False)

    with engine.connect() as connection:
        current_review = (
            connection.execute(
                select(weekly_review_run).where(weekly_review_run.c.run_key == str(run_id))
            )
            .mappings()
            .one()
        )
        assert set(current_review["decision_ids"]) == {str(mature_id), str(pending_id)}
        outcome = (
            connection.execute(
                select(decision_outcome).where(
                    decision_outcome.c.weekly_review_run_id == current_review["id"]
                )
            )
            .mappings()
            .one()
        )
        assert outcome["decision_id"] == mature_id
        assert outcome["status"] == "MATURED"
        assert outcome["returns"] == {"1": "-0.1", "5": "-0.2"}
        assert outcome["excess_returns"] == {"1": "-0.11", "5": "-0.25"}
        assert outcome["maximum_favorable_excursion"] == Decimal("0")
        assert outcome["maximum_adverse_excursion"] == Decimal("-0.2")
        assert outcome["risk_adjusted_return"] == Decimal("-1")
        assert outcome["calibration_error"] == Decimal("2")
        current_replays = connection.execute(
            select(replay_run.c.lesson_id, replay_run.c.decision_ids).where(
                replay_run.c.data_cutoff == cutoff
            )
        ).all()
        assert [tuple(item) for item in current_replays] == [(approved_lesson_id, [str(mature_id)])]
        assert (
            connection.execute(select(func.count()).select_from(policy_candidate)).scalar_one() == 0
        )
        assert set(
            connection.execute(
                select(candidate_lesson.c.status).where(candidate_lesson.c.created_at == cutoff)
            ).scalars()
        ) == {"CANDIDATE"}
    engine.dispose()
