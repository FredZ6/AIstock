"""Compiled LangGraph for one bounded offline daily research run."""

from __future__ import annotations

from typing import cast

from langgraph.graph import END, START, StateGraph

from stock_platform.agents.harness.task_spec import TaskSpecification
from stock_platform.agents.research.nodes import ResearchNodes
from stock_platform.agents.research.nodes.core import ResearchCollectionProvider
from stock_platform.agents.research.state import ResearchResult, ResearchState, ResearchStatus
from stock_platform.application.research.persistence import ResearchStore


class DailyResearchGraph:
    node_names = (
        "preflight",
        "planner",
        "parallel_collection",
        "normalize_freshness_lineage",
        "parallel_analysts",
        "evidence_judge",
        "reflect",
        "deterministic_score_confidence",
        "investment_thesis",
        "research_opinion",
        "writer",
        "citation_verifier",
        "decision_diff",
        "persist_decision",
    )

    def __init__(self, *, provider: ResearchCollectionProvider, store: ResearchStore) -> None:
        self._store = store
        nodes = ResearchNodes(provider=provider, store=store)
        builder = StateGraph(ResearchState)
        for name in self.node_names:
            builder.add_node(name, getattr(nodes, name))
        builder.add_edge(START, "preflight")
        builder.add_conditional_edges(
            "preflight",
            lambda state: "cancel" if state["status"] is ResearchStatus.CANCELLED else "continue",
            {"cancel": END, "continue": "planner"},
        )
        builder.add_edge("planner", "parallel_collection")
        builder.add_edge("parallel_collection", "normalize_freshness_lineage")
        builder.add_edge("normalize_freshness_lineage", "parallel_analysts")
        builder.add_edge("parallel_analysts", "evidence_judge")
        builder.add_conditional_edges(
            "evidence_judge",
            lambda state: (
                "reflect"
                if (state["gaps"] or state["conflicts"]) and state["reflections"] < 1
                else "score"
            ),
            {"reflect": "reflect", "score": "deterministic_score_confidence"},
        )
        builder.add_edge("reflect", "deterministic_score_confidence")
        builder.add_edge("deterministic_score_confidence", "investment_thesis")
        builder.add_edge("investment_thesis", "research_opinion")
        builder.add_edge("research_opinion", "writer")
        builder.add_edge("writer", "citation_verifier")
        builder.add_edge("citation_verifier", "decision_diff")
        builder.add_edge("decision_diff", "persist_decision")
        builder.add_edge("persist_decision", END)
        self._compiled = builder.compile()

    def run(
        self,
        *,
        run_id: str,
        specification: TaskSpecification,
        cancelled: bool = False,
    ) -> ResearchResult:
        existing = self._store.latest(run_id)
        if existing is not None:
            return existing
        initial: ResearchState = {
            "run_id": run_id,
            "specification": specification,
            "status": ResearchStatus.RUNNING,
            "cancelled": cancelled,
            "route": (),
            "responses": (),
            "evidence": (),
            "claims": (),
            "gaps": (),
            "conflicts": (),
            "warnings": (),
            "reflections": 0,
            "score": None,
            "confidence": None,
            "thesis": None,
            "opinion": None,
            "evidence_links": (),
            "report": None,
            "citations_verified": False,
            "decision_diff": None,
            "decision_id": None,
        }
        final = cast(ResearchState, self._compiled.invoke(initial))
        return ResearchResult.from_state(final)
