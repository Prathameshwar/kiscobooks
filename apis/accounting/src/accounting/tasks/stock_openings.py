"""Eligible posted GL opening lines; a read never claims or reserves their value."""

from billing_platform.db.types import Money
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from sqlalchemy import select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from accounting.api.auth import Access
from accounting.financial_resources import FINANCIAL_BY_NAME
from accounting.models.ledger import Journal, JournalLine
from accounting.schemas.stock import StockOpeningLineListItem, StockOpeningLineQuery
from accounting.stock_resources import STOCK_MOVEMENT, STOCK_POLICY, STOCK_POSITION
from accounting.tasks.access import authority_fingerprint, authorize, readable
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.stock_opening_claims import claimed as opening_claimed
from accounting.tasks.stock_policy import effective
from accounting.tasks.stock_reads import view


async def opening_lines(
    db: AsyncSession, current: Access, query: StockOpeningLineQuery, secret: bytes
) -> Page[StockOpeningLineListItem]:
    company = current.context.company_id
    authorize(current, STOCK_POSITION, "read")
    for spec, fields in (
        (STOCK_POLICY, {"inventory_account_id"}),
        (
            FINANCIAL_BY_NAME["journal"],
            {"kind", "status", "number", "posting_date", "reversal_of_id"},
        ),
        (
            FINANCIAL_BY_NAME["journal_line"],
            {"journal_id", "account_id", "side", "currency", "base_currency", "base_amount"},
        ),
    ):
        authorize(current, spec, "read")
        if not fields <= readable(current, spec):
            raise PermissionDeniedError("opening selection inputs must be readable")
    if not {"value", "currency"} <= view(current, STOCK_MOVEMENT)[2]:
        raise PermissionDeniedError("claimed inventory value must be readable")
    if query.stock_date != financial_context(current).books_begin_date:
        raise ValidationFailedError("stock opening date must equal the company's books-begin date")
    policy = await effective(db, current, query.stock_date)
    claimed = opening_claimed(company, JournalLine.id).scalar_subquery()
    reversed_journal = aliased(Journal)
    reversed_opening = (
        select(reversed_journal.id)
        .where(
            reversed_journal.company_id == company,
            reversed_journal.reversal_of_id == Journal.id,
            reversed_journal.status == "POSTED",
        )
        .correlate(Journal)
        .exists()
    )
    remaining = type_coerce(JournalLine.base_amount - claimed, Money)
    statement = (
        select(
            JournalLine.id,
            JournalLine.journal_id,
            Journal.number,
            JournalLine.base_currency.label("currency"),
            remaining.label("remaining_value"),
        )
        .join(Journal, Journal.id == JournalLine.journal_id)
        .where(
            JournalLine.company_id == company,
            Journal.company_id == company,
            Journal.kind == "OPENING",
            Journal.status == "POSTED",
            Journal.posting_date == query.stock_date,
            ~reversed_opening,
            JournalLine.side == "DEBIT",
            JournalLine.account_id == policy.inventory_account_id,
            JournalLine.currency == current.context.base_currency,
            remaining > 0,
        )
    )
    if query.q:
        if len(query.q.strip()) < 2 or len(query.q) > 100:
            raise ValidationFailedError("search opening numbers using two to 100 characters")
        term = query.q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(Journal.number.startswith(term, escape="\\"))
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(JournalLine.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    codec = CursorCodec(
        secret,
        context=canonical_json(
            {
                "resource": "stock_opening_lines",
                "tenant": str(current.actor.tenant_id),
                "company": str(company),
                "authority": authority_fingerprint(current),
                "query": query.model_dump(mode="json", exclude={"cursor"}),
            }
        ).decode(),
    )
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=codec,
        project=lambda row: StockOpeningLineListItem.model_validate(dict(row)),
    )
