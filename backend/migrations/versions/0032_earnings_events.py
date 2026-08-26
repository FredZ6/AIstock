"""Add append-only Alpha Vantage earnings events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_earnings_events"
down_revision: str | None = "0031_financial_filing_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "earnings_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "security_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("security.id"),
            nullable=False,
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
        sa.Column("provider_symbol", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("fiscal_date_end", sa.Date(), nullable=False),
        sa.Column("estimate", sa.Numeric()),
        sa.Column("currency", sa.Text()),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "supersedes_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("earnings_event.id")
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id <> id",
            name=op.f("ck_earnings_event_supersedes_self"),
        ),
        sa.UniqueConstraint(
            "provider",
            "normalized_record_id",
            "provider_symbol",
            "fiscal_date_end",
            name="uq_earnings_event_snapshot_version",
        ),
    )
    op.create_index(
        "earnings_event_pit_idx", "earnings_event", ["security_id", "event_date", "available_at"]
    )
    op.execute(
        """
        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON earnings_event
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER enforce_append_only ON earnings_event")
    op.drop_index("earnings_event_pit_idx", table_name="earnings_event")
    op.drop_table("earnings_event")
