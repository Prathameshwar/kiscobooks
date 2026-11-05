"""Bounded continuity over the same verified cut as statements and dated open items."""

import datetime as dt
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.balance_continuity import calendars, continuity
from reports.domain.statements import calculation_evidence
from reports.queries.native_context import NativeContext
from reports.queries.native_open_items import execute as open_items
from reports.queries.native_statements import reduced
from reports.schemas.requests import RunRequest


async def execute(
    db: AsyncSession, context: NativeContext, query: RunRequest, maximum: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    await context.validate(db, query)
    calendars(context.data, query, context.coverage)
    assert query.date_from is not None
    boundary = query.model_copy(update={"code": "TRIAL_BALANCE", "date_to": query.date_from})
    data = await reduced(db, context, boundary, maximum)
    bill_query = query.model_copy(
        update={
            "code": "OUTSTANDING_BILLS",
            "date_from": context.coverage,
            "date_to": query.date_from - dt.timedelta(days=1),
        }
    )
    bills, _ = await open_items(db, context, bill_query, maximum)
    rows = continuity(data, query, context.coverage, bills)
    for row in rows:
        row["period"] = "CURRENT"
    if len(rows) > maximum:
        raise ConflictError("native continuity result exceeds its configured row bound")
    return rows, calculation_evidence(data, query, context.coverage, rows)
