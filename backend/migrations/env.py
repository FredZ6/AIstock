import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from stock_platform.infrastructure.db.base import Base
from stock_platform.infrastructure.db.models import tables as _tables  # noqa: F401

config = context.config
default_url = "postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform"
configured_url = config.get_main_option("sqlalchemy.url")
database_url = config.attributes.get("database_url")
if database_url is None and configured_url == default_url:
    database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
_LANGGRAPH_OWNED_TABLES = frozenset(
    {"checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"}
)


def include_object(
    object_: object, name: str | None, type_: str, reflected: bool, compare_to: object | None
) -> bool:
    del object_, compare_to
    return not (
        type_ == "table" and reflected and name is not None and name in _LANGGRAPH_OWNED_TABLES
    )


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
