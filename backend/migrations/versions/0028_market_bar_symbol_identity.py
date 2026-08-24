"""Include symbol in the append-only market-bar stream identity."""

from collections.abc import Sequence

from alembic import op

revision: str = "0028_market_bar_symbol_identity"
down_revision: str | None = "0027_alpaca_news_pit_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_market_bar_stream_content", table_name="market_bar")
    op.create_index(
        "uq_market_bar_stream_content",
        "market_bar",
        ["provider", "feed_type", "content_hash", "event_time", "symbol"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_market_bar_stream_content", table_name="market_bar")
    op.create_index(
        "uq_market_bar_stream_content",
        "market_bar",
        ["provider", "feed_type", "content_hash", "event_time"],
        unique=True,
    )
