"""Persist immutable risk decisions and require every order to reference one."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_risk_decision_audit"
down_revision: str | None = "0012_idempotent_fill_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_decision",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("requested_weight", sa.Numeric(), nullable=False),
        sa.Column("approved_weight", sa.Numeric(), nullable=False),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("risk_policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('APPROVED', 'CLIPPED', 'REJECTED')", name="ck_risk_decision_status"
        ),
        sa.CheckConstraint(
            "requested_weight >= 0 AND approved_weight >= 0", name="ck_risk_decision_weights"
        ),
        sa.CheckConstraint(
            "status <> 'REJECTED' OR approved_weight = 0", name="ck_risk_decision_rejected_weight"
        ),
        sa.ForeignKeyConstraint(["research_decision_id"], ["decision_snapshot.id"]),
        sa.ForeignKeyConstraint(["risk_policy_version_id"], ["risk_policy_version.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "order_intent",
        sa.Column("risk_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        INSERT INTO risk_policy_version (version, policy)
        VALUES ('legacy-risk-v1', '{"source":"0013_backfill"}'::jsonb)
        ON CONFLICT (version) DO NOTHING;

        INSERT INTO risk_decision (
            id, proposal_id, portfolio_id, symbol, status, requested_weight,
            approved_weight, reason_codes, risk_policy_version_id, decided_at, created_at
        )
        SELECT
            intent.id,
            intent.id,
            intent.portfolio_id,
            intent.symbol,
            CASE WHEN intent.risk_approved THEN 'APPROVED' ELSE 'REJECTED' END,
            0,
            0,
            '["LEGACY_BACKFILL"]'::jsonb,
            policy.id,
            intent.decision_time,
            intent.created_at
        FROM order_intent intent
        CROSS JOIN LATERAL (
            SELECT id FROM risk_policy_version WHERE version = 'legacy-risk-v1' LIMIT 1
        ) policy;

        UPDATE order_intent SET risk_decision_id = id WHERE risk_decision_id IS NULL;
        """
    )
    op.alter_column("order_intent", "risk_decision_id", nullable=False)
    op.create_foreign_key(
        "order_intent_risk_decision_id_fkey",
        "order_intent",
        "risk_decision",
        ["risk_decision_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "order_intent_risk_decision_id_key",
        "order_intent",
        ["risk_decision_id"],
    )
    op.execute(
        """
        CREATE FUNCTION validate_order_risk_decision() RETURNS trigger AS $$
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

        CREATE TRIGGER validate_order_risk_decision_before_write
        BEFORE INSERT OR UPDATE ON order_intent
        FOR EACH ROW EXECUTE FUNCTION validate_order_risk_decision();

        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON risk_decision
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS validate_order_risk_decision_before_write ON order_intent")
    op.execute("DROP FUNCTION IF EXISTS validate_order_risk_decision")
    op.drop_constraint("order_intent_risk_decision_id_key", "order_intent", type_="unique")
    op.drop_constraint("order_intent_risk_decision_id_fkey", "order_intent", type_="foreignkey")
    op.drop_column("order_intent", "risk_decision_id")
    op.drop_table("risk_decision")
