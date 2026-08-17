from collections.abc import Iterable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

REQUIRED_TABLES = {
    "raw_data_object",
    "normalized_record",
    "derived_metric",
    "evidence_item",
    "evidence_gap",
    "claim",
    "investment_thesis",
    "thesis_evidence_link",
    "research_opinion",
    "portfolio_action",
    "decision_snapshot",
    "decision_diff",
    "market_context_snapshot",
    "research_scoring_policy_version",
    "risk_policy_version",
    "execution_policy_version",
    "confidence_policy_version",
    "tool_call",
    "agent_event",
    "paper_fill",
    "cash_ledger",
}


def _foreign_key_targets(engine: Engine, table_name: str) -> set[tuple[str, str, str]]:
    result: set[tuple[str, str, str]] = set()
    for foreign_key in inspect(engine).get_foreign_keys(table_name):
        referred_table = foreign_key["referred_table"]
        for local, remote in zip(
            foreign_key["constrained_columns"], foreign_key["referred_columns"], strict=True
        ):
            result.add((local, referred_table, remote))
    return result


def _enum_values(engine: Engine, enum_name: str) -> set[str]:
    with engine.connect() as connection:
        rows: Iterable[str] = connection.execute(
            text(
                """
                SELECT enumlabel
                FROM pg_enum
                JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
                WHERE pg_type.typname = :enum_name
                """
            ),
            {"enum_name": enum_name},
        ).scalars()
        return set(rows)


def test_v02_core_tables_exist(engine: Engine) -> None:
    assert REQUIRED_TABLES <= set(inspect(engine).get_table_names())


def test_complete_lineage_foreign_keys_exist(engine: Engine) -> None:
    expected = {
        "normalized_record": ("raw_data_object_id", "raw_data_object", "id"),
        "derived_metric": ("normalized_record_id", "normalized_record", "id"),
        "evidence_item": ("derived_metric_id", "derived_metric", "id"),
        "claim": ("evidence_id", "evidence_item", "id"),
        "thesis_evidence_link": ("evidence_id", "evidence_item", "id"),
        "decision_snapshot": ("thesis_id", "investment_thesis", "id"),
    }
    for table_name, foreign_key in expected.items():
        assert foreign_key in _foreign_key_targets(engine, table_name)


def test_thesis_uses_normalized_evidence_links(engine: Engine) -> None:
    thesis_columns = {column["name"] for column in inspect(engine).get_columns("investment_thesis")}
    assert "evidence_ids" not in thesis_columns
    link_columns = {
        column["name"] for column in inspect(engine).get_columns("thesis_evidence_link")
    }
    assert {"thesis_id", "evidence_id", "relation", "weight", "rationale"} <= link_columns
    assert _enum_values(engine, "thesis_evidence_relation") == {
        "SUPPORTS",
        "CONTRADICTS",
        "CONTEXT",
    }


def test_gap_opinion_and_action_enums_are_exact_and_independent(engine: Engine) -> None:
    assert _enum_values(engine, "evidence_gap_kind") == {
        "UNKNOWN",
        "MISSING",
        "UNAVAILABLE",
        "CONFLICTED",
    }
    assert _enum_values(engine, "research_opinion_value") == {
        "BULLISH",
        "NEUTRAL",
        "BEARISH",
        "ABSTAIN",
    }
    assert _enum_values(engine, "portfolio_action_value") == {
        "ENTER",
        "ADD",
        "HOLD",
        "REDUCE",
        "EXIT",
        "NO_ACTION",
    }


def test_decision_pins_four_policies_and_replay_inputs(engine: Engine) -> None:
    columns = {
        column["name"]: column for column in inspect(engine).get_columns("decision_snapshot")
    }
    required = {
        "research_scoring_policy_version_id",
        "risk_policy_version_id",
        "execution_policy_version_id",
        "confidence_policy_version_id",
        "prompt_version",
        "model_version",
        "data_cutoff",
    }
    assert required <= columns.keys()
    assert all(columns[name]["nullable"] is False for name in required)


def test_external_data_and_quality_dimensions_are_raw_facts(engine: Engine) -> None:
    raw_columns = {column["name"] for column in inspect(engine).get_columns("raw_data_object")}
    assert {
        "provider",
        "feed_type",
        "event_time",
        "available_at",
        "ingested_at",
        "content_hash",
        "raw_object_key",
    } <= raw_columns
    evidence_columns = {column["name"] for column in inspect(engine).get_columns("evidence_item")}
    assert {"freshness", "coverage", "provider", "delay", "conflict"} <= evidence_columns
    assert "quality_grade" not in evidence_columns


def test_normalized_records_pin_the_normalization_version(engine: Engine) -> None:
    columns = {
        column["name"]: column for column in inspect(engine).get_columns("normalized_record")
    }

    assert columns["normalization_version"]["nullable"] is False


def test_external_market_data_has_complete_provenance_and_raw_lineage(engine: Engine) -> None:
    required = {
        "raw_data_object_id",
        "provider",
        "feed_type",
        "event_time",
        "available_at",
        "ingested_at",
        "content_hash",
        "raw_object_key",
    }
    for table_name in ("market_bar", "option_snapshot"):
        columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
        assert required <= columns
        assert (
            "raw_data_object_id",
            "raw_data_object",
            "id",
        ) in _foreign_key_targets(engine, table_name)


def test_timescale_hypertables_exist(engine: Engine) -> None:
    with engine.connect() as connection:
        hypertables = set(
            connection.execute(
                text("SELECT hypertable_name FROM timescaledb_information.hypertables")
            ).scalars()
        )
    assert {"market_bar", "option_snapshot", "portfolio_nav", "alert_metric"} <= hypertables
