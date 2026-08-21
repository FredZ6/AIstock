"""Keep denormalized paper orders consistent with their source intents."""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_paper_order_intent_guard"
down_revision: str | None = "0009_paper_fill_quantity_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION validate_paper_order_intent() RETURNS trigger AS $$
        DECLARE
            source_intent order_intent%ROWTYPE;
        BEGIN
            SELECT * INTO source_intent
            FROM order_intent
            WHERE id = NEW.order_intent_id
            FOR KEY SHARE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'paper order requires an order intent';
            END IF;
            IF NEW.portfolio_id IS DISTINCT FROM source_intent.portfolio_id
               OR NEW.symbol IS DISTINCT FROM source_intent.symbol
               OR NEW.side IS DISTINCT FROM source_intent.side
               OR NEW.quantity IS DISTINCT FROM source_intent.quantity
               OR NEW.decision_time IS DISTINCT FROM source_intent.decision_time
               OR NEW.execution_policy_version_id IS DISTINCT FROM
                   source_intent.execution_policy_version_id
               OR NEW.risk_approved IS DISTINCT FROM source_intent.risk_approved THEN
                RAISE EXCEPTION 'paper order must match order intent';
            END IF;
            IF (NOT NEW.risk_approved AND NEW.status <> 'REJECTED')
               OR (NEW.risk_approved AND NEW.status = 'REJECTED') THEN
                RAISE EXCEPTION 'paper order status must match risk decision';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER validate_paper_order_intent_before_write
            BEFORE INSERT OR UPDATE ON paper_order
            FOR EACH ROW EXECUTE FUNCTION validate_paper_order_intent();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS validate_paper_order_intent_before_write ON paper_order;
        DROP FUNCTION IF EXISTS validate_paper_order_intent;
        """
    )
