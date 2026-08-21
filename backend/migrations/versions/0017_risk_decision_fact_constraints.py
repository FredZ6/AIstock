"""Reject contradictory immutable risk-decision facts at the database boundary."""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_risk_fact_constraints"
down_revision: str | None = "0016_market_context_risk_pin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        op.f("ck_risk_decision_status_facts"),
        "risk_decision",
        """
        (status = 'APPROVED' AND approved_weight = requested_weight
         AND (jsonb_array_length(reason_codes) = 0
              OR reason_codes = '["LEGACY_BACKFILL"]'::jsonb))
        OR (status = 'CLIPPED' AND approved_weight <> requested_weight
            AND jsonb_array_length(reason_codes) > 0)
        OR (status = 'REJECTED' AND approved_weight = 0
            AND jsonb_array_length(reason_codes) > 0)
        """,
    )
    op.create_check_constraint(
        op.f("ck_risk_decision_authorization_facts"),
        "risk_decision",
        """
        (authorization_source = 'LEGACY_BACKFILL' AND (
            (status = 'REJECTED' AND max_order_quantity = 0 AND authorized_side IS NULL)
            OR (status <> 'REJECTED' AND max_order_quantity > 0
                AND authorized_side IN ('BUY', 'SELL'))
        ))
        OR (authorization_source = 'DETERMINISTIC' AND (
            (status = 'REJECTED' AND max_order_quantity = 0 AND authorized_side IS NULL)
            OR (status <> 'REJECTED' AND (
                (approved_delta = 0 AND max_order_quantity = 0 AND authorized_side IS NULL)
                OR (approved_delta <> 0 AND reference_nav > 0 AND reference_price > 0
                    AND max_order_quantity = abs(approved_delta) * reference_nav / reference_price
                    AND authorized_side = CASE WHEN approved_delta > 0 THEN 'BUY' ELSE 'SELL' END)
            ))
        ))
        """,
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_risk_decision_authorization_facts"),
        "risk_decision",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_risk_decision_status_facts"),
        "risk_decision",
        type_="check",
    )
