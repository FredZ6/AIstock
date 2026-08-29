#!/usr/bin/env python3
"""Run the deterministic, credential-free M8 interview scenario."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import create_engine, insert, select
from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.portfolio.graph import PortfolioDecisionGraph
from stock_platform.agents.portfolio.state import FrozenResearchDecision
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.agents.weekly_review.graph import WeeklyReviewGraph
from stock_platform.application.alerting.dedup import AlertIdentity
from stock_platform.application.alerting.features import FeatureCalculator, GapContext, MinuteBar
from stock_platform.application.alerting.rules import AlertRule
from stock_platform.application.learning.approval import record_lesson_decision
from stock_platform.application.learning.persistence import PostgresWeeklyReviewStore
from stock_platform.application.learning.promotion import (
    HumanActor,
    InMemoryPolicyRepository,
    PolicyPromotionService,
)
from stock_platform.application.portfolio.accounting import initial_funding
from stock_platform.application.portfolio.allocation import classify_market_regime
from stock_platform.application.portfolio.benchmarks import PriceFrame
from stock_platform.application.portfolio.execution import ExecutionPolicy
from stock_platform.application.portfolio.risk import RiskDecisionStatus, RiskPolicy
from stock_platform.application.research.persistence import InMemoryResearchStore
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.learning.outcome import DecisionForReview, PriceObservation
from stock_platform.domain.learning.policy import PolicyCandidate, PolicyStatus
from stock_platform.domain.portfolio.fill import ExecutionBar
from stock_platform.domain.research.claims import ResearchOpinionValue
from stock_platform.infrastructure.db.models.tables import (
    confidence_policy_version,
    decision_snapshot,
    execution_policy_version,
    investment_thesis,
    research_scoring_policy_version,
    risk_policy_version,
    weekly_review_run,
)
from stock_platform.infrastructure.providers.base import FeedType
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from stock_platform.settings import Settings

RESEARCH_TIME = datetime(2026, 8, 16, tzinfo=UTC)
DECISION_TIME = datetime(2026, 8, 21, 20, 0, tzinfo=UTC)
PORTFOLIO_ID = UUID("10000000-0000-0000-0000-000000000018")
RISK_POLICY_ID = UUID("40000000-0000-0000-0000-000000000018")
EXECUTION_POLICY_ID = UUID("30000000-0000-0000-0000-000000000018")
DEMO_DRAWDOWN = Decimal("-0.018")
DEMO_INITIAL_NAV = Decimal("100425.18")
DEMO_DECISION_ID = UUID(int=1821)
DEMO_THESIS_ID = UUID(int=1820)


def _policy_versions() -> PolicyVersions:
    return PolicyVersions(
        "research-v1",
        "risk-v1",
        "execution-v1",
        "confidence-v1",
        "prompt-v1",
        "fixture-v1",
    )


def _research() -> dict[str, object]:
    specification = TaskSpecification(
        objective="Research the frozen NVDA fixture",
        symbols=("NVDA",),
        decision_time=RESEARCH_TIME,
        data_cutoff=RESEARCH_TIME,
        allowed_tools=frozenset(feed.value for feed in FeedType),
        budgets=BudgetLimits(),
        output_schema="research-decision-v1",
        completion_rules=frozenset({"decision_persisted", "citations_verified"}),
        policy_versions=_policy_versions(),
    )
    result = DailyResearchGraph(
        provider=FixtureCatalog.load_default().provider(),
        store=InMemoryResearchStore(),
    ).run(run_id="13aa2003-c231-4b0f-8fbb-ff064a0ca918", specification=specification)
    assert result.opinion is not None
    return {
        "conflict_count": len(result.conflicts),
        "opinion": result.opinion.value.value,
        "symbol": "NVDA",
    }


def _minute_bar(index: int, close: str, volume: str) -> MinuteBar:
    event_time = DECISION_TIME + timedelta(minutes=index)
    price = Decimal(close)
    return MinuteBar(
        symbol=Symbol("NVDA"),
        event_time=event_time,
        available_at=event_time + timedelta(seconds=1),
        ingested_at=event_time + timedelta(seconds=2),
        open=Decimal("100"),
        high=price + Decimal("0.2"),
        low=price - Decimal("0.2"),
        close=price,
        volume=Decimal(volume),
        previous_close=None,
        provider="FIXTURE",
        content_hash=str(index) * 64,
        raw_object_key=f"fixture/demo/bar-{index}.json",
        raw_payload={"symbol": "NVDA", "close": close, "volume": volume},
    )


def _alert() -> dict[str, object]:
    bars = tuple(
        _minute_bar(index, close, volume)
        for index, (close, volume) in enumerate(
            (
                ("100", "100"),
                ("100.2", "110"),
                ("99.9", "90"),
                ("100.3", "105"),
                ("100.1", "95"),
                ("106", "600"),
            )
        )
    )
    features = FeatureCalculator().calculate(
        bars,
        evaluated_at=bars[-1].ingested_at,
        gap_context=GapContext(session_open=Decimal("100"), previous_close=Decimal("100")),
    )
    evaluation = AlertRule.default().evaluate(features)
    first = AlertIdentity.for_trigger(
        symbol="NVDA",
        rule_id=evaluation.rule_id,
        event_time=features.event_time,
        cooldown=timedelta(minutes=30),
    )
    replayed = AlertIdentity.for_trigger(
        symbol="NVDA",
        rule_id=evaluation.rule_id,
        event_time=features.event_time,
        cooldown=timedelta(minutes=30),
    )
    return {"deterministic": first == replayed, "triggered": evaluation.triggered}


def _portfolio_specification() -> TaskSpecification:
    return TaskSpecification(
        objective="rebalance the frozen paper portfolio",
        symbols=("NVDA",),
        decision_time=DECISION_TIME,
        data_cutoff=DECISION_TIME,
        allowed_tools=frozenset(),
        budgets=BudgetLimits(
            llm_calls=3,
            tool_calls=0,
            tokens=5_000,
            reflections=0,
            wall_time=timedelta(seconds=60),
        ),
        output_schema="PortfolioDecision",
        completion_rules=frozenset({"risk_decision_for_every_order"}),
        policy_versions=_policy_versions(),
    )


def _portfolio_graph() -> PortfolioDecisionGraph:
    return PortfolioDecisionGraph(
        risk_policy=RiskPolicy(
            id=RISK_POLICY_ID,
            version="risk-v1",
            max_position_weight=Decimal("0.20"),
            max_gross_exposure=Decimal("1"),
            min_cash_reserve=Decimal("0.05"),
            max_daily_turnover=Decimal("0.25"),
            max_drawdown=Decimal("0.20"),
            max_research_age=timedelta(days=2),
            earnings_blackout=timedelta(days=1),
        ),
        execution_policy=ExecutionPolicy(
            id=EXECUTION_POLICY_ID,
            version="execution-v1",
            spread_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
            fee_per_share=Decimal("0"),
            minimum_fee=Decimal("0"),
            volume_participation=Decimal("1"),
        ),
    )


def _portfolio() -> dict[str, object]:
    frozen = FrozenResearchDecision(
        decision_id=UUID(int=1801),
        thesis_id=UUID(int=1802),
        symbol=Symbol("NVDA"),
        opinion=ResearchOpinionValue.BULLISH,
        as_of=DECISION_TIME - timedelta(hours=1),
        available_at=DECISION_TIME - timedelta(hours=1),
        evidence_complete=True,
        proposed_weight=Decimal("0.20"),
        rationale="approved frozen fixture used only for paper allocation",
        policy_versions=_policy_versions(),
        data_cutoff=DECISION_TIME,
    )
    context = classify_market_regime(
        snapshot_id=UUID(int=1803),
        as_of=DECISION_TIME,
        available_at=DECISION_TIME,
        qqq_trend=Decimal("0.05"),
        qqq_volatility=Decimal("0.18"),
        soxx_relative_strength=Decimal("0.02"),
        vix=Decimal("18"),
        algorithm_version="regime-v1",
        source_lineage=(UUID(int=1811), UUID(int=1812), UUID(int=1813)),
    )
    decision_bar = ExecutionBar(
        Symbol("NVDA"),
        event_time=DECISION_TIME - timedelta(minutes=1),
        available_at=DECISION_TIME - timedelta(seconds=30),
        open=Decimal("100"),
        volume=Decimal("100"),
        content_hash="demo-decision-bar",
    )
    next_bar = ExecutionBar(
        Symbol("NVDA"),
        event_time=DECISION_TIME + timedelta(minutes=1),
        available_at=DECISION_TIME + timedelta(minutes=1, seconds=2),
        open=Decimal("100"),
        volume=Decimal("100"),
        content_hash="demo-next-bar",
    )
    ledger = initial_funding(PORTFOLIO_ID, DEMO_INITIAL_NAV, "USD", DECISION_TIME)
    frames = (
        PriceFrame(
            DECISION_TIME,
            {Symbol("QQQ"): Decimal("100"), Symbol("NVDA"): Decimal("100")},
        ),
        PriceFrame(
            DECISION_TIME + timedelta(days=1),
            {Symbol("QQQ"): Decimal("101"), Symbol("NVDA"): Decimal("102")},
        ),
    )
    accepted = _portfolio_graph().run(
        run_id="demo-portfolio-fill",
        portfolio_id=PORTFOLIO_ID,
        specification=_portfolio_specification(),
        research=(frozen,),
        market_context=context,
        bars=(decision_bar, next_bar),
        ledger=ledger,
        benchmark_frames=frames,
        benchmark_watchlist=(Symbol("NVDA"),),
        drawdown=DEMO_DRAWDOWN,
    )
    rejected = _portfolio_graph().run(
        run_id="demo-portfolio-reject",
        portfolio_id=PORTFOLIO_ID,
        specification=_portfolio_specification(),
        research=(frozen,),
        market_context=context,
        bars=(decision_bar,),
        ledger=ledger,
        drawdown=Decimal("-0.25"),
    )
    assert rejected.risk_decisions[0].status is RiskDecisionStatus.REJECTED
    return {
        "benchmark_count": len(accepted.benchmarks.__dataclass_fields__),
        "drawdown": str(DEMO_DRAWDOWN),
        "fill_count": len(accepted.fills),
        "nav": str(accepted.nav.total),
        "risk_rejection": rejected.risk_decisions[0].status.value,
    }


def _weekly_review_and_policy() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    specification = TaskSpecification(
        objective="weekly controlled learning",
        symbols=("NVDA",),
        decision_time=DECISION_TIME,
        data_cutoff=DECISION_TIME,
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
        policy_versions=_policy_versions(),
    )
    decision = DecisionForReview(
        DEMO_DECISION_ID,
        "NVDA",
        DECISION_TIME - timedelta(days=6),
        Decimal("100"),
        ResearchOpinionValue.BULLISH,
    )
    review = WeeklyReviewGraph().run(
        run_id="demo-weekly-review",
        specification=specification,
        decisions=(decision,),
        prices={
            decision.id: (
                PriceObservation(
                    DECISION_TIME - timedelta(days=5),
                    DECISION_TIME - timedelta(days=5),
                    Decimal("90"),
                ),
            )
        },
        benchmark_prices=(),
    )

    actor = HumanActor("demo-human-reviewer", authenticated=True)
    engine = create_engine(Settings().database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                policy_rows = (
                    (research_scoring_policy_version, UUID(int=1831), "demo-research-v1"),
                    (risk_policy_version, UUID(int=1832), "demo-risk-v1"),
                    (execution_policy_version, UUID(int=1833), "demo-execution-v1"),
                    (confidence_policy_version, UUID(int=1834), "demo-confidence-v1"),
                )
                for table, identifier, version in policy_rows:
                    connection.execute(insert(table).values(id=identifier, version=version))
                connection.execute(
                    insert(investment_thesis).values(
                        id=DEMO_THESIS_ID,
                        symbol="NVDA",
                        as_of=decision.decision_time,
                        direction="BULLISH",
                        summary="frozen demo thesis",
                        confidence=Decimal("0.75"),
                        confidence_policy_version_id=UUID(int=1834),
                    )
                )
                connection.execute(
                    insert(decision_snapshot).values(
                        id=DEMO_DECISION_ID,
                        thesis_id=DEMO_THESIS_ID,
                        research_scoring_policy_version_id=UUID(int=1831),
                        risk_policy_version_id=UUID(int=1832),
                        execution_policy_version_id=UUID(int=1833),
                        confidence_policy_version_id=UUID(int=1834),
                        prompt_version="demo-prompt-v1",
                        model_version="fixture-v1",
                        data_cutoff=decision.decision_time,
                        available_at=decision.decision_time,
                    )
                )
                PostgresWeeklyReviewStore(connection).persist(review, specification=specification)
                review_id = connection.execute(
                    select(weekly_review_run.c.id).where(
                        weekly_review_run.c.run_key == review.run_id
                    )
                ).scalar_one()
                approval = record_lesson_decision(
                    connection,
                    review_id=review_id,
                    lesson_id=review.lessons[0].id,
                    actor=actor,
                    action="APPROVE",
                    rationale="human-reviewed fixture lesson",
                )
                lesson_approval_summary = {
                    "action": approval["action"],
                    "actor_id": approval["actor_id"],
                    "persistence": "ROLLBACK_PROBE",
                }
            finally:
                transaction.rollback()
    finally:
        engine.dispose()

    repository = InMemoryPolicyRepository(active_versions={"RISK": "risk-v1"})
    service = PolicyPromotionService(repository)
    candidate = PolicyCandidate(
        id=UUID(int=1822),
        policy_kind="RISK",
        version="risk-v2-candidate",
        base_version="risk-v1",
        lesson_ids=(review.lessons[0].id,),
        created_at=DECISION_TIME,
    )
    repository.transact(
        candidate=candidate,
        actor=actor,
        action="SUBMIT",
        expected_revision=0,
        next_status=PolicyStatus.CANDIDATE,
    )
    activation_rejected = False
    try:
        service.activate(candidate.id, actor=actor, expected_revision=1)
    except ValueError as error:
        activation_rejected = str(error) == "only approved policy candidates can be activated"
    return (
        {
            "candidate_lesson_count": len(review.lessons),
            "matured_outcome_count": len(review.outcomes),
        },
        {
            "candidate_status": candidate.status.value,
            "unapproved_activation_rejected": activation_rejected,
        },
        lesson_approval_summary,
    )


def main() -> int:
    weekly_review, policy, lesson_approval = _weekly_review_and_policy()
    manifest = {
        "alert": _alert(),
        "evaluation": {"artifact": "evals/reports/latest/summary.json"},
        "lesson_approval": lesson_approval,
        "mode": "fixture",
        "policy": policy,
        "portfolio": _portfolio(),
        "product_boundary": "research and paper trading only",
        "research": _research(),
        "weekly_review": weekly_review,
    }
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
