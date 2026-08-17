from stock_platform.infrastructure.db.base import Base
from stock_platform.infrastructure.db.models.schema import CORE_TABLES


def test_authoritative_tables_are_registered_in_sqlalchemy_metadata() -> None:
    assert CORE_TABLES <= frozenset(Base.metadata.tables)
