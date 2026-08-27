"""Authoritative SQLAlchemy 2 metadata for the v0.2 database schema."""

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
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
    Column("record_key", Text, nullable=False),
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
        "record_key",
        name="uq_normalized_record_version",
    ),
)
normalization_rejection = Table(
    "normalization_rejection",
    metadata,
    uuid_pk(),
    Column(
        "raw_data_object_id",
        UUID(as_uuid=True),
        ForeignKey("raw_data_object.id"),
        nullable=False,
    ),
    Column("record_key", Text),
    Column("normalization_version", Text, nullable=False),
    Column("error_class", Text, nullable=False),
    Column("error_detail", JSONB, nullable=False),
    created_at(),
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
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("qqq_trend", Numeric),
    Column("qqq_volatility", Numeric),
    Column("soxx_relative_strength", Numeric),
    Column("vix_regime", Text),
    Column("vix", Numeric),
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
    Column("available_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
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
    Column(
        "correlation_id",
        UUID(as_uuid=True),
        nullable=False,
        server_default=text("gen_random_uuid()"),
    ),
    Column("run_id", UUID(as_uuid=True)),
    Column("tool_name", Text),
    Column("request_fingerprint", Text),
    created_at(),
)
agent_event = Table(
    "agent_event",
    metadata,
    uuid_pk(),
    Column(
        "correlation_id",
        UUID(as_uuid=True),
        nullable=False,
        server_default=text("gen_random_uuid()"),
    ),
    Column("run_id", UUID(as_uuid=True)),
    Column("sequence", BigInteger),
    Column("event_type", Text),
    Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    created_at(),
    UniqueConstraint("run_id", "sequence", name="agent_event_run_id_sequence_key"),
)
agent_run = Table(
    "agent_run",
    metadata,
    uuid_pk(),
    Column(
        "correlation_id",
        UUID(as_uuid=True),
        nullable=False,
        server_default=text("gen_random_uuid()"),
    ),
    Column("run_type", Text, nullable=False),
    Column("idempotency_key", Text, nullable=False),
    Column("request_hash", Text, nullable=False),
    Column("request_payload", JSONB, nullable=False),
    Column("symbol", Text),
    Column("decision_time", DateTime(timezone=True), nullable=False),
    Column("data_cutoff", DateTime(timezone=True), nullable=False),
    Column("status", Text, nullable=False, server_default=text("'QUEUED'")),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("max_attempts", Integer, nullable=False, server_default=text("3")),
    Column("last_error", JSONB),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column(
        "research_scoring_policy_version",
        Text,
        nullable=False,
        server_default=text("'research-v1'"),
    ),
    Column("risk_policy_version", Text, nullable=False, server_default=text("'risk-v1'")),
    Column("execution_policy_version", Text, nullable=False, server_default=text("'execution-v1'")),
    Column(
        "confidence_policy_version", Text, nullable=False, server_default=text("'confidence-v1'")
    ),
    Column("prompt_version", Text, nullable=False, server_default=text("'prompt-v1'")),
    Column("model_version", Text, nullable=False, server_default=text("'fixture-v1'")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    created_at(),
    UniqueConstraint("idempotency_key", name="agent_run_idempotency_key_key"),
    CheckConstraint(
        "run_type IN ('RESEARCH', 'PORTFOLIO', 'ALERT_MONITOR', 'WEEKLY_REVIEW')",
        name=conv("ck_agent_run_type"),
    ),
    CheckConstraint(
        "status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
        name=conv("ck_agent_run_status"),
    ),
    CheckConstraint("data_cutoff <= decision_time", name=conv("ck_agent_run_cutoff")),
    CheckConstraint(
        "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
        name=conv("ck_agent_run_attempts"),
    ),
)
Index("agent_run_active_created_idx", agent_run.c.status, agent_run.c.created_at)
paper_portfolio_config = Table(
    "paper_portfolio_config",
    metadata,
    uuid_pk(),
    Column("name", Text, nullable=False),
    Column("initial_cash", Numeric, nullable=False),
    Column("currency", Text, nullable=False),
    created_at(),
    UniqueConstraint("name", name="paper_portfolio_config_name_key"),
    CheckConstraint(
        "id = '10000000-0000-0000-0000-000000000001'::uuid",
        name=conv("ck_paper_portfolio_config_singleton_id"),
    ),
    CheckConstraint("initial_cash > 0", name=conv("ck_paper_portfolio_config_cash")),
    CheckConstraint("currency = 'USD'", name=conv("ck_paper_portfolio_config_currency")),
)
security = Table(
    "security",
    metadata,
    uuid_pk(),
    Column("instrument_type", Text, nullable=False),
    created_at(),
)
security_identifier_version = Table(
    "security_identifier_version",
    metadata,
    uuid_pk(),
    Column("security_id", UUID(as_uuid=True), ForeignKey("security.id"), nullable=False),
    Column("identifier_type", Text, nullable=False),
    Column("identifier_value", Text, nullable=False),
    Column("exchange", Text),
    Column("provider_identifiers", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("effective_from", DateTime(timezone=True), nullable=False),
    Column("effective_to", DateTime(timezone=True)),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("supersedes_id", UUID(as_uuid=True), ForeignKey("security_identifier_version.id")),
    created_at(),
    CheckConstraint(
        "effective_to IS NULL OR effective_from < effective_to",
        name=conv("ck_security_identifier_effective_range"),
    ),
    CheckConstraint(
        "supersedes_id IS NULL OR supersedes_id <> id",
        name=conv("ck_security_identifier_supersedes_self"),
    ),
    UniqueConstraint(
        "security_id",
        "identifier_type",
        "identifier_value",
        "available_at",
        name="uq_security_identifier_version",
    ),
)
Index(
    "security_identifier_lookup_idx",
    security_identifier_version.c.identifier_type,
    security_identifier_version.c.identifier_value,
    security_identifier_version.c.available_at,
)
security_profile_version = Table(
    "security_profile_version",
    metadata,
    uuid_pk(),
    Column("security_id", UUID(as_uuid=True), ForeignKey("security.id"), nullable=False),
    Column("company_name", Text),
    Column("currency", Text),
    Column("cik", Text),
    Column("filing_regime", Text),
    Column("industry_role", Text),
    Column("country_of_incorporation", Text),
    Column("exchange_timezone", Text),
    Column("is_adr", Boolean, nullable=False, server_default=text("false")),
    Column("adr_ratio", Numeric),
    Column("primary_market", Text),
    Column("source_currency", Text),
    Column("effective_from", DateTime(timezone=True), nullable=False),
    Column("effective_to", DateTime(timezone=True)),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("supersedes_id", UUID(as_uuid=True), ForeignKey("security_profile_version.id")),
    created_at(),
    CheckConstraint(
        "effective_to IS NULL OR effective_from < effective_to",
        name=conv("ck_security_profile_effective_range"),
    ),
    CheckConstraint(
        "supersedes_id IS NULL OR supersedes_id <> id",
        name=conv("ck_security_profile_supersedes_self"),
    ),
    CheckConstraint(
        "adr_ratio IS NULL OR adr_ratio > 0",
        name=conv("ck_security_profile_adr_ratio"),
    ),
    UniqueConstraint("security_id", "available_at", name="uq_security_profile_version"),
)
Index(
    "security_profile_pit_idx",
    security_profile_version.c.security_id,
    security_profile_version.c.available_at,
)
ingestion_job = Table(
    "ingestion_job",
    metadata,
    uuid_pk(),
    Column("request_hash", Text, nullable=False),
    Column("request_payload", JSONB, nullable=False),
    Column("provider", Text, nullable=False),
    Column("dataset", Text, nullable=False),
    Column("security_id", UUID(as_uuid=True), ForeignKey("security.id")),
    Column("window_start", DateTime(timezone=True), nullable=False),
    Column("window_end", DateTime(timezone=True), nullable=False),
    Column("purpose", Text, nullable=False),
    Column("state", Text, nullable=False, server_default=text("'QUEUED'")),
    Column("max_attempts", Integer, nullable=False),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("lease_token", UUID(as_uuid=True)),
    Column("lease_generation", Integer, nullable=False, server_default=text("0")),
    Column("lease_owner", Text),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("attempt_started_at", DateTime(timezone=True)),
    Column("next_attempt_at", DateTime(timezone=True)),
    Column("policy_version", Text, nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    created_at(),
    CheckConstraint("window_start <= window_end", name=conv("ck_ingestion_job_window")),
    CheckConstraint(
        "max_attempts > 0 AND attempt_count >= 0 AND attempt_count <= max_attempts "
        "AND lease_generation >= 0",
        name=conv("ck_ingestion_job_attempts"),
    ),
    CheckConstraint(
        "state IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'COMPLETED_WITH_GAPS', "
        "'RETRY_SCHEDULED', 'FAILED', 'DEAD_LETTER', 'CANCELLED')",
        name=conv("ck_ingestion_job_state"),
    ),
    CheckConstraint(
        "(state = 'RUNNING' AND lease_token IS NOT NULL AND lease_owner IS NOT NULL "
        "AND lease_expires_at IS NOT NULL AND attempt_started_at IS NOT NULL) OR "
        "(state <> 'RUNNING' AND lease_token IS NULL AND lease_owner IS NULL "
        "AND lease_expires_at IS NULL AND attempt_started_at IS NULL)",
        name=conv("ck_ingestion_job_running_lease"),
    ),
    CheckConstraint(
        "(state = 'RETRY_SCHEDULED') = (next_attempt_at IS NOT NULL)",
        name=conv("ck_ingestion_job_retry_time"),
    ),
    CheckConstraint(
        "(state IN ('SUCCEEDED', 'COMPLETED_WITH_GAPS', 'FAILED', 'DEAD_LETTER', "
        "'CANCELLED')) = (completed_at IS NOT NULL)",
        name=conv("ck_ingestion_job_completion_time"),
    ),
)
Index(
    "uq_ingestion_job_active_request",
    ingestion_job.c.request_hash,
    unique=True,
    postgresql_where=ingestion_job.c.state.in_(("QUEUED", "RUNNING", "RETRY_SCHEDULED")),
)
Index("ingestion_job_due_idx", ingestion_job.c.state, ingestion_job.c.next_attempt_at)
ingestion_attempt = Table(
    "ingestion_attempt",
    metadata,
    uuid_pk(),
    Column("job_id", UUID(as_uuid=True), ForeignKey("ingestion_job.id"), nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("lease_generation", Integer, nullable=False),
    Column("worker_id", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=False),
    Column("outcome", Text, nullable=False),
    Column("error_class", Text),
    Column("error_detail", JSONB),
    created_at(),
    CheckConstraint(
        "attempt_number > 0 AND lease_generation > 0",
        name=conv("ck_ingestion_attempt_number"),
    ),
    CheckConstraint("started_at <= finished_at", name=conv("ck_ingestion_attempt_time_order")),
    CheckConstraint(
        "outcome IN ('SUCCEEDED', 'COMPLETED_WITH_GAPS', 'RETRY_SCHEDULED', "
        "'FAILED', 'DEAD_LETTER')",
        name=conv("ck_ingestion_attempt_outcome"),
    ),
    CheckConstraint(
        "error_class IS NULL OR error_class IN ('TIMEOUT', 'NETWORK', 'RATE_LIMIT', "
        "'PROVIDER_5XX', 'TEMPORARY_DATABASE', 'TEMPORARY_OBJECT_STORE', 'INVALID_AUTH', "
        "'MISSING_CREDENTIALS', 'UNSUPPORTED_DATASET', 'INVALID_SECURITY', 'SCHEMA_DRIFT')",
        name=conv("ck_ingestion_attempt_error_class"),
    ),
    UniqueConstraint("job_id", "attempt_number", name="uq_ingestion_attempt_number"),
)
ingestion_cursor = Table(
    "ingestion_cursor",
    metadata,
    uuid_pk(),
    Column("provider", Text, nullable=False),
    Column("dataset", Text, nullable=False),
    Column("scope_key", Text, nullable=False),
    Column("cursor_payload", JSONB, nullable=False),
    Column("watermark", DateTime(timezone=True), nullable=False),
    Column("generation", Integer, nullable=False, server_default=text("0")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    created_at(),
    CheckConstraint("generation >= 0", name=conv("ck_ingestion_cursor_generation")),
    UniqueConstraint("provider", "dataset", "scope_key", name="uq_ingestion_cursor_scope"),
)
ingestion_dead_letter = Table(
    "ingestion_dead_letter",
    metadata,
    uuid_pk(),
    Column("job_id", UUID(as_uuid=True), ForeignKey("ingestion_job.id"), nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("error_class", Text, nullable=False),
    Column("error_detail", JSONB, nullable=False),
    created_at(),
    CheckConstraint(
        "error_class IN ('TIMEOUT', 'NETWORK', 'RATE_LIMIT', 'PROVIDER_5XX', "
        "'TEMPORARY_DATABASE', 'TEMPORARY_OBJECT_STORE', 'INVALID_AUTH', "
        "'MISSING_CREDENTIALS', 'UNSUPPORTED_DATASET', 'INVALID_SECURITY', 'SCHEMA_DRIFT')",
        name=conv("ck_ingestion_dead_letter_error_class"),
    ),
    UniqueConstraint("job_id", "attempt_number", name="uq_ingestion_dead_letter_attempt"),
)
ingestion_raw_link = Table(
    "ingestion_raw_link",
    metadata,
    Column("job_id", UUID(as_uuid=True), ForeignKey("ingestion_job.id"), primary_key=True),
    Column(
        "raw_data_object_id",
        UUID(as_uuid=True),
        ForeignKey("raw_data_object.id"),
        primary_key=True,
    ),
    created_at(),
)
normalization_dispatch = Table(
    "normalization_dispatch",
    metadata,
    uuid_pk(),
    Column(
        "raw_data_object_id",
        UUID(as_uuid=True),
        ForeignKey("raw_data_object.id"),
        nullable=False,
    ),
    Column("normalization_version", Text, nullable=False),
    Column("record_type", Text, nullable=False),
    Column("record_key", Text, nullable=False),
    Column("normalized_payload", JSONB, nullable=False),
    Column("state", Text, nullable=False, server_default=text("'PENDING'")),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("lease_token", UUID(as_uuid=True)),
    Column("lease_generation", Integer, nullable=False, server_default=text("0")),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("next_attempt_at", DateTime(timezone=True), nullable=False),
    Column("last_error", JSONB),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    created_at(),
    CheckConstraint(
        "state IN ('PENDING', 'CLAIMED', 'DISPATCHED', 'FAILED')",
        name=conv("ck_normalization_dispatch_state"),
    ),
    CheckConstraint(
        "attempt_count >= 0 AND lease_generation >= 0",
        name=conv("ck_normalization_dispatch_counts"),
    ),
    CheckConstraint(
        "(state = 'CLAIMED' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
        "(state <> 'CLAIMED' AND lease_token IS NULL AND lease_expires_at IS NULL)",
        name=conv("ck_normalization_dispatch_lease"),
    ),
    UniqueConstraint(
        "raw_data_object_id",
        "normalization_version",
        name="uq_normalization_dispatch_version",
    ),
)
watchlist_item = Table(
    "watchlist_item",
    metadata,
    Column("security_id", UUID(as_uuid=True), ForeignKey("security.id"), primary_key=True),
    Column("symbol", Text, nullable=False, unique=True),
    Column("daily_research", Boolean, nullable=False, server_default=text("true")),
    Column("intraday_monitoring", Boolean, nullable=False, server_default=text("true")),
    Column("thresholds", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    created_at(),
)
risk_decision = Table(
    "risk_decision",
    metadata,
    uuid_pk(),
    Column("proposal_id", UUID(as_uuid=True), nullable=False),
    Column("research_decision_id", UUID(as_uuid=True), ForeignKey("decision_snapshot.id")),
    Column("portfolio_id", UUID(as_uuid=True), nullable=False),
    Column("symbol", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("requested_weight", Numeric, nullable=False),
    Column("approved_weight", Numeric, nullable=False),
    Column("current_weight", Numeric, nullable=False, server_default=text("0")),
    Column("approved_delta", Numeric, nullable=False, server_default=text("0")),
    Column("reference_nav", Numeric),
    Column("reference_price", Numeric),
    Column("max_order_quantity", Numeric, nullable=False, server_default=text("0")),
    Column(
        "authorization_source",
        Text,
        nullable=False,
        server_default=text("'DETERMINISTIC'"),
    ),
    Column("authorized_side", Text),
    Column(
        "market_context_snapshot_id",
        UUID(as_uuid=True),
        ForeignKey("market_context_snapshot.id"),
        nullable=False,
    ),
    Column("reason_codes", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column(
        "risk_policy_version_id",
        UUID(as_uuid=True),
        ForeignKey("risk_policy_version.id"),
        nullable=False,
    ),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    created_at(),
    CheckConstraint(
        "status IN ('APPROVED', 'CLIPPED', 'REJECTED')",
        name=conv("ck_risk_decision_status"),
    ),
    CheckConstraint(
        "requested_weight >= 0 AND approved_weight >= 0",
        name=conv("ck_risk_decision_weights"),
    ),
    CheckConstraint(
        "status <> 'REJECTED' OR approved_weight = 0",
        name=conv("ck_risk_decision_rejected_weight"),
    ),
    CheckConstraint(
        "approved_delta = approved_weight - current_weight AND max_order_quantity >= 0",
        name=conv("ck_risk_decision_order_economics"),
    ),
    CheckConstraint(
        "(status = 'APPROVED' AND approved_weight = requested_weight "
        "AND (jsonb_array_length(reason_codes) = 0 "
        "OR reason_codes = '[\"LEGACY_BACKFILL\"]'::jsonb)) "
        "OR (status = 'CLIPPED' AND approved_weight <> requested_weight "
        "AND jsonb_array_length(reason_codes) > 0) "
        "OR (status = 'REJECTED' AND approved_weight = 0 "
        "AND jsonb_array_length(reason_codes) > 0)",
        name=conv("ck_risk_decision_status_facts"),
    ),
    CheckConstraint(
        "(authorization_source = 'LEGACY_BACKFILL' AND "
        " ((status = 'REJECTED' AND max_order_quantity = 0 AND authorized_side IS NULL) "
        "  OR (status <> 'REJECTED' AND max_order_quantity > 0 "
        "      AND authorized_side IN ('BUY', 'SELL')))) "
        "OR (authorization_source = 'DETERMINISTIC' AND "
        " ((status = 'REJECTED' AND max_order_quantity = 0 AND authorized_side IS NULL) "
        "  OR (status <> 'REJECTED' AND "
        "      ((approved_delta = 0 AND max_order_quantity = 0 AND authorized_side IS NULL) "
        "       OR (approved_delta <> 0 AND reference_nav > 0 AND reference_price > 0 "
        "           AND max_order_quantity = abs(approved_delta) * reference_nav / reference_price "
        "           AND authorized_side = CASE WHEN approved_delta > 0 "
        "               THEN 'BUY' ELSE 'SELL' END)))))",
        name=conv("ck_risk_decision_authorization_facts"),
    ),
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
        "risk_decision_id",
        UUID(as_uuid=True),
        ForeignKey("risk_decision.id"),
        nullable=False,
    ),
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
    UniqueConstraint(
        "risk_decision_id",
        name=conv("uq_order_intent_risk_decision_id"),
    ),
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
    Column(
        "normalized_record_id",
        UUID(as_uuid=True),
        ForeignKey("normalized_record.id"),
        nullable=False,
    ),
    Column("security_id", UUID(as_uuid=True), ForeignKey("security.id")),
    Column("provider_action_id", Text, nullable=False),
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
    Column("stock_ratio", Numeric),
    Column("old_adr_ratio", Numeric),
    Column("new_adr_ratio", Numeric),
    Column("currency", Text, nullable=False, server_default=text("'USD'")),
    Column("source_currency", Text, nullable=False, server_default=text("'USD'")),
    Column("details", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("supersedes_id", UUID(as_uuid=True), ForeignKey("corporate_action.id")),
    created_at(),
    CheckConstraint(
        "action_type IN ('SPLIT', 'CASH_DIVIDEND', 'STOCK_DIVIDEND', 'SPIN_OFF', "
        "'SYMBOL_CHANGE', 'MERGER_ACQUISITION', 'ADR_RATIO_CHANGE')",
        name=conv("ck_corporate_action_type"),
    ),
    CheckConstraint(
        "(action_type = 'SPLIT' AND split_ratio > 0) OR "
        "(action_type = 'CASH_DIVIDEND' AND cash_per_share >= 0) OR "
        "(action_type = 'STOCK_DIVIDEND' AND stock_ratio >= 0) OR "
        "(action_type = 'ADR_RATIO_CHANGE' AND old_adr_ratio > 0 AND new_adr_ratio > 0) OR "
        "action_type IN ('SPIN_OFF', 'SYMBOL_CHANGE', 'MERGER_ACQUISITION')",
        name=conv("ck_corporate_action_value"),
    ),
    CheckConstraint(
        "supersedes_id IS NULL OR supersedes_id <> id",
        name=conv("ck_corporate_action_supersedes_self"),
    ),
    CheckConstraint("available_at <= ingested_at", name=conv("ck_corporate_action_times")),
    UniqueConstraint(
        "provider", "provider_action_id", "available_at", name="uq_corporate_action_version"
    ),
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
    Column(
        "correlation_id",
        UUID(as_uuid=True),
        nullable=False,
        server_default=text("gen_random_uuid()"),
    ),
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
    Column("acknowledged_at", DateTime(timezone=True)),
    Column("acknowledged_by", Text),
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
Index("agent_run_correlation_idx", agent_run.c.correlation_id)
Index("agent_event_correlation_idx", agent_event.c.correlation_id)
Index("tool_call_correlation_idx", tool_call.c.correlation_id)
Index("alert_event_correlation_idx", alert_event.c.correlation_id)
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

weekly_review_run = Table(
    "weekly_review_run",
    metadata,
    uuid_pk(),
    Column("run_key", Text, nullable=False),
    Column("decision_ids", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("decision_time", DateTime(timezone=True), nullable=False),
    Column("data_cutoff", DateTime(timezone=True), nullable=False),
    Column("research_scoring_policy_version", Text, nullable=False),
    Column("risk_policy_version", Text, nullable=False),
    Column("execution_policy_version", Text, nullable=False),
    Column("confidence_policy_version", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column("model_version", Text, nullable=False),
    Column("status", Text, nullable=False),
    created_at(),
    CheckConstraint("data_cutoff <= decision_time", name=conv("ck_weekly_review_cutoff")),
    CheckConstraint(
        "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
        name=conv("ck_weekly_review_status"),
    ),
    UniqueConstraint("run_key", name="weekly_review_run_run_key_key"),
)
decision_outcome = Table(
    "decision_outcome",
    metadata,
    uuid_pk(),
    Column(
        "weekly_review_run_id",
        UUID(as_uuid=True),
        ForeignKey("weekly_review_run.id"),
        nullable=False,
    ),
    Column("decision_id", UUID(as_uuid=True), ForeignKey("decision_snapshot.id"), nullable=False),
    Column("status", Text, nullable=False),
    Column("returns", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("excess_returns", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("maximum_favorable_excursion", Numeric, nullable=False),
    Column("maximum_adverse_excursion", Numeric, nullable=False),
    Column("risk_adjusted_return", Numeric, nullable=False),
    Column("calibration_error", Numeric, nullable=False),
    Column("computed_at", DateTime(timezone=True), nullable=False),
    created_at(),
    UniqueConstraint("weekly_review_run_id", "decision_id", name="uq_outcome_run_decision"),
    CheckConstraint("status IN ('PENDING', 'MATURED')", name=conv("ck_outcome_status")),
)
error_attribution = Table(
    "error_attribution",
    metadata,
    uuid_pk(),
    Column("outcome_id", UUID(as_uuid=True), ForeignKey("decision_outcome.id"), nullable=False),
    Column("category", Text, nullable=False),
    Column("rationale", Text, nullable=False),
    Column("controllable", Boolean, nullable=False),
    created_at(),
    CheckConstraint(
        "category IN ('STALE_DATA', 'MISSING_EVIDENCE', 'FACT_ERROR', "
        "'CONFLICT_IGNORED', 'THESIS_ERROR', 'TIMING_ERROR', "
        "'POSITION_SIZING_ERROR', 'EXECUTION_ERROR', 'REGIME_CHANGE', "
        "'RISK_POLICY_FAILURE', 'UNCONTROLLABLE_EVENT')",
        name=conv("ck_error_attribution_category"),
    ),
    UniqueConstraint("outcome_id", "category", name="uq_attribution_outcome_category"),
)
candidate_lesson = Table(
    "candidate_lesson",
    metadata,
    uuid_pk(),
    Column(
        "attribution_id", UUID(as_uuid=True), ForeignKey("error_attribution.id"), nullable=False
    ),
    Column("scope", Text, nullable=False),
    Column("statement", Text, nullable=False),
    Column("duplicate_key", Text, nullable=False),
    Column("evidence", JSONB, nullable=False),
    Column("counter_evidence", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("confidence", Numeric, nullable=False),
    Column("replay_delta", Numeric, nullable=False),
    Column("creator", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'CANDIDATE'")),
    created_at(),
    UniqueConstraint("duplicate_key", name="candidate_lesson_duplicate_key_key"),
    CheckConstraint("confidence >= 0 AND confidence <= 1", name=conv("ck_lesson_confidence")),
    CheckConstraint(
        "status IN ('CANDIDATE', 'APPROVED', 'REJECTED')",
        name=conv("ck_lesson_status"),
    ),
)
lesson_attribution_link = Table(
    "lesson_attribution_link",
    metadata,
    Column(
        "lesson_id",
        UUID(as_uuid=True),
        ForeignKey("candidate_lesson.id"),
        primary_key=True,
    ),
    Column(
        "attribution_id",
        UUID(as_uuid=True),
        ForeignKey("error_attribution.id"),
        primary_key=True,
    ),
    created_at(),
)
replay_run = Table(
    "replay_run",
    metadata,
    uuid_pk(),
    Column("lesson_id", UUID(as_uuid=True), ForeignKey("candidate_lesson.id"), nullable=False),
    Column("decision_ids", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("baseline_score", Numeric, nullable=False),
    Column("candidate_score", Numeric, nullable=False),
    Column("delta", Numeric, nullable=False),
    Column("data_cutoff", DateTime(timezone=True), nullable=False),
    created_at(),
    UniqueConstraint("lesson_id", "data_cutoff", name="uq_replay_lesson_cutoff"),
)
lesson_approval = Table(
    "lesson_approval",
    metadata,
    uuid_pk(),
    Column("lesson_id", UUID(as_uuid=True), ForeignKey("candidate_lesson.id"), nullable=False),
    Column("actor_id", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("rationale", Text, nullable=False),
    created_at(),
    CheckConstraint("action IN ('APPROVE', 'REJECT')", name=conv("ck_lesson_approval_action")),
)
policy_control = Table(
    "policy_control",
    metadata,
    Column("policy_kind", Text, primary_key=True),
    Column("active_version", Text, nullable=False),
    Column("revision", BigInteger, nullable=False, server_default=text("0")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    CheckConstraint("revision >= 0", name=conv("ck_policy_control_revision")),
)
policy_candidate = Table(
    "policy_candidate",
    metadata,
    uuid_pk(),
    Column("policy_kind", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("base_version", Text, nullable=False),
    Column("lesson_ids", JSONB, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'CANDIDATE'")),
    Column("revision", BigInteger, nullable=False, server_default=text("0")),
    created_at(),
    UniqueConstraint("policy_kind", "version", name="uq_policy_candidate_kind_version"),
    CheckConstraint(
        "status IN ('CANDIDATE', 'APPROVED', 'ACTIVE', 'REJECTED', 'ROLLED_BACK')",
        name=conv("ck_policy_candidate_status"),
    ),
    CheckConstraint("revision >= 0", name=conv("ck_policy_candidate_revision")),
)
policy_promotion_audit = Table(
    "policy_promotion_audit",
    metadata,
    uuid_pk(),
    Column(
        "policy_candidate_id", UUID(as_uuid=True), ForeignKey("policy_candidate.id"), nullable=False
    ),
    Column("actor_id", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("expected_revision", BigInteger, nullable=False),
    Column("observed_revision", BigInteger, nullable=False),
    created_at(),
    CheckConstraint(
        "action IN ('APPROVE', 'ACTIVATE', 'REJECT', 'ROLLBACK', "
        "'DENY_APPROVE', 'DENY_ACTIVATE', 'DENY_REJECT', 'DENY_ROLLBACK')",
        name=conv("ck_policy_promotion_action"),
    ),
    CheckConstraint(
        "outcome IN ('COMPLETED', 'FORBIDDEN', 'CONFLICT')",
        name=conv("ck_policy_promotion_outcome"),
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
    Column(
        "normalized_record_id",
        UUID(as_uuid=True),
        ForeignKey("normalized_record.id"),
        nullable=True,
    ),
    Column("provider", Text, nullable=False),
    Column("feed_type", Text, nullable=False),
    Column("coverage", Text),
    Column("session", Text),
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
    CheckConstraint(
        "coverage IS NULL OR coverage IN ('IEX', 'SIP')",
        name=conv("ck_market_bar_coverage"),
    ),
    CheckConstraint(
        "session IS NULL OR session IN ('PRE_MARKET', 'REGULAR', 'AFTER_HOURS', 'OVERNIGHT')",
        name=conv("ck_market_bar_session"),
    ),
)
Index(
    "uq_market_bar_stream_content",
    market_bar.c.provider,
    market_bar.c.feed_type,
    market_bar.c.content_hash,
    market_bar.c.event_time,
    market_bar.c.symbol,
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
news_article = Table(
    "news_article",
    metadata,
    uuid_pk(),
    Column(
        "raw_data_object_id", UUID(as_uuid=True), ForeignKey("raw_data_object.id"), nullable=False
    ),
    Column(
        "normalized_record_id",
        UUID(as_uuid=True),
        ForeignKey("normalized_record.id"),
        nullable=False,
    ),
    Column("provider", Text, nullable=False),
    Column("article_id", Text, nullable=False),
    Column("symbols", JSONB, nullable=False),
    Column("headline", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False),
    Column("observed_at", DateTime(timezone=True)),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False),
    Column("pit_eligible", Boolean, nullable=False),
    Column("payload", JSONB, nullable=False),
    created_at(),
    CheckConstraint(
        "published_at <= available_at AND available_at <= ingested_at",
        name=conv("ck_news_article_times"),
    ),
    CheckConstraint(
        "(observed_at IS NULL OR "
        "(published_at <= observed_at AND observed_at <= available_at)) "
        "AND (NOT pit_eligible OR observed_at IS NOT NULL)",
        name=conv("ck_news_article_pit_eligibility"),
    ),
    UniqueConstraint(
        "provider",
        "article_id",
        "normalized_record_id",
        name="uq_news_article_version",
    ),
)
Index("news_article_pit_idx", news_article.c.published_at, news_article.c.available_at)
sec_filing = Table(
    "sec_filing",
    metadata,
    uuid_pk(),
    Column("security_id", UUID(as_uuid=True), ForeignKey("security.id"), nullable=False),
    Column(
        "raw_data_object_id", UUID(as_uuid=True), ForeignKey("raw_data_object.id"), nullable=False
    ),
    Column(
        "normalized_record_id",
        UUID(as_uuid=True),
        ForeignKey("normalized_record.id"),
        nullable=False,
    ),
    Column(
        "document_raw_data_object_id",
        UUID(as_uuid=True),
        ForeignKey("raw_data_object.id"),
        nullable=False,
    ),
    Column("provider", Text, nullable=False),
    Column("cik", Text, nullable=False),
    Column("accession_number", Text, nullable=False),
    Column("form", Text, nullable=False),
    Column("base_form", Text, nullable=False),
    Column("filing_date", Date, nullable=False),
    Column("report_date", Date),
    Column("accepted_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("primary_document", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("is_amendment", Boolean, nullable=False),
    Column("supersedes_id", UUID(as_uuid=True), ForeignKey("sec_filing.id")),
    Column("payload", JSONB, nullable=False),
    created_at(),
    CheckConstraint("accepted_at = available_at", name=conv("ck_sec_filing_availability")),
    CheckConstraint(
        "supersedes_id IS NULL OR supersedes_id <> id", name=conv("ck_sec_filing_supersedes_self")
    ),
    CheckConstraint(
        "(is_amendment AND form LIKE '%/A') OR (NOT is_amendment AND form NOT LIKE '%/A')",
        name=conv("ck_sec_filing_amendment"),
    ),
    UniqueConstraint("provider", "accession_number", name="uq_sec_filing_accession"),
)
Index(
    "sec_filing_pit_idx",
    sec_filing.c.security_id,
    sec_filing.c.accepted_at,
    sec_filing.c.available_at,
)
financial_fact = Table(
    "financial_fact",
    metadata,
    uuid_pk(),
    Column("security_id", UUID(as_uuid=True), ForeignKey("security.id"), nullable=False),
    Column("sec_filing_id", UUID(as_uuid=True), ForeignKey("sec_filing.id"), nullable=False),
    Column(
        "raw_data_object_id", UUID(as_uuid=True), ForeignKey("raw_data_object.id"), nullable=False
    ),
    Column(
        "normalized_record_id",
        UUID(as_uuid=True),
        ForeignKey("normalized_record.id"),
        nullable=False,
    ),
    Column("provider", Text, nullable=False),
    Column("taxonomy", Text, nullable=False),
    Column("source_concept", Text, nullable=False),
    Column("canonical_concept", Text),
    Column("value", Numeric, nullable=False),
    Column("unit", Text, nullable=False),
    Column("currency", Text),
    Column("period_start", Date, nullable=False),
    Column("period_end", Date, nullable=False),
    Column("accession_number", Text, nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("mapping_status", Text, nullable=False),
    Column("mapping_version", Text, nullable=False),
    Column("input_provenance", JSONB, nullable=False),
    Column("supersedes_id", UUID(as_uuid=True), ForeignKey("financial_fact.id")),
    created_at(),
    CheckConstraint("period_start <= period_end", name=conv("ck_financial_fact_period")),
    CheckConstraint(
        "mapping_status IN ('EXACT', 'DERIVED', 'UNMAPPED', 'AMBIGUOUS')",
        name=conv("ck_financial_fact_mapping_status"),
    ),
    CheckConstraint(
        "(mapping_status IN ('EXACT', 'DERIVED')) = (canonical_concept IS NOT NULL)",
        name=conv("ck_financial_fact_canonical_status"),
    ),
    CheckConstraint(
        "supersedes_id IS NULL OR supersedes_id <> id",
        name=conv("ck_financial_fact_supersedes_self"),
    ),
    UniqueConstraint(
        "provider",
        "security_id",
        "taxonomy",
        "source_concept",
        "accession_number",
        "unit",
        "period_start",
        "period_end",
        "mapping_version",
        name="uq_financial_fact_version",
    ),
)
Index(
    "financial_fact_pit_idx",
    financial_fact.c.security_id,
    financial_fact.c.period_end,
    financial_fact.c.available_at,
)
earnings_event = Table(
    "earnings_event",
    metadata,
    uuid_pk(),
    Column("security_id", UUID(as_uuid=True), ForeignKey("security.id"), nullable=False),
    Column(
        "raw_data_object_id", UUID(as_uuid=True), ForeignKey("raw_data_object.id"), nullable=False
    ),
    Column(
        "normalized_record_id",
        UUID(as_uuid=True),
        ForeignKey("normalized_record.id"),
        nullable=False,
    ),
    Column("provider", Text, nullable=False),
    Column("provider_symbol", Text, nullable=False),
    Column("symbol", Text, nullable=False),
    Column("event_date", Date, nullable=False),
    Column("fiscal_date_end", Date, nullable=False),
    Column("estimate", Numeric),
    Column("currency", Text),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("supersedes_id", UUID(as_uuid=True), ForeignKey("earnings_event.id")),
    Column("payload", JSONB, nullable=False),
    created_at(),
    CheckConstraint(
        "supersedes_id IS NULL OR supersedes_id <> id",
        name=conv("ck_earnings_event_supersedes_self"),
    ),
    UniqueConstraint(
        "provider",
        "normalized_record_id",
        "provider_symbol",
        "fiscal_date_end",
        name="uq_earnings_event_snapshot_version",
    ),
)
Index(
    "earnings_event_pit_idx",
    earnings_event.c.security_id,
    earnings_event.c.event_date,
    earnings_event.c.available_at,
)
data_quality_observation = Table(
    "data_quality_observation",
    metadata,
    uuid_pk(),
    Column(
        "raw_data_object_id",
        UUID(as_uuid=True),
        ForeignKey("raw_data_object.id"),
        nullable=False,
    ),
    Column(
        "normalized_record_id",
        UUID(as_uuid=True),
        ForeignKey("normalized_record.id"),
        nullable=False,
    ),
    Column("provider", Text, nullable=False),
    Column("dataset", Text, nullable=False),
    Column("dimension", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("freshness", Interval),
    Column("coverage", Text),
    Column("delay", Interval),
    Column("conflict", Boolean, nullable=False, server_default=text("false")),
    Column("policy_version", Text, nullable=False),
    Column("details", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    created_at(),
    CheckConstraint(
        "dimension IN ('FRESHNESS', 'COVERAGE', 'PROVIDER', 'DELAY', "
        "'CONFLICT', 'RECONCILIATION', 'HEARTBEAT')",
        name=conv("ck_data_quality_dimension"),
    ),
    CheckConstraint(
        "status IN ('PASS', 'DEGRADED', 'UNAVAILABLE', 'FAIL')",
        name=conv("ck_data_quality_status"),
    ),
    CheckConstraint(
        "coverage IS NULL OR coverage IN ('IEX', 'SIP')",
        name=conv("ck_data_quality_coverage"),
    ),
    CheckConstraint(
        "(freshness IS NULL OR freshness >= interval '0 seconds') "
        "AND (delay IS NULL OR delay >= interval '0 seconds')",
        name=conv("ck_data_quality_intervals"),
    ),
    UniqueConstraint(
        "normalized_record_id",
        "dimension",
        "observed_at",
        "policy_version",
        name="uq_data_quality_observation_version",
    ),
)
Index(
    "data_quality_provider_observed_idx",
    data_quality_observation.c.provider,
    data_quality_observation.c.dataset,
    data_quality_observation.c.observed_at,
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
