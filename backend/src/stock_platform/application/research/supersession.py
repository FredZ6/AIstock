"""Point-in-time validity for append-only research decisions."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, Connection, and_, exists, select
from sqlalchemy.dialects.postgresql import insert

from stock_platform.domain.common.time import require_aware
from stock_platform.domain.research.decision_diff import build_decision_diff
from stock_platform.infrastructure.db.models.tables import (
    decision_diff,
    decision_snapshot,
    investment_thesis,
)


def decision_is_active_at(
    decision_id: ColumnElement[object], cutoff: datetime
) -> ColumnElement[bool]:
    """Exclude decisions replaced by correction facts visible at the cutoff."""

    correction = decision_diff.alias("decision_correction")
    replacement = decision_snapshot.alias("decision_replacement")
    return and_(
        ~exists(
            select(1)
            .select_from(correction.join(replacement, correction.c.decision_id == replacement.c.id))
            .where(
                correction.c.previous_decision_id == decision_id,
                correction.c.created_at <= cutoff,
                replacement.c.available_at <= cutoff,
                replacement.c.created_at <= cutoff,
            )
        ),
        ~exists(
            select(1).where(
                replacement.c.supersedes_decision_id == decision_id,
                replacement.c.available_at <= cutoff,
                replacement.c.created_at <= cutoff,
            )
        ),
    )


def record_decision_supersession(
    connection: Connection,
    *,
    previous_decision_id: UUID,
    replacement_decision_id: UUID,
    reason: str,
    recorded_at: datetime,
) -> bool:
    """Append one deterministic correction relation; return false on redelivery."""

    timestamp = require_aware(recorded_at)
    normalized_reason = reason.strip().upper()
    if not normalized_reason:
        raise ValueError("supersession reason is required")
    if previous_decision_id == replacement_decision_id:
        raise ValueError("a decision cannot supersede itself")

    existing_replacement = connection.execute(
        select(decision_diff.c.decision_id).where(
            decision_diff.c.previous_decision_id == previous_decision_id
        )
    ).scalar_one_or_none()
    if existing_replacement is not None:
        if existing_replacement == replacement_decision_id:
            return False
        raise ValueError("decision already has a different replacement")

    def decision_fact(decision_id: UUID) -> tuple[dict[str, str], datetime, datetime]:
        row = (
            connection.execute(
                select(
                    decision_snapshot.c.id,
                    decision_snapshot.c.thesis_id,
                    decision_snapshot.c.data_cutoff,
                    decision_snapshot.c.available_at,
                    decision_snapshot.c.created_at,
                    investment_thesis.c.run_id,
                    investment_thesis.c.symbol,
                    investment_thesis.c.as_of,
                )
                .join(
                    investment_thesis,
                    decision_snapshot.c.thesis_id == investment_thesis.c.id,
                )
                .where(decision_snapshot.c.id == decision_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ValueError(f"research decision does not exist: {decision_id}")
        return (
            {
                "decision_id": str(row["id"]),
                "thesis_id": str(row["thesis_id"]),
                "run_id": str(row["run_id"]),
                "symbol": str(row["symbol"]),
                "as_of": row["as_of"].isoformat(),
                "data_cutoff": row["data_cutoff"].isoformat(),
                "available_at": row["available_at"].isoformat(),
                "created_at": row["created_at"].isoformat(),
            },
            require_aware(row["available_at"]),
            require_aware(row["created_at"]),
        )

    previous, _, _ = decision_fact(previous_decision_id)
    replacement, replacement_available_at, replacement_created_at = decision_fact(
        replacement_decision_id
    )
    if replacement["symbol"] != previous["symbol"]:
        raise ValueError("replacement decision must have the same symbol")
    if replacement["data_cutoff"] < previous["data_cutoff"]:
        raise ValueError("replacement decision cannot move the data cutoff backward")
    replacement_visible_at = max(replacement_available_at, replacement_created_at)
    if timestamp < replacement_visible_at:
        raise ValueError("replacement decision is not visible at the supersession time")
    replacement["correction_reason"] = normalized_reason

    inserted = connection.execute(
        insert(decision_diff)
        .values(
            id=uuid4(),
            decision_id=replacement_decision_id,
            previous_decision_id=previous_decision_id,
            generator="DETERMINISTIC_CODE",
            changes=build_decision_diff(previous, replacement),
            created_at=timestamp,
        )
        .on_conflict_do_nothing(index_elements=[decision_diff.c.previous_decision_id])
        .returning(decision_diff.c.id)
    ).scalar_one_or_none()
    if inserted is not None:
        return True
    # Under READ COMMITTED, a new statement sees the committed concurrent winner.
    winner = connection.execute(
        select(decision_diff.c.decision_id).where(
            decision_diff.c.previous_decision_id == previous_decision_id
        )
    ).scalar_one()
    if winner != replacement_decision_id:
        raise ValueError("decision already has a different replacement")
    return False
