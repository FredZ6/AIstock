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


def downgrade() -> None:
    op.execute("DROP TRIGGER enforce_append_only ON data_quality_observation")
    op.drop_index("data_quality_provider_observed_idx", table_name="data_quality_observation")
    op.drop_table("data_quality_observation")
