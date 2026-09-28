"""Persist the authoritative Watchlist display order."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_watchlist_display_order"
down_revision: str | None = "0041_portfolio_nav_read_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE watchlist_display_order_seq START WITH 1")
    op.add_column(
        "watchlist_item",
        sa.Column("display_order", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT security_id,
                   row_number() OVER (
                       ORDER BY CASE symbol
                           WHEN 'NVDA' THEN 1
                           WHEN 'AVGO' THEN 2
                           WHEN 'TSM' THEN 3
                           WHEN 'SKHY' THEN 4
                           WHEN 'WDC' THEN 5
                           WHEN 'SNDK' THEN 6
                           WHEN 'MU' THEN 7
                           WHEN 'NBIS' THEN 8
                           WHEN 'MRVL' THEN 9
                           WHEN 'BE' THEN 10
                           WHEN 'INTC' THEN 11
                           ELSE 12
                       END,
                       created_at,
                       symbol,
                       security_id
                   ) AS display_order
            FROM watchlist_item
        )
        UPDATE watchlist_item AS item
        SET display_order = ranked.display_order
        FROM ranked
        WHERE item.security_id = ranked.security_id
        """
    )
    op.execute(
        """
        SELECT setval(
            'watchlist_display_order_seq',
            COALESCE((SELECT max(display_order) FROM watchlist_item), 1),
            EXISTS (SELECT 1 FROM watchlist_item)
        )
        """
    )
    op.alter_column(
        "watchlist_item",
        "display_order",
        nullable=False,
        server_default=sa.text("nextval('watchlist_display_order_seq')"),
    )
    op.create_check_constraint(
        op.f("ck_watchlist_item_display_order_positive"),
        "watchlist_item",
        "display_order > 0",
    )
    op.create_unique_constraint(
        op.f("uq_watchlist_item_display_order"),
        "watchlist_item",
        ["display_order"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_watchlist_item_display_order"),
        "watchlist_item",
        type_="unique",
    )
    op.drop_constraint(
        op.f("ck_watchlist_item_display_order_positive"),
        "watchlist_item",
        type_="check",
    )
    op.drop_column("watchlist_item", "display_order")
    op.execute("DROP SEQUENCE watchlist_display_order_seq")
