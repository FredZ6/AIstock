"""Preserve market-bar conflict state and accelerate canonical revisions."""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_alert_market_bar_hardening"
down_revision: str | None = "0005_alerts_and_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE market_bar
            ADD COLUMN conflict boolean NOT NULL DEFAULT false;
        CREATE INDEX market_bar_canonical_revision_idx
            ON market_bar (
                symbol,
                feed_type,
                event_time DESC,
                available_at DESC,
                ingested_at DESC
            );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS market_bar_canonical_revision_idx;
        ALTER TABLE market_bar DROP COLUMN IF EXISTS conflict;
        """
    )
