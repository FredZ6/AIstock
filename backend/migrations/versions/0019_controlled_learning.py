"""Persist weekly outcomes, replayed lessons, and audited policy promotion."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_controlled_learning"
down_revision: str | None = "0018_risk_authorization_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def _protect(table_names: tuple[str, ...]) -> None:
    for table_name in table_names:
        op.execute(
            f"""
            CREATE TRIGGER enforce_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
            """
        )


def upgrade() -> None:
    op.create_table(
        "weekly_review_run",
        _id(),
        sa.Column("run_key", sa.Text(), nullable=False),
        sa.Column(
            "decision_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_scoring_policy_version", sa.Text(), nullable=False),
        sa.Column("risk_policy_version", sa.Text(), nullable=False),
        sa.Column("execution_policy_version", sa.Text(), nullable=False),
        sa.Column("confidence_policy_version", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        _created_at(),
        sa.CheckConstraint("data_cutoff <= decision_time", name=op.f("ck_weekly_review_cutoff")),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name=op.f("ck_weekly_review_status"),
        ),
        sa.UniqueConstraint("run_key", name="weekly_review_run_run_key_key"),
    )
    op.create_table(
        "decision_outcome",
        _id(),
        sa.Column(
            "weekly_review_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("weekly_review_run.id"),
            nullable=False,
        ),
        sa.Column(
            "decision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("decision_snapshot.id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "returns", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "excess_returns",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("maximum_favorable_excursion", sa.Numeric(), nullable=False),
        sa.Column("maximum_adverse_excursion", sa.Numeric(), nullable=False),
        sa.Column("risk_adjusted_return", sa.Numeric(), nullable=False),
        sa.Column("calibration_error", sa.Numeric(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.UniqueConstraint("weekly_review_run_id", "decision_id", name="uq_outcome_run_decision"),
        sa.CheckConstraint("status IN ('PENDING', 'MATURED')", name=op.f("ck_outcome_status")),
    )
    op.create_table(
        "error_attribution",
        _id(),
        sa.Column(
            "outcome_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("decision_outcome.id"),
            nullable=False,
        ),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("controllable", sa.Boolean(), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "category IN ('STALE_DATA', 'MISSING_EVIDENCE', 'FACT_ERROR', "
            "'CONFLICT_IGNORED', 'THESIS_ERROR', 'TIMING_ERROR', "
            "'POSITION_SIZING_ERROR', 'EXECUTION_ERROR', 'REGIME_CHANGE', "
            "'RISK_POLICY_FAILURE', 'UNCONTROLLABLE_EVENT')",
            name=op.f("ck_error_attribution_category"),
        ),
        sa.UniqueConstraint("outcome_id", "category", name="uq_attribution_outcome_category"),
    )
    op.create_table(
        "candidate_lesson",
        _id(),
        sa.Column(
            "attribution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("error_attribution.id"),
            nullable=False,
        ),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("duplicate_key", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column(
            "counter_evidence",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("replay_delta", sa.Numeric(), nullable=False),
        sa.Column("creator", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'CANDIDATE'")),
        _created_at(),
        sa.UniqueConstraint("duplicate_key", name="candidate_lesson_duplicate_key_key"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name=op.f("ck_lesson_confidence")
        ),
        sa.CheckConstraint(
            "status IN ('CANDIDATE', 'APPROVED', 'REJECTED')",
            name=op.f("ck_lesson_status"),
        ),
    )
    op.create_table(
        "lesson_attribution_link",
        sa.Column(
            "lesson_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidate_lesson.id"),
            primary_key=True,
        ),
        sa.Column(
            "attribution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("error_attribution.id"),
            primary_key=True,
        ),
        _created_at(),
    )
    op.create_table(
        "replay_run",
        _id(),
        sa.Column(
            "lesson_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidate_lesson.id"),
            nullable=False,
        ),
        sa.Column(
            "decision_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("baseline_score", sa.Numeric(), nullable=False),
        sa.Column("candidate_score", sa.Numeric(), nullable=False),
        sa.Column("delta", sa.Numeric(), nullable=False),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.UniqueConstraint("lesson_id", "data_cutoff", name="uq_replay_lesson_cutoff"),
    )
    op.create_table(
        "lesson_approval",
        _id(),
        sa.Column(
            "lesson_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidate_lesson.id"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "action IN ('APPROVE', 'REJECT')", name=op.f("ck_lesson_approval_action")
        ),
    )
    op.create_table(
        "policy_control",
        sa.Column("policy_kind", sa.Text(), primary_key=True),
        sa.Column("active_version", sa.Text(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("revision >= 0", name=op.f("ck_policy_control_revision")),
    )
    op.create_table(
        "policy_candidate",
        _id(),
        sa.Column("policy_kind", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("base_version", sa.Text(), nullable=False),
        sa.Column("lesson_ids", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'CANDIDATE'")),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        _created_at(),
        sa.UniqueConstraint("policy_kind", "version", name="uq_policy_candidate_kind_version"),
        sa.CheckConstraint(
            "status IN ('CANDIDATE', 'APPROVED', 'ACTIVE', 'REJECTED', 'ROLLED_BACK')",
            name=op.f("ck_policy_candidate_status"),
        ),
        sa.CheckConstraint("revision >= 0", name=op.f("ck_policy_candidate_revision")),
    )
    op.create_table(
        "policy_promotion_audit",
        _id(),
        sa.Column(
            "policy_candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policy_candidate.id"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("expected_revision", sa.BigInteger(), nullable=False),
        sa.Column("observed_revision", sa.BigInteger(), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "action IN ('APPROVE', 'ACTIVATE', 'REJECT', 'ROLLBACK', "
            "'DENY_APPROVE', 'DENY_ACTIVATE', 'DENY_REJECT', 'DENY_ROLLBACK')",
            name=op.f("ck_policy_promotion_action"),
        ),
        sa.CheckConstraint(
            "outcome IN ('COMPLETED', 'FORBIDDEN', 'CONFLICT')",
            name=op.f("ck_policy_promotion_outcome"),
        ),
    )
    _protect(
        (
            "weekly_review_run",
            "decision_outcome",
            "error_attribution",
            "candidate_lesson",
            "lesson_attribution_link",
            "replay_run",
            "lesson_approval",
            "policy_promotion_audit",
        )
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lesson_attribution_link")
    for table_name in (
        "policy_promotion_audit",
        "policy_candidate",
        "lesson_approval",
        "replay_run",
        "candidate_lesson",
        "error_attribution",
        "decision_outcome",
        "weekly_review_run",
    ):
        op.drop_table(table_name)
    op.execute("DROP TABLE IF EXISTS policy_control")
