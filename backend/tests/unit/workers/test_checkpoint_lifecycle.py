from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from stock_platform.workers import portfolio_tasks, research_tasks


@pytest.mark.parametrize(
    ("module", "execute"),
    (
        (research_tasks, research_tasks.execute_research_run),
        (portfolio_tasks, portfolio_tasks.execute_portfolio_run),
    ),
)
def test_worker_prepares_checkpointer_before_opening_business_transaction(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    execute: Any,
) -> None:
    lifecycle: list[str] = []
    checkpointer = object()

    @contextmanager
    def fake_checkpointer(database_url: str) -> Iterator[object]:
        assert database_url == "postgresql+psycopg://checkpoint-test"
        lifecycle.append("checkpoint.enter")
        yield checkpointer
        lifecycle.append("checkpoint.exit")

    def fake_execute_run(*args: Any, **kwargs: Any) -> bool:
        del args, kwargs
        lifecycle.append("business.execute")
        assert lifecycle == ["checkpoint.enter", "business.execute"]
        return True

    monkeypatch.setattr(module, "postgres_checkpointer", fake_checkpointer)
    monkeypatch.setattr(module, "execute_run", fake_execute_run)

    assert execute(
        "postgresql+psycopg://checkpoint-test",
        "7ab9fdd8-ab7e-4322-842a-842ff1c2d626",
    )
    assert lifecycle == ["checkpoint.enter", "business.execute", "checkpoint.exit"]
