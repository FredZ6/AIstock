"""Enforce the approved singleton paper portfolio identity."""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_single_portfolio_guard"
down_revision: str | None = "0021_single_paper_portfolio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        op.f("ck_paper_portfolio_config_singleton_id"),
        "paper_portfolio_config",
        "id = '10000000-0000-0000-0000-000000000001'::uuid",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_paper_portfolio_config_singleton_id"),
        "paper_portfolio_config",
        type_="check",
    )
