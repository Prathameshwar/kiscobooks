"""Offline, company-fenced stock projection recovery from immutable owner history.

Preview is read-only. Apply requires the exact preview generation and digest,
refuses pending money work, and reconciles physical state and GL before commit.
This is an operator mechanism, never a public balance-authoring endpoint. It
repairs retained projections; missing structural/history rows require reviewed
recovery, rather than invented movements, cost, currency or foreign keys.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.models import stock as s
from accounting.models.masters import AccountingSetup, Record
from accounting.models.voucher_money import VoucherMoneyIntent
from accounting.tasks.stock_claim_reconciliation import origin_history, source_history
from accounting.tasks.stock_ordering import assert_committed, committed_generation, generation
from accounting.tasks.stock_projection_history import layer_remaining, origin_remaining
from accounting.tasks.stock_reconciliation import assert_physical, assert_value_control
from accounting.tasks.stock_repair_evidence import assert_history
from accounting.tasks.stock_totals import total
from accounting.tasks.stock_unit_reconciliation import unit_history

PAGE = 200
MAXIMUM_ROWS = 1_000_000
MAXIMUM_CHANGES = 10_000


def wire(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, uuid.UUID | Decimal | dt.date) else value
        for key, value in values.items()
    }


@dataclass(frozen=True)
class Change:
    row: Record
    before: dict[str, Any]
    after: dict[str, Any]


@dataclass(frozen=True)
class Preview:
    setup: AccountingSetup
    digest: str
    changes: tuple[Change, ...]
    examined: int


def expectations(company: uuid.UUID) -> list[tuple[type[Record], dict[str, Any]]]:
    def sum_for(model: type[Record], column: Any, identity: Any) -> Any:
        return (
            select(total(column))
            .where(model.company_id == company, identity)
            .correlate_except(model)
            .scalar_subquery()
        )

    def last(column: Any) -> Any:
        return (
            select(column)
            .select_from(s.StockMovement)
            .join(s.StockPosting, s.StockPosting.id == s.StockMovement.posting_id)
            .join(s.StockCostPoolEvent, s.StockCostPoolEvent.movement_id == s.StockMovement.id)
            .where(
                s.StockMovement.company_id == company,
                s.StockPosting.company_id == company,
                s.StockMovement.pool_id == s.StockCostPool.id,
            )
            .order_by(generation(s.StockPosting).desc(), s.StockMovement.id.desc())
            .limit(1)
            .correlate(s.StockCostPool)
            .scalar_subquery()
        )

    return [
        (
            s.StockBalance,
            {
                "quantity": sum_for(
                    s.StockMovement,
                    s.StockMovement.quantity,
                    s.StockMovement.position_id == s.StockBalance.position_id,
                )
            },
        ),
        (s.StockOriginBalance, {"quantity": origin_remaining(company)}),
        (
            s.StockCostPool,
            {
                "quantity": sum_for(
                    s.StockMovement,
                    s.StockMovement.quantity,
                    s.StockMovement.pool_id == s.StockCostPool.id,
                ),
                "value": sum_for(
                    s.StockValueEntry,
                    s.StockValueEntry.amount,
                    s.StockValueEntry.pool_id == s.StockCostPool.id,
                ),
                "last_stock_date": last(s.StockPosting.stock_date),
                "last_posting_id": last(s.StockPosting.id),
                "method": func.coalesce(last(s.StockCostPoolEvent.method), s.StockCostPool.method),
            },
        ),
        (
            s.StockCostLayer,
            {
                "remaining_quantity": layer_remaining(company),
                "remaining_value": layer_remaining(company, value=True),
            },
        ),
        (
            s.StockSourceClaim,
            {
                "quantity": source_history(company, s.StockClaimAllocation.quantity),
                "value": source_history(company, s.StockClaimAllocation.value),
            },
        ),
        (s.StockOriginClaim, {"quantity": origin_history(company)}),
    ]


async def preview(db: AsyncSession, tenant: uuid.UUID, company: uuid.UUID) -> Preview:
    """Caller owns the transaction; the company lock fences every native writer."""
    setup = await db.scalar(
        select(AccountingSetup).where(AccountingSetup.company_id == company).with_for_update()
    )
    if setup is None or setup.tenant_id != tenant:
        raise ConflictError("stock repair requires this tenant's initialized company")
    pending = await db.scalar(
        select(VoucherMoneyIntent.id)
        .where(VoucherMoneyIntent.company_id == company, VoucherMoneyIntent.status == "PREPARED")
        .limit(1)
    )
    if pending:
        raise ConflictError("reconcile prepared executions before stock projection repair")
    await assert_committed(db, company)
    examined = 0
    changes: list[Change] = []
    checksum = hashlib.sha256(
        canonical_json(
            {
                "tenant_id": str(tenant),
                "company_id": str(company),
                "generation": setup.generation,
            }
        )
    )

    async def inspect(query: Select[Any], model: type[Record], fields: list[str]) -> None:
        nonlocal examined
        after: uuid.UUID | None = None
        while True:
            page = query.where(model.id > after) if after else query
            rows = (await db.execute(page.order_by(model.id).limit(PAGE))).all()
            if not rows:
                return
            for selected in rows:
                row = selected[0]
                examined += 1
                if examined > MAXIMUM_ROWS:
                    raise ConflictError("stock repair exceeds its offline rehearsal bound")
                before = {key: getattr(row, key) for key in fields}
                desired = dict(zip(fields, selected[1:], strict=True))
                checksum.update(
                    canonical_json(
                        {
                            "table": model.__tablename__,
                            "id": str(row.id),
                            "version": row.row_version,
                            "before": wire(before),
                            "after": wire(desired),
                        }
                    )
                )
                if before != desired:
                    changes.append(Change(row, before, desired))
                    if len(changes) > MAXIMUM_CHANGES:
                        raise ConflictError("stock repair requires a reviewed large recovery")
            after = rows[-1][0].id

    for model, fields in expectations(company):
        query = select(model, *(value.label(key) for key, value in fields.items())).where(
            model.company_id == company
        )
        await inspect(query, model, list(fields))
    units = unit_history(company)
    await inspect(
        select(s.StockUnitPosition, units.c.position_id, units.c.origin_id, units.c.movement_id)
        .join(units, units.c.unit_id == s.StockUnitPosition.unit_id)
        .where(s.StockUnitPosition.company_id == company),
        s.StockUnitPosition,
        ["position_id", "origin_id", "last_movement_id"],
    )
    # Validate complete production receipt bindings in bounded pages, not just their dates.
    after_posting: uuid.UUID | None = None
    while True:
        posting_query = select(s.StockPosting).where(s.StockPosting.company_id == company)
        if after_posting:
            posting_query = posting_query.where(s.StockPosting.id > after_posting)
        postings = list(await db.scalars(posting_query.order_by(s.StockPosting.id).limit(PAGE)))
        if not postings:
            break
        for posting in postings:
            await committed_generation(db, posting)
            await assert_history(db, posting)
            examined += 1
            if examined > MAXIMUM_ROWS:
                raise ConflictError("stock repair exceeds its offline rehearsal bound")
        after_posting = postings[-1].id
    return Preview(setup, checksum.hexdigest(), tuple(changes), examined)


async def apply(
    db: AsyncSession,
    tenant: uuid.UUID,
    company: uuid.UUID,
    *,
    expected_generation: int,
    expected_digest: str,
    reason: str,
) -> Preview:
    if not 3 <= len(reason.strip()) <= 500:
        raise ConflictError("stock repair requires a bounded operator reason")
    plan = await preview(db, tenant, company)
    if plan.setup.generation != expected_generation or plan.digest != expected_digest:
        raise ConflictError("stock changed since the repair preview; review a fresh preview")
    for change in plan.changes:
        for key, value in change.after.items():
            setattr(change.row, key, value)
        change.row.row_version += 1
    await db.flush()
    await assert_physical(db, company)
    await assert_value_control(db, company)
    if plan.changes:
        plan.setup.generation += 1
        event = "accounting.stock_projection.rebuild"
        emit(
            db,
            tenant_id=tenant,
            aggregate_type="accounting.stock_projection",
            aggregate_id=plan.setup.id,
            event_type=event,
            payload=audit_payload(
                action=event,
                category="system",
                entity_type="accounting.stock_projection",
                entity_id=plan.setup.id,
                actor_user_id=None,
                company_id=company,
                reason=reason.strip(),
            )
            | {
                "actor_type": "system",
                "context": {
                    "projection_digest": plan.digest,
                    "repaired_rows": len(plan.changes),
                    "generation": plan.setup.generation,
                },
            },
        )
        await db.flush()
    return plan
