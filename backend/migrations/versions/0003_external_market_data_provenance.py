"""Attach external market data to complete raw-data provenance."""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_market_data_provenance"
down_revision: str | None = "0002_timescale_hypertables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name, feed_type in (
        ("market_bar", "MARKET_BAR"),
        ("option_snapshot", "OPTION_SNAPSHOT"),
    ):
        op.execute(
            f"""
            ALTER TABLE {table_name}
                ADD COLUMN raw_data_object_id uuid,
                ADD COLUMN provider text,
                ADD COLUMN feed_type text,
                ADD COLUMN content_hash text,
                ADD COLUMN raw_object_key text;

            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM {table_name} AS external_row
                    WHERE (
                        SELECT count(*)
                        FROM raw_data_object AS raw
                        WHERE raw.feed_type = '{feed_type}'
                          AND raw.event_time = external_row.event_time
                          AND raw.available_at = external_row.available_at
                          AND raw.ingested_at = external_row.ingested_at
                    ) <> 1
                ) THEN
                    RAISE EXCEPTION USING MESSAGE =
                        '{table_name} provenance migration requires exactly one ' ||
                        'matching RawDataObject per row';
                END IF;
            END
            $$;

            UPDATE {table_name} AS external_row
            SET raw_data_object_id = raw.id,
                provider = raw.provider,
                feed_type = raw.feed_type,
                content_hash = raw.content_hash,
                raw_object_key = raw.raw_object_key
            FROM raw_data_object AS raw
            WHERE raw.feed_type = '{feed_type}'
              AND raw.event_time = external_row.event_time
              AND raw.available_at = external_row.available_at
              AND raw.ingested_at = external_row.ingested_at;

            ALTER TABLE {table_name}
                ALTER COLUMN raw_data_object_id SET NOT NULL,
                ALTER COLUMN provider SET NOT NULL,
                ALTER COLUMN feed_type SET NOT NULL,
                ALTER COLUMN content_hash SET NOT NULL,
                ALTER COLUMN raw_object_key SET NOT NULL,
                ADD CONSTRAINT fk_{table_name}_raw_data_object
                    FOREIGN KEY (raw_data_object_id) REFERENCES raw_data_object(id),
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
