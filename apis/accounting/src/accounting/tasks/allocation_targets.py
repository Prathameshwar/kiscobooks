"""Early proof that every allocation names a real, compatible, open bill of this company.

Preview and prepare call this so an advance or settlement against a missing, foreign,
mismatched or exhausted open item is a clear 422 before any intent or journal exists.
Commit-time allocation (`allocations.create_in_transaction`) remains the final authority
for dated history and cumulative consumption.
"""

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from billing_platform.errors import ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.money import BillAllocation

from accounting.api.auth import Access
from accounting.models.subledger import OpenItem
from accounting.tasks.subledger_reads import item_balance, require_inputs


@dataclass(frozen=True)
class NewBill:
    """Account and currency of a tracked entry this voucher posts, targeted by `line_key`."""

    account_id: uuid.UUID
    currency: str


async def check_allocation_targets(
    db: AsyncSession,
    access: Access,
    allocations: Sequence[BillAllocation],
    *,
    posting_date: dt.date,
    new_bills: Mapping[uuid.UUID, NewBill],
) -> None:
    """Refuse allocations whose existing open items cannot carry them.

    Missing and other-company items are indistinguishable here, so the response never
    confirms that an identifier exists elsewhere. Each allocation is checked on its own
    against the item's balance at the posting date; several allocations drawing on one
    item are summed by the commit-time allocation, which rejects the excess.
    """
    wanted = {
        target.item_id
        for allocation in allocations
        for target in (allocation.debt, allocation.credit)
        if target.item_id is not None
    }
    if not wanted:
        return
    require_inputs(access)
    found = {
        row.id: row
        for row in await db.scalars(
            select(OpenItem).where(
                OpenItem.company_id == access.context.company_id, OpenItem.id.in_(wanted)
            )
        )
    }
    remaining: dict[uuid.UUID, Decimal] = {}
    for allocation in allocations:
        items: list[OpenItem] = []
        sides: set[tuple[uuid.UUID, str]] = set()
        for direction, target in (("DEBT", allocation.debt), ("CREDIT", allocation.credit)):
            if target.item_id is None:
                bill = new_bills.get(target.line_key) if target.line_key is not None else None
                if bill is not None:
                    sides.add((bill.account_id, bill.currency))
                continue
            item = found.get(target.item_id)
            if item is None:
                raise ValidationFailedError(
                    "allocation references an open bill that does not exist"
                )
            if item.direction != direction:
                raise ValidationFailedError("allocation requires a debt bill and a credit bill")
            if item.currency != allocation.currency:
                raise ValidationFailedError("allocation currency differs from selected bills")
            items.append(item)
            sides.add((item.account_id, item.currency))
        if len(sides) > 1:
            raise ValidationFailedError(
                "allocation requires debt and credit for the same party role, account and currency"
            )
        for item in items:
            # Reversed or later-dated items are refused by the commit-time history guard.
            if item.reversal_date is not None or item.posting_date > posting_date:
                continue
            if item.id not in remaining:
                balance = await item_balance(db, access, item.id, posting_date)
                remaining[item.id] = balance.remaining
            if allocation.amount > remaining[item.id]:
                raise ValidationFailedError("allocation exceeds the available outstanding amount")
