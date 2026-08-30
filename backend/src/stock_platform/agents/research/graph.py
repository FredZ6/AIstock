"""Compiled LangGraph for one bounded offline daily research run."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

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
        "degrade_unverified_decision",
        "decision_diff",
        "persist_decision",
    )

    def __init__(
        self,
        *,
        provider: ResearchCollectionProvider,
        store: ResearchStore,
        on_node_completed: Callable[[str], None] | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self._store = store
        self._checkpointer = checkpointer
        nodes = ResearchNodes(provider=provider, store=store)
        builder = StateGraph(ResearchState)

        def observed(name: str, node: Callable[[Any], Any]) -> Callable[[Any], Any]:
            def run_node(state: Any) -> Any:
                result = node(state)
                if on_node_completed is not None:
                    on_node_completed(name)
                return result

            return run_node

        for name in self.node_names:
            node = getattr(nodes, name)
            builder.add_node(name, cast(Any, observed(name, node)))
        builder.add_node("collect_feed", cast(Any, observed("collect_feed", nodes.collect_feed)))
        builder.add_node(
            "analyze_evidence", cast(Any, observed("analyze_evidence", nodes.analyze_evidence))
        )
        builder.add_edge(START, "preflight")
        builder.add_conditional_edges(
            "preflight",
            lambda state: "cancel" if state["status"] is ResearchStatus.CANCELLED else "continue",
            {"cancel": END, "continue": "planner"},
        )
        builder.add_edge("planner", "parallel_collection")

        def dispatch_collection(state: ResearchState) -> list[Send]:
            task = state["specification"]
            return [
                Send(
                    "collect_feed",
                    {
                        "feed_type": feed,
                        "symbol": task.symbols[0],
                        "data_cutoff": task.data_cutoff,
                    },
                )
                for feed in state["collection_targets"]
            ]

        builder.add_conditional_edges("parallel_collection", dispatch_collection)
        builder.add_edge("collect_feed", "normalize_freshness_lineage")
        builder.add_edge("normalize_freshness_lineage", "parallel_analysts")

        def dispatch_analysts(state: ResearchState) -> list[Send] | str:
            if not state["evidence"]:
                return "evidence_judge"
            return [Send("analyze_evidence", {"evidence": item}) for item in state["evidence"]]

        builder.add_conditional_edges("parallel_analysts", dispatch_analysts)
        builder.add_edge("analyze_evidence", "evidence_judge")
        builder.add_conditional_edges(
            "evidence_judge",
            lambda state: (
                "reflect"
                if (state["gaps"] or state["conflicts"]) and state["reflections"] < 1
                else "score"
            ),
            {"reflect": "reflect", "score": "deterministic_score_confidence"},
        )
        builder.add_edge("reflect", "parallel_collection")
        builder.add_edge("deterministic_score_confidence", "investment_thesis")
        builder.add_edge("investment_thesis", "research_opinion")
        builder.add_edge("research_opinion", "writer")
        builder.add_edge("writer", "citation_verifier")
        builder.add_conditional_edges(
            "citation_verifier",
            lambda state: "verified" if state["citations_verified"] else "degrade",
            {
                "verified": "decision_diff",
                "degrade": "degrade_unverified_decision",
            },
        )
        builder.add_edge("degrade_unverified_decision", "decision_diff")
        builder.add_edge("decision_diff", "persist_decision")
        builder.add_edge("persist_decision", END)
        self._compiled = builder.compile(checkpointer=checkpointer)

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
            "collection_targets": (),
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
        config: RunnableConfig = {"configurable": {"thread_id": run_id}}
        graph_input: ResearchState | None = initial
        if self._checkpointer is not None and self._checkpointer.get(config) is not None:
            graph_input = None
        final = cast(
            ResearchState,
            self._compiled.invoke(graph_input, config),
        )
        result = ResearchResult.from_state(final)
        if result.decision_id is not None:
            self._store.persist(result)
        return result
