"""Create the canonical v0.2 research and paper-trading schema."""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_core_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TYPE thesis_evidence_relation AS ENUM ('SUPPORTS', 'CONTRADICTS', 'CONTEXT');
        CREATE TYPE evidence_gap_kind AS ENUM ('UNKNOWN', 'MISSING', 'UNAVAILABLE', 'CONFLICTED');
        CREATE TYPE research_opinion_value AS ENUM ('BULLISH', 'NEUTRAL', 'BEARISH', 'ABSTAIN');
        CREATE TYPE portfolio_action_value AS ENUM
            ('ENTER', 'ADD', 'HOLD', 'REDUCE', 'EXIT', 'NO_ACTION');

        CREATE TABLE raw_data_object (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            provider text NOT NULL,
            feed_type text NOT NULL,
            event_time timestamptz NOT NULL,
            available_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT now(),
            content_hash text NOT NULL,
            raw_object_key text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_raw_data_times CHECK (
                event_time <= available_at AND available_at <= ingested_at
            ),
            CONSTRAINT uq_raw_data_provider_content UNIQUE (provider, feed_type, content_hash)
        );

        CREATE TABLE normalized_record (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            raw_data_object_id uuid NOT NULL REFERENCES raw_data_object(id),
            record_type text,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE derived_metric (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            normalized_record_id uuid NOT NULL REFERENCES normalized_record(id),
            metric_name text,
            metric_value numeric,
            algorithm_version text,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE evidence_item (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            derived_metric_id uuid NOT NULL REFERENCES derived_metric(id),
            provider text NOT NULL,
            freshness interval,
            coverage numeric,
            delay interval,
            conflict boolean NOT NULL DEFAULT false,
            content jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE evidence_gap (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            kind evidence_gap_kind NOT NULL,
            field text NOT NULL,
            domain text NOT NULL,
            reason text NOT NULL,
            provider text,
            observed_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE claim (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            evidence_id uuid NOT NULL REFERENCES evidence_item(id),
            statement text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE research_scoring_policy_version (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            version text NOT NULL DEFAULT 'fixture-v1',
            policy jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (version)
        );
        CREATE TABLE risk_policy_version (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            version text NOT NULL DEFAULT 'fixture-v1',
            policy jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (version)
        );
        CREATE TABLE execution_policy_version (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            version text NOT NULL DEFAULT 'fixture-v1',
            policy jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (version)
        );
        CREATE TABLE confidence_policy_version (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            version text NOT NULL DEFAULT 'fixture-v1',
            policy jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (version)
        );

        CREATE TABLE investment_thesis (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id uuid NOT NULL DEFAULT gen_random_uuid(),
            symbol text NOT NULL DEFAULT 'FIXTURE',
            as_of timestamptz NOT NULL DEFAULT now(),
            direction text NOT NULL DEFAULT 'NEUTRAL',
            summary text NOT NULL DEFAULT '',
            catalysts jsonb NOT NULL DEFAULT '[]'::jsonb,
            risks jsonb NOT NULL DEFAULT '[]'::jsonb,
            invalidation_conditions jsonb NOT NULL DEFAULT '[]'::jsonb,
            horizon text NOT NULL DEFAULT 'UNSPECIFIED',
            confidence numeric NOT NULL DEFAULT 0,
            confidence_policy_version_id uuid REFERENCES confidence_policy_version(id),
            supersedes_thesis_id uuid REFERENCES investment_thesis(id),
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE thesis_evidence_link (
            thesis_id uuid NOT NULL REFERENCES investment_thesis(id),
            evidence_id uuid NOT NULL REFERENCES evidence_item(id),
            relation thesis_evidence_relation NOT NULL,
            weight numeric NOT NULL,
            rationale text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (thesis_id, evidence_id, relation)
        );

        CREATE TABLE research_opinion (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            thesis_id uuid NOT NULL REFERENCES investment_thesis(id),
            value research_opinion_value NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE portfolio_action (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            decision_id uuid,
            value portfolio_action_value NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE market_context_snapshot (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            as_of timestamptz NOT NULL,
            qqq_trend numeric,
            qqq_volatility numeric,
            soxx_relative_strength numeric,
            vix_regime text,
            regime_label text,
            algorithm_version text NOT NULL,
            source_lineage jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE decision_snapshot (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            thesis_id uuid NOT NULL REFERENCES investment_thesis(id),
            research_scoring_policy_version_id uuid NOT NULL
                REFERENCES research_scoring_policy_version(id),
            risk_policy_version_id uuid NOT NULL REFERENCES risk_policy_version(id),
            execution_policy_version_id uuid NOT NULL REFERENCES execution_policy_version(id),
            confidence_policy_version_id uuid NOT NULL REFERENCES confidence_policy_version(id),
            market_context_snapshot_id uuid REFERENCES market_context_snapshot(id),
            prompt_version text NOT NULL,
            model_version text NOT NULL,
            data_cutoff timestamptz NOT NULL,
            supersedes_decision_id uuid REFERENCES decision_snapshot(id),
            created_at timestamptz NOT NULL DEFAULT now()
        );
        ALTER TABLE portfolio_action ADD CONSTRAINT fk_portfolio_action_decision
            FOREIGN KEY (decision_id) REFERENCES decision_snapshot(id);

        CREATE TABLE decision_diff (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            decision_id uuid REFERENCES decision_snapshot(id),
            previous_decision_id uuid REFERENCES decision_snapshot(id),
            generator text NOT NULL DEFAULT 'DETERMINISTIC_CODE',
            changes jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_decision_diff_generator CHECK (generator = 'DETERMINISTIC_CODE')
        );

        CREATE TABLE tool_call (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id uuid,
            tool_name text,
            request_fingerprint text,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE agent_event (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id uuid,
            sequence bigint,
            event_type text,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (run_id, sequence)
        );
        CREATE TABLE paper_fill (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id uuid,
            quantity numeric,
            price numeric,
            currency text NOT NULL DEFAULT 'USD',
            filled_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE cash_ledger (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            portfolio_id uuid,
            amount numeric NOT NULL DEFAULT 0,
            currency text NOT NULL DEFAULT 'USD',
            entry_type text NOT NULL DEFAULT 'FIXTURE',
            occurred_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE market_bar (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            event_time timestamptz NOT NULL,
            symbol text NOT NULL,
            available_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT now(),
            close numeric,
            PRIMARY KEY (id, event_time)
        );
        CREATE TABLE option_snapshot (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            event_time timestamptz NOT NULL,
            symbol text NOT NULL,
            available_at timestamptz NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT now(),
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (id, event_time)
        );
        CREATE TABLE portfolio_nav (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            event_time timestamptz NOT NULL,
            portfolio_id uuid NOT NULL,
            nav numeric NOT NULL,
            PRIMARY KEY (id, event_time)
        );
        CREATE TABLE alert_metric (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            event_time timestamptz NOT NULL,
            symbol text NOT NULL,
            metric_name text NOT NULL,
            metric_value numeric NOT NULL,
            PRIMARY KEY (id, event_time)
        );

        CREATE FUNCTION reject_append_only_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'append-only table % rejects %', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table_name in (
        "investment_thesis",
        "decision_snapshot",
        "decision_diff",
        "paper_fill",
        "cash_ledger",
        "tool_call",
        "agent_event",
    ):
        op.execute(
            f"""
            CREATE TRIGGER enforce_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
            """
        )


def downgrade() -> None:
    for table_name in (
        "alert_metric",
        "portfolio_nav",
        "option_snapshot",
        "market_bar",
        "cash_ledger",
        "paper_fill",
        "agent_event",
        "tool_call",
        "decision_diff",
        "portfolio_action",
        "decision_snapshot",
        "market_context_snapshot",
        "research_opinion",
        "thesis_evidence_link",
        "investment_thesis",
        "confidence_policy_version",
        "execution_policy_version",
        "risk_policy_version",
        "research_scoring_policy_version",
        "claim",
        "evidence_gap",
        "evidence_item",
        "derived_metric",
        "normalized_record",
        "raw_data_object",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS reject_append_only_mutation")
    op.execute("DROP TYPE IF EXISTS portfolio_action_value")
    op.execute("DROP TYPE IF EXISTS research_opinion_value")
    op.execute("DROP TYPE IF EXISTS evidence_gap_kind")
    op.execute("DROP TYPE IF EXISTS thesis_evidence_relation")
