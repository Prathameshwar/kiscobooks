"""As-of balances from immutable item and allocation amounts."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.db.types import Money
from billing_platform.errors import PermissionDeniedError
from sqlalchemy import case, func, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from accounting.api.auth import Access
from accounting.models.masters import Account, Party
from accounting.models.subledger import Allocation, OpenItem
from accounting.schemas.subledger import Ageing, ItemBalance, ItemQuery
from accounting.tasks.finance_records import require_fields


def allocation_sum(date: dt.date, *, base: bool = False) -> ColumnElement[Decimal]:
    debt = Allocation.debt_item_id == OpenItem.id
    amount = (
        case((debt, Allocation.debt_base_amount), else_=Allocation.credit_base_amount)
        if base
        else Allocation.amount
    )
    return type_coerce(
        select(func.coalesce(func.sum(amount), 0))
        .where(
            Allocation.company_id == OpenItem.company_id,
            (debt | (Allocation.credit_item_id == OpenItem.id)),
            Allocation.posting_date <= date,
            (Allocation.reversal_date.is_(None)) | (Allocation.reversal_date > date),
        )
        .correlate(OpenItem)
        .scalar_subquery(),
        Money,
    )


def remaining(date: dt.date, *, base: bool = False) -> ColumnElement[Decimal]:
    return type_coerce(
        (OpenItem.base_amount if base else OpenItem.amount) - allocation_sum(date, base=base), Money
    )


def active(date: dt.date) -> ColumnElement[bool]:
    return (OpenItem.posting_date <= date) & (
        (OpenItem.reversal_date.is_(None)) | (OpenItem.reversal_date > date)
    )


def require_inputs(access: Access) -> None:
    require_fields(
        access,
        "open_item",
        {
            "account_id",
            "party_id",
            "role",
            "direction",
            "currency",
            "amount",
            "base_currency",
            "base_amount",
            "posting_date",
            "due_date",
            "reversal_date",
        },
    )
    require_fields(
        access,
        "allocation",
        {
            "debt_item_id",
            "credit_item_id",
            "amount",
            "debt_base_amount",
            "credit_base_amount",
            "posting_date",
            "reversal_date",
        },
    )


async def item_balance(
    db: AsyncSession, access: Access, object_id: uuid.UUID, date: dt.date
) -> ItemBalance:
    require_inputs(access)
    item = await company_object(db, OpenItem, object_id, company_id=access.context.company_id)
    result = (
        await db.execute(
            select(remaining(date), remaining(date, base=True)).where(
                OpenItem.id == item.id, active(date)
            )
        )
    ).one_or_none()
    return ItemBalance(
        item_id=item.id,
        as_of=date,
        currency=item.currency,
        remaining=result[0] if result else Decimal(0),
        base_currency=item.base_currency,
        base_remaining=result[1] if result else Decimal(0),
    )


async def ageing(db: AsyncSession, access: Access, query: ItemQuery) -> Ageing:
    require_inputs(access)
    await company_object(db, Party, query.party_id, company_id=access.context.company_id)
    if query.account_id:
        account = await company_object(
            db, Account, query.account_id, company_id=access.context.company_id
        )
        if account.party_id != query.party_id or account.party_role != query.role:
            raise PermissionDeniedError("account does not belong to the requested party role")
    amount = remaining(query.as_of)
    debt = OpenItem.direction == "DEBT"
    # Boundaries are calculated in Python for identical MySQL/SQLite business-date behavior.
    bounds = [query.as_of - dt.timedelta(days=days) for days in (30, 60, 90)]
    filters = [
        debt & (OpenItem.due_date >= query.as_of),
        debt & (OpenItem.due_date < query.as_of) & (OpenItem.due_date >= bounds[0]),
        debt & (OpenItem.due_date < bounds[0]) & (OpenItem.due_date >= bounds[1]),
        debt & (OpenItem.due_date < bounds[1]) & (OpenItem.due_date >= bounds[2]),
        debt & (OpenItem.due_date < bounds[2]),
        debt & OpenItem.due_date.is_(None),
        debt,
        ~debt,
    ]
    columns = [
        type_coerce(func.coalesce(func.sum(case((condition, amount), else_=0)), 0), Money)
        for condition in filters
    ]
    statement = select(*columns).where(
        OpenItem.company_id == access.context.company_id,
        OpenItem.party_id == query.party_id,
        OpenItem.role == query.role,
        OpenItem.currency == query.currency,
        active(query.as_of),
    )
    if query.account_id:
        statement = statement.where(OpenItem.account_id == query.account_id)
    values = (await db.execute(statement)).one()
    names = (
        "not_due",
        "days_1_30",
        "days_31_60",
        "days_61_90",
        "days_91_plus",
        "unknown_due",
        "debt",
        "unapplied_credit",
    )
    amounts: dict[str, Any] = dict(zip(names, values, strict=True))
    return Ageing(
        as_of=query.as_of,
        party_id=query.party_id,
        role=query.role,
        currency=query.currency,
        **amounts,
    )
