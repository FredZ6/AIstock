"""Add authoritative availability time to paper portfolio NAV facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_portfolio_nav_availability"
down_revision: str | None = "0034_corp_action_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portfolio_nav",
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE portfolio_nav SET available_at = event_time WHERE available_at IS NULL")
    op.alter_column("portfolio_nav", "available_at", nullable=False)
    op.create_check_constraint(
        op.f("ck_portfolio_nav_availability"),
        "portfolio_nav",
        "event_time <= available_at",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_portfolio_nav_availability"), "portfolio_nav", type_="check")
    op.drop_column("portfolio_nav", "available_at")
