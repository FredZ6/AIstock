"""Repair corporate-action guards for databases already stamped at 0033."""

from collections.abc import Sequence

from alembic import op

revision: str = "0034_corp_action_guards"
down_revision: str | None = "0033_ingestion_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE corporate_action ALTER COLUMN source_currency DROP DEFAULT;

        ALTER TABLE corporate_action DROP CONSTRAINT IF EXISTS ck_corporate_action_value;
        ALTER TABLE corporate_action ADD CONSTRAINT ck_corporate_action_value CHECK (
            (action_type = 'SPLIT' AND split_ratio > 0 AND cash_per_share IS NULL
             AND stock_ratio IS NULL AND old_adr_ratio IS NULL AND new_adr_ratio IS NULL)
            OR (action_type = 'CASH_DIVIDEND' AND cash_per_share >= 0 AND split_ratio IS NULL
                AND stock_ratio IS NULL AND old_adr_ratio IS NULL AND new_adr_ratio IS NULL)
            OR (action_type = 'STOCK_DIVIDEND' AND stock_ratio > 0 AND split_ratio IS NULL
                AND cash_per_share IS NULL AND old_adr_ratio IS NULL AND new_adr_ratio IS NULL)
            OR (action_type = 'ADR_RATIO_CHANGE' AND old_adr_ratio > 0 AND new_adr_ratio > 0
                AND split_ratio IS NULL AND cash_per_share IS NULL AND stock_ratio IS NULL)
            OR (action_type IN ('SPIN_OFF', 'SYMBOL_CHANGE', 'MERGER_ACQUISITION')
                AND split_ratio IS NULL AND cash_per_share IS NULL AND stock_ratio IS NULL
                AND old_adr_ratio IS NULL AND new_adr_ratio IS NULL)
        );

        CREATE OR REPLACE FUNCTION validate_corporate_action_revision() RETURNS trigger AS $$
        DECLARE
            previous corporate_action%ROWTYPE;
        BEGIN
            PERFORM pg_advisory_xact_lock(
                hashtextextended(NEW.provider || chr(31) || NEW.provider_action_id, 0)
            );
            SELECT * INTO previous
            FROM corporate_action
            WHERE provider = NEW.provider
              AND provider_action_id = NEW.provider_action_id
            ORDER BY available_at DESC, created_at DESC
            LIMIT 1;
            IF FOUND THEN
                IF NEW.supersedes_id IS NULL OR NEW.supersedes_id <> previous.id THEN
                    RAISE EXCEPTION 'corporate action revision must supersede latest version';
                END IF;
                IF NEW.available_at <= previous.available_at THEN
                    RAISE EXCEPTION 'corporate action revision availability must increase';
                END IF;
            ELSIF NEW.supersedes_id IS NOT NULL THEN
                RAISE EXCEPTION 'first corporate action version cannot supersede another identity';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        DROP TRIGGER IF EXISTS validate_revision_chain ON corporate_action;
        CREATE TRIGGER validate_revision_chain
            BEFORE INSERT ON corporate_action
            FOR EACH ROW EXECUTE FUNCTION validate_corporate_action_revision();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        -- Current 0033 already defines the strict value constraint and serialized
        -- revision-chain trigger. 0034 repairs databases stamped before those
        -- guards were backfilled, so downgrading the revision marker must retain
        -- the schema that a clean current 0033 migration creates.
        ALTER TABLE corporate_action ALTER COLUMN source_currency DROP DEFAULT;
        """
    )
