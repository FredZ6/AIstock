from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

APPEND_ONLY_TABLES = {
    "investment_thesis",
    "decision_snapshot",
    "decision_diff",
    "paper_fill",
    "cash_ledger",
    "tool_call",
    "agent_event",
}


def _row_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            table_name: connection.execute(text(f"SELECT count(*) FROM {table_name}")).scalar_one()
            for table_name in APPEND_ONLY_TABLES
        }


def test_all_historical_fact_tables_have_append_only_triggers(engine: Engine) -> None:
    with engine.connect() as connection:
        protected = set(
            connection.execute(
                text(
                    """
                    SELECT c.relname
                    FROM pg_trigger t
                    JOIN pg_class c ON c.oid = t.tgrelid
                    WHERE NOT t.tgisinternal AND t.tgname = 'enforce_append_only'
                    """
                )
            ).scalars()
        )
    assert APPEND_ONLY_TABLES <= protected


def test_database_rejects_update_and_delete_for_every_append_only_table(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        for policy_table in (
            "research_scoring_policy_version",
            "risk_policy_version",
            "execution_policy_version",
            "confidence_policy_version",
        ):
            connection.execute(
                text(
                    f"INSERT INTO {policy_table} (version) VALUES ('fixture-v1') "
                    "ON CONFLICT (version) DO NOTHING"
                )
            )
        connection.execute(text("INSERT INTO investment_thesis DEFAULT VALUES"))
        connection.execute(
            text(
                """
                INSERT INTO decision_snapshot (
                    thesis_id,
                    research_scoring_policy_version_id,
                    risk_policy_version_id,
                    execution_policy_version_id,
                    confidence_policy_version_id,
                    prompt_version,
                    model_version,
                    data_cutoff
                )
                SELECT
                    (SELECT id FROM investment_thesis LIMIT 1),
                    (SELECT id FROM research_scoring_policy_version LIMIT 1),
                    (SELECT id FROM risk_policy_version LIMIT 1),
                    (SELECT id FROM execution_policy_version LIMIT 1),
                    (SELECT id FROM confidence_policy_version LIMIT 1),
                    'test-prompt',
                    'test-model',
                    now()
                """
            )
        )
        for table_name in APPEND_ONLY_TABLES - {"investment_thesis", "decision_snapshot"}:
            connection.execute(text(f"INSERT INTO {table_name} DEFAULT VALUES"))

        for operation in ("UPDATE", "DELETE"):
            for table_name in sorted(APPEND_ONLY_TABLES):
                statement = (
                    f"{operation} {table_name} SET created_at = created_at"
                    if operation == "UPDATE"
                    else f"{operation} FROM {table_name}"
                )
                savepoint = connection.begin_nested()
                try:
                    connection.execute(text(statement))
                except DBAPIError as error:
                    savepoint.rollback()
                    assert "append-only" in str(error.orig)
                else:
                    savepoint.rollback()
                    raise AssertionError(f"database allowed {operation} on {table_name}")
        transaction.rollback()


def test_append_only_verification_leaves_database_unchanged(engine: Engine) -> None:
    before = _row_counts(engine)
    test_database_rejects_update_and_delete_for_every_append_only_table(engine)
    assert _row_counts(engine) == before
