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
paper_fill = Table(
    "paper_fill",
    metadata,
    uuid_pk(),
    Column("order_id", UUID(as_uuid=True)),
    Column("quantity", Numeric),
    Column("price", Numeric),
    Column("currency", Text, nullable=False, server_default=text("'USD'")),
    Column("filled_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    created_at(),
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
    created_at(),
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
    Column("close", Numeric),
    CheckConstraint(
        "event_time <= available_at AND available_at <= ingested_at",
        name=conv("ck_market_bar_times"),
    ),
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
    Column("symbol", Text, nullable=False),
    Column("metric_name", Text, nullable=False),
    Column("metric_value", Numeric, nullable=False),
)
