from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, select
from sqlalchemy.engine import RowMapping

from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.weekly_review.graph import WeeklyReviewGraph
from stock_platform.application.learning.persistence import PostgresWeeklyReviewStore
from stock_platform.application.runs import RunControl, execute_run
from stock_platform.domain.learning.outcome import DecisionForReview, PriceObservation
from stock_platform.infrastructure.db.models.tables import (
    decision_snapshot,
    investment_thesis,
    research_opinion,
)
from stock_platform.infrastructure.providers.base import FeedType
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from stock_platform.settings import Settings
from stock_platform.workers.celery_app import celery_app


@celery_app.task(name="stock_platform.workers.review_tasks.run_weekly_review")  # type: ignore[untyped-decorator]
def run_weekly_review(run_id: str) -> bool:
    return execute_weekly_review_run(Settings().database_url, run_id)


def execute_weekly_review_run(database_url: str, run_id: str) -> bool:
    run_uuid = UUID(run_id)

    def work(connection: Connection, row: RowMapping, control: RunControl) -> None:
        specification = TaskSpecification(
            objective="weekly controlled learning",
            symbols=("NVDA",),
            decision_time=row["decision_time"],
            data_cutoff=row["data_cutoff"],
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
                row["research_scoring_policy_version"],
                row["risk_policy_version"],
                row["execution_policy_version"],
                row["confidence_policy_version"],
                row["prompt_version"],
                row["model_version"],
            ),
        )
        catalog = FixtureCatalog.load_default()
        frozen_rows = connection.execute(
            select(
                decision_snapshot.c.id,
                investment_thesis.c.symbol,
                investment_thesis.c.as_of,
                research_opinion.c.value,
            )
            .select_from(
                decision_snapshot.join(
                    investment_thesis,
                    decision_snapshot.c.thesis_id == investment_thesis.c.id,
                ).join(
                    research_opinion,
                    research_opinion.c.thesis_id == investment_thesis.c.id,
                )
            )
            .where(decision_snapshot.c.data_cutoff <= specification.data_cutoff)
            .where(
                decision_snapshot.c.available_at <= specification.data_cutoff,
                investment_thesis.c.as_of <= specification.decision_time,
            )
            .order_by(investment_thesis.c.as_of, decision_snapshot.c.id)
        ).all()
        decisions: list[DecisionForReview] = []
        prices: dict[UUID, tuple[PriceObservation, ...]] = {}
        for decision_id, symbol, decision_time, opinion in frozen_rows:
            bars = tuple(
                entry
                for entry in catalog.entries
                if entry.feed_type is FeedType.PRICE_BARS
                and str(entry.symbol) == symbol
                and "close" in entry.payload
                and entry.available_at <= specification.data_cutoff
            )
            reference = [entry for entry in bars if entry.event_time <= decision_time]
            if not reference:
                continue
            reference_bar = max(reference, key=lambda entry: (entry.event_time, entry.available_at))
            decisions.append(
                DecisionForReview(
                    decision_id,
                    symbol,
                    decision_time,
                    Decimal(str(reference_bar.payload["close"])),
                    opinion,
                )
            )
            prices[decision_id] = tuple(
                PriceObservation(
                    entry.event_time,
                    entry.available_at,
                    Decimal(str(entry.payload["close"])),
                )
                for entry in sorted(bars, key=lambda item: (item.event_time, item.available_at))
                if entry.event_time >= decision_time
            )
        result = WeeklyReviewGraph().run(
            run_id=run_id,
            specification=specification,
            decisions=decisions,
            prices=prices,
            benchmark_prices=(),
            on_node_completed=control.node_completed,
        )
        PostgresWeeklyReviewStore(connection).persist(result, specification=specification)

    return execute_run(database_url, run_uuid, "WEEKLY_REVIEW", work)
