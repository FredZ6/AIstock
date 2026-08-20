"""Allow validated append-only reversal fills without weakening order checks."""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_paper_fill_reversals"
down_revision: str | None = "0007_paper_execution_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_paper_fill_insert() RETURNS trigger AS $$
        DECLARE
            source_order paper_order%ROWTYPE;
            original_fill paper_fill%ROWTYPE;
        BEGIN
            IF NEW.reversal_of_id IS NOT NULL THEN
                SELECT * INTO original_fill FROM paper_fill WHERE id = NEW.reversal_of_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'paper fill reversal requires an original fill';
                END IF;
                IF original_fill.reversal_of_id IS NOT NULL
                   OR NEW.order_id <> original_fill.order_id
                   OR NEW.portfolio_id <> original_fill.portfolio_id
                   OR NEW.symbol <> original_fill.symbol
                   OR NEW.quantity <> original_fill.quantity
                   OR NEW.price <> original_fill.price
                   OR NEW.currency <> original_fill.currency
                   OR NEW.execution_policy_version_id <>
                       original_fill.execution_policy_version_id
                   OR NEW.side = original_fill.side
                   OR NEW.fee <> 0
                   OR NEW.filled_at <= original_fill.filled_at THEN
                    RAISE EXCEPTION 'paper fill reversal does not invert the original fill';
                END IF;
                RETURN NEW;
            END IF;

            SELECT * INTO source_order FROM paper_order WHERE id = NEW.order_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'paper fill requires a paper order';
            END IF;
            IF NOT source_order.risk_approved THEN
                RAISE EXCEPTION 'paper fill requires a risk-approved order';
            END IF;
            IF NEW.filled_at <= source_order.decision_time
               OR NEW.source_bar_time <= source_order.decision_time THEN
                RAISE EXCEPTION 'paper fill must be strictly after decision time';
            END IF;
            IF NEW.execution_policy_version_id <> source_order.execution_policy_version_id THEN
                RAISE EXCEPTION 'paper fill execution policy does not match order';
            END IF;
            IF NEW.portfolio_id <> source_order.portfolio_id
               OR NEW.symbol <> source_order.symbol
               OR NEW.side <> source_order.side THEN
                RAISE EXCEPTION 'paper fill identity does not match order';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_paper_fill_insert() RETURNS trigger AS $$
        DECLARE
            source_order paper_order%ROWTYPE;
        BEGIN
            SELECT * INTO source_order FROM paper_order WHERE id = NEW.order_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'paper fill requires a paper order';
            END IF;
            IF NOT source_order.risk_approved THEN
                RAISE EXCEPTION 'paper fill requires a risk-approved order';
            END IF;
            IF NEW.filled_at <= source_order.decision_time
               OR NEW.source_bar_time <= source_order.decision_time THEN
                RAISE EXCEPTION 'paper fill must be strictly after decision time';
            END IF;
            IF NEW.execution_policy_version_id <> source_order.execution_policy_version_id THEN
                RAISE EXCEPTION 'paper fill execution policy does not match order';
            END IF;
            IF NEW.portfolio_id <> source_order.portfolio_id
               OR NEW.symbol <> source_order.symbol
               OR NEW.side <> source_order.side THEN
                RAISE EXCEPTION 'paper fill identity does not match order';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
