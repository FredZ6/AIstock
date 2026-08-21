"""Align risk audit constraint names with authoritative metadata."""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_risk_constraint_names"
down_revision: str | None = "0013_risk_decision_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE order_intent
            RENAME CONSTRAINT order_intent_risk_decision_id_key
            TO uq_order_intent_risk_decision_id;
        ALTER TABLE risk_decision
            RENAME CONSTRAINT ck_risk_decision_ck_risk_decision_status
            TO ck_risk_decision_status;
        ALTER TABLE risk_decision
            RENAME CONSTRAINT ck_risk_decision_ck_risk_decision_weights
            TO ck_risk_decision_weights;
        ALTER TABLE risk_decision
            RENAME CONSTRAINT ck_risk_decision_ck_risk_decision_rejected_weight
            TO ck_risk_decision_rejected_weight;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE order_intent
            RENAME CONSTRAINT uq_order_intent_risk_decision_id
            TO order_intent_risk_decision_id_key;
        ALTER TABLE risk_decision
            RENAME CONSTRAINT ck_risk_decision_status
            TO ck_risk_decision_ck_risk_decision_status;
        ALTER TABLE risk_decision
            RENAME CONSTRAINT ck_risk_decision_weights
            TO ck_risk_decision_ck_risk_decision_weights;
        ALTER TABLE risk_decision
            RENAME CONSTRAINT ck_risk_decision_rejected_weight
            TO ck_risk_decision_ck_risk_decision_rejected_weight;
        """
    )
