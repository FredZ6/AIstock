"""Add deterministic alerts, thesis links, and notification outbox."""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_alerts_and_outbox"
down_revision: str | None = "0004_normalization_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE alert_event (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_key text NOT NULL UNIQUE,
            symbol text NOT NULL,
            event_time timestamptz NOT NULL,
            rule_id text NOT NULL,
            rule_version text NOT NULL,
            severity text NOT NULL,
            materiality numeric NOT NULL,
            conditions jsonb NOT NULL DEFAULT '[]'::jsonb,
            metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
            data_quality jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_alert_event_severity
                CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
            CONSTRAINT ck_alert_event_materiality
                CHECK (materiality >= 0 AND materiality <= 1)
        );

        CREATE TABLE alert_thesis_link (
            alert_event_id uuid NOT NULL REFERENCES alert_event(id),
            thesis_id uuid NOT NULL REFERENCES investment_thesis(id),
            invalidation_condition text,
            severity text NOT NULL,
            materiality numeric NOT NULL,
            evidence_id uuid REFERENCES evidence_item(id),
            review_action text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (alert_event_id, thesis_id)
        );

        CREATE TABLE alert_explanation (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_id uuid NOT NULL UNIQUE REFERENCES alert_event(id),
            status text NOT NULL,
            content text,
            error_code text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_alert_explanation_status
                CHECK (status IN ('DISABLED', 'SUCCEEDED', 'FAILED'))
        );

        CREATE TABLE notification_outbox (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_id uuid NOT NULL UNIQUE REFERENCES alert_event(id),
            alert_key text NOT NULL UNIQUE,
            payload jsonb NOT NULL,
            channels jsonb NOT NULL,
            channel_states jsonb NOT NULL,
            status text NOT NULL DEFAULT 'PENDING',
            attempts integer NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL,
            last_error text,
            delivered_at timestamptz,
            updated_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_notification_outbox_status
                CHECK (status IN ('PENDING', 'RETRY', 'DELIVERED'))
        );

        ALTER TABLE market_bar ADD COLUMN open numeric;
        ALTER TABLE market_bar ADD COLUMN high numeric;
        ALTER TABLE market_bar ADD COLUMN low numeric;
        ALTER TABLE market_bar ADD COLUMN volume numeric;
        ALTER TABLE market_bar ADD COLUMN previous_close numeric;
        ALTER TABLE market_bar ADD COLUMN payload jsonb NOT NULL DEFAULT '{}'::jsonb;
        CREATE UNIQUE INDEX uq_market_bar_stream_content
            ON market_bar (provider, feed_type, content_hash, event_time);

        ALTER TABLE alert_metric ADD COLUMN alert_id uuid REFERENCES alert_event(id);
        ALTER TABLE alert_metric ADD COLUMN algorithm_version text NOT NULL
            DEFAULT 'alert-policy-v1';
        ALTER TABLE alert_metric ADD COLUMN data_quality jsonb NOT NULL DEFAULT '{}'::jsonb;
        CREATE INDEX alert_metric_alert_id_idx ON alert_metric (alert_id, event_time DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS alert_metric_alert_id_idx;
        ALTER TABLE alert_metric DROP COLUMN IF EXISTS data_quality;
        ALTER TABLE alert_metric DROP COLUMN IF EXISTS algorithm_version;
        ALTER TABLE alert_metric DROP COLUMN IF EXISTS alert_id;

        DROP INDEX IF EXISTS uq_market_bar_stream_content;
        ALTER TABLE market_bar DROP COLUMN IF EXISTS payload;
        ALTER TABLE market_bar DROP COLUMN IF EXISTS previous_close;
        ALTER TABLE market_bar DROP COLUMN IF EXISTS volume;
        ALTER TABLE market_bar DROP COLUMN IF EXISTS low;
        ALTER TABLE market_bar DROP COLUMN IF EXISTS high;
        ALTER TABLE market_bar DROP COLUMN IF EXISTS open;

        DROP TABLE IF EXISTS notification_outbox;
        DROP TABLE IF EXISTS alert_explanation;
        DROP TABLE IF EXISTS alert_thesis_link;
        DROP TABLE IF EXISTS alert_event;
        """
    )
