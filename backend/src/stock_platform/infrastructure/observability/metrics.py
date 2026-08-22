"""Bounded Prometheus metrics for the operational acceptance categories."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest, multiprocess

_UNBOUNDED_LABELS = frozenset({"symbol", "run_id", "correlation_id", "user_id"})
_ALERT_RULES = frozenset({"market_anomaly", "market-anomaly-v1"})


class PlatformMetrics:
    def __init__(self, multiprocess_dir: str | None = None) -> None:
        self._multiprocess_dir = multiprocess_dir
        if multiprocess_dir is not None:
            Path(multiprocess_dir).mkdir(parents=True, exist_ok=True)
        self._registry = CollectorRegistry()
        self._families = {
            "service_requests": Counter(
                "platform_service_requests",
                "Service requests",
                ("service", "route", "status"),
                registry=self._registry,
            ),
            "provider_calls": Counter(
                "platform_provider_calls",
                "Provider calls",
                ("provider", "outcome"),
                registry=self._registry,
            ),
            "tool_calls": Counter(
                "platform_tool_calls", "Tool calls", ("tool", "outcome"), registry=self._registry
            ),
            "graph_nodes": Counter(
                "platform_graph_nodes",
                "Graph node executions",
                ("graph", "node", "outcome"),
                registry=self._registry,
            ),
            "alerts": Counter(
                "platform_alerts", "Alert outcomes", ("rule", "outcome"), registry=self._registry
            ),
            "queue": Gauge(
                "platform_queue_depth",
                "Queue depth",
                ("queue",),
                registry=self._registry,
                multiprocess_mode="livemostrecent",
            ),
            "cost": Counter(
                "platform_cost", "Deterministic cost units", ("kind",), registry=self._registry
            ),
            "evaluation_runs": Counter(
                "platform_evaluation_runs",
                "Evaluation outcomes",
                ("suite", "outcome"),
                registry=self._registry,
            ),
        }

    def observe(self, family: str, labels: Mapping[str, str], amount: float = 1) -> None:
        if _UNBOUNDED_LABELS.intersection(labels):
            raise ValueError("unbounded metric labels are forbidden")
        metric = self._families[family].labels(**labels)
        if family == "queue":
            cast(Gauge, metric).set(amount)
        else:
            cast(Counter, metric).inc(amount)

    def observe_request(self, *, service: str, route: str, status: str) -> None:
        self.observe("service_requests", {"service": service, "route": route, "status": status})

    def observe_provider(self, *, provider: str, outcome: str) -> None:
        self.observe("provider_calls", {"provider": provider, "outcome": outcome})

    def observe_tool(self, *, tool: str, outcome: str) -> None:
        self.observe("tool_calls", {"tool": tool, "outcome": outcome})

    def observe_graph(self, *, graph: str, node: str, outcome: str) -> None:
        self.observe("graph_nodes", {"graph": graph, "node": node, "outcome": outcome})

    def observe_alert(self, *, rule: str, outcome: str) -> None:
        if rule not in _ALERT_RULES:
            raise ValueError("alert rule metric labels must use a bounded rule set")
        self.observe("alerts", {"rule": rule, "outcome": outcome})

    def set_queue(self, *, queue: str, depth: int) -> None:
        self.observe("queue", {"queue": queue}, depth)

    def observe_cost(self, *, kind: str, amount: int) -> None:
        self.observe("cost", {"kind": kind}, amount)

    def observe_evaluation(self, *, suite: str, outcome: str) -> None:
        self.observe("evaluation_runs", {"suite": suite, "outcome": outcome})

    def render(self) -> str:
        if self._multiprocess_dir is not None:
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(  # type: ignore[no-untyped-call]
                registry, path=self._multiprocess_dir
            )
            return generate_latest(registry).decode()
        return generate_latest(self._registry).decode()


platform_metrics = PlatformMetrics(os.getenv("PROMETHEUS_MULTIPROC_DIR"))
