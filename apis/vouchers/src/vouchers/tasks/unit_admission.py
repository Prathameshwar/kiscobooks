"""Admission from indexed signed local facts inside the company writer guard."""

import uuid
from fractions import Fraction

from billing_platform.errors import ConflictError, ValidationFailedError
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.quantity import QuantityCapture

from vouchers.api.auth import Access
from vouchers.domain.unit_admission import admit_quantity, admit_role
from vouchers.models.core import VoucherMasterEvidence
from vouchers.models.unit_sources import VoucherItemUnitProjection
from vouchers.schemas.documents import VoucherInput
from vouchers.schemas.sources import ItemUnitFacts, UnitMasterFacts


async def validate_units(
    db: AsyncSession, current: Access, body: VoucherInput, kind: str | None
) -> None:
    if not body.lines:
        return
    company, ids = current.context.company_id, {line.item.item_id for line in body.lines}
    date = body.stock.stock_date if body.stock is not None else body.document_date
    items = {
        row.source_id: row
        for row in await db.scalars(
            select(VoucherMasterEvidence).where(
                VoucherMasterEvidence.company_id == company,
                VoucherMasterEvidence.owner == "catalog",
                VoucherMasterEvidence.entity_type == "item",
                VoucherMasterEvidence.source_id.in_(ids),
            )
        )
    }
    try:
        bases = {identity: uuid.UUID(row.facts["base_unit_id"]) for identity, row in items.items()}
    except (KeyError, ValueError, TypeError) as error:
        raise ConflictError(
            "product base unit evidence is unavailable; synchronize Catalog sources"
        ) from error
    if set(bases) != ids:
        raise ConflictError("product unit evidence is unavailable")
    unit_ids = set(bases.values()) | {line.item.unit_id for line in body.lines}
    supplies = (
        {row.item_line_key: row for row in body.invoice.supplies if row.item_line_key is not None}
        if body.invoice
        else {}
    )
    unit_ids |= {quantity.unit_id for row in supplies.values() for quantity in row.quantities}
    entries: dict[uuid.UUID, QuantityCapture] = {}
    if body.stock is not None:
        for stock_line in body.stock.lines:
            if stock_line.quantity_entry is not None:
                entries[stock_line.line_id] = stock_line.quantity_entry
            elif stock_line.opening is not None:
                opening = stock_line.opening
                entries[stock_line.line_id] = QuantityCapture(
                    entered_unit_id=opening.entered_unit_id,
                    unit_revision_id=opening.unit_revision_id,
                    entered_quantity=opening.entered_quantity,
                    measured_base_quantity=opening.measured_base_quantity,
                )
    unit_ids |= {entry.entered_unit_id for entry in entries.values()}
    masters = {
        row.source_id: row
        for row in await db.scalars(
            select(VoucherMasterEvidence).where(
                VoucherMasterEvidence.company_id == company,
                VoucherMasterEvidence.owner == "catalog",
                VoucherMasterEvidence.entity_type == "unit",
                VoucherMasterEvidence.source_id.in_(unit_ids),
            )
        )
    }
    rows = list(
        await db.scalars(
            select(VoucherItemUnitProjection)
            .where(
                VoucherItemUnitProjection.company_id == company,
                VoucherItemUnitProjection.item_id.in_(ids),
                VoucherItemUnitProjection.unit_id.in_(unit_ids),
                VoucherItemUnitProjection.valid_from <= date,
                or_(
                    VoucherItemUnitProjection.valid_to.is_(None),
                    VoucherItemUnitProjection.valid_to >= date,
                ),
            )
            .limit(401)
        )
    )
    if len(rows) > 400:
        raise ConflictError("ambiguous product unit evidence exceeds the voucher bound")
    try:
        facts = [ItemUnitFacts.model_validate(row.facts) for row in rows]
        revisions = {row.source_id: fact for row, fact in zip(rows, facts, strict=True)}
        grids = {
            identity: UnitMasterFacts.model_validate(row.facts)
            for identity, row in masters.items()
            if row.status == "ACTIVE"
        }
    except ValidationError as error:
        raise ConflictError(
            "product unit evidence is incomplete; synchronize Catalog sources"
        ) from error
    for line in body.lines:
        item = line.item
        available = [fact for fact in facts if fact.item_id == item.item_id]
        selected = [fact for fact in available if fact.unit_id == item.unit_id]
        base = [fact for fact in available if fact.usage_role == "BASE"]
        if (
            len(selected) != 1
            or len(base) != 1
            or base[0].unit_id != bases[item.item_id]
            or item.unit_id not in grids
            or base[0].unit_id not in grids
            or base[0].conversion_mode != "FIXED"
            or base[0].numerator != base[0].denominator
        ):
            raise ConflictError(
                "product unit binding is unavailable or ambiguous on the voucher date"
            )
        admit_role(selected[0], kind)
        supply = supplies.get(line.line_key)
        if supply is not None:
            for invoice_quantity in supply.quantities:
                candidates = [
                    fact for fact in available if fact.unit_id == invoice_quantity.unit_id
                ]
                if len(candidates) != 1 or invoice_quantity.unit_id not in grids:
                    raise ConflictError(
                        "invoice quantity unit is unavailable for this product/date"
                    )
                admit_role(candidates[0], kind)
                admit_quantity(
                    invoice_quantity.quantity,
                    candidates[0],
                    grids[invoice_quantity.unit_id],
                    base[0],
                    grids[base[0].unit_id],
                )
        for quantity in (item.actual_quantity, item.billed_quantity, item.planned_quantity):
            if quantity is not None:
                admit_quantity(
                    quantity, selected[0], grids[item.unit_id], base[0], grids[base[0].unit_id]
                )
        entry = entries.get(line.line_key)
        if entry is not None:
            fact = revisions.get(entry.unit_revision_id)
            if (
                fact is None
                or fact.unit_id != entry.entered_unit_id
                or fact.item_id != item.item_id
                or fact.unit_id not in grids
            ):
                raise ConflictError(
                    "entered stock unit revision is unavailable for this product/date"
                )
            admit_role(fact, kind)
            converted = admit_quantity(
                entry.entered_quantity, fact, grids[fact.unit_id], base[0], grids[base[0].unit_id]
            )
            if fact.conversion_mode == "FIXED":
                if entry.measured_base_quantity is not None or converted != Fraction(
                    item.actual_quantity
                ):
                    raise ValidationFailedError("entered and base stock quantity do not agree")
            elif (
                entry.measured_base_quantity is None
                or entry.measured_base_quantity != item.actual_quantity
            ):
                raise ValidationFailedError(
                    "measured entry requires the actual base stock quantity"
                )
