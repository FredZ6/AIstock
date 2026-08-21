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
    "risk_decision",
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
        portfolio_id = connection.execute(text("SELECT gen_random_uuid()")).scalar_one()
        order_id = connection.execute(text("SELECT gen_random_uuid()")).scalar_one()
        risk_decision_id = connection.execute(text("SELECT gen_random_uuid()")).scalar_one()
        transaction_id = connection.execute(text("SELECT gen_random_uuid()")).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO risk_decision (
                    id, proposal_id, research_decision_id, portfolio_id, symbol, status,
                    requested_weight, approved_weight, current_weight, approved_delta,
                    reference_nav, reference_price, max_order_quantity,
                    risk_policy_version_id, decided_at, market_context_snapshot_id
                ) VALUES (
                    :risk_decision_id, :risk_decision_id,
                    (SELECT id FROM decision_snapshot LIMIT 1),
                    :portfolio_id, 'FIXTURE', 'APPROVED', 1, 1, 0, 1, 1, 1, 1,
                    (SELECT id FROM risk_policy_version LIMIT 1),
                    now() - interval '1 minute',
                    '00000000-0000-0000-0000-000000000016'::uuid
                )
                """
            ),
            {"portfolio_id": portfolio_id, "risk_decision_id": risk_decision_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO order_intent (
                    id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved, risk_decision_id
                ) VALUES (
                    :order_id, :portfolio_id, 'FIXTURE', 'BUY', 1,
                    (SELECT decided_at FROM risk_decision WHERE id = :risk_decision_id),
                    (SELECT id FROM execution_policy_version LIMIT 1), true,
                    :risk_decision_id
                )
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "order_id": order_id,
                "risk_decision_id": risk_decision_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO paper_order (
                    id, order_intent_id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved, status
                )
                SELECT id, id, portfolio_id, symbol, side, quantity, decision_time,
                       execution_policy_version_id, risk_approved, 'FILLED'
                FROM order_intent WHERE id = :order_id
                """
            ),
            {"order_id": order_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO paper_fill (
                    order_id, portfolio_id, symbol, side, quantity, price, fee, currency,
                    filled_at, source_bar_time, execution_policy_version_id, idempotency_key
                ) VALUES (
                    :order_id, :portfolio_id, 'FIXTURE', 'BUY', 1, 1, 0, 'USD', now(), now(),
                    (SELECT id FROM execution_policy_version LIMIT 1),
                    'append-only-fill:' || :order_id
                )
                """
            ),
            {"portfolio_id": portfolio_id, "order_id": order_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO cash_ledger (
                    portfolio_id, amount, currency, entry_type, occurred_at, transaction_id,
                    source_id, account, debit, credit, idempotency_key
                ) VALUES
                (
                    :portfolio_id, 1, 'USD', 'ASSET:CASH', now(), :transaction_id,
                    :transaction_id, 'ASSET:CASH', 1, 0,
                    'append-only-ledger:cash:' || :transaction_id
                ),
                (
                    :portfolio_id, -1, 'USD', 'EQUITY:OPENING_BALANCE', now(), :transaction_id,
                    :transaction_id, 'EQUITY:OPENING_BALANCE', 0, 1,
                    'append-only-ledger:equity:' || :transaction_id
                )
                """
            ),
            {"portfolio_id": portfolio_id, "transaction_id": transaction_id},
        )
        for table_name in APPEND_ONLY_TABLES - {
            "investment_thesis",
            "decision_snapshot",
            "paper_fill",
            "cash_ledger",
            "risk_decision",
        }:
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
