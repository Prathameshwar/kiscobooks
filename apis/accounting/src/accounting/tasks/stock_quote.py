"""Use the actual local ledger for quotes, with unconditional savepoint rollback."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any, TypeVar

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from accounting.models.masters import Record
from accounting.tasks.stock_ledger import StockLedger

Result = TypeVar("Result")
FLAG = "accounting_stock_quote"
REPORT_KEYS = ("accounting_reporting_touched", "accounting_reporting_before")


@event.listens_for(Session, "before_commit")
def cannot_commit_quote(db: Session) -> None:
    if db.info.get(FLAG):
        raise ConflictError("a stock quote cannot commit any physical or financial effect")


async def simulate(db: AsyncSession, work: Callable[[], Awaitable[Result]]) -> Result:
    if not db.in_transaction() or db.info.get(FLAG):
        raise ConflictError("stock quotation requires its own local company transaction")
    # Reporting's before-images are transaction-local bookkeeping, not SQL rows.
    # Restore them as well as SQL when rolling a quote's temporary rows back.
    retained = {key: copy.deepcopy(db.info[key]) for key in REPORT_KEYS if key in db.info}
    savepoint = await db.begin_nested()
    db.info[FLAG] = True
    try:
        return await work()
    finally:
        try:
            await savepoint.rollback()
        finally:
            db.info.pop(FLAG, None)
            for key in REPORT_KEYS:
                db.info.pop(key, None)
            db.info.update(retained)


def semantic_effects(ledger: StockLedger) -> dict[str, Any]:
    """Hash actual effects independently of fresh UUIDv7 allocation and clocks.

    Existing owner identities and their before-versions remain significant. Only
    identities allocated within this exact proposed transaction become tokens.
    """
    tokens = {ledger.posting.id: "$posting", ledger.posting.intent_id: "$intent"}
    counts: Counter[str] = Counter()
    for row in ledger.created:
        counts[row.__tablename__] += 1
        tokens[row.id] = f"${row.__tablename__}:{counts[row.__tablename__]}"

    def wire(value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return tokens.get(value, str(value))
        if isinstance(value, Decimal):
            return format(value, ".4f")
        if isinstance(value, dt.date | dt.datetime):
            return value.isoformat()
        if isinstance(value, tuple | list):
            return [wire(entry) for entry in value]
        if isinstance(value, dict):
            return {str(key): wire(entry) for key, entry in value.items()}
        return value

    def fields(row: Record) -> dict[str, Any]:
        return {
            column.key: wire(getattr(row, column.key))
            for column in row.__table__.columns
            if column.key not in {"created_at", "updated_at"}
        }

    return {
        "created": [{"entity": row.__tablename__, "values": fields(row)} for row in ledger.created],
        "observed": [
            {
                "entity": table,
                "id": wire(identity),
                "before_version": version,
                "values": fields(row),
            }
            for (table, identity), (row, version) in sorted(ledger.observed.items())
        ],
    }


def semantic_hash(effects: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(effects, maximum_bytes=8_388_608)).hexdigest()
