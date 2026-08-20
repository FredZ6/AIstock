"""Add deterministic paper orders, double-entry ledger, and corporate actions."""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_paper_execution_ledger"
down_revision: str | None = "0006_alert_market_bar_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_POLICY_ID = "00000000-0000-0000-0000-000000000007"
LEGACY_PORTFOLIO_ID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO execution_policy_version (id, version, policy)
        VALUES (
            '{LEGACY_POLICY_ID}',
            'legacy-execution-v0',
            '{{"fill_timing":"LEGACY"}}'::jsonb
        ) ON CONFLICT (version) DO NOTHING;

        CREATE TABLE order_intent (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            portfolio_id uuid NOT NULL,
            symbol text NOT NULL,
            side text NOT NULL,
            quantity numeric NOT NULL,
            decision_time timestamptz NOT NULL,
            execution_policy_version_id uuid NOT NULL REFERENCES execution_policy_version(id),
            risk_approved boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_order_intent_side CHECK (side IN ('BUY', 'SELL')),
            CONSTRAINT ck_order_intent_quantity CHECK (quantity > 0)
        );
        CREATE TABLE paper_order (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            order_intent_id uuid NOT NULL REFERENCES order_intent(id),
            portfolio_id uuid NOT NULL,
            symbol text NOT NULL,
            side text NOT NULL,
            quantity numeric NOT NULL,
            decision_time timestamptz NOT NULL,
            execution_policy_version_id uuid NOT NULL REFERENCES execution_policy_version(id),
            risk_approved boolean NOT NULL,
            status text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT paper_order_order_intent_id_key UNIQUE (order_intent_id),
            CONSTRAINT ck_paper_order_side CHECK (side IN ('BUY', 'SELL')),
            CONSTRAINT ck_paper_order_quantity CHECK (quantity > 0),
            CONSTRAINT ck_paper_order_status CHECK (
                status IN ('REJECTED', 'PENDING', 'PARTIALLY_FILLED', 'FILLED')
            )
        );

        ALTER TABLE paper_fill DISABLE TRIGGER enforce_append_only;
        UPDATE paper_fill SET order_id = id WHERE order_id IS NULL;
        INSERT INTO order_intent (
            id, portfolio_id, symbol, side, quantity, decision_time,
            execution_policy_version_id, risk_approved
        )
        SELECT DISTINCT ON (order_id)
            order_id,
            '{LEGACY_PORTFOLIO_ID}',
            'FIXTURE',
            'BUY',
            GREATEST(COALESCE(quantity, 0), 1),
            filled_at - interval '1 microsecond',
            '{LEGACY_POLICY_ID}',
            true
        FROM paper_fill
        ORDER BY order_id, filled_at;
        INSERT INTO paper_order (
            id, order_intent_id, portfolio_id, symbol, side, quantity, decision_time,
            execution_policy_version_id, risk_approved, status
        )
        SELECT id, id, portfolio_id, symbol, side, quantity, decision_time,
               execution_policy_version_id, true, 'FILLED'
        FROM order_intent
        WHERE execution_policy_version_id = '{LEGACY_POLICY_ID}';

        ALTER TABLE paper_fill
            ADD COLUMN portfolio_id uuid,
            ADD COLUMN symbol text,
            ADD COLUMN side text,
            ADD COLUMN fee numeric,
            ADD COLUMN source_bar_time timestamptz,
            ADD COLUMN execution_policy_version_id uuid,
            ADD COLUMN idempotency_key text,
            ADD COLUMN reversal_of_id uuid;
        UPDATE paper_fill SET
            portfolio_id = '{LEGACY_PORTFOLIO_ID}',
            symbol = 'FIXTURE',
            side = 'BUY',
            quantity = COALESCE(quantity, 0),
            price = COALESCE(price, 0),
            fee = 0,
            source_bar_time = filled_at,
            execution_policy_version_id = '{LEGACY_POLICY_ID}',
            idempotency_key = 'legacy:' || id::text;
        ALTER TABLE paper_fill
            ALTER COLUMN order_id SET NOT NULL,
            ALTER COLUMN quantity SET NOT NULL,
            ALTER COLUMN price SET NOT NULL,
            ALTER COLUMN portfolio_id SET NOT NULL,
            ALTER COLUMN symbol SET NOT NULL,
            ALTER COLUMN side SET NOT NULL,
            ALTER COLUMN fee SET NOT NULL,
            ALTER COLUMN fee SET DEFAULT 0,
            ALTER COLUMN source_bar_time SET NOT NULL,
            ALTER COLUMN execution_policy_version_id SET NOT NULL,
            ALTER COLUMN idempotency_key SET NOT NULL,
            ADD CONSTRAINT fk_paper_fill_order FOREIGN KEY (order_id) REFERENCES paper_order(id),
            ADD CONSTRAINT fk_paper_fill_policy FOREIGN KEY (execution_policy_version_id)
                REFERENCES execution_policy_version(id),
            ADD CONSTRAINT fk_paper_fill_reversal FOREIGN KEY (reversal_of_id)
                REFERENCES paper_fill(id),
            ADD CONSTRAINT paper_fill_idempotency_key_key UNIQUE (idempotency_key),
            ADD CONSTRAINT ck_paper_fill_side CHECK (side IN ('BUY', 'SELL')),
            ADD CONSTRAINT ck_paper_fill_values CHECK (
                (quantity > 0 AND price > 0) OR symbol = 'FIXTURE'
            ),
            ADD CONSTRAINT ck_paper_fill_fee CHECK (fee >= 0),
            ADD CONSTRAINT ck_paper_fill_bar_time CHECK (filled_at >= source_bar_time);
        ALTER TABLE paper_fill ENABLE TRIGGER enforce_append_only;

        ALTER TABLE cash_ledger DISABLE TRIGGER enforce_append_only;
        ALTER TABLE cash_ledger
            ADD COLUMN transaction_id uuid,
            ADD COLUMN source_id uuid,
            ADD COLUMN account text,
            ADD COLUMN debit numeric,
            ADD COLUMN credit numeric,
            ADD COLUMN idempotency_key text,
            ADD COLUMN reversal_of_id uuid;
        UPDATE cash_ledger SET
            transaction_id = id,
            source_id = id,
            account = 'LEGACY:CASH',
            debit = CASE WHEN amount > 0 THEN amount ELSE 0 END,
            credit = CASE WHEN amount < 0 THEN -amount ELSE 0 END,
            idempotency_key = 'legacy:' || id::text;
        ALTER TABLE cash_ledger
            ALTER COLUMN transaction_id SET NOT NULL,
            ALTER COLUMN source_id SET NOT NULL,
            ALTER COLUMN account SET NOT NULL,
            ALTER COLUMN debit SET NOT NULL,
            ALTER COLUMN credit SET NOT NULL,
            ALTER COLUMN idempotency_key SET NOT NULL,
            ADD CONSTRAINT fk_cash_ledger_reversal FOREIGN KEY (reversal_of_id)
                REFERENCES cash_ledger(id),
            ADD CONSTRAINT cash_ledger_idempotency_key_key UNIQUE (idempotency_key),
            ADD CONSTRAINT ck_cash_ledger_double_entry CHECK (
                debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0)
                AND (debit > 0 OR credit > 0 OR account = 'LEGACY:CASH')
            );
        ALTER TABLE cash_ledger ENABLE TRIGGER enforce_append_only;

        CREATE FUNCTION validate_paper_fill_insert() RETURNS trigger AS $$
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
        CREATE TRIGGER validate_paper_fill_before_insert
            BEFORE INSERT ON paper_fill
            FOR EACH ROW EXECUTE FUNCTION validate_paper_fill_insert();

        CREATE TABLE corporate_action (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            raw_data_object_id uuid NOT NULL REFERENCES raw_data_object(id),
            symbol text NOT NULL,
            action_type text NOT NULL,
            effective_at timestamptz NOT NULL,
            available_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT now(),
            provider text NOT NULL,
            feed_type text NOT NULL,
            content_hash text NOT NULL,
            raw_object_key text NOT NULL,
            split_ratio numeric,
            cash_per_share numeric,
            currency text NOT NULL DEFAULT 'USD',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_corporate_action_type CHECK (
                action_type IN ('SPLIT', 'CASH_DIVIDEND')
            ),
            CONSTRAINT ck_corporate_action_value CHECK (
                (action_type = 'SPLIT' AND split_ratio > 0 AND cash_per_share IS NULL)
                OR (action_type = 'CASH_DIVIDEND' AND cash_per_share >= 0
                    AND split_ratio IS NULL)
            ),
            CONSTRAINT ck_corporate_action_times CHECK (available_at <= ingested_at)
        );
        CREATE INDEX corporate_action_visible_idx
            ON corporate_action (symbol, effective_at, available_at);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS corporate_action;
        DROP TRIGGER IF EXISTS validate_paper_fill_before_insert ON paper_fill;
        DROP FUNCTION IF EXISTS validate_paper_fill_insert;
        ALTER TABLE cash_ledger
            DROP CONSTRAINT IF EXISTS ck_cash_ledger_double_entry,
            DROP CONSTRAINT IF EXISTS cash_ledger_idempotency_key_key,
            DROP CONSTRAINT IF EXISTS fk_cash_ledger_reversal,
            DROP COLUMN IF EXISTS reversal_of_id,
            DROP COLUMN IF EXISTS idempotency_key,
            DROP COLUMN IF EXISTS credit,
            DROP COLUMN IF EXISTS debit,
            DROP COLUMN IF EXISTS account,
            DROP COLUMN IF EXISTS source_id,
            DROP COLUMN IF EXISTS transaction_id;
        ALTER TABLE paper_fill
            DROP CONSTRAINT IF EXISTS ck_paper_fill_bar_time,
            DROP CONSTRAINT IF EXISTS ck_paper_fill_fee,
            DROP CONSTRAINT IF EXISTS ck_paper_fill_values,
            DROP CONSTRAINT IF EXISTS ck_paper_fill_side,
            DROP CONSTRAINT IF EXISTS paper_fill_idempotency_key_key,
            DROP CONSTRAINT IF EXISTS fk_paper_fill_reversal,
            DROP CONSTRAINT IF EXISTS fk_paper_fill_policy,
            DROP CONSTRAINT IF EXISTS fk_paper_fill_order,
            DROP COLUMN IF EXISTS reversal_of_id,
            DROP COLUMN IF EXISTS idempotency_key,
            DROP COLUMN IF EXISTS execution_policy_version_id,
            DROP COLUMN IF EXISTS source_bar_time,
            DROP COLUMN IF EXISTS fee,
            DROP COLUMN IF EXISTS side,
            DROP COLUMN IF EXISTS symbol,
            DROP COLUMN IF EXISTS portfolio_id;
        DROP TABLE IF EXISTS paper_order;
        DROP TABLE IF EXISTS order_intent;
        """
    )
