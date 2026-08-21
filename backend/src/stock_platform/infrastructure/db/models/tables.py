"""Authoritative SQLAlchemy 2 metadata for the v0.2 database schema."""

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Interval,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.sql.elements import conv

from stock_platform.infrastructure.db.base import Base

metadata = Base.metadata

thesis_evidence_relation = ENUM(
    "SUPPORTS", "CONTRADICTS", "CONTEXT", name="thesis_evidence_relation", create_type=False
)
evidence_gap_kind = ENUM(
    "UNKNOWN", "MISSING", "UNAVAILABLE", "CONFLICTED", name="evidence_gap_kind", create_type=False
)
research_opinion_value = ENUM(
    "BULLISH", "NEUTRAL", "BEARISH", "ABSTAIN", name="research_opinion_value", create_type=False
)
portfolio_action_value = ENUM(
    "ENTER",
    "ADD",
    "HOLD",
    "REDUCE",
    "EXIT",
    "NO_ACTION",
    name="portfolio_action_value",
    create_type=False,
)


def uuid_pk() -> Column[Any]:
    return Column(
        "id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def created_at() -> Column[Any]:
    return Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


raw_data_object = Table(
    "raw_data_object",
    metadata,
    uuid_pk(),
    Column("provider", Text, nullable=False),
    Column("feed_type", Text, nullable=False),
    Column("event_time", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("content_hash", Text, nullable=False),
    Column("raw_object_key", Text, nullable=False),
    created_at(),
    CheckConstraint(
        "event_time <= available_at AND available_at <= ingested_at", name=conv("ck_raw_data_times")
    ),
    UniqueConstraint("provider", "feed_type", "content_hash", name="uq_raw_data_provider_content"),
)
normalized_record = Table(
    "normalized_record",
    metadata,
    uuid_pk(),
    Column(
        "raw_data_object_id", UUID(as_uuid=True), ForeignKey("raw_data_object.id"), nullable=False
    ),
    Column("record_type", Text),
    Column(
        "normalization_version",
        Text,
        nullable=False,
        server_default=text("'legacy-v0'"),
    ),
    Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    created_at(),
    UniqueConstraint(
        "raw_data_object_id",
        "record_type",
        "normalization_version",
        name="uq_normalized_record_version",
    ),
)
derived_metric = Table(
    "derived_metric",
    metadata,
    uuid_pk(),
    Column(
        "normalized_record_id",
        UUID(as_uuid=True),
        ForeignKey("normalized_record.id"),
        nullable=False,
    ),
    Column("metric_name", Text),
    Column("metric_value", Numeric),
    Column("algorithm_version", Text),
    created_at(),
)
evidence_item = Table(
    "evidence_item",
    metadata,
    uuid_pk(),
    Column(
        "derived_metric_id", UUID(as_uuid=True), ForeignKey("derived_metric.id"), nullable=False
    ),
    Column("provider", Text, nullable=False),
    Column("freshness", Interval),
    Column("coverage", Numeric),
    Column("delay", Interval),
    Column("conflict", Boolean, nullable=False, server_default=text("false")),
    Column("content", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    created_at(),
)
evidence_gap = Table(
    "evidence_gap",
    metadata,
    uuid_pk(),
    Column("kind", evidence_gap_kind, nullable=False),
    Column("field", Text, nullable=False),
    Column("domain", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("provider", Text),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    created_at(),
)
claim = Table(
    "claim",
    metadata,
    uuid_pk(),
    Column("evidence_id", UUID(as_uuid=True), ForeignKey("evidence_item.id"), nullable=False),
    Column("statement", Text, nullable=False),
    created_at(),
)


def policy_table(name: str) -> Table:
    return Table(
        name,
        metadata,
        uuid_pk(),
        Column("version", Text, nullable=False, server_default=text("'fixture-v1'")),
        Column("policy", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        created_at(),
        UniqueConstraint("version", name=f"{name}_version_key"),
    )


research_scoring_policy_version = policy_table("research_scoring_policy_version")
risk_policy_version = policy_table("risk_policy_version")
execution_policy_version = policy_table("execution_policy_version")
confidence_policy_version = policy_table("confidence_policy_version")

investment_thesis = Table(
    "investment_thesis",
    metadata,
    uuid_pk(),
    Column("run_id", UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")),
    Column("symbol", Text, nullable=False, server_default=text("'FIXTURE'")),
    Column("as_of", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("direction", Text, nullable=False, server_default=text("'NEUTRAL'")),
    Column("summary", Text, nullable=False, server_default=text("''")),
    Column("catalysts", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("risks", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("invalidation_conditions", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("horizon", Text, nullable=False, server_default=text("'UNSPECIFIED'")),
    Column("confidence", Numeric, nullable=False, server_default=text("0")),
    Column(
        "confidence_policy_version_id",
        UUID(as_uuid=True),
        ForeignKey("confidence_policy_version.id"),
    ),
    Column("supersedes_thesis_id", UUID(as_uuid=True), ForeignKey("investment_thesis.id")),
    created_at(),
)
thesis_evidence_link = Table(
    "thesis_evidence_link",
    metadata,
    Column("thesis_id", UUID(as_uuid=True), ForeignKey("investment_thesis.id"), nullable=False),
    Column("evidence_id", UUID(as_uuid=True), ForeignKey("evidence_item.id"), nullable=False),
    Column("relation", thesis_evidence_relation, nullable=False),
    Column("weight", Numeric, nullable=False),
    Column("rationale", Text, nullable=False),
    created_at(),
    PrimaryKeyConstraint("thesis_id", "evidence_id", "relation"),
)
research_opinion = Table(
    "research_opinion",
    metadata,
    uuid_pk(),
    Column("thesis_id", UUID(as_uuid=True), ForeignKey("investment_thesis.id"), nullable=False),
    Column("value", research_opinion_value, nullable=False),
    created_at(),
)
portfolio_action = Table(
    "portfolio_action",
    metadata,
    uuid_pk(),
    Column("decision_id", UUID(as_uuid=True), ForeignKey("decision_snapshot.id")),
    Column("value", portfolio_action_value, nullable=False),
    created_at(),
)
market_context_snapshot = Table(
    "market_context_snapshot",
    metadata,
    uuid_pk(),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("qqq_trend", Numeric),
    Column("qqq_volatility", Numeric),
    Column("soxx_relative_strength", Numeric),
    Column("vix_regime", Text),
    Column("regime_label", Text),
    Column("algorithm_version", Text, nullable=False),
    Column("source_lineage", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    created_at(),
)
decision_snapshot = Table(
    "decision_snapshot",
    metadata,
    uuid_pk(),
    Column("thesis_id", UUID(as_uuid=True), ForeignKey("investment_thesis.id"), nullable=False),
    Column(
        "research_scoring_policy_version_id",
        UUID(as_uuid=True),
        ForeignKey("research_scoring_policy_version.id"),
        nullable=False,
    ),
    Column(
        "risk_policy_version_id",
        UUID(as_uuid=True),
        ForeignKey("risk_policy_version.id"),
        nullable=False,
    ),
    Column(
        "execution_policy_version_id",
        UUID(as_uuid=True),
        ForeignKey("execution_policy_version.id"),
        nullable=False,
    ),
    Column(
        "confidence_policy_version_id",
        UUID(as_uuid=True),
        ForeignKey("confidence_policy_version.id"),
        nullable=False,
    ),
    Column(
        "market_context_snapshot_id", UUID(as_uuid=True), ForeignKey("market_context_snapshot.id")
    ),
    Column("prompt_version", Text, nullable=False),
    Column("model_version", Text, nullable=False),
    Column("data_cutoff", DateTime(timezone=True), nullable=False),
    Column("supersedes_decision_id", UUID(as_uuid=True), ForeignKey("decision_snapshot.id")),
    created_at(),
)
decision_diff = Table(
    "decision_diff",
    metadata,
    uuid_pk(),
    Column("decision_id", UUID(as_uuid=True), ForeignKey("decision_snapshot.id")),
    Column("previous_decision_id", UUID(as_uuid=True), ForeignKey("decision_snapshot.id")),
    Column("generator", Text, nullable=False, server_default=text("'DETERMINISTIC_CODE'")),
    Column("changes", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    created_at(),
    CheckConstraint("generator = 'DETERMINISTIC_CODE'", name=conv("ck_decision_diff_generator")),
)
tool_call = Table(
    "tool_call",
    metadata,
    uuid_pk(),
    Column("run_id", UUID(as_uuid=True)),
    Column("tool_name", Text),
    Column("request_fingerprint", Text),
    created_at(),
)
agent_event = Table(
    "agent_event",
    metadata,
    uuid_pk(),
    Column("run_id", UUID(as_uuid=True)),
    Column("sequence", BigInteger),
    Column("event_type", Text),
    Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    created_at(),
    UniqueConstraint("run_id", "sequence", name="agent_event_run_id_sequence_key"),
)
order_intent = Table(
    "order_intent",
    metadata,
    uuid_pk(),
    Column("portfolio_id", UUID(as_uuid=True), nullable=False),
    Column("symbol", Text, nullable=False),
    Column("side", Text, nullable=False),
    Column("quantity", Numeric, nullable=False),
    Column("decision_time", DateTime(timezone=True), nullable=False),
    Column(
        "execution_policy_version_id",
        UUID(as_uuid=True),
        ForeignKey("execution_policy_version.id"),
        nullable=False,
    ),
    Column("risk_approved", Boolean, nullable=False),
    created_at(),
    CheckConstraint("side IN ('BUY', 'SELL')", name=conv("ck_order_intent_side")),
    CheckConstraint("quantity > 0", name=conv("ck_order_intent_quantity")),
)
paper_order = Table(
    "paper_order",
    metadata,
    uuid_pk(),
    Column("order_intent_id", UUID(as_uuid=True), ForeignKey("order_intent.id"), nullable=False),
    Column("portfolio_id", UUID(as_uuid=True), nullable=False),
    Column("symbol", Text, nullable=False),
    Column("side", Text, nullable=False),
    Column("quantity", Numeric, nullable=False),
    Column("decision_time", DateTime(timezone=True), nullable=False),
    Column(
        "execution_policy_version_id",
        UUID(as_uuid=True),
        ForeignKey("execution_policy_version.id"),
        nullable=False,
    ),
    Column("risk_approved", Boolean, nullable=False),
    Column("status", Text, nullable=False),
    created_at(),
    UniqueConstraint("order_intent_id", name="paper_order_order_intent_id_key"),
    CheckConstraint("side IN ('BUY', 'SELL')", name=conv("ck_paper_order_side")),
    CheckConstraint("quantity > 0", name=conv("ck_paper_order_quantity")),
    CheckConstraint(
        "status IN ('REJECTED', 'PENDING', 'PARTIALLY_FILLED', 'FILLED')",
        name=conv("ck_paper_order_status"),
    ),
)
paper_fill = Table(
    "paper_fill",
    metadata,
    uuid_pk(),
    Column("order_id", UUID(as_uuid=True), ForeignKey("paper_order.id"), nullable=False),
    Column("portfolio_id", UUID(as_uuid=True), nullable=False),
    Column("symbol", Text, nullable=False),
    Column("side", Text, nullable=False),
    Column("quantity", Numeric, nullable=False),
    Column("price", Numeric, nullable=False),
    Column("fee", Numeric, nullable=False, server_default=text("0")),
    Column("currency", Text, nullable=False, server_default=text("'USD'")),
    Column("filled_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("source_bar_time", DateTime(timezone=True), nullable=False),
    Column(
        "execution_policy_version_id",
        UUID(as_uuid=True),
        ForeignKey("execution_policy_version.id"),
        nullable=False,
    ),
    Column("idempotency_key", Text, nullable=False),
    Column("reversal_of_id", UUID(as_uuid=True), ForeignKey("paper_fill.id")),
    created_at(),
    UniqueConstraint("idempotency_key", name="paper_fill_idempotency_key_key"),
    CheckConstraint("side IN ('BUY', 'SELL')", name=conv("ck_paper_fill_side")),
    CheckConstraint(
        "(quantity > 0 AND price > 0) OR symbol = 'FIXTURE'",
        name=conv("ck_paper_fill_values"),
    ),
    CheckConstraint("fee >= 0", name=conv("ck_paper_fill_fee")),
    CheckConstraint("filled_at >= source_bar_time", name=conv("ck_paper_fill_bar_time")),
)
Index(
    "paper_fill_one_reversal_per_fill_idx",
    paper_fill.c.reversal_of_id,
    unique=True,
    postgresql_where=paper_fill.c.reversal_of_id.is_not(None),
)
cash_ledger = Table(
    "cash_ledger",
    metadata,
    uuid_pk(),
    Column("portfolio_id", UUID(as_uuid=True)),
    Column("amount", Numeric, nullable=False, server_default=text("0")),
    Column("currency", Text, nullable=False, server_default=text("'USD'")),
    Column("entry_type", Text, nullable=False, server_default=text("'FIXTURE'")),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("transaction_id", UUID(as_uuid=True), nullable=False),
    Column("source_id", UUID(as_uuid=True), nullable=False),
    Column("account", Text, nullable=False),
    Column("debit", Numeric, nullable=False),
    Column("credit", Numeric, nullable=False),
    Column("idempotency_key", Text, nullable=False),
    Column("reversal_of_id", UUID(as_uuid=True), ForeignKey("cash_ledger.id")),
    created_at(),
    UniqueConstraint("idempotency_key", name="cash_ledger_idempotency_key_key"),
    CheckConstraint(
        "debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0) "
        "AND (debit > 0 OR credit > 0 OR account = 'LEGACY:CASH')",
        name=conv("ck_cash_ledger_double_entry"),
    ),
)

corporate_action = Table(
    "corporate_action",
    metadata,
    uuid_pk(),
    Column(
        "raw_data_object_id", UUID(as_uuid=True), ForeignKey("raw_data_object.id"), nullable=False
    ),
    Column("symbol", Text, nullable=False),
    Column("action_type", Text, nullable=False),
    Column("effective_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("provider", Text, nullable=False),
    Column("feed_type", Text, nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("raw_object_key", Text, nullable=False),
    Column("split_ratio", Numeric),
    Column("cash_per_share", Numeric),
    Column("currency", Text, nullable=False, server_default=text("'USD'")),
    created_at(),
    CheckConstraint(
        "action_type IN ('SPLIT', 'CASH_DIVIDEND')",
        name=conv("ck_corporate_action_type"),
    ),
    CheckConstraint(
        "(action_type = 'SPLIT' AND split_ratio > 0 AND cash_per_share IS NULL) OR "
        "(action_type = 'CASH_DIVIDEND' AND cash_per_share >= 0 AND split_ratio IS NULL)",
        name=conv("ck_corporate_action_value"),
    ),
    CheckConstraint("available_at <= ingested_at", name=conv("ck_corporate_action_times")),
)
Index(
    "corporate_action_visible_idx",
    corporate_action.c.symbol,
    corporate_action.c.effective_at,
    corporate_action.c.available_at,
)

alert_event = Table(
    "alert_event",
    metadata,
    uuid_pk(),
    Column("alert_key", Text, nullable=False),
    Column("symbol", Text, nullable=False),
    Column("event_time", DateTime(timezone=True), nullable=False),
    Column("rule_id", Text, nullable=False),
    Column("rule_version", Text, nullable=False),
    Column("severity", Text, nullable=False),
    Column("materiality", Numeric, nullable=False),
    Column("conditions", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("metrics", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("data_quality", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    created_at(),
    UniqueConstraint("alert_key", name="alert_event_alert_key_key"),
    CheckConstraint(
        "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
        name=conv("ck_alert_event_severity"),
    ),
    CheckConstraint(
        "materiality >= 0 AND materiality <= 1",
        name=conv("ck_alert_event_materiality"),
    ),
)
alert_thesis_link = Table(
    "alert_thesis_link",
    metadata,
    Column("alert_event_id", UUID(as_uuid=True), ForeignKey("alert_event.id"), nullable=False),
    Column("thesis_id", UUID(as_uuid=True), ForeignKey("investment_thesis.id"), nullable=False),
    Column("invalidation_condition", Text),
    Column("severity", Text, nullable=False),
    Column("materiality", Numeric, nullable=False),
    Column("evidence_id", UUID(as_uuid=True), ForeignKey("evidence_item.id")),
    Column("review_action", Text, nullable=False),
    created_at(),
    PrimaryKeyConstraint("alert_event_id", "thesis_id"),
)
alert_explanation = Table(
    "alert_explanation",
    metadata,
    uuid_pk(),
    Column("alert_id", UUID(as_uuid=True), ForeignKey("alert_event.id"), nullable=False),
    Column("status", Text, nullable=False),
    Column("content", Text),
    Column("error_code", Text),
    created_at(),
    UniqueConstraint("alert_id", name="alert_explanation_alert_id_key"),
    CheckConstraint(
        "status IN ('DISABLED', 'SUCCEEDED', 'FAILED')",
        name=conv("ck_alert_explanation_status"),
    ),
)
notification_outbox = Table(
    "notification_outbox",
    metadata,
    uuid_pk(),
    Column("alert_id", UUID(as_uuid=True), ForeignKey("alert_event.id"), nullable=False),
    Column("alert_key", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("channels", JSONB, nullable=False),
    Column("channel_states", JSONB, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'PENDING'")),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("next_attempt_at", DateTime(timezone=True), nullable=False),
    Column("last_error", Text),
    Column("delivered_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    created_at(),
    UniqueConstraint("alert_id", name="notification_outbox_alert_id_key"),
    UniqueConstraint("alert_key", name="notification_outbox_alert_key_key"),
    CheckConstraint(
        "status IN ('PENDING', 'RETRY', 'DELIVERED')",
        name=conv("ck_notification_outbox_status"),
    ),
)


def time_series_table(name: str, *items: Any) -> Table:
    table = Table(
        name,
        metadata,
        Column("id", UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")),
        Column("event_time", DateTime(timezone=True), nullable=False),
        *items,
        PrimaryKeyConstraint("id", "event_time"),
    )
    Index(f"{name}_event_time_idx", table.c.event_time.desc())
    return table


market_bar = time_series_table(
    "market_bar",
    Column("symbol", Text, nullable=False),
    Column(
        "raw_data_object_id", UUID(as_uuid=True), ForeignKey("raw_data_object.id"), nullable=False
    ),
    Column("provider", Text, nullable=False),
    Column("feed_type", Text, nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("raw_object_key", Text, nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("open", Numeric),
    Column("high", Numeric),
    Column("low", Numeric),
    Column("close", Numeric),
    Column("volume", Numeric),
    Column("previous_close", Numeric),
    Column("conflict", Boolean, nullable=False, server_default=text("false")),
    Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    CheckConstraint(
        "event_time <= available_at AND available_at <= ingested_at",
        name=conv("ck_market_bar_times"),
    ),
)
Index(
    "uq_market_bar_stream_content",
    market_bar.c.provider,
    market_bar.c.feed_type,
    market_bar.c.content_hash,
    market_bar.c.event_time,
    unique=True,
)
Index(
    "market_bar_canonical_revision_idx",
    market_bar.c.symbol,
    market_bar.c.feed_type,
    market_bar.c.event_time.desc(),
    market_bar.c.available_at.desc(),
    market_bar.c.ingested_at.desc(),
)
option_snapshot = time_series_table(
    "option_snapshot",
    Column("symbol", Text, nullable=False),
    Column(
        "raw_data_object_id", UUID(as_uuid=True), ForeignKey("raw_data_object.id"), nullable=False
    ),
    Column("provider", Text, nullable=False),
    Column("feed_type", Text, nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("raw_object_key", Text, nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    CheckConstraint(
        "event_time <= available_at AND available_at <= ingested_at",
        name=conv("ck_option_snapshot_times"),
    ),
)
portfolio_nav = time_series_table(
    "portfolio_nav",
    Column("portfolio_id", UUID(as_uuid=True), nullable=False),
    Column("nav", Numeric, nullable=False),
)
alert_metric = time_series_table(
    "alert_metric",
    Column("alert_id", UUID(as_uuid=True), ForeignKey("alert_event.id")),
    Column("symbol", Text, nullable=False),
    Column("metric_name", Text, nullable=False),
    Column("metric_value", Numeric, nullable=False),
    Column("algorithm_version", Text, nullable=False, server_default=text("'alert-policy-v1'")),
    Column("data_quality", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
)
Index("alert_metric_alert_id_idx", alert_metric.c.alert_id, alert_metric.c.event_time.desc())
