from stock_platform.agents.research.graph import DailyResearchGraph
from stock_platform.agents.research.state import ResearchStatus
from stock_platform.application.research.persistence import InMemoryResearchStore
from stock_platform.domain.research.claims import ResearchOpinionValue
from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from test_graph_routes import specification


def test_failed_verification_crosses_downgrade_gate_before_persistence() -> None:
    result = DailyResearchGraph(
        provider=FixtureCatalog.load_default().provider(),
        store=InMemoryResearchStore(),
    ).run(
        run_id="71545eca-8f7d-416b-86ce-d59fd5b1a319",
        specification=specification(),
    )

    assert result.citations_verified is False
    assert result.opinion is not None
    assert result.opinion.value is ResearchOpinionValue.ABSTAIN
    assert result.status is ResearchStatus.COMPLETED_WITH_LIMITATIONS
    assert "degrade_unverified_decision" in result.route
    assert "validation:decision_downgraded" in result.warnings
    assert result.route.index("degrade_unverified_decision") < result.route.index(
        "persist_decision"
    )
