"""Pin risk decisions to point-in-time market context and research policy lineage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_market_context_risk_pin"
down_revision: str | None = "0015_risk_order_economics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "market_context_snapshot",
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("market_context_snapshot", sa.Column("vix", sa.Numeric(), nullable=True))
    op.execute("UPDATE market_context_snapshot SET available_at = as_of WHERE available_at IS NULL")
    op.alter_column("market_context_snapshot", "available_at", nullable=False)

    op.add_column(
        "risk_decision",
        sa.Column("market_context_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        INSERT INTO market_context_snapshot (
            id, as_of, available_at, qqq_trend, qqq_volatility,
            soxx_relative_strength, vix, regime_label, algorithm_version, source_lineage
        )
        SELECT
            '00000000-0000-0000-0000-000000000016'::uuid,
            MIN(decided_at),
            MIN(decided_at),
            NULL, NULL, NULL, NULL, 'UNKNOWN', 'legacy-context-v1',
            '["LEGACY_UNKNOWN"]'::jsonb
        FROM risk_decision
        HAVING COUNT(*) > 0
        ON CONFLICT (id) DO NOTHING;

        DROP TRIGGER enforce_append_only ON risk_decision;
        UPDATE risk_decision
        SET market_context_snapshot_id = '00000000-0000-0000-0000-000000000016'::uuid
        WHERE market_context_snapshot_id IS NULL;
        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON risk_decision
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
        """
    )
    op.alter_column("risk_decision", "market_context_snapshot_id", nullable=False)
    op.create_foreign_key(
        op.f("risk_decision_market_context_snapshot_id_fkey"),
        "risk_decision",
        "market_context_snapshot",
        ["market_context_snapshot_id"],
        ["id"],
    )
    op.execute(
        """
        CREATE FUNCTION validate_risk_decision_lineage() RETURNS trigger AS $$
        DECLARE
            pinned_risk_policy uuid;
        BEGIN
            IF NEW.research_decision_id IS NOT NULL THEN
                SELECT risk_policy_version_id INTO pinned_risk_policy
                FROM decision_snapshot WHERE id = NEW.research_decision_id;
                IF NOT FOUND OR pinned_risk_policy <> NEW.risk_policy_version_id THEN
                    RAISE EXCEPTION 'risk decision policy must match frozen research decision';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER validate_risk_decision_lineage_before_insert
        BEFORE INSERT ON risk_decision
        FOR EACH ROW EXECUTE FUNCTION validate_risk_decision_lineage();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER validate_risk_decision_lineage_before_insert ON risk_decision")
    op.execute("DROP FUNCTION validate_risk_decision_lineage")
    op.drop_constraint(
        op.f("risk_decision_market_context_snapshot_id_fkey"),
        "risk_decision",
        type_="foreignkey",
    )
    op.drop_column("risk_decision", "market_context_snapshot_id")
    op.drop_column("market_context_snapshot", "vix")
    op.drop_column("market_context_snapshot", "available_at")
