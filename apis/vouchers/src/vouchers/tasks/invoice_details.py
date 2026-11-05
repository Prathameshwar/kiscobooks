"""Native common invoice sections, with revision-scoped targets and dependencies."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.invoice import (
    InvoiceComponent,
    InvoiceInput,
    InvoiceSupply,
    InvoiceTaxContext,
)
from voucher_execution.money import Tender

from vouchers.api.auth import Access
from vouchers.models import core as m
from vouchers.models import invoice as i
from vouchers.tasks.common import values
from vouchers.tasks.financial_details import load_allocations, store_allocations


async def store(
    db: AsyncSession, current: Access, revision: m.VoucherRevision, body: InvoiceInput, *, kind: str
) -> None:
    base = {"revision_id": revision.id}
    header = body.model_dump(exclude={"supplies", "components", "tax", "tenders", "allocations"})
    db.add(
        i.VoucherInvoiceDetail(
            **values(current), **base, currency=revision.currency, **header, **body.tax.model_dump()
        )
    )
    existing = {
        row.line_key: row
        for row in await db.scalars(
            select(m.VoucherLine).where(
                m.VoucherLine.company_id == current.context.company_id,
                m.VoucherLine.revision_id == revision.id,
            )
        )
    }
    sequence = len(existing)
    supplies: dict[uuid.UUID, i.VoucherSupplyDetail] = {}
    for position, supply in enumerate(body.supplies, 1):
        line = existing.get(supply.line_key)
        if line is None:
            sequence += 1
            line = m.VoucherLine(
                **values(current),
                **base,
                line_key=supply.line_key,
                sequence=sequence,
                line_kind="ACCOUNT",
                description=supply.description,
            )
            db.add(line)
        # Invoice service descriptions are retained independently from item labels.
        data = supply.model_dump(exclude={"line_key", "description", "quantities", "tax"})
        row = i.VoucherSupplyDetail(
            **values(current),
            **base,
            line_id=line.id,
            sequence=position,
            currency=revision.currency,
            description=supply.description,
            **data,
        )
        db.add(row)
        supplies[supply.line_key] = row
        if supply.tax is not None:
            db.add(
                i.VoucherSupplyTaxContext(
                    **values(current),
                    **base,
                    supply_id=row.id,
                    sequence=position,
                    **supply.tax.model_dump(),
                )
            )
        for number, quantity in enumerate(supply.quantities, 1):
            db.add(
                i.VoucherSupplyQuantity(
                    **values(current),
                    **base,
                    supply_id=row.id,
                    sequence=number,
                    **quantity.model_dump(),
                )
            )
    charges: dict[uuid.UUID, i.VoucherChargeDetail] = {}
    for position, component in enumerate(body.components, 1):
        sequence += 1
        line = m.VoucherLine(
            **values(current),
            **base,
            line_key=component.component_key,
            sequence=sequence,
            line_kind="CHARGE",
            description=component.source_evidence,
        )
        db.add(line)
        data = component.model_dump(
            exclude={"component_key", "targets", "dependencies", "cost_targets", "tax_targets"}
        )
        if component.input_kind == "PERCENT":
            data["percentage"] = data.pop("value")
        charge = i.VoucherChargeDetail(
            **values(current),
            **base,
            line_id=line.id,
            sequence=position,
            currency=revision.currency,
            **data,
        )
        charges[component.component_key] = charge
        db.add(charge)
    await db.flush()
    for component in body.components:
        for purpose, targets in (
            ("BASIS", component.targets),
            ("STOCK_COST", component.cost_targets),
            ("TAX_BASE", component.tax_targets),
        ):
            for position, target in enumerate(targets, 1):
                db.add(
                    i.VoucherChargeTarget(
                        **values(current),
                        **base,
                        charge_id=charges[component.component_key].id,
                        supply_id=supplies[target].id,
                        purpose=purpose,
                        sequence=position,
                    )
                )
        for position, dependency in enumerate(component.dependencies, 1):
            db.add(
                i.VoucherChargeDependency(
                    **values(current),
                    **base,
                    charge_id=charges[component.component_key].id,
                    depends_on_id=charges[dependency].id,
                    sequence=position,
                )
            )
    tender_keys = list(dict.fromkeys(row.tender.line_key for row in body.tenders))
    for position, line_key in enumerate(tender_keys, 1):
        members = [row for row in body.tenders if row.tender.line_key == line_key]
        first = members[0]
        db.add(
            m.VoucherAccountDetail(
                **values(current),
                **base,
                sequence=position,
                line_key=line_key,
                account_id=first.account_id,
                source_version=first.account_version,
                side="DEBIT" if kind in {"SALES", "DEBIT_NOTE"} else "CREDIT",
                currency=revision.currency,
                amount=sum((row.tender.amount for row in members), Decimal(0)),
                exchange_rate=body.exchange_rate,
                purpose="PRINCIPAL",
                description="Invoice settlement",
                tracking="NONE",
            )
        )
    await db.flush()
    for position, entry in enumerate(body.tenders, 1):
        db.add(
            m.VoucherTender(
                **values(current), **base, sequence=position, **entry.tender.model_dump()
            )
        )
    await store_allocations(db, current, revision, body.allocations)


async def rows(
    db: AsyncSession, current: Access, revision: m.VoucherRevision, model: Any
) -> list[Any]:
    return list(
        await db.scalars(
            select(model)
            .where(model.company_id == current.context.company_id, model.revision_id == revision.id)
            .order_by(model.sequence)
        )
    )


async def load(
    db: AsyncSession, current: Access, revision: m.VoucherRevision
) -> dict[str, Any] | None:
    header = await db.scalar(
        select(i.VoucherInvoiceDetail).where(
            i.VoucherInvoiceDetail.company_id == current.context.company_id,
            i.VoucherInvoiceDetail.revision_id == revision.id,
        )
    )
    if header is None:
        return None
    result = {
        key: getattr(header, key)
        for key in InvoiceInput.model_fields
        if key not in {"supplies", "components", "tax", "tenders", "allocations"}
    }
    result["tax"] = {key: getattr(header, key) for key in InvoiceTaxContext.model_fields}
    lines = {row.id: row for row in await rows(db, current, revision, m.VoucherLine)}
    supplies = await rows(db, current, revision, i.VoucherSupplyDetail)
    quantities = await rows(db, current, revision, i.VoucherSupplyQuantity)
    tax_contexts = {
        row.supply_id: {key: getattr(row, key) for key in InvoiceTaxContext.model_fields}
        for row in await rows(db, current, revision, i.VoucherSupplyTaxContext)
    }
    result["supplies"] = [
        {
            key: getattr(row, key)
            for key in InvoiceSupply.model_fields
            if key not in {"line_key", "quantities", "tax"}
        }
        | {
            "line_key": lines[row.line_id].line_key,
            "tax": tax_contexts.get(row.id),
            "quantities": [
                {"basis": q.basis, "quantity": q.quantity, "unit_id": q.unit_id}
                for q in quantities
                if q.supply_id == row.id
            ],
        }
        for row in supplies
    ]
    supply_keys = {row.id: lines[row.line_id].line_key for row in supplies}
    charges = await rows(db, current, revision, i.VoucherChargeDetail)
    charge_keys = {row.id: lines[row.line_id].line_key for row in charges}
    targets = await rows(db, current, revision, i.VoucherChargeTarget)
    dependencies = await rows(db, current, revision, i.VoucherChargeDependency)
    result["components"] = [
        {
            key: getattr(row, key)
            for key in InvoiceComponent.model_fields
            if key
            not in {
                "component_key",
                "targets",
                "cost_targets",
                "tax_targets",
                "dependencies",
                "value",
            }
        }
        | {
            "component_key": charge_keys[row.id],
            "value": row.percentage if row.input_kind == "PERCENT" else row.value,
            "targets": [
                supply_keys[t.supply_id]
                for t in targets
                if t.charge_id == row.id and t.purpose == "BASIS"
            ],
            "cost_targets": [
                supply_keys[t.supply_id]
                for t in targets
                if t.charge_id == row.id and t.purpose == "STOCK_COST"
            ],
            "tax_targets": [
                supply_keys[t.supply_id]
                for t in targets
                if t.charge_id == row.id and t.purpose == "TAX_BASE"
            ],
            "dependencies": [
                charge_keys[d.depends_on_id] for d in dependencies if d.charge_id == row.id
            ],
        }
        for row in charges
    ]
    accounts = {
        row.line_key: row for row in await rows(db, current, revision, m.VoucherAccountDetail)
    }
    result["tenders"] = [
        {
            "account_id": accounts[row.line_key].account_id,
            "account_version": accounts[row.line_key].source_version,
            "tender": {key: getattr(row, key) for key in Tender.model_fields},
        }
        for row in await rows(db, current, revision, m.VoucherTender)
    ]
    result["allocations"] = await load_allocations(db, current, revision)
    return InvoiceInput.model_validate(result).model_dump(mode="json")
