"""Repair legacy risk facts and pin orders to frozen execution policy lineage."""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_risk_authorization_lineage"
down_revision: str | None = "0017_risk_fact_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUTHORIZATION_CONSTRAINT = """
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
"""


def _replace_order_validator(*, enforce_execution_policy: bool) -> None:
    execution_policy_check = (
        """
            IF source_risk.research_decision_id IS NOT NULL THEN
                SELECT execution_policy_version_id INTO pinned_execution_policy
                FROM decision_snapshot WHERE id = source_risk.research_decision_id;
                IF NOT FOUND OR pinned_execution_policy <> NEW.execution_policy_version_id THEN
                    RAISE EXCEPTION
                        'order execution policy must match frozen research decision';
                END IF;
            END IF;
        """
        if enforce_execution_policy
        else ""
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION validate_order_risk_decision() RETURNS trigger AS $$
        DECLARE
            source_risk risk_decision%ROWTYPE;
            pinned_execution_policy uuid;
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
            {execution_policy_check}
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE risk_decision
            ADD COLUMN IF NOT EXISTS authorization_source text NOT NULL
            DEFAULT 'DETERMINISTIC';
        ALTER TABLE risk_decision
            ADD COLUMN IF NOT EXISTS authorized_side text;

        ALTER TABLE risk_decision
            DROP CONSTRAINT IF EXISTS ck_risk_decision_authorization_facts;
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
        WHERE intent.risk_decision_id = risk.id
          AND risk.reason_codes = '["LEGACY_BACKFILL"]'::jsonb;

        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON risk_decision
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

        UPDATE market_context_snapshot
        SET qqq_trend = NULL,
            qqq_volatility = NULL,
            soxx_relative_strength = NULL,
            vix = NULL,
            regime_label = 'UNKNOWN',
            source_lineage = '["LEGACY_UNKNOWN"]'::jsonb
        WHERE id = '00000000-0000-0000-0000-000000000016'::uuid;

        DELETE FROM market_context_snapshot AS context
        WHERE context.id = '00000000-0000-0000-0000-000000000016'::uuid
          AND NOT EXISTS (
              SELECT 1 FROM risk_decision AS risk
              WHERE risk.market_context_snapshot_id = context.id
          );
        """
    )
    op.create_check_constraint(
        op.f("ck_risk_decision_authorization_facts"),
        "risk_decision",
        _AUTHORIZATION_CONSTRAINT,
    )
    _replace_order_validator(enforce_execution_policy=True)


def downgrade() -> None:
    _replace_order_validator(enforce_execution_policy=False)
