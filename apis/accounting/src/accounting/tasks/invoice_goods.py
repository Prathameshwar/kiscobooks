"""Goods lines of a Purchase bill that brings its goods into stock (B24, D02 2026-11-03).

The bill's stock lines name the items; Catalog's signed facts (read before any Accounting
transaction) say what each item is on the stock date, including its purchase GST bundle.
Accounting never accepts a rate, an HSN code or a stock value from the bill itself.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.invoice import InvoicePreviewCommand, InvoiceSupply
from voucher_execution.stock import StockLine
from voucher_execution.stock_facts import (
    StockFenceFacts,
    StockFenceRequest,
    StockItemFact,
    StockWarehouseFact,
)

from accounting.models.stock import StockAccountPolicy
from accounting.tasks.stock_source_client import StockSourceClient, StockSourceUnavailableError


@dataclass(frozen=True)
class GoodsFacts:
    """Catalog facts for one bill's goods, by stock line (= the supply's item line key)."""

    lines: dict[uuid.UUID, StockLine]
    items: dict[uuid.UUID, StockItemFact]
    warehouses: dict[uuid.UUID, StockWarehouseFact]

    def item(self, supply: InvoiceSupply) -> tuple[StockLine, StockItemFact]:
        assert supply.item_line_key is not None
        line = self.lines[supply.item_line_key]
        return line, self.items[line.item_id]


def fence_request(command: InvoicePreviewCommand, *, labels: bool = False) -> StockFenceRequest:
    assert command.stock is not None
    lines = command.stock.lines
    return StockFenceRequest(
        purpose="PREVIEW",
        tenant_id=command.tenant_id,
        company_id=command.company_id,
        execution_id=uuid7(),
        actor_user_id=command.actor_user_id,
        authority=command.authority,
        authority_expires_at=utcnow() + dt.timedelta(seconds=45),
        stock_date=command.stock.stock_date,
        content_hash=hashlib.sha256(
            canonical_json(command.stock.model_dump(mode="json"))
        ).hexdigest(),
        item_ids=tuple(sorted({line.item_id for line in lines})),
        warehouse_ids=tuple(sorted({line.warehouse_id for line in lines})),
        bin_ids=tuple(sorted({line.bin_id for line in lines if line.bin_id is not None})),
        include_purchase_tax=True,
        include_labels=labels,
    )


def facts_for(command: InvoicePreviewCommand, facts: StockFenceFacts) -> GoodsFacts:
    assert command.stock is not None
    if facts.company_id != command.company_id or facts.tenant_id != command.tenant_id:
        raise ConflictError("product facts belong to another company")
    return GoodsFacts(
        {line.line_id: line for line in command.stock.lines},
        {row.item_id: row for row in facts.items},
        {row.warehouse_id: row for row in facts.warehouses},
    )


async def acquire(
    settings: Any, command: InvoicePreviewCommand, *, labels: bool = False
) -> GoodsFacts | None:
    """Read the bill's item facts from Catalog; called outside every Accounting session.

    ``labels`` also asks for what a print shows (each item's base-unit symbol).
    """
    if command.stock is None:
        return None
    if not settings.stock_owner_url or not settings.stock_owner_secret:
        raise StockSourceUnavailableError("product facts are not configured for goods bills")
    client = StockSourceClient(
        settings.stock_owner_url, settings.stock_owner_secret.get_secret_value().encode()
    )
    return facts_for(command, await client.acquire(fence_request(command, labels=labels)))


async def inventory_account(db: AsyncSession, company: uuid.UUID, day: dt.date) -> uuid.UUID:
    """The company's inventory account on ``day``; a read, so it takes no lock."""
    policies = list(
        await db.scalars(
            select(StockAccountPolicy)
            .where(
                StockAccountPolicy.company_id == company,
                StockAccountPolicy.valid_from <= day,
                (StockAccountPolicy.valid_to.is_(None)) | (StockAccountPolicy.valid_to >= day),
            )
            .limit(2)
        )
    )
    if len(policies) != 1:
        raise ConflictError("configure the company's stock accounts for this posting date first")
    return policies[0].inventory_account_id


def check_line(
    supply: InvoiceSupply, goods: GoodsFacts, inventory: uuid.UUID
) -> tuple[StockLine, StockItemFact]:
    """A goods supply bills exactly its stock line, in the item's base unit, into inventory."""
    from accounting.tasks.stock_effects import permitted

    line, item = goods.item(supply)
    if item.status != "ACTIVE" or item.family_status != "ACTIVE":
        raise ConflictError("activate the product before billing it")
    if not item.purchasable:
        raise ValidationFailedError("the product is not set up to be purchased")
    permitted(item, goods.warehouses[line.warehouse_id], "PURCHASE_RECEIPT")
    if supply.account_id != inventory:
        raise ValidationFailedError("purchased goods post to the company's inventory account")
    quantities = {row.basis: row for row in supply.quantities}
    billed = quantities.get("BILLED")
    if billed is None or billed.unit_id != item.base_unit_id or billed.quantity != line.quantity:
        raise ValidationFailedError(
            "a goods line bills its received quantity in the product's base unit"
        )
    actual = quantities.get("ACTUAL")
    if actual is not None and (actual.unit_id, actual.quantity) != (billed.unit_id, line.quantity):
        raise ValidationFailedError("a goods line receives what it bills")
    if supply.free_purpose != "NONE":
        raise ConflictError("free goods on a purchase bill are not available yet")
    return line, item
