"""Attach external market data to complete raw-data provenance."""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_market_data_provenance"
down_revision: str | None = "0002_timescale_hypertables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("market_bar", "option_snapshot"):
        op.execute(
            f"""
            ALTER TABLE {table_name}
                ADD COLUMN raw_data_object_id uuid NOT NULL REFERENCES raw_data_object(id),
                ADD COLUMN provider text NOT NULL,
                ADD COLUMN feed_type text NOT NULL,
                ADD COLUMN content_hash text NOT NULL,
                ADD COLUMN raw_object_key text NOT NULL,
                ADD CONSTRAINT ck_{table_name}_times CHECK (
                    event_time <= available_at AND available_at <= ingested_at
                );
            """
        )


def downgrade() -> None:
    for table_name in ("option_snapshot", "market_bar"):
        op.execute(
            f"""
            ALTER TABLE {table_name}
                DROP CONSTRAINT ck_{table_name}_times,
                DROP COLUMN raw_object_key,
                DROP COLUMN content_hash,
                DROP COLUMN feed_type,
                DROP COLUMN provider,
                DROP COLUMN raw_data_object_id;
            """
        )
