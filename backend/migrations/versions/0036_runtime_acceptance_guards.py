"""Bind portfolio idempotency and serialize decision supersession facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_runtime_acceptance_guards"
down_revision: str | None = "0035_portfolio_nav_availability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "decision_diff_previous_decision_id_key",
        "decision_diff",
        ["previous_decision_id"],
    )
    op.create_table(
        "portfolio_initialization_request",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["paper_portfolio_config.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="portfolio_initialization_request_idempotency_key_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("portfolio_initialization_request")
    op.drop_constraint("decision_diff_previous_decision_id_key", "decision_diff", type_="unique")
