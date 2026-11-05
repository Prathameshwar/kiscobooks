"""Native common financial sections; no type-specific monetary document tables."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.money import AccountEntry, BillAllocation, MoneyInput, Tender

from vouchers.api.auth import Access
from vouchers.models import core as m
from vouchers.tasks.common import values


async def store(
    db: AsyncSession, current: Access, revision: m.VoucherRevision, body: MoneyInput
) -> None:
    base = {"revision_id": revision.id}
    db.add(
        m.VoucherFinancialDetail(
            **values(current), **base, schema_version=body.schema_version, purpose=body.purpose
        )
    )
    for sequence, entry in enumerate(body.accounts, 1):
        db.add(
            m.VoucherAccountDetail(
                **values(current), **base, sequence=sequence, **entry.model_dump()
            )
        )
    await db.flush()
    for sequence, tender in enumerate(body.tenders, 1):
        db.add(m.VoucherTender(**values(current), **base, sequence=sequence, **tender.model_dump()))
    await store_allocations(db, current, revision, body.allocations)


async def store_allocations(
    db: AsyncSession,
    current: Access,
    revision: m.VoucherRevision,
    allocations: tuple[BillAllocation, ...],
) -> None:
    for sequence, allocation in enumerate(allocations, 1):
        data = allocation.model_dump(exclude={"debt", "credit"})
        for name in ("debt", "credit"):
            target = getattr(allocation, name)
            data[name + "_item_id"] = target.item_id
            data[name + "_line_key"] = target.line_key
        db.add(
            m.VoucherBillInstruction(
                **values(current), revision_id=revision.id, sequence=sequence, **data
            )
        )


async def load(
    db: AsyncSession, current: Access, revision: m.VoucherRevision
) -> dict[str, Any] | None:
    header = await db.scalar(
        select(m.VoucherFinancialDetail).where(
            m.VoucherFinancialDetail.company_id == current.context.company_id,
            m.VoucherFinancialDetail.revision_id == revision.id,
        )
    )
    if header is None:
        return None
    result: dict[str, Any] = {"schema_version": header.schema_version, "purpose": header.purpose}
    for model, schema, name in (
        (m.VoucherAccountDetail, AccountEntry, "accounts"),
        (m.VoucherTender, Tender, "tenders"),
    ):
        rows = await db.scalars(
            select(model)
            .where(model.company_id == current.context.company_id, model.revision_id == revision.id)
            .order_by(model.sequence)
        )
        result[name] = [{key: getattr(row, key) for key in schema.model_fields} for row in rows]
    result["allocations"] = await load_allocations(db, current, revision)
    return MoneyInput.model_validate(result).model_dump(mode="json")


async def load_allocations(
    db: AsyncSession, current: Access, revision: m.VoucherRevision
) -> list[dict[str, Any]]:
    allocations = await db.scalars(
        select(m.VoucherBillInstruction)
        .where(
            m.VoucherBillInstruction.company_id == current.context.company_id,
            m.VoucherBillInstruction.revision_id == revision.id,
        )
        .order_by(m.VoucherBillInstruction.sequence)
    )
    return [
        {
            "allocation_key": row.allocation_key,
            "amount": row.amount,
            "currency": row.currency,
            "fx_account_id": row.fx_account_id,
            "debt": {"item_id": row.debt_item_id, "line_key": row.debt_line_key},
            "credit": {"item_id": row.credit_item_id, "line_key": row.credit_line_key},
        }
        for row in allocations
    ]
