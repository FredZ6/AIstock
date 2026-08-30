"""Native LangGraph checkpoint lifecycle helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import Connection
from psycopg.rows import dict_row

CHECKPOINT_ALLOWED_MODULES = (
    ("stock_platform.agents.harness.budget", "BudgetLimits"),
    ("stock_platform.agents.harness.task_spec", "PolicyVersions"),
    ("stock_platform.agents.harness.task_spec", "TaskSpecification"),
    ("stock_platform.agents.portfolio.state", "FrozenResearchDecision"),
    ("stock_platform.agents.portfolio.state", "PortfolioAction"),
    ("stock_platform.agents.research.state", "ReplaceById"),
    ("stock_platform.agents.research.state", "ResearchStatus"),
    ("stock_platform.application.portfolio.allocation", "MarketContextSnapshot"),
    ("stock_platform.application.portfolio.allocation", "MarketRegime"),
    ("stock_platform.application.portfolio.allocation", "PortfolioActionValue"),
    ("stock_platform.application.portfolio.benchmarks", "BenchmarkReturns"),
    ("stock_platform.application.portfolio.benchmarks", "PriceFrame"),
    ("stock_platform.application.portfolio.risk", "RiskDecision"),
    ("stock_platform.application.portfolio.risk", "RiskDecisionStatus"),
    ("stock_platform.application.portfolio.risk", "RiskReason"),
    ("stock_platform.application.portfolio.risk", "TargetWeightProposal"),
    ("stock_platform.domain.ingestion.models", "FeedType"),
    ("stock_platform.domain.portfolio.fill", "ExecutionBar"),
    ("stock_platform.domain.portfolio.fill", "PaperFill"),
    ("stock_platform.domain.portfolio.ledger", "LedgerEntry"),
    ("stock_platform.domain.portfolio.nav", "PortfolioNav"),
    ("stock_platform.domain.portfolio.order", "OrderIntent"),
    ("stock_platform.domain.portfolio.order", "OrderSide"),
    ("stock_platform.domain.research.claims", "Claim"),
    ("stock_platform.domain.research.claims", "InvestmentThesis"),
    ("stock_platform.domain.research.claims", "ResearchOpinion"),
    ("stock_platform.domain.research.claims", "ResearchOpinionValue"),
    ("stock_platform.domain.research.evidence", "EvidenceConflict"),
    ("stock_platform.domain.research.evidence", "EvidenceGap"),
    ("stock_platform.domain.research.evidence", "EvidenceGapKind"),
    ("stock_platform.domain.research.evidence", "EvidenceItem"),
    ("stock_platform.domain.research.evidence", "EvidenceRelation"),
    ("stock_platform.domain.research.evidence", "ThesisEvidenceLink"),
    ("stock_platform.domain.research.scores", "ConfidenceScore"),
    ("stock_platform.domain.research.scores", "ResearchScore"),
    ("stock_platform.infrastructure.providers.base", "ProviderRecord"),
    ("stock_platform.infrastructure.providers.base", "ProviderResponse"),
    ("stock_platform.infrastructure.providers.base", "ProviderStatus"),
)


def checkpoint_serializer() -> JsonPlusSerializer:
    """Return the strict serializer shared by every durable agent checkpoint."""

    return JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_ALLOWED_MODULES)


@contextmanager
def postgres_checkpointer(database_url: str) -> Iterator[BaseCheckpointSaver[Any]]:
    """Yield a setup PostgreSQL saver using the application's database."""

    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError("LangGraph checkpoints require a PostgreSQL database URL")

    checkpoint_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    serializer = checkpoint_serializer()
    with Connection.connect(
        checkpoint_url,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    ) as connection:
        saver = PostgresSaver(connection, serde=serializer)
        saver.setup()
        yield saver
