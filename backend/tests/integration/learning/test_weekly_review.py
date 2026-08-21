from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.checkpoint import InMemoryCheckpointStore
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.weekly_review.graph import WeeklyReviewGraph
from stock_platform.agents.weekly_review.state import WeeklyReviewResult
from stock_platform.application.learning.persistence import PostgresWeeklyReviewStore
from stock_platform.application.learning.promotion import (
    HumanActor,
    PolicyPromotionForbidden,
    PolicyPromotionService,
    PostgresPolicyRepository,
    VersionConflict,
)
from stock_platform.domain.learning.attribution import ErrorCategory
from stock_platform.domain.learning.lesson import CandidateLesson
from stock_platform.domain.learning.outcome import DecisionForReview, PriceObservation
from stock_platform.domain.learning.policy import PolicyCandidate
from stock_platform.domain.research.claims import ResearchOpinionValue

NOW = datetime(2026, 8, 21, tzinfo=UTC)


def specification() -> TaskSpecification:
    return TaskSpecification(
        objective="weekly controlled learning",
        symbols=("NVDA",),
        decision_time=NOW,
        data_cutoff=NOW,
        allowed_tools=frozenset(),
        budgets=BudgetLimits(
            llm_calls=8,
            tool_calls=8,
            tokens=10_000,
            reflections=1,
            wall_time=timedelta(minutes=10),
        ),
        output_schema="weekly-review-v1",
        completion_rules=frozenset({"persist_outcomes", "candidate_only"}),
        policy_versions=PolicyVersions(
            "research-v1", "risk-v1", "execution-v1", "confidence-v1", "prompt-v1", "model-v1"
        ),
    )


def insert_validated_lesson(
    connection: Connection, lesson_id: UUID, *, include_replay: bool = True
) -> None:
    for table_name in (
        "research_scoring_policy_version",
        "risk_policy_version",
        "execution_policy_version",
        "confidence_policy_version",
    ):
        connection.execute(
            text(
                f"INSERT INTO {table_name} (version) VALUES ('learning-lineage-v1') "
                "ON CONFLICT (version) DO NOTHING"
            )
        )
    thesis_id = connection.execute(
        text("INSERT INTO investment_thesis DEFAULT VALUES RETURNING id")
    ).scalar_one()
    decision_id = uuid4()
    connection.execute(
        text(
            """
            INSERT INTO decision_snapshot (
                id, thesis_id, research_scoring_policy_version_id, risk_policy_version_id,
                execution_policy_version_id, confidence_policy_version_id,
                prompt_version, model_version, data_cutoff
            ) SELECT :decision_id, :thesis_id,
                (SELECT id FROM research_scoring_policy_version
                 WHERE version = 'learning-lineage-v1'),
                (SELECT id FROM risk_policy_version WHERE version = 'learning-lineage-v1'),
                (SELECT id FROM execution_policy_version WHERE version = 'learning-lineage-v1'),
                (SELECT id FROM confidence_policy_version WHERE version = 'learning-lineage-v1'),
                'prompt-v1', 'model-v1', :now
            """
        ),
        {"decision_id": decision_id, "thesis_id": thesis_id, "now": NOW},
    )
    run_id = connection.execute(
        text(
            """
            INSERT INTO weekly_review_run (
                run_key, decision_time, data_cutoff, research_scoring_policy_version,
                risk_policy_version, execution_policy_version, confidence_policy_version,
                prompt_version, model_version, status
            ) VALUES (
                :run_key, :now, :now, 'research-v1', 'risk-v1', 'execution-v1',
                'confidence-v1', 'prompt-v1', 'model-v1', 'COMPLETED'
            ) RETURNING id
            """
        ),
        {"run_key": f"lesson-lineage-{lesson_id}", "now": NOW},
    ).scalar_one()
    outcome_id = connection.execute(
        text(
            """
            INSERT INTO decision_outcome (
                weekly_review_run_id, decision_id, status, maximum_favorable_excursion,
                maximum_adverse_excursion, risk_adjusted_return, calibration_error, computed_at
            ) VALUES (:run_id, :decision_id, 'MATURED', 0, 0, 0, 0, :now)
            RETURNING id
            """
        ),
        {"run_id": run_id, "decision_id": decision_id, "now": NOW},
    ).scalar_one()
    attribution_id = connection.execute(
        text(
            """
            INSERT INTO error_attribution (outcome_id, category, rationale, controllable)
            VALUES (:outcome_id, 'THESIS_ERROR', 'fixture', true) RETURNING id
            """
        ),
        {"outcome_id": outcome_id},
    ).scalar_one()
    connection.execute(
        text(
            """
            INSERT INTO candidate_lesson (
                id, attribution_id, scope, statement, duplicate_key, evidence,
                confidence, replay_delta, creator
            ) VALUES (
                :lesson_id, :attribution_id, 'fixture', 'fixture', :duplicate_key,
                '["fixture"]'::jsonb, 0.8, 0.1, 'fixture'
            )
            """
        ),
        {
            "lesson_id": lesson_id,
            "attribution_id": attribution_id,
            "duplicate_key": f"fixture-{lesson_id}",
        },
    )
    if include_replay:
        connection.execute(
            text(
                """
                INSERT INTO replay_run (
                    lesson_id, decision_ids, baseline_score, candidate_score, delta, data_cutoff
                ) VALUES (
                    :lesson_id, jsonb_build_array(CAST(:decision_id AS text)), 0, 0.1, 0.1, :now
                )
                """
            ),
            {"lesson_id": lesson_id, "decision_id": str(decision_id), "now": NOW},
        )
    connection.execute(
        text(
            """
            INSERT INTO lesson_approval (lesson_id, actor_id, action, rationale, created_at)
            VALUES (:lesson_id, 'human-42', 'APPROVE', 'fixture approval', :created_at)
            """
        ),
        {"lesson_id": lesson_id, "created_at": NOW},
    )


def insert_decision_snapshot(connection: Connection, decision_id: UUID) -> None:
    for table_name, version in (
        ("research_scoring_policy_version", "research-v1"),
        ("risk_policy_version", "risk-v1"),
        ("execution_policy_version", "execution-v1"),
        ("confidence_policy_version", "confidence-v1"),
    ):
        connection.execute(
            text(
                f"INSERT INTO {table_name} (version) VALUES (:version) "
                "ON CONFLICT (version) DO NOTHING"
            ),
            {"version": version},
        )
    thesis_id = connection.execute(
        text("INSERT INTO investment_thesis DEFAULT VALUES RETURNING id")
    ).scalar_one()
    connection.execute(
        text(
            """
            INSERT INTO decision_snapshot (
                id, thesis_id, research_scoring_policy_version_id,
                risk_policy_version_id, execution_policy_version_id,
                confidence_policy_version_id, prompt_version, model_version, data_cutoff
            ) SELECT :decision_id, :thesis_id,
                (SELECT id FROM research_scoring_policy_version WHERE version = 'research-v1'),
                (SELECT id FROM risk_policy_version WHERE version = 'risk-v1'),
                (SELECT id FROM execution_policy_version WHERE version = 'execution-v1'),
                (SELECT id FROM confidence_policy_version WHERE version = 'confidence-v1'),
                'prompt-v1', 'model-v1', :now
            """
        ),
        {"decision_id": decision_id, "thesis_id": thesis_id, "now": NOW},
    )


def test_weekly_review_processes_only_matured_decisions_and_checkpoints_outcomes() -> None:
    old = DecisionForReview(
        uuid4(), "NVDA", NOW - timedelta(days=6), Decimal("100"), ResearchOpinionValue.BULLISH
    )
    new = DecisionForReview(
        uuid4(), "NVDA", NOW - timedelta(hours=12), Decimal("100"), ResearchOpinionValue.BULLISH
    )
    prices = {
        old.id: (
            PriceObservation(NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("90")),
            PriceObservation(NOW - timedelta(days=1), NOW - timedelta(days=1), Decimal("80")),
        )
    }
    checkpoints = InMemoryCheckpointStore()
    result = WeeklyReviewGraph(checkpoints=checkpoints).run(
        run_id="weekly-1",
        specification=specification(),
        decisions=(old, new),
        prices=prices,
        benchmark_prices=(),
    )

    assert [item.decision_id for item in result.outcomes] == [old.id]
    assert result.pending_decision_ids == (new.id,)
    assert result.attributions and result.lessons
    assert result.reflections == ("THESIS_ERROR:thesis direction opposed realized return",)
    assert all(item.status.value == "CANDIDATE" for item in result.lessons)
    assert result.checkpoints == ("weekly_outcome",)
    checkpoint = checkpoints.latest("weekly-1")
    assert checkpoint is not None
    assert checkpoint.state["stage"] == "weekly_outcome"
    assert checkpoint.state["outcome_ids"] == tuple(str(item.id) for item in result.outcomes)
    assert result.route == (
        "select_matured",
        "compute_outcomes",
        "attribute_errors",
        "reflect",
        "create_candidate_lessons",
        "replay",
    )


def test_weekly_review_consolidates_duplicate_lessons_across_decisions() -> None:
    decisions = tuple(
        DecisionForReview(
            uuid4(),
            symbol,
            NOW - timedelta(days=6),
            Decimal("100"),
            ResearchOpinionValue.BULLISH,
        )
        for symbol in ("NVDA", "AMD")
    )
    prices = {
        item.id: (
            PriceObservation(NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("90")),
        )
        for item in decisions
    }

    result = WeeklyReviewGraph().run(
        run_id="weekly-duplicates",
        specification=specification(),
        decisions=decisions,
        prices=prices,
        benchmark_prices=(),
    )

    assert len(result.attributions) == 2
    assert len(result.lessons) == 1
    assert set(result.lessons[0].evidence) == {
        f"outcome:{item.outcome_id}" for item in result.attributions
    }


def test_weekly_review_replays_only_preexisting_lessons_on_later_decisions() -> None:
    decision = DecisionForReview(
        uuid4(),
        "NVDA",
        NOW - timedelta(days=6),
        Decimal("100"),
        ResearchOpinionValue.BULLISH,
    )
    prior_lesson = CandidateLesson(
        id=uuid4(),
        attribution_id=uuid4(),
        scope="weekly:thesis_error",
        statement="Review thesis direction",
        evidence=("outcome:prior",),
        counter_evidence=(),
        confidence=Decimal("0.5"),
        replay_delta=Decimal("0"),
        creator="weekly-review-v1",
        created_at=NOW - timedelta(days=7),
        category=ErrorCategory.THESIS_ERROR,
    )

    result = WeeklyReviewGraph().run(
        run_id="weekly-forward-replay",
        specification=specification(),
        decisions=(decision,),
        prices={
            decision.id: (
                PriceObservation(NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("90")),
            )
        },
        benchmark_prices=(),
        replay_candidates=(prior_lesson,),
    )

    assert result.lessons
    assert len(result.replays) == 1
    assert result.replays[0].lesson_id == prior_lesson.id
    assert result.replays[0].decision_ids == (decision.id,)
    assert result.replays[0].delta == Decimal("0.1")
    assert all(
        replay.lesson_id not in {lesson.id for lesson in result.lessons}
        for replay in result.replays
    )


def test_weekly_review_routes_real_data_quality_facts_to_attribution() -> None:
    missing = DecisionForReview(
        uuid4(),
        "NVDA",
        NOW - timedelta(days=6),
        Decimal("100"),
        data_complete=False,
    )
    stale = DecisionForReview(
        uuid4(),
        "AMD",
        NOW - timedelta(days=6),
        Decimal("100"),
        data_fresh=False,
    )
    conflicted = DecisionForReview(
        uuid4(),
        "AVGO",
        NOW - timedelta(days=6),
        Decimal("100"),
        evidence_conflicted=True,
    )
    prices = {
        item.id: (
            PriceObservation(NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("100")),
        )
        for item in (stale, conflicted)
    }

    result = WeeklyReviewGraph().run(
        run_id="weekly-quality",
        specification=specification(),
        decisions=(missing, stale, conflicted),
        prices=prices,
        benchmark_prices=(),
    )

    assert {item.category.value for item in result.attributions} == {
        "MISSING_EVIDENCE",
        "STALE_DATA",
        "CONFLICT_IGNORED",
    }


def test_learning_schema_is_persistable_and_auditable(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert {
        "weekly_review_run",
        "decision_outcome",
        "error_attribution",
        "candidate_lesson",
        "lesson_attribution_link",
        "lesson_approval",
        "policy_candidate",
        "replay_run",
        "policy_promotion_audit",
    } <= tables


def test_learning_history_tables_are_append_only_in_postgres(engine: Engine) -> None:
    expected = {
        "weekly_review_run",
        "decision_outcome",
        "error_attribution",
        "candidate_lesson",
        "lesson_attribution_link",
        "lesson_approval",
        "replay_run",
        "policy_promotion_audit",
    }
    with engine.connect() as connection:
        transaction = connection.begin()
        protected = set(
            connection.execute(
                text(
                    """
                    SELECT c.relname
                    FROM pg_trigger t
                    JOIN pg_class c ON c.oid = t.tgrelid
                    WHERE NOT t.tgisinternal AND t.tgname = 'enforce_append_only'
                    """
                )
            ).scalars()
        )
        assert expected <= protected
        run_id = connection.execute(
            text(
                """
                INSERT INTO weekly_review_run (
                    run_key, decision_time, data_cutoff, research_scoring_policy_version,
                    risk_policy_version, execution_policy_version,
                    confidence_policy_version, prompt_version, model_version, status
                ) VALUES (
                    'append-only-fixture', :now, :now, 'research-v1', 'risk-v1', 'execution-v1',
                    'confidence-v1', 'prompt-v1', 'model-v1', 'COMPLETED'
                ) RETURNING id
                """
            ),
            {"now": NOW},
        ).scalar_one()
        for statement in (
            "UPDATE weekly_review_run SET status = 'FAILED' WHERE id = :id",
            "DELETE FROM weekly_review_run WHERE id = :id",
        ):
            savepoint = connection.begin_nested()
            with pytest.raises(DBAPIError, match="append-only"):
                connection.execute(text(statement), {"id": run_id})
            savepoint.rollback()
        transaction.rollback()


def test_policy_candidate_constraints_reject_invalid_state_and_revision(engine: Engine) -> None:
    with engine.begin() as connection:
        savepoint = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO policy_candidate (
                        policy_kind, version, base_version, lesson_ids, status, revision
                    ) VALUES ('RISK', 'invalid-v1', 'risk-v1', '[]'::jsonb, 'ACTIVE', -1)
                    """
                )
            )
        savepoint.rollback()


def test_weekly_review_persists_complete_result_idempotently(engine: Engine) -> None:
    decision_id = uuid4()
    with engine.connect() as connection:
        transaction = connection.begin()
        for table_name, version in (
            ("research_scoring_policy_version", "research-v1"),
            ("risk_policy_version", "risk-v1"),
            ("execution_policy_version", "execution-v1"),
            ("confidence_policy_version", "confidence-v1"),
        ):
            connection.execute(
                text(
                    f"INSERT INTO {table_name} (version) VALUES (:version) "
                    "ON CONFLICT (version) DO NOTHING"
                ),
                {"version": version},
            )
        thesis_id = connection.execute(
            text("INSERT INTO investment_thesis DEFAULT VALUES RETURNING id")
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO decision_snapshot (
                    id, thesis_id, research_scoring_policy_version_id,
                    risk_policy_version_id, execution_policy_version_id,
                    confidence_policy_version_id, prompt_version, model_version, data_cutoff
                ) SELECT :decision_id, :thesis_id,
                    (SELECT id FROM research_scoring_policy_version WHERE version = 'research-v1'),
                    (SELECT id FROM risk_policy_version WHERE version = 'risk-v1'),
                    (SELECT id FROM execution_policy_version WHERE version = 'execution-v1'),
                    (SELECT id FROM confidence_policy_version WHERE version = 'confidence-v1'),
                    'prompt-v1', 'model-v1', :now
                """
            ),
            {"decision_id": decision_id, "thesis_id": thesis_id, "now": NOW},
        )
        decision = DecisionForReview(
            decision_id,
            "NVDA",
            NOW - timedelta(days=6),
            Decimal("100"),
            ResearchOpinionValue.BULLISH,
        )
        result = WeeklyReviewGraph().run(
            run_id="weekly-persist-1",
            specification=specification(),
            decisions=(decision,),
            prices={
                decision.id: (
                    PriceObservation(
                        NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("90")
                    ),
                    PriceObservation(
                        NOW - timedelta(days=1), NOW - timedelta(days=1), Decimal("80")
                    ),
                )
            },
            benchmark_prices=(),
        )
        store = PostgresWeeklyReviewStore(connection)

        store.persist(result, specification=specification())
        retry_result = WeeklyReviewGraph().run(
            run_id="weekly-persist-1",
            specification=specification(),
            decisions=(decision,),
            prices={
                decision.id: (
                    PriceObservation(
                        NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("90")
                    ),
                    PriceObservation(
                        NOW - timedelta(days=1), NOW - timedelta(days=1), Decimal("80")
                    ),
                )
            },
            benchmark_prices=(),
        )
        store.persist(retry_result, specification=specification())

        run_id = connection.execute(
            text("SELECT id FROM weekly_review_run WHERE run_key = 'weekly-persist-1'")
        ).scalar_one()
        assert (
            connection.execute(
                text("SELECT count(*) FROM decision_outcome WHERE weekly_review_run_id = :run_id"),
                {"run_id": run_id},
            ).scalar_one()
            == 1
        )
        assert connection.execute(text("SELECT count(*) FROM error_attribution")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM candidate_lesson")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM replay_run")).scalar_one() == 0
        transaction.rollback()


def test_duplicate_lesson_retains_each_run_attribution_link(engine: Engine) -> None:
    first_id = uuid4()
    second_id = uuid4()
    with engine.connect() as connection:
        transaction = connection.begin()
        insert_decision_snapshot(connection, first_id)
        insert_decision_snapshot(connection, second_id)
        store = PostgresWeeklyReviewStore(connection)

        for decision_id in (first_id, second_id):
            decision = DecisionForReview(
                decision_id,
                "NVDA",
                NOW - timedelta(days=6),
                Decimal("100"),
                ResearchOpinionValue.BULLISH,
            )
            result = WeeklyReviewGraph().run(
                run_id=f"weekly-dedupe-{decision_id}",
                specification=specification(),
                decisions=(decision,),
                prices={
                    decision.id: (
                        PriceObservation(
                            NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("90")
                        ),
                    )
                },
                benchmark_prices=(),
            )
            store.persist(result, specification=specification())

        duplicate_key = "|".join(result.lessons[0].duplicate_key)
        lesson_id = connection.execute(
            text("SELECT id FROM candidate_lesson WHERE duplicate_key = :duplicate_key"),
            {"duplicate_key": duplicate_key},
        ).scalar_one()
        linked_runs = set(
            connection.execute(
                text(
                    """
                    SELECT wr.run_key
                    FROM lesson_attribution_link lal
                    JOIN error_attribution ea ON ea.id = lal.attribution_id
                    JOIN decision_outcome outcome ON outcome.id = ea.outcome_id
                    JOIN weekly_review_run wr ON wr.id = outcome.weekly_review_run_id
                    WHERE lal.lesson_id = :lesson_id
                    """
                ),
                {"lesson_id": lesson_id},
            ).scalars()
        )
        assert linked_runs == {
            f"weekly-dedupe-{first_id}",
            f"weekly-dedupe-{second_id}",
        }
        transaction.rollback()


def test_weekly_review_persists_forward_replay_for_existing_lesson(engine: Engine) -> None:
    decision_id = uuid4()
    prior_lesson_id = uuid4()
    with engine.connect() as connection:
        transaction = connection.begin()
        insert_decision_snapshot(connection, decision_id)
        insert_validated_lesson(connection, prior_lesson_id, include_replay=False)
        decision = DecisionForReview(
            decision_id,
            "NVDA",
            NOW - timedelta(days=6),
            Decimal("100"),
            ResearchOpinionValue.BULLISH,
        )
        prior_lesson = CandidateLesson(
            id=prior_lesson_id,
            attribution_id=uuid4(),
            scope="weekly:thesis_error",
            statement="Review thesis direction",
            evidence=("outcome:prior",),
            counter_evidence=(),
            confidence=Decimal("0.5"),
            replay_delta=Decimal("0.1"),
            creator="weekly-review-v1",
            created_at=NOW - timedelta(days=7),
            category=ErrorCategory.THESIS_ERROR,
        )
        result = WeeklyReviewGraph().run(
            run_id=f"weekly-forward-persist-{decision_id}",
            specification=specification(),
            decisions=(decision,),
            prices={
                decision.id: (
                    PriceObservation(
                        NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("90")
                    ),
                )
            },
            benchmark_prices=(),
            replay_candidates=(prior_lesson,),
        )

        PostgresWeeklyReviewStore(connection).persist(result, specification=specification())

        persisted = (
            connection.execute(
                text(
                    "SELECT lesson_id, decision_ids FROM replay_run "
                    "WHERE lesson_id = :lesson_id AND data_cutoff = :data_cutoff"
                ),
                {"lesson_id": prior_lesson_id, "data_cutoff": NOW},
            )
            .mappings()
            .one()
        )
        assert persisted["lesson_id"] == prior_lesson_id
        assert persisted["decision_ids"] == [str(decision_id)]
        transaction.rollback()


def test_weekly_review_rejects_forward_replay_for_unknown_lesson(engine: Engine) -> None:
    decision_id = uuid4()
    unknown_lesson_id = uuid4()
    with engine.connect() as connection:
        transaction = connection.begin()
        insert_decision_snapshot(connection, decision_id)
        decision = DecisionForReview(
            decision_id,
            "NVDA",
            NOW - timedelta(days=6),
            Decimal("100"),
            ResearchOpinionValue.BULLISH,
        )
        prior_lesson = CandidateLesson(
            id=unknown_lesson_id,
            attribution_id=uuid4(),
            scope="weekly:thesis_error",
            statement="Review thesis direction",
            evidence=("outcome:prior",),
            counter_evidence=(),
            confidence=Decimal("0.5"),
            replay_delta=Decimal("0.1"),
            creator="weekly-review-v1",
            created_at=NOW - timedelta(days=7),
            category=ErrorCategory.THESIS_ERROR,
        )
        result = WeeklyReviewGraph().run(
            run_id=f"weekly-unknown-replay-{decision_id}",
            specification=specification(),
            decisions=(decision,),
            prices={
                decision.id: (
                    PriceObservation(
                        NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("90")
                    ),
                )
            },
            benchmark_prices=(),
            replay_candidates=(prior_lesson,),
        )

        with pytest.raises(ValueError, match="existing candidate lesson"):
            PostgresWeeklyReviewStore(connection).persist(result, specification=specification())
        transaction.rollback()


def test_weekly_review_run_key_rejects_changed_decision_set(engine: Engine) -> None:
    first_id = uuid4()
    second_id = uuid4()
    with engine.connect() as connection:
        transaction = connection.begin()
        insert_decision_snapshot(connection, first_id)
        insert_decision_snapshot(connection, second_id)
        store = PostgresWeeklyReviewStore(connection)

        def review(decision_id: UUID) -> WeeklyReviewResult:
            decision = DecisionForReview(
                decision_id,
                "NVDA",
                NOW - timedelta(days=6),
                Decimal("100"),
                ResearchOpinionValue.BULLISH,
            )
            return WeeklyReviewGraph().run(
                run_id=f"weekly-frozen-{first_id}",
                specification=specification(),
                decisions=(decision,),
                prices={
                    decision.id: (
                        PriceObservation(
                            NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("90")
                        ),
                    )
                },
                benchmark_prices=(),
            )

        store.persist(review(first_id), specification=specification())

        with pytest.raises(ValueError, match="frozen inputs"):
            store.persist(review(second_id), specification=specification())
        transaction.rollback()


def test_weekly_review_run_key_rejects_changed_pending_decision_set(engine: Engine) -> None:
    matured_id = uuid4()
    first_pending_id = uuid4()
    second_pending_id = uuid4()
    with engine.connect() as connection:
        transaction = connection.begin()
        insert_decision_snapshot(connection, matured_id)
        store = PostgresWeeklyReviewStore(connection)
        matured = DecisionForReview(
            matured_id,
            "NVDA",
            NOW - timedelta(days=6),
            Decimal("100"),
            ResearchOpinionValue.BULLISH,
        )

        def review(pending_id: UUID) -> WeeklyReviewResult:
            pending = DecisionForReview(
                pending_id,
                "AMD",
                NOW - timedelta(hours=12),
                Decimal("100"),
                ResearchOpinionValue.NEUTRAL,
            )
            return WeeklyReviewGraph().run(
                run_id=f"weekly-pending-frozen-{matured_id}",
                specification=specification(),
                decisions=(matured, pending),
                prices={
                    matured.id: (
                        PriceObservation(
                            NOW - timedelta(days=5), NOW - timedelta(days=5), Decimal("90")
                        ),
                    )
                },
                benchmark_prices=(),
            )

        store.persist(review(first_pending_id), specification=specification())

        with pytest.raises(ValueError, match="frozen inputs"):
            store.persist(review(second_pending_id), specification=specification())
        transaction.rollback()


def test_policy_promotion_is_transactional_and_persistently_audited(engine: Engine) -> None:
    policy_kind = f"RISK_VALID_{uuid4()}"
    with engine.connect() as connection:
        transaction = connection.begin()
        repository = PostgresPolicyRepository(
            connection, bootstrap_active_versions={policy_kind: "risk-v1"}
        )
        service = PolicyPromotionService(repository)
        human = HumanActor("human-42", authenticated=True)
        lesson_id = uuid4()
        insert_validated_lesson(connection, lesson_id)
        policy = PolicyCandidate(
            id=uuid4(),
            policy_kind=policy_kind,
            version="risk-v2",
            base_version="risk-v1",
            lesson_ids=(lesson_id,),
            created_at=NOW,
        )

        approved = service.approve(policy, actor=human, expected_revision=0)
        active = service.activate(approved.id, actor=human, expected_revision=1)
        rolled_back = service.rollback(active.id, actor=human, expected_revision=2)
        assert rolled_back.status.value == "ROLLED_BACK"
        assert repository.active_version(policy_kind) == "risk-v1"
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM policy_promotion_audit "
                    "WHERE policy_candidate_id = :candidate_id"
                ),
                {"candidate_id": policy.id},
            ).scalar_one()
            == 3
        )
        assert (
            connection.execute(
                text("SELECT revision FROM policy_control WHERE policy_kind = :policy_kind"),
                {"policy_kind": policy_kind},
            ).scalar_one()
            == 3
        )
        transaction.rollback()
    with engine.begin() as cleanup:
        cleanup.execute(
            text("DELETE FROM policy_control WHERE policy_kind = :policy_kind"),
            {"policy_kind": policy_kind},
        )


def test_policy_rollback_rejects_candidate_that_is_no_longer_active(engine: Engine) -> None:
    policy_kind = f"RISK_STALE_ROLLBACK_{uuid4()}"
    with engine.connect() as connection:
        transaction = connection.begin()
        repository = PostgresPolicyRepository(
            connection, bootstrap_active_versions={policy_kind: "risk-v1"}
        )
        service = PolicyPromotionService(repository)
        human = HumanActor("human-42", authenticated=True)
        first_lesson = uuid4()
        second_lesson = uuid4()
        insert_validated_lesson(connection, first_lesson)
        insert_validated_lesson(connection, second_lesson)
        first = PolicyCandidate(
            id=uuid4(),
            policy_kind=policy_kind,
            version="risk-v2",
            base_version="risk-v1",
            lesson_ids=(first_lesson,),
            created_at=NOW,
        )
        second = PolicyCandidate(
            id=uuid4(),
            policy_kind=policy_kind,
            version="risk-v3",
            base_version="risk-v2",
            lesson_ids=(second_lesson,),
            created_at=NOW,
        )

        first_approved = service.approve(first, actor=human, expected_revision=0)
        first_active = service.activate(first_approved.id, actor=human, expected_revision=1)
        second_approved = service.approve(second, actor=human, expected_revision=2)
        service.activate(second_approved.id, actor=human, expected_revision=3)

        with pytest.raises(VersionConflict, match="no longer active"):
            service.rollback(first_active.id, actor=human, expected_revision=4)
        assert repository.active_version(policy_kind) == "risk-v3"
        transaction.rollback()
    with engine.begin() as cleanup:
        cleanup.execute(
            text("DELETE FROM policy_control WHERE policy_kind = :policy_kind"),
            {"policy_kind": policy_kind},
        )


def test_policy_activation_revalidates_latest_lesson_approval(engine: Engine) -> None:
    policy_kind = f"RISK_ACTIVATION_LINEAGE_{uuid4()}"
    with engine.connect() as connection:
        transaction = connection.begin()
        repository = PostgresPolicyRepository(
            connection, bootstrap_active_versions={policy_kind: "risk-v1"}
        )
        service = PolicyPromotionService(repository)
        human = HumanActor("human-42", authenticated=True)
        lesson_id = uuid4()
        insert_validated_lesson(connection, lesson_id)
        policy = PolicyCandidate(
            id=uuid4(),
            policy_kind=policy_kind,
            version="risk-v2",
            base_version="risk-v1",
            lesson_ids=(lesson_id,),
            created_at=NOW,
        )
        approved = service.approve(policy, actor=human, expected_revision=0)
        connection.execute(
            text(
                """
                INSERT INTO lesson_approval (
                    lesson_id, actor_id, action, rationale, created_at
                ) VALUES (
                    :lesson_id, 'human-43', 'REJECT', 'supersedes approval', :created_at
                )
                """
            ),
            {"lesson_id": lesson_id, "created_at": NOW + timedelta(seconds=1)},
        )

        with pytest.raises(ValueError, match="approved and replayed lesson"):
            service.activate(approved.id, actor=human, expected_revision=1)
        assert repository.active_version(policy_kind) == "risk-v1"
        transaction.rollback()
    with engine.begin() as cleanup:
        cleanup.execute(
            text("DELETE FROM policy_control WHERE policy_kind = :policy_kind"),
            {"policy_kind": policy_kind},
        )


def test_postgres_concurrent_approvals_have_exactly_one_cas_winner(
    isolated_database_url: str,
) -> None:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", isolated_database_url)
    command.upgrade(config, "head")
    isolated_engine = create_engine(isolated_database_url)
    policy_kind = f"RISK_CONCURRENT_{uuid4()}"
    first_lesson = uuid4()
    second_lesson = uuid4()
    human = HumanActor("human-42", authenticated=True)
    try:
        with isolated_engine.begin() as connection:
            insert_validated_lesson(connection, first_lesson)
            insert_validated_lesson(connection, second_lesson)
        with isolated_engine.connect() as connection:
            PostgresPolicyRepository(connection, bootstrap_active_versions={policy_kind: "risk-v1"})
        candidates = (
            PolicyCandidate(
                id=uuid4(),
                policy_kind=policy_kind,
                version="risk-v2",
                base_version="risk-v1",
                lesson_ids=(first_lesson,),
                created_at=NOW,
            ),
            PolicyCandidate(
                id=uuid4(),
                policy_kind=policy_kind,
                version="risk-v3",
                base_version="risk-v1",
                lesson_ids=(second_lesson,),
                created_at=NOW,
            ),
        )
        barrier = Barrier(2)

        def approve(candidate: PolicyCandidate) -> str:
            try:
                with isolated_engine.begin() as connection:
                    service = PolicyPromotionService(
                        PostgresPolicyRepository(
                            connection,
                            bootstrap_active_versions={policy_kind: "risk-v1"},
                        )
                    )
                    barrier.wait()
                    service.approve(candidate, actor=human, expected_revision=0)
            except VersionConflict:
                return "CONFLICT"
            return "APPROVED"

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = tuple(executor.submit(approve, candidate) for candidate in candidates)
            results = tuple(future.result(timeout=10) for future in futures)

        assert sorted(results) == ["APPROVED", "CONFLICT"]
        with isolated_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT revision FROM policy_control WHERE policy_kind = :policy_kind"),
                    {"policy_kind": policy_kind},
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM policy_promotion_audit "
                        "WHERE action = 'APPROVE' AND outcome = 'COMPLETED'"
                    )
                ).scalar_one()
                == 1
            )
    finally:
        isolated_engine.dispose()


def test_forbidden_policy_audit_survives_business_transaction_rollback(engine: Engine) -> None:
    policy_kind = f"RISK_DENIAL_{uuid4()}"
    denied_policy = PolicyCandidate(
        id=uuid4(),
        policy_kind=policy_kind,
        version="risk-v2",
        base_version="risk-v1",
        lesson_ids=(uuid4(),),
        created_at=NOW,
    )
    with engine.connect() as audit_connection:
        audit_transaction = audit_connection.begin()
        with engine.connect() as business_connection:
            business_transaction = business_connection.begin()
            repository = PostgresPolicyRepository(
                business_connection,
                bootstrap_active_versions={policy_kind: "risk-v1"},
                denial_audit_connection=audit_connection,
            )
            service = PolicyPromotionService(repository)
            with pytest.raises(PolicyPromotionForbidden) as denied:
                service.approve(
                    denied_policy,
                    actor=HumanActor("automation-42", authenticated=True, is_human=False),
                    expected_revision=0,
                )
            business_transaction.rollback()

        assert denied.value.status_code == 403
        assert (
            audit_connection.execute(
                text(
                    "SELECT count(*) FROM policy_promotion_audit "
                    "WHERE policy_candidate_id = :candidate_id AND outcome = 'FORBIDDEN'"
                ),
                {"candidate_id": denied_policy.id},
            ).scalar_one()
            == 1
        )
        audit_transaction.rollback()
    with engine.begin() as cleanup:
        cleanup.execute(
            text("DELETE FROM policy_control WHERE policy_kind = :policy_kind"),
            {"policy_kind": policy_kind},
        )


def test_forbidden_audit_uses_existing_control_without_repeated_bootstrap(engine: Engine) -> None:
    policy_kind = f"RISK_EXISTING_DENIAL_{uuid4()}"
    denied_policy = PolicyCandidate(
        id=uuid4(),
        policy_kind=policy_kind,
        version="risk-v2",
        base_version="risk-v1",
        lesson_ids=(uuid4(),),
        created_at=NOW,
    )
    with engine.connect() as connection:
        PostgresPolicyRepository(connection, bootstrap_active_versions={policy_kind: "risk-v1"})
    with engine.connect() as audit_connection:
        audit_transaction = audit_connection.begin()
        with engine.connect() as business_connection:
            repository = PostgresPolicyRepository(
                business_connection,
                bootstrap_active_versions={},
                denial_audit_connection=audit_connection,
            )
            with pytest.raises(PolicyPromotionForbidden):
                PolicyPromotionService(repository).approve(
                    denied_policy,
                    actor=HumanActor("automation-42", authenticated=True, is_human=False),
                    expected_revision=0,
                )
        assert (
            audit_connection.execute(
                text(
                    "SELECT count(*) FROM policy_promotion_audit "
                    "WHERE policy_candidate_id = :candidate_id AND outcome = 'FORBIDDEN'"
                ),
                {"candidate_id": denied_policy.id},
            ).scalar_one()
            == 1
        )
        audit_transaction.rollback()
    with engine.begin() as cleanup:
        cleanup.execute(
            text("DELETE FROM policy_control WHERE policy_kind = :policy_kind"),
            {"policy_kind": policy_kind},
        )


def test_policy_approval_rejects_missing_lesson_approval_or_replay(engine: Engine) -> None:
    policy_kind = f"RISK_LINEAGE_{uuid4()}"
    with engine.connect() as connection:
        transaction = connection.begin()
        repository = PostgresPolicyRepository(
            connection, bootstrap_active_versions={policy_kind: "risk-v1"}
        )
        service = PolicyPromotionService(repository)
        policy = PolicyCandidate(
            id=uuid4(),
            policy_kind=policy_kind,
            version="risk-v2",
            base_version="risk-v1",
            lesson_ids=(uuid4(),),
            created_at=NOW,
        )

        with pytest.raises(ValueError, match="approved and replayed lesson"):
            service.approve(
                policy,
                actor=HumanActor("human-42", authenticated=True),
                expected_revision=0,
            )
        transaction.rollback()
    with engine.begin() as cleanup:
        cleanup.execute(
            text("DELETE FROM policy_control WHERE policy_kind = :policy_kind"),
            {"policy_kind": policy_kind},
        )


def test_policy_approval_requires_latest_lesson_decision_to_be_approve(engine: Engine) -> None:
    policy_kind = f"RISK_REJECTED_LESSON_{uuid4()}"
    with engine.connect() as connection:
        transaction = connection.begin()
        repository = PostgresPolicyRepository(
            connection, bootstrap_active_versions={policy_kind: "risk-v1"}
        )
        service = PolicyPromotionService(repository)
        lesson_id = uuid4()
        insert_validated_lesson(connection, lesson_id)
        connection.execute(
            text(
                """
                INSERT INTO lesson_approval (
                    lesson_id, actor_id, action, rationale, created_at
                ) VALUES (
                    :lesson_id, 'human-43', 'REJECT', 'supersedes approval', :created_at
                )
                """
            ),
            {"lesson_id": lesson_id, "created_at": NOW + timedelta(seconds=1)},
        )
        policy = PolicyCandidate(
            id=uuid4(),
            policy_kind=policy_kind,
            version="risk-v2",
            base_version="risk-v1",
            lesson_ids=(lesson_id,),
            created_at=NOW,
        )

        with pytest.raises(ValueError, match="approved and replayed lesson"):
            service.approve(
                policy,
                actor=HumanActor("human-42", authenticated=True),
                expected_revision=0,
            )
        transaction.rollback()
    with engine.begin() as cleanup:
        cleanup.execute(
            text("DELETE FROM policy_control WHERE policy_kind = :policy_kind"),
            {"policy_kind": policy_kind},
        )
