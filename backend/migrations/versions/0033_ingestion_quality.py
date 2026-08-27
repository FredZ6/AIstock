"""Add append-only raw-dimension ingestion quality observations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_ingestion_quality"
down_revision: str | None = "0032_earnings_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_quality_observation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "raw_data_object_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_data_object.id"),
            nullable=False,
        ),
        sa.Column(
            "normalized_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("normalized_record.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("dataset", sa.Text(), nullable=False),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("freshness", sa.Interval()),
        sa.Column("coverage", sa.Text()),
        sa.Column("delay", sa.Interval()),
        sa.Column("conflict", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "dimension IN ('FRESHNESS', 'COVERAGE', 'PROVIDER', 'DELAY', "
            "'CONFLICT', 'RECONCILIATION', 'HEARTBEAT')",
            name=op.f("ck_data_quality_dimension"),
        ),
        sa.CheckConstraint(
            "status IN ('PASS', 'DEGRADED', 'UNAVAILABLE', 'FAIL')",
            name=op.f("ck_data_quality_status"),
        ),
        sa.CheckConstraint(
            "coverage IS NULL OR coverage IN ('IEX', 'SIP')",
            name=op.f("ck_data_quality_coverage"),
        ),
        sa.CheckConstraint(
            "(freshness IS NULL OR freshness >= interval '0 seconds') "
            "AND (delay IS NULL OR delay >= interval '0 seconds')",
            name=op.f("ck_data_quality_intervals"),
        ),
        sa.UniqueConstraint(
            "normalized_record_id",
            "dimension",
            "observed_at",
            "policy_version",
            name="uq_data_quality_observation_version",
        ),
    )
    op.create_index(
        "data_quality_provider_observed_idx",
        "data_quality_observation",
        ["provider", "dataset", "observed_at"],
    )
    op.execute(
        """
        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON data_quality_observation
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
        """
    )
    op.add_column(
        "corporate_action",
        sa.Column("normalized_record_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "corporate_action", sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("corporate_action", sa.Column("provider_action_id", sa.Text(), nullable=True))
    op.add_column("corporate_action", sa.Column("stock_ratio", sa.Numeric()))
    op.add_column("corporate_action", sa.Column("old_adr_ratio", sa.Numeric()))
    op.add_column("corporate_action", sa.Column("new_adr_ratio", sa.Numeric()))
    op.add_column(
        "corporate_action",
        sa.Column("source_currency", sa.Text(), nullable=False, server_default=sa.text("'USD'")),
    )
    op.add_column(
        "corporate_action",
        sa.Column(
            "details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.add_column(
        "corporate_action",
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_corporate_action_normalized_record_id_normalized_record",
        "corporate_action",
        "normalized_record",
        ["normalized_record_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_corporate_action_security_id_security",
        "corporate_action",
        "security",
        ["security_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_corporate_action_supersedes_id_corporate_action",
        "corporate_action",
        "corporate_action",
        ["supersedes_id"],
        ["id"],
    )
    op.execute(
        """
        INSERT INTO normalized_record (
            raw_data_object_id, record_type, record_key, normalization_version, payload
        )
        SELECT DISTINCT ca.raw_data_object_id, 'corporate_action',
               'legacy:' || ca.raw_data_object_id::text, 'corporate-action-v2', '{}'::jsonb
        FROM corporate_action ca
        WHERE NOT EXISTS (
            SELECT 1 FROM normalized_record nr
            WHERE nr.raw_data_object_id = ca.raw_data_object_id
              AND nr.record_type = 'corporate_action'
              AND nr.record_key = 'legacy:' || ca.raw_data_object_id::text
              AND nr.normalization_version = 'corporate-action-v2'
        );
        UPDATE corporate_action ca
        SET normalized_record_id = nr.id,
            provider_action_id = COALESCE(ca.provider_action_id, ca.id::text)
        FROM normalized_record nr
        WHERE nr.raw_data_object_id = ca.raw_data_object_id
          AND nr.record_type = 'corporate_action'
          AND nr.normalization_version = 'corporate-action-v2'
          AND ca.normalized_record_id IS NULL;
        ALTER TABLE corporate_action ALTER COLUMN normalized_record_id SET NOT NULL;
        ALTER TABLE corporate_action ALTER COLUMN provider_action_id SET NOT NULL;
        ALTER TABLE corporate_action DROP CONSTRAINT ck_corporate_action_type;
        ALTER TABLE corporate_action DROP CONSTRAINT ck_corporate_action_value;
        ALTER TABLE corporate_action ADD CONSTRAINT ck_corporate_action_type CHECK (
            action_type IN ('SPLIT', 'CASH_DIVIDEND', 'STOCK_DIVIDEND', 'SPIN_OFF',
                            'SYMBOL_CHANGE', 'MERGER_ACQUISITION', 'ADR_RATIO_CHANGE')
        );
        ALTER TABLE corporate_action ADD CONSTRAINT ck_corporate_action_value CHECK (
            (action_type = 'SPLIT' AND split_ratio > 0)
            OR (action_type = 'CASH_DIVIDEND' AND cash_per_share >= 0)
            OR (action_type = 'STOCK_DIVIDEND' AND stock_ratio >= 0)
            OR (action_type = 'ADR_RATIO_CHANGE' AND old_adr_ratio > 0 AND new_adr_ratio > 0)
            OR action_type IN ('SPIN_OFF', 'SYMBOL_CHANGE', 'MERGER_ACQUISITION')
        );
        ALTER TABLE corporate_action ADD CONSTRAINT ck_corporate_action_supersedes_self
            CHECK (supersedes_id IS NULL OR supersedes_id <> id);
        ALTER TABLE corporate_action ADD CONSTRAINT uq_corporate_action_version
            UNIQUE (provider, provider_action_id, available_at);
        CREATE TRIGGER enforce_append_only
            BEFORE UPDATE OR DELETE ON corporate_action
            FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
        """
    )


def downgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("corporate_action")}
    if "normalized_record_id" in columns:
        op.execute("DROP TRIGGER IF EXISTS enforce_append_only ON corporate_action")
        op.drop_constraint("uq_corporate_action_version", "corporate_action", type_="unique")
        op.drop_constraint("ck_corporate_action_supersedes_self", "corporate_action", type_="check")
        op.drop_constraint("ck_corporate_action_value", "corporate_action", type_="check")
        op.drop_constraint("ck_corporate_action_type", "corporate_action", type_="check")
        op.create_check_constraint(
            "ck_corporate_action_type",
            "corporate_action",
            "action_type IN ('SPLIT', 'CASH_DIVIDEND')",
        )
        op.create_check_constraint(
            "ck_corporate_action_value",
            "corporate_action",
            "(action_type = 'SPLIT' AND split_ratio > 0 AND cash_per_share IS NULL) OR "
            "(action_type = 'CASH_DIVIDEND' AND cash_per_share >= 0 AND split_ratio IS NULL)",
        )
        for constraint in (
            "fk_corporate_action_supersedes_id_corporate_action",
            "fk_corporate_action_security_id_security",
            "fk_corporate_action_normalized_record_id_normalized_record",
        ):
            op.drop_constraint(constraint, "corporate_action", type_="foreignkey")
        for column in (
            "supersedes_id",
            "details",
            "source_currency",
            "new_adr_ratio",
            "old_adr_ratio",
            "stock_ratio",
            "provider_action_id",
            "security_id",
            "normalized_record_id",
        ):
            op.drop_column("corporate_action", column)
    op.execute("DROP TRIGGER enforce_append_only ON data_quality_observation")
    op.drop_index("data_quality_provider_observed_idx", table_name="data_quality_observation")
    op.drop_table("data_quality_observation")
