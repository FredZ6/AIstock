"""Add append-only SEC filing facts for the RDB-3 provider lane."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_sec_alpha_facts"
down_revision: str | None = "0028_market_bar_symbol_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sec_filing",
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
        sa.Column(
            "document_raw_data_object_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_data_object.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("cik", sa.Text(), nullable=False),
        sa.Column("accession_number", sa.Text(), nullable=False),
        sa.Column("form", sa.Text(), nullable=False),
        sa.Column("base_form", sa.Text(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("report_date", sa.Date()),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("primary_document", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_amendment", sa.Boolean(), nullable=False),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sec_filing.id")),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("accepted_at = available_at", name=op.f("ck_sec_filing_availability")),
        sa.CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id <> id",
            name=op.f("ck_sec_filing_supersedes_self"),
        ),
        sa.CheckConstraint(
            "(is_amendment AND form LIKE '%/A') OR (NOT is_amendment AND form NOT LIKE '%/A')",
            name=op.f("ck_sec_filing_amendment"),
        ),
        sa.UniqueConstraint("provider", "accession_number", name="uq_sec_filing_accession"),
    )
    op.create_index(
        "sec_filing_pit_idx", "sec_filing", ["security_id", "accepted_at", "available_at"]
    )
    op.execute(
        """
        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON sec_filing
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER enforce_append_only ON sec_filing")
    op.drop_index("sec_filing_pit_idx", table_name="sec_filing")
    op.drop_table("sec_filing")
