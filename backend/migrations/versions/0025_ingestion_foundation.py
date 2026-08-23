"""Add Security master data and migrate Watchlist identity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_ingestion_foundation"
down_revision: str | None = "0024_observability_correlation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def upgrade() -> None:
    op.create_table(
        "security",
        _uuid_pk(),
        sa.Column("instrument_type", sa.Text(), nullable=False),
        _created_at(),
    )
    op.create_table(
        "security_identifier_version",
        _uuid_pk(),
        sa.Column(
            "security_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("security.id"),
            nullable=False,
        ),
        sa.Column("identifier_type", sa.Text(), nullable=False),
        sa.Column("identifier_value", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text()),
        sa.Column(
            "provider_identifiers",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("security_identifier_version.id"),
        ),
        _created_at(),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from < effective_to",
            name=op.f("ck_security_identifier_effective_range"),
        ),
        sa.CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id <> id",
            name=op.f("ck_security_identifier_supersedes_self"),
        ),
        sa.UniqueConstraint(
            "security_id",
            "identifier_type",
            "identifier_value",
            "available_at",
            name="uq_security_identifier_version",
        ),
    )
    op.create_index(
        "security_identifier_lookup_idx",
        "security_identifier_version",
        ["identifier_type", "identifier_value", "available_at"],
    )
    op.create_table(
        "security_profile_version",
        _uuid_pk(),
        sa.Column(
            "security_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("security.id"),
            nullable=False,
        ),
        sa.Column("company_name", sa.Text()),
        sa.Column("currency", sa.Text()),
        sa.Column("cik", sa.Text()),
        sa.Column("filing_regime", sa.Text()),
        sa.Column("industry_role", sa.Text()),
        sa.Column("country_of_incorporation", sa.Text()),
        sa.Column("exchange_timezone", sa.Text()),
        sa.Column("is_adr", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("adr_ratio", sa.Numeric()),
        sa.Column("primary_market", sa.Text()),
        sa.Column("source_currency", sa.Text()),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("security_profile_version.id"),
        ),
        _created_at(),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from < effective_to",
            name=op.f("ck_security_profile_effective_range"),
        ),
        sa.CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id <> id",
            name=op.f("ck_security_profile_supersedes_self"),
        ),
        sa.CheckConstraint(
            "adr_ratio IS NULL OR adr_ratio > 0",
            name=op.f("ck_security_profile_adr_ratio"),
        ),
        sa.UniqueConstraint("security_id", "available_at", name="uq_security_profile_version"),
    )
    op.create_index(
        "security_profile_pit_idx",
        "security_profile_version",
        ["security_id", "available_at"],
    )

    op.add_column(
        "watchlist_item",
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        CREATE TEMPORARY TABLE watchlist_security_backfill ON COMMIT DROP AS
        SELECT symbol, gen_random_uuid() AS security_id, created_at
        FROM watchlist_item
        """
    )
    op.execute(
        """
        INSERT INTO security (id, instrument_type, created_at)
        SELECT security_id, 'COMMON_STOCK', created_at
        FROM watchlist_security_backfill
        """
    )
    op.execute(
        """
        INSERT INTO security_identifier_version (
            security_id, identifier_type, identifier_value, provider_identifiers,
            effective_from, available_at, created_at
        )
        SELECT security_id, 'PRIMARY_SYMBOL', symbol, '{}'::jsonb,
               created_at, created_at, created_at
        FROM watchlist_security_backfill
        """
    )
    op.execute(
        """
        INSERT INTO security_profile_version (
            security_id, effective_from, available_at, created_at
        )
        SELECT security_id, created_at, created_at, created_at
        FROM watchlist_security_backfill
        """
    )
    op.execute(
        """
        UPDATE watchlist_item AS watchlist
        SET security_id = backfill.security_id
        FROM watchlist_security_backfill AS backfill
        WHERE watchlist.symbol = backfill.symbol
        """
    )
    op.alter_column(
        "watchlist_item",
        "security_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_constraint(op.f("pk_watchlist_item"), "watchlist_item", type_="primary")
    op.create_primary_key(op.f("pk_watchlist_item"), "watchlist_item", ["security_id"])
    op.create_unique_constraint(op.f("uq_watchlist_item_symbol"), "watchlist_item", ["symbol"])
    op.create_foreign_key(
        op.f("fk_watchlist_item_security_id_security"),
        "watchlist_item",
        "security",
        ["security_id"],
        ["id"],
    )

    op.execute(
        """
        CREATE FUNCTION reject_security_identifier_reassignment() RETURNS trigger AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM security_identifier_version
                WHERE identifier_type = NEW.identifier_type
                  AND identifier_value = NEW.identifier_value
                  AND security_id <> NEW.security_id
            ) THEN
                RAISE EXCEPTION 'security identifier cannot change owner';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER security_identifier_owner_guard
        BEFORE INSERT ON security_identifier_version
        FOR EACH ROW EXECUTE FUNCTION reject_security_identifier_reassignment()
        """
    )
    for table in ("security_identifier_version", "security_profile_version"):
        op.execute(
            f"""
            CREATE TRIGGER enforce_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
            """
        )

    op.create_table(
        "ingestion_job",
        _uuid_pk(),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("dataset", sa.Text(), nullable=False),
        sa.Column(
            "security_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("security.id"),
        ),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'QUEUED'")),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lease_owner", sa.Text()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_started_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _created_at(),
        sa.CheckConstraint("window_start <= window_end", name=op.f("ck_ingestion_job_window")),
        sa.CheckConstraint(
            "max_attempts > 0 AND attempt_count >= 0 AND attempt_count <= max_attempts "
            "AND lease_generation >= 0",
            name=op.f("ck_ingestion_job_attempts"),
        ),
        sa.CheckConstraint(
            "state IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'COMPLETED_WITH_GAPS', "
            "'RETRY_SCHEDULED', 'FAILED', 'DEAD_LETTER', 'CANCELLED')",
            name=op.f("ck_ingestion_job_state"),
        ),
        sa.CheckConstraint(
            "(state = 'RUNNING' AND lease_token IS NOT NULL AND lease_owner IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND attempt_started_at IS NOT NULL) OR "
            "(state <> 'RUNNING' AND lease_token IS NULL AND lease_owner IS NULL "
            "AND lease_expires_at IS NULL AND attempt_started_at IS NULL)",
            name=op.f("ck_ingestion_job_running_lease"),
        ),
        sa.CheckConstraint(
            "(state = 'RETRY_SCHEDULED') = (next_attempt_at IS NOT NULL)",
            name=op.f("ck_ingestion_job_retry_time"),
        ),
        sa.CheckConstraint(
            "(state IN ('SUCCEEDED', 'COMPLETED_WITH_GAPS', 'FAILED', 'DEAD_LETTER', "
            "'CANCELLED')) = (completed_at IS NOT NULL)",
            name=op.f("ck_ingestion_job_completion_time"),
        ),
    )
    op.create_index(
        "uq_ingestion_job_active_request",
        "ingestion_job",
        ["request_hash"],
        unique=True,
        postgresql_where=sa.text("state IN ('QUEUED', 'RUNNING', 'RETRY_SCHEDULED')"),
    )
    op.create_index("ingestion_job_due_idx", "ingestion_job", ["state", "next_attempt_at"])
    op.create_table(
        "ingestion_attempt",
        _uuid_pk(),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_job.id"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("lease_generation", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("error_class", sa.Text()),
        sa.Column("error_detail", postgresql.JSONB()),
        _created_at(),
        sa.CheckConstraint(
            "attempt_number > 0 AND lease_generation > 0",
            name=op.f("ck_ingestion_attempt_number"),
        ),
        sa.CheckConstraint(
            "started_at <= finished_at", name=op.f("ck_ingestion_attempt_time_order")
        ),
        sa.CheckConstraint(
            "outcome IN ('SUCCEEDED', 'COMPLETED_WITH_GAPS', 'RETRY_SCHEDULED', "
            "'FAILED', 'DEAD_LETTER')",
            name=op.f("ck_ingestion_attempt_outcome"),
        ),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_ingestion_attempt_number"),
    )
    op.create_table(
        "ingestion_cursor",
        _uuid_pk(),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("dataset", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("cursor_payload", postgresql.JSONB(), nullable=False),
        sa.Column("watermark", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _created_at(),
        sa.CheckConstraint("generation >= 0", name=op.f("ck_ingestion_cursor_generation")),
        sa.UniqueConstraint("provider", "dataset", "scope_key", name="uq_ingestion_cursor_scope"),
    )
    op.create_table(
        "ingestion_dead_letter",
        _uuid_pk(),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_job.id"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("error_class", sa.Text(), nullable=False),
        sa.Column("error_detail", postgresql.JSONB(), nullable=False),
        _created_at(),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_ingestion_dead_letter_attempt"),
    )
    op.create_table(
        "ingestion_raw_link",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_job.id"),
            primary_key=True,
        ),
        sa.Column(
            "raw_data_object_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_data_object.id"),
            primary_key=True,
        ),
        _created_at(),
    )
    op.create_table(
        "normalization_dispatch",
        _uuid_pk(),
        sa.Column(
            "raw_data_object_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_data_object.id"),
            nullable=False,
        ),
        sa.Column("normalization_version", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", postgresql.JSONB()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _created_at(),
        sa.CheckConstraint(
            "state IN ('PENDING', 'CLAIMED', 'DISPATCHED', 'FAILED')",
            name=op.f("ck_normalization_dispatch_state"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND lease_generation >= 0",
            name=op.f("ck_normalization_dispatch_counts"),
        ),
        sa.UniqueConstraint(
            "raw_data_object_id",
            "normalization_version",
            name="uq_normalization_dispatch_version",
        ),
    )
    for table in ("ingestion_attempt", "ingestion_dead_letter", "ingestion_raw_link"):
        op.execute(
            f"""
            CREATE TRIGGER enforce_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
            """
        )


def downgrade() -> None:
    op.drop_table("normalization_dispatch")
    op.drop_table("ingestion_raw_link")
    op.drop_table("ingestion_dead_letter")
    op.drop_table("ingestion_cursor")
    op.drop_table("ingestion_attempt")
    op.drop_index("ingestion_job_due_idx", table_name="ingestion_job")
    op.drop_index("uq_ingestion_job_active_request", table_name="ingestion_job")
    op.drop_table("ingestion_job")
    op.drop_constraint(
        op.f("fk_watchlist_item_security_id_security"), "watchlist_item", type_="foreignkey"
    )
    op.drop_constraint(op.f("pk_watchlist_item"), "watchlist_item", type_="primary")
    op.drop_constraint(op.f("uq_watchlist_item_symbol"), "watchlist_item", type_="unique")
    op.create_primary_key(op.f("pk_watchlist_item"), "watchlist_item", ["symbol"])
    op.drop_column("watchlist_item", "security_id")
    op.drop_table("security_profile_version")
    op.drop_table("security_identifier_version")
    op.execute("DROP FUNCTION reject_security_identifier_reassignment()")
    op.drop_table("security")
