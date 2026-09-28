"""Bound canonical paper NAV history reads with a matching composite index."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_portfolio_nav_read_index"
down_revision: str | None = "0040_entitlement_risk_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "portfolio_nav_canonical_read_idx",
        "portfolio_nav",
        [
            "portfolio_id",
            sa.literal_column("event_time DESC"),
            sa.literal_column("available_at DESC"),
            sa.literal_column("id DESC"),
        ],
    )


def downgrade() -> None:
    op.drop_index("portfolio_nav_canonical_read_idx", table_name="portfolio_nav")
