"""Allow audited entitlement denials without fabricated market context."""

from collections.abc import Sequence

from alembic import op

revision: str = "0040_entitlement_risk_context"
down_revision: str | None = "0039_eval_constraint_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("risk_decision", "market_context_snapshot_id", nullable=True)
    op.create_check_constraint(
        op.f("ck_risk_decision_market_context_required"),
        "risk_decision",
        "market_context_snapshot_id IS NOT NULL OR "
        "(status = 'REJECTED' AND "
        "reason_codes @> '[\"MARKET_DATA_ENTITLEMENT\"]'::jsonb)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_risk_decision_market_context_required"),
        "risk_decision",
        type_="check",
    )
    op.alter_column("risk_decision", "market_context_snapshot_id", nullable=False)
