"""Native LangGraph checkpoint lifecycle helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import Connection
from psycopg.rows import dict_row


@contextmanager
def postgres_checkpointer(database_url: str) -> Iterator[BaseCheckpointSaver[Any]]:
    """Yield a setup PostgreSQL saver using the application's database."""

    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError("LangGraph checkpoints require a PostgreSQL database URL")

    checkpoint_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    serializer = JsonPlusSerializer(allowed_msgpack_modules=True)
    with Connection.connect(
        checkpoint_url,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    ) as connection:
        saver = PostgresSaver(connection, serde=serializer)
        saver.setup()
        yield saver
