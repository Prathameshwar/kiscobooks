"""Reuse native grouped account inputs; freeze the same hierarchy as the reference path."""

from decimal import localcontext
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.trial_balance import evidence, period_rows
from reports.queries.native_context import NativeContext
from reports.queries.native_statements import reduced
from reports.schemas.requests import RunRequest


async def execute(
    db: AsyncSession, context: NativeContext, query: RunRequest, maximum: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    current = query.model_copy(update={"comparative_from": None, "comparative_to": None})
    data = await reduced(db, context, current, maximum)
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        rows, summary = period_rows(data, current, "CURRENT", maximum)
        periods = {"CURRENT": summary}
        if query.comparative_from and query.comparative_to:
            comparison = current.model_copy(
                update={"date_from": query.comparative_from, "date_to": query.comparative_to}
            )
            other = await reduced(db, context, comparison, maximum)
            extra, periods["COMPARATIVE"] = period_rows(
                other, comparison, "COMPARATIVE", maximum - len(rows)
            )
            rows.extend(extra)
    if len(rows) > maximum:
        raise ConflictError("trial balance hierarchy exceeds result capacity")
    return rows, evidence(data, query, context.coverage, rows, periods)
