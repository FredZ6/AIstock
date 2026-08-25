import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, inspect, select, text, update
from sqlalchemy.exc import DBAPIError
from stock_platform.application.ingestion.concept_mapping import ConceptMappingRegistry
from stock_platform.application.ingestion.normalizers.sec import SecFiling
from stock_platform.application.ingestion.raw_writer import RawWriter
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.ingestion.models import FeedType
from stock_platform.domain.market_data.concepts import FinancialFactInput
from stock_platform.infrastructure.db.models.tables import (
    financial_fact,
    normalized_record,
    raw_data_object,
    sec_filing,
    security_identifier_version,
)
from stock_platform.infrastructure.db.security_seed import SECURITY_MASTER, seed_security_master
from stock_platform.infrastructure.ingestion.fact_store import (
    PostgresFinancialFactStore,
    PostgresSecFactStore,
)
from stock_platform.infrastructure.providers.base import ProviderRecord
from stock_platform.infrastructure.providers.sec import (
    PostgresSecIdentityResolver,
    SecFilingRegime,
)


def _migrate(database_url: str) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def test_all_watchlist_securities_resolve_cik_and_filing_regime_point_in_time(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    as_of = datetime(2026, 8, 25, tzinfo=UTC)
    with engine.begin() as connection:
        seed_security_master(connection)
        resolver = PostgresSecIdentityResolver(connection)
        identities = {
            item["symbol"]: resolver.resolve(Symbol(item["symbol"]), as_of)
            for item in SECURITY_MASTER
        }

    assert len(identities) == 11
    assert all(identity is not None and len(identity.cik) == 10 for identity in identities.values())
    assert identities["NVDA"] is not None
    assert identities["TSM"] is not None
    assert identities["NVDA"].regime is SecFilingRegime.US_DOMESTIC
    assert identities["TSM"].regime is SecFilingRegime.FOREIGN_PRIVATE_ISSUER
    engine.dispose()


def test_sec_filing_is_append_only_idempotent_and_links_amendment_to_raw_document(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    original_accepted = datetime(2026, 8, 20, 16, 1, 2, tzinfo=UTC)
    amendment_accepted = datetime(2026, 8, 21, 17, 2, 3, tzinfo=UTC)
    with engine.begin() as connection:
        seed_security_master(connection)
        security_id = connection.execute(
            select(security_identifier_version.c.security_id).where(
                security_identifier_version.c.identifier_value == "NVDA"
            )
        ).scalar_one()
        raw_id = connection.execute(
            insert(raw_data_object)
            .values(
                provider="SEC",
                feed_type="filings",
                event_time=original_accepted,
                available_at=original_accepted,
                ingested_at=amendment_accepted,
                content_hash="a" * 64,
                raw_object_key=f"live/SEC/filings/{'a' * 64}.json",
            )
            .returning(raw_data_object.c.id)
        ).scalar_one()
        normalized_id = connection.execute(
            insert(normalized_record)
            .values(
                raw_data_object_id=raw_id,
                record_type="sec_filing",
                record_key="NVDA",
                normalization_version="sec-filings-v1",
                payload={"symbol": "NVDA"},
            )
            .returning(normalized_record.c.id)
        ).scalar_one()
        document_raw_id = connection.execute(
            insert(raw_data_object)
            .values(
                provider="SEC",
                feed_type="filing_document",
                event_time=original_accepted,
                available_at=original_accepted,
                ingested_at=amendment_accepted,
                content_hash="b" * 64,
                raw_object_key=f"live/SEC/filing_document/{'b' * 64}.html",
            )
            .returning(raw_data_object.c.id)
        ).scalar_one()
        store = PostgresSecFactStore(connection)
        original = SecFiling.from_values(
            symbol="NVDA",
            cik="1045810",
            accession_number="0001045810-26-000042",
            form="10-Q",
            filing_date="2026-08-20",
            report_date="2026-07-31",
            accepted_at=original_accepted,
            primary_document="nvda-20260731.htm",
            description="Quarterly report",
        )
        amendment = SecFiling.from_values(
            symbol="NVDA",
            cik="1045810",
            accession_number="0001045810-26-000043",
            form="10-Q/A",
            filing_date="2026-08-21",
            report_date="2026-07-31",
            accepted_at=amendment_accepted,
            primary_document="nvda-20260731x10qa.htm",
            description="Quarterly report amendment",
        )

        original_id = store.persist_filing(
            security_id=security_id,
            raw_id=raw_id,
            normalized_id=normalized_id,
            document_raw_id=document_raw_id,
            filing=original,
        )
        assert (
            store.persist_filing(
                security_id=security_id,
                raw_id=raw_id,
                normalized_id=normalized_id,
                document_raw_id=document_raw_id,
                filing=original,
            )
            == original_id
        )
        amendment_id = store.persist_filing(
            security_id=security_id,
            raw_id=raw_id,
            normalized_id=normalized_id,
            document_raw_id=document_raw_id,
            filing=amendment,
        )

        rows = (
            connection.execute(select(sec_filing).order_by(sec_filing.c.accepted_at))
            .mappings()
            .all()
        )
        assert connection.execute(select(func.count()).select_from(sec_filing)).scalar_one() == 2
        assert rows[0]["id"] == original_id
        assert rows[1]["id"] == amendment_id
        assert rows[1]["supersedes_id"] == original_id
        assert rows[1]["available_at"] == amendment_accepted
        assert rows[1]["document_raw_data_object_id"] == document_raw_id
    with engine.connect() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(update(sec_filing).values(description="mutated"))
    with engine.connect() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(text("DELETE FROM sec_filing"))
    engine.dispose()


def test_sec_schema_contains_typed_filing_but_no_redundant_document_table(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    inspector = inspect(engine)

    assert "sec_filing" in inspector.get_table_names()
    assert "sec_document" not in inspector.get_table_names()
    assert {
        "normalized_record_id",
        "document_raw_data_object_id",
        "accession_number",
        "accepted_at",
        "available_at",
        "supersedes_id",
    } <= {column["name"] for column in inspector.get_columns("sec_filing")}
    engine.dispose()


def test_sec_document_bytes_are_persisted_raw_without_a_parallel_typed_document(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    now = datetime(2026, 8, 25, tzinfo=UTC)
    body = b"<html><body>redacted filing</body></html>"
    content_hash = hashlib.sha256(body).hexdigest()

    class RecordingRawStore:
        writes: list[tuple[str, bytes, str]] = []

        def put(self, object_key: str, content: bytes, content_type: str) -> None:
            self.writes.append((object_key, content, content_type))

    raw_store = RecordingRawStore()
    record = ProviderRecord(
        symbol=Symbol("NVDA"),
        feed_type=FeedType.FILING_SECTIONS,
        provider="SEC",
        event_time=now,
        available_at=now,
        ingested_at=now,
        content_hash=content_hash,
        raw_object_key=f"live/SEC/filing_document/{content_hash}.html",
        payload={"accession_number": "0001045810-26-000042"},
    )

    raw_id = RawWriter(engine=engine, raw_store=raw_store).write_artifact(
        record=record,
        raw_content=body,
        content_type="text/html",
    )

    assert raw_store.writes == [(record.raw_object_key, body, "text/html")]
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(raw_data_object.c.id).where(raw_data_object.c.id == raw_id)
            ).scalar_one()
            == raw_id
        )
    engine.dispose()


def test_financial_fact_versions_are_decimal_append_only_and_point_in_time(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    first_available = datetime(2026, 8, 20, 16, 1, 2, tzinfo=UTC)
    revised_available = datetime(2026, 8, 21, 17, 2, 3, tzinfo=UTC)
    registry = ConceptMappingRegistry.load(Path("backend/config/financial_concepts_v1.yaml"))
    with engine.begin() as connection:
        seed_security_master(connection)
        security_id = connection.execute(
            select(security_identifier_version.c.security_id).where(
                security_identifier_version.c.identifier_value == "NVDA"
            )
        ).scalar_one()
        raw_ids: list[UUID] = []
        normalized_ids: list[UUID] = []
        for index, available_at in enumerate((first_available, revised_available)):
            raw_id = connection.execute(
                insert(raw_data_object)
                .values(
                    provider="SEC",
                    feed_type="company_facts",
                    event_time=available_at,
                    available_at=available_at,
                    ingested_at=revised_available,
                    content_hash=str(index + 3) * 64,
                    raw_object_key=f"live/SEC/company_facts/{str(index + 3) * 64}.json",
                )
                .returning(raw_data_object.c.id)
            ).scalar_one()
            normalized_id = connection.execute(
                insert(normalized_record)
                .values(
                    raw_data_object_id=raw_id,
                    record_type="financial_fact",
                    record_key=f"NVDA:revenue:{index}",
                    normalization_version="sec-company-facts-v1",
                    payload={"concept": "Revenues"},
                )
                .returning(normalized_record.c.id)
            ).scalar_one()
            raw_ids.append(raw_id)
            normalized_ids.append(normalized_id)

        store = PostgresFinancialFactStore(connection)
        first = registry.map_fact(
            FinancialFactInput.from_values(
                taxonomy="us-gaap",
                concept="Revenues",
                value="44000000000.10",
                unit="USD",
                currency="USD",
                period_start="2026-01-01",
                period_end="2026-06-30",
                accession_number="0001045810-26-000042",
            )
        )
        revised = registry.map_fact(
            FinancialFactInput.from_values(
                taxonomy="us-gaap",
                concept="Revenues",
                value="44000000001.10",
                unit="USD",
                currency="USD",
                period_start="2026-01-01",
                period_end="2026-06-30",
                accession_number="0001045810-26-000043",
            )
        )
        with pytest.raises(ValueError, match="SEC filing lineage is required"):
            store.persist_fact(
                security_id=security_id,
                raw_id=raw_ids[0],
                normalized_id=normalized_ids[0],
                available_at=first_available,
                result=first,
            )
        filing_ids: list[UUID] = []
        for index, (accession, available_at) in enumerate(
            (
                ("0001045810-26-000042", first_available),
                ("0001045810-26-000043", revised_available),
            )
        ):
            filing_ids.append(
                connection.execute(
                    insert(sec_filing)
                    .values(
                        security_id=security_id,
                        raw_data_object_id=raw_ids[index],
                        normalized_record_id=normalized_ids[index],
                        document_raw_data_object_id=raw_ids[index],
                        provider="SEC",
                        cik="0001045810",
                        accession_number=accession,
                        form="10-Q" if index == 0 else "10-Q/A",
                        base_form="10-Q",
                        filing_date=available_at.date(),
                        report_date=datetime(2026, 6, 30).date(),
                        accepted_at=available_at,
                        available_at=available_at,
                        primary_document=f"filing-{index}.htm",
                        description="",
                        is_amendment=index == 1,
                        supersedes_id=filing_ids[0] if index == 1 else None,
                        payload={},
                    )
                    .returning(sec_filing.c.id)
                ).scalar_one()
            )
        first_id = store.persist_fact(
            security_id=security_id,
            raw_id=raw_ids[0],
            normalized_id=normalized_ids[0],
            available_at=first_available,
            result=first,
        )
        assert (
            store.persist_fact(
                security_id=security_id,
                raw_id=raw_ids[0],
                normalized_id=normalized_ids[0],
                available_at=first_available,
                result=first,
            )
            == first_id
        )
        revised_id = store.persist_fact(
            security_id=security_id,
            raw_id=raw_ids[1],
            normalized_id=normalized_ids[1],
            available_at=revised_available,
            result=revised,
        )

        rows = (
            connection.execute(select(financial_fact).order_by(financial_fact.c.available_at))
            .mappings()
            .all()
        )
        assert rows[0]["id"] == first_id
        assert rows[1]["id"] == revised_id
        assert rows[1]["supersedes_id"] == first_id
        assert rows[0]["sec_filing_id"] == filing_ids[0]
        assert rows[1]["sec_filing_id"] == filing_ids[1]
        assert rows[0]["value"] == Decimal("44000000000.10")
        visible = (
            connection.execute(
                select(financial_fact.c.id).where(
                    financial_fact.c.available_at <= first_available,
                    financial_fact.c.period_end <= first_available.date(),
                )
            )
            .scalars()
            .all()
        )
        assert visible == [first_id]
    with engine.connect() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(update(financial_fact).values(value=Decimal("0")))
    engine.dispose()
