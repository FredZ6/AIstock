"""Persist the explicitly approved singleton paper portfolio configuration."""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_single_paper_portfolio"
down_revision: str | None = "0020_api_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PORTFOLIO_ID = "10000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "paper_portfolio_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("initial_cash", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="paper_portfolio_config_name_key"),
        sa.CheckConstraint("initial_cash > 0", name=op.f("ck_paper_portfolio_config_cash")),
        sa.CheckConstraint("currency = 'USD'", name=op.f("ck_paper_portfolio_config_currency")),
    )
    op.execute(
        sa.text(
            "INSERT INTO paper_portfolio_config (id, name, initial_cash, currency) "
            "VALUES (:id, 'default-paper', 100000, 'USD')"
        ).bindparams(
            sa.bindparam(
                "id",
                value=UUID(PORTFOLIO_ID),
                type_=postgresql.UUID(as_uuid=True),
            )
        )
    )
    op.execute(
        """
        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON paper_portfolio_config
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
        """
    )


def downgrade() -> None:
    op.drop_table("paper_portfolio_config")
