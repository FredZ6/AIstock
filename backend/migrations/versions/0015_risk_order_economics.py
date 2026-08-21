"""Bind every approved order to exact deterministic risk economics."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_risk_order_economics"
down_revision: str | None = "0014_risk_constraint_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "risk_decision",
        sa.Column("current_weight", sa.Numeric(), server_default="0", nullable=False),
    )
    op.add_column(
        "risk_decision",
        sa.Column("approved_delta", sa.Numeric(), server_default="0", nullable=False),
    )
    op.add_column("risk_decision", sa.Column("reference_nav", sa.Numeric(), nullable=True))
    op.add_column("risk_decision", sa.Column("reference_price", sa.Numeric(), nullable=True))
    op.add_column(
        "risk_decision",
        sa.Column("max_order_quantity", sa.Numeric(), server_default="0", nullable=False),
    )
    op.add_column(
        "risk_decision",
        sa.Column(
            "authorization_source",
            sa.Text(),
            server_default="DETERMINISTIC",
            nullable=False,
        ),
    )
    op.add_column("risk_decision", sa.Column("authorized_side", sa.Text(), nullable=True))
    op.execute(
        """
        DROP TRIGGER enforce_append_only ON risk_decision;

        UPDATE risk_decision AS risk
        SET requested_weight = 0,
            approved_weight = 0,
            current_weight = 0,
            approved_delta = 0,
            reference_nav = NULL,
            reference_price = NULL,
            max_order_quantity = CASE WHEN intent.risk_approved THEN intent.quantity ELSE 0 END,
            authorization_source = 'LEGACY_BACKFILL',
            authorized_side = CASE WHEN intent.risk_approved THEN intent.side ELSE NULL END
        FROM order_intent AS intent
        WHERE intent.risk_decision_id = risk.id;

        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON risk_decision
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

        CREATE OR REPLACE FUNCTION validate_order_risk_decision() RETURNS trigger AS $$
        DECLARE
            source_risk risk_decision%ROWTYPE;
        BEGIN
            SELECT * INTO source_risk FROM risk_decision WHERE id = NEW.risk_decision_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'order intent requires a deterministic risk decision';
            END IF;
            IF NEW.portfolio_id <> source_risk.portfolio_id
               OR NEW.symbol <> source_risk.symbol
               OR NEW.decision_time <> source_risk.decided_at THEN
                RAISE EXCEPTION 'order intent identity must match risk decision';
            END IF;
            IF NEW.risk_approved <> (source_risk.status <> 'REJECTED') THEN
                RAISE EXCEPTION 'order approval must match risk decision';
            END IF;
            IF NEW.risk_approved AND (
                NEW.quantity <> source_risk.max_order_quantity
                OR NEW.side <> source_risk.authorized_side
                OR (source_risk.authorization_source = 'DETERMINISTIC'
                    AND source_risk.approved_delta = 0)
            ) THEN
                RAISE EXCEPTION 'order quantity or side exceeds risk decision authorization';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.create_check_constraint(
        op.f("ck_risk_decision_order_economics"),
        "risk_decision",
        "approved_delta = approved_weight - current_weight AND max_order_quantity >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_risk_decision_order_economics"),
        "risk_decision",
        type_="check",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_order_risk_decision() RETURNS trigger AS $$
        DECLARE
            source_risk risk_decision%ROWTYPE;
        BEGIN
            SELECT * INTO source_risk FROM risk_decision WHERE id = NEW.risk_decision_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'order intent requires a deterministic risk decision';
            END IF;
            IF NEW.portfolio_id <> source_risk.portfolio_id
               OR NEW.symbol <> source_risk.symbol
               OR NEW.decision_time <> source_risk.decided_at THEN
                RAISE EXCEPTION 'order intent identity must match risk decision';
            END IF;
            IF NEW.risk_approved <> (source_risk.status <> 'REJECTED') THEN
                RAISE EXCEPTION 'order approval must match risk decision';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.drop_column("risk_decision", "max_order_quantity")
    op.drop_column("risk_decision", "authorized_side")
    op.drop_column("risk_decision", "authorization_source")
    op.drop_column("risk_decision", "reference_price")
    op.drop_column("risk_decision", "reference_nav")
    op.drop_column("risk_decision", "approved_delta")
    op.drop_column("risk_decision", "current_weight")
