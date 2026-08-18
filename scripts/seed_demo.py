"""Idempotently seed the frozen M1 fixture catalog into MinIO and PostgreSQL."""

from sqlalchemy import create_engine

from stock_platform.infrastructure.providers.fixture.loader import FixtureCatalog
from stock_platform.infrastructure.providers.object_store import MinioRawObjectStore
from stock_platform.settings import Settings


def main() -> None:
    settings = Settings()
    if not settings.fixture_mode:
        raise RuntimeError("the demo seed is only available in fixture/test mode")
    catalog = FixtureCatalog.load_default()
    store = MinioRawObjectStore.from_settings(settings)
    object_count = catalog.seed_object_store(store)
    engine = create_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            inserted_count = catalog.seed_database(connection)
    finally:
        engine.dispose()
    print(
        f"Fixture mode seeded {object_count} raw objects and "
        f"{inserted_count} new normalized records (version fixture-m1-v1)."
    )


if __name__ == "__main__":
    main()
