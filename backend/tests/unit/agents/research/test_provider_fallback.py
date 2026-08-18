from dataclasses import dataclass
from datetime import UTC, datetime

from stock_platform.agents.harness.budget import BudgetLimits
from stock_platform.agents.harness.task_spec import PolicyVersions, TaskSpecification
from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.application.market_data.fallback import FallbackPolicy
from stock_platform.application.research.persistence import InMemoryResearchStore
from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.providers.base import FeedType, ProviderResponse, ProviderStatus
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog

AS_OF = datetime(2026, 8, 16, tzinfo=UTC)


@dataclass
class UnavailableProvider:
    name: str = "PRIMARY"

    def fetch(self, feed_type: FeedType, symbol: str, as_of: datetime) -> ProviderResponse:
        return ProviderResponse(
            status=ProviderStatus.UNAVAILABLE,
            provider=self.name,
            feed_type=feed_type,
            symbol=Symbol(symbol),
            query_as_of=as_of,
            records=(),
            missingness="UNAVAILABLE",
        )


def test_collection_uses_existing_provider_fallback_without_time_travel() -> None:
    provider = FallbackPolicy(
        primary=UnavailableProvider(),
        fallback=FixtureCatalog.load_default().provider(),
    )
    task = TaskSpecification(
        objective="Research NVDA",
        symbols=("NVDA",),
        decision_time=AS_OF,
        data_cutoff=AS_OF,
        allowed_tools=frozenset(feed.value for feed in FeedType),
        budgets=BudgetLimits(),
        output_schema="research-decision-v1",
        completion_rules=frozenset({"decision_persisted"}),
        policy_versions=PolicyVersions("r1", "risk1", "e1", "c1", "p1", "fixture1"),
    )

    result = DailyResearchGraph(provider=provider, store=InMemoryResearchStore()).run(
        run_id="13aa2003-c231-4b0f-8fbb-ff064a0ca914",
        specification=task,
    )

    assert result.evidence
    assert all(item.available_at <= task.data_cutoff for item in result.evidence)
    assert any("fallback_from=PRIMARY" in warning for warning in result.warnings)
