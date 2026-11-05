"""Bounded exact cash aggregates and GL-controlled open items at one retained cut."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import Numeric, case, cast, func
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.analytics_common import periods
from reports.domain.reconcile import fixed
from reports.models.core import ReportGeneration
from reports.models.posted_lines import ReportPostedLine
from reports.queries.native_context import NativeContext
from reports.queries.native_ledger import LedgerQuery
from reports.queries.native_open_items import execute as open_items
from reports.queries.native_statements import reduced
from reports.schemas.requests import RunRequest


async def inputs(
    db: AsyncSession,
    context: NativeContext,
    generation: ReportGeneration,
    values: dict[str, Any],
    maximum: int,
) -> dict[str, Any]:
    accounts = {
        key: value
        for key, value in context.data.accounts.items()
        if value["kind"] in {"CASH", "BANK"}
    }
    periods_data: dict[str, Any] = {}
    for period, begin, end in periods(values):
        query = RunRequest.model_validate(
            {
                "code": "ACCOUNT_SUMMARY",
                "generation_id": generation.id,
                "date_from": begin,
                "date_to": end,
                "grain": "DAY",
            }
        )
        balances = await reduced(db, context, query, maximum)
        p = ReportPostedLine
        ledger = LedgerQuery(context, query.model_copy(update={"code": "ACCOUNT_LEDGER"}))
        # Net the cash/bank legs of each journal before counting a receipt/payment.
        # Transfers within the cash/bank set have zero aggregate effect.
        statement = ledger.source_for(
            p,
            p.journal_id,
            p.posting_date,
            cast(
                func.sum(case((p.side == "DEBIT", p.base_amount), else_=-p.base_amount)),
                Numeric(38, 4),
            ),
        )
        statement = statement.where(
            p.account_id.in_([uuid.UUID(key) for key in accounts]),
            p.posting_date >= query.date_from,
            p.posting_date <= query.date_to,
            p.opening_effect.is_(False),
        )
        result = (
            await db.execute(
                statement.group_by(p.journal_id, p.posting_date)
                .order_by(p.posting_date, p.journal_id)
                .limit(maximum + 1)
            )
        ).all()
        if len(result) > maximum:
            raise ConflictError("cash journal aggregate exceeds its supported result bound")
        journals = await context.view.lookup(db, "journal", [row[0] for row in result])
        movements = []
        for identity, day, amount in result:
            if not isinstance(amount, Decimal):
                raise ConflictError("cash aggregates require exact Decimal amounts")
            journal = journals[identity].data
            assert journal is not None
            movements.append(
                {
                    "journal_id": str(identity),
                    "date": day.isoformat(),
                    "amount": fixed(amount),
                    "journal_kind": journal["kind"],
                    "label": journal.get("number") or str(identity),
                }
            )
        bills, _ = await open_items(
            db,
            context,
            query.model_copy(update={"code": "OUTSTANDING_BILLS", "date_from": context.coverage}),
            maximum,
        )
        periods_data[period] = {
            "lines": [
                line
                | {
                    "posting_date": line["posting_date"].isoformat(),
                    "base_amount": fixed(line["value"]),
                }
                for line in balances.aggregated
            ],
            "movements": movements,
            "bills": bills,
        }
    return {"accounts": accounts, "periods": periods_data}
