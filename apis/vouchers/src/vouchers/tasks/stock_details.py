"""Normalized immutable capture; common item rows remain the quantity authority."""

from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.stock import StockInput, StockLine

from vouchers.api.auth import Access
from vouchers.models import core as m
from vouchers.models.stock import VoucherStockContext, VoucherStockDetail, VoucherStockUnit
from vouchers.schemas.documents import ItemInput
from vouchers.tasks.access import denied, writable
from vouchers.tasks.common import values

DIMENSIONS = frozenset(StockLine.model_fields) - {"line_id", "item_id", "quantity"}


def protect_schema(current: Access, schema: dict[str, Any]) -> None:
    """The duplicate stock representation obeys the common header/item field rules."""

    def variants(value: dict[str, Any]) -> list[dict[str, Any]]:
        return [value, *(branch for branch in value.get("anyOf", []) if isinstance(branch, dict))]

    def protect(value: dict[str, Any], entity: str, mapping: dict[str, str]) -> None:
        if "properties" not in value:
            return
        properties = value.get("properties", {})
        blocked = denied(current, entity, set(mapping.values()), "read")
        for key, target in mapping.items():
            if key not in properties:
                continue
            if target in blocked:
                del properties[key]
            else:
                properties[key]["readOnly"] = bool(denied(current, entity, {target}, "write"))
        value["required"] = [key for key in value.get("required", []) if key in properties]

    for stock in variants(schema.get("properties", {}).get("stock", {})):
        protect(
            stock,
            "vouchers.voucher",
            {
                "stock_date": "stock_date",
                "currency": "currency",
                "lines": "lines",
            },
        )
        for line in variants(stock.get("properties", {}).get("lines", {}).get("items", {})):
            protect(
                line,
                "vouchers.voucher_item",
                {
                    **{key: key for key in DIMENSIONS},
                    "item_id": "item_id",
                    "quantity": "actual_quantity",
                },
            )
            properties = line.get("properties", {})
            for evidence in ("quantity_entry", "count"):
                if evidence in properties:
                    required = {"unit_id", "actual_quantity", evidence}
                    if denied(current, "vouchers.voucher_item", required, "read"):
                        properties.pop(evidence)
                    elif denied(current, "vouchers.voucher_item", required, "write"):
                        properties[evidence]["readOnly"] = True


async def store(
    db: AsyncSession,
    current: Access,
    revision: m.VoucherRevision,
    body: StockInput,
    *,
    previous: dict[str, Any],
) -> None:
    rows = list(
        await db.scalars(
            select(m.VoucherLine)
            .where(
                m.VoucherLine.company_id == revision.company_id,
                m.VoucherLine.revision_id == revision.id,
            )
            .order_by(m.VoucherLine.sequence)
        )
    )
    # A mixed Purchase bill also has account/service and charge lines; only item lines move.
    common = {row.line_key: row for row in rows if row.line_kind == "ITEM"}
    if set(common) != {line.line_id for line in body.lines}:
        raise ConflictError("physical stock details must match the common voucher item lines")
    old_stock = previous.get("stock") or {}
    old_lines = {line["line_id"]: line for line in old_stock.get("lines", [])}
    old_items = {line["line_key"]: line["item"] for line in previous.get("lines", [])}
    db.add(
        VoucherStockContext(
            **values(current),
            revision_id=revision.id,
            schema_version=body.version,
            action=body.action,
            opening_mode=body.opening_mode,
            opening_control_id=body.opening_control_id,
            reason=body.reason,
        )
    )
    await db.flush()
    items = {
        row.line_id: row
        for row in await db.scalars(
            select(m.VoucherItemDetail).where(
                m.VoucherItemDetail.company_id == revision.company_id,
                m.VoucherItemDetail.revision_id == revision.id,
            )
        )
    }
    for line in body.lines:
        parent = common[line.line_id]
        item = items.get(parent.id)
        if (
            item is None
            or item.item_id != line.item_id
            or item.actual_quantity != line.quantity
            # A goods Purchase bill bills what it receives; other stock vouchers bill nothing.
            or item.billed_quantity != (line.quantity if body.action == "PURCHASE_INVOICE" else 0)
        ):
            raise ConflictError("native physical capture differs from its common base quantity")
        previous_line = old_lines.get(str(line.line_id), {})
        before = old_items.get(str(line.line_id), {}) | {
            key: value for key, value in previous_line.items() if key in DIMENSIONS
        }
        authored = line.model_dump(mode="json", include=set(DIMENSIONS))
        if any(
            before.get(key) != authored.get(key) for key in ("quantity_entry", "count")
        ) and denied(
            current, "vouchers.voucher_item", {"unit_id", "actual_quantity"}, "write", before
        ):
            from billing_platform.errors import PermissionDeniedError

            raise PermissionDeniedError("entered stock quantity/unit fields are not writable")
        after = (
            ItemInput.model_validate(
                {key: getattr(item, key) for key in ItemInput.model_fields}
            ).model_dump(mode="json")
            | authored
        )
        writable(current, "vouchers.voucher_item", before, after)
        detail = VoucherStockDetail(
            **values(current),
            revision_id=revision.id,
            line_id=parent.id,
            currency=revision.currency,
            **line.model_dump(
                include=set(DIMENSIONS - {"unit_ids", "opening", "quantity_entry", "count"})
            ),
            count=line.count.model_dump(mode="json") if line.count else None,
            opening=line.opening.model_dump(mode="json") if line.opening else None,
            quantity_entry=line.quantity_entry.model_dump(mode="json")
            if line.quantity_entry
            else None,
        )
        db.add(detail)
        await db.flush()
        for sequence, unit_id in enumerate(line.unit_ids, 1):
            db.add(
                VoucherStockUnit(
                    **values(current),
                    revision_id=revision.id,
                    stock_detail_id=detail.id,
                    unit_id=unit_id,
                    sequence=sequence,
                )
            )


async def load(
    db: AsyncSession, current: Access, revision: m.VoucherRevision
) -> dict[str, Any] | None:
    header = await db.scalar(
        select(VoucherStockContext).where(
            VoucherStockContext.company_id == revision.company_id,
            VoucherStockContext.revision_id == revision.id,
        )
    )
    if header is None:
        return None
    details = {
        row.line_id: row
        for row in await db.scalars(
            select(VoucherStockDetail)
            .where(
                VoucherStockDetail.company_id == revision.company_id,
                VoucherStockDetail.revision_id == revision.id,
            )
            .limit(101)
        )
    }
    rows = list(
        await db.scalars(
            select(m.VoucherLine)
            .where(
                m.VoucherLine.company_id == revision.company_id,
                m.VoucherLine.revision_id == revision.id,
                # A mixed Purchase bill's account/service and charge lines carry no stock.
                m.VoucherLine.line_kind == "ITEM",
            )
            .order_by(m.VoucherLine.sequence)
            .limit(101)
        )
    )
    items = {
        row.line_id: row
        for row in await db.scalars(
            select(m.VoucherItemDetail)
            .where(
                m.VoucherItemDetail.company_id == revision.company_id,
                m.VoucherItemDetail.revision_id == revision.id,
            )
            .limit(101)
        )
    }
    if len(rows) > 100 or set(details) != {row.id for row in rows} or set(items) != set(details):
        raise ConflictError("native stock capture is incomplete")
    members: dict[Any, list[Any]] = {}
    unit_rows = list(
        await db.scalars(
            select(VoucherStockUnit)
            .where(
                VoucherStockUnit.company_id == revision.company_id,
                VoucherStockUnit.revision_id == revision.id,
            )
            .order_by(VoucherStockUnit.stock_detail_id, VoucherStockUnit.sequence)
            .limit(1001)
        )
    )
    if len(unit_rows) > 1000:
        raise ConflictError("native stock unit capture exceeds its reviewed bound")
    for member in unit_rows:
        members.setdefault(member.stock_detail_id, []).append(member.unit_id)
    lines = []
    for row in rows:
        detail, item = details[row.id], items[row.id]
        if detail.currency != revision.currency:
            raise ConflictError("native stock value currency differs from its common revision")
        lines.append(
            {
                "line_id": row.line_key,
                "item_id": item.item_id,
                "quantity": item.actual_quantity,
                "unit_ids": members.get(detail.id, []),
                **{key: getattr(detail, key) for key in DIMENSIONS - {"unit_ids"}},
            }
        )
    return StockInput.model_validate(
        {
            "version": header.schema_version,
            "action": header.action,
            "stock_date": revision.stock_date,
            "currency": revision.currency,
            "opening_mode": header.opening_mode,
            "opening_control_id": header.opening_control_id,
            "reason": header.reason,
            "lines": lines,
        }
    ).model_dump(mode="json")


def restricted(current: Access, content: dict[str, Any]) -> bool:
    """A complete typed stock block cannot disclose a denied contributing field.

    Common item rows remain sparse. Hide their immutable aggregate copy as a
    whole when one of its inputs is denied, including duplicate header fields.
    """
    stock = content.get("stock")
    if stock is None:
        return False
    if denied(
        current, "vouchers.voucher", {"stock", "stock_date", "currency", "lines"}, "read", content
    ):
        return True
    common = {line["line_key"]: line["item"] for line in content["lines"]}
    for line in stock["lines"]:
        item = common[line["line_id"]]
        values = item | item.get("custom_fields", {}) | line
        if denied(current, "vouchers.voucher_item", set(values), "read", values):
            return True
    return False
