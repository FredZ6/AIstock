"""Add append-only deterministic financial facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_financial_facts"
down_revision: str | None = "0029_sec_alpha_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_fact",
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
        sa.Column("sec_filing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sec_filing.id")),
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
        sa.Column("taxonomy", sa.Text(), nullable=False),
        sa.Column("source_concept", sa.Text(), nullable=False),
        sa.Column("canonical_concept", sa.Text()),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text()),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("accession_number", sa.Text(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mapping_status", sa.Text(), nullable=False),
        sa.Column("mapping_version", sa.Text(), nullable=False),
        sa.Column("input_provenance", postgresql.JSONB(), nullable=False),
        sa.Column(
            "supersedes_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("financial_fact.id")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("period_start <= period_end", name=op.f("ck_financial_fact_period")),
        sa.CheckConstraint(
            "mapping_status IN ('EXACT', 'DERIVED', 'UNMAPPED', 'AMBIGUOUS')",
            name=op.f("ck_financial_fact_mapping_status"),
        ),
        sa.CheckConstraint(
            "(mapping_status IN ('EXACT', 'DERIVED')) = (canonical_concept IS NOT NULL)",
            name=op.f("ck_financial_fact_canonical_status"),
        ),
        sa.CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id <> id",
            name=op.f("ck_financial_fact_supersedes_self"),
        ),
        sa.UniqueConstraint(
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
    op.create_index(
        "financial_fact_pit_idx", "financial_fact", ["security_id", "period_end", "available_at"]
    )
    op.execute(
        """
        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON financial_fact
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER enforce_append_only ON financial_fact")
    op.drop_index("financial_fact_pit_idx", table_name="financial_fact")
    op.drop_table("financial_fact")
