"""Canonical v0.2 table registry used by persistence and schema tooling."""

from stock_platform.infrastructure.db.models import tables as _tables  # noqa: F401

CORE_TABLES = frozenset(
    {
        "raw_data_object",
        "normalized_record",
        "derived_metric",
        "evidence_item",
        "evidence_gap",
        "claim",
        "investment_thesis",
        "thesis_evidence_link",
        "research_opinion",
        "portfolio_action",
        "decision_snapshot",
        "decision_diff",
        "market_context_snapshot",
        "research_scoring_policy_version",
        "risk_policy_version",
        "execution_policy_version",
        "confidence_policy_version",
        "tool_call",
        "agent_event",
        "order_intent",
        "paper_order",
        "paper_fill",
        "cash_ledger",
        "corporate_action",
        "alert_event",
        "alert_thesis_link",
        "alert_explanation",
        "notification_outbox",
        "alert_metric",
    }
)

APPEND_ONLY_TABLES = frozenset(
    {
        "investment_thesis",
        "decision_snapshot",
        "decision_diff",
        "paper_fill",
        "cash_ledger",
        "tool_call",
        "agent_event",
    }
)
