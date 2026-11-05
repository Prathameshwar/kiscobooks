"""Publish bounded daily deltas beside immutable posted lines and verify both controls."""

import itertools
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import Numeric, cast, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.domain.reconcile import fixed, money
from reports.models.daily_balances import GRAIN, ReportDailyBalance, grouped
from reports.models.posted_lines import ReportPostedLine
from reports.models.source_versions import ReportSourceCut
from reports.tasks.common import company_lock

MAXIMUM_GROUPS = 100000


async def partitions(
    reader: AsyncSession, cut: ReportSourceCut, predicates: tuple[Any, ...] = (), depth: int = 0
) -> AsyncIterator[list[Any]]:
    """Bound each read, not a company's cardinality; split overflowing indexed grains.

    Unlike deep group offsets, each child query restricts source keys. Most cuts fit
    one read; large cuts partition accounts, then dates/currencies/sides as needed.
    Dropping an oversized result before recursion bounds the live Python buffer.
    """
    p = ReportPostedLine
    keys = tuple(getattr(p, key) for key in GRAIN)
    query = grouped(cut.company_id, cut.epoch_id, cut.sequence).where(*predicates)
    rows = list((await reader.execute(query.order_by(*keys).limit(MAXIMUM_GROUPS + 1))).mappings())
    if len(rows) <= MAXIMUM_GROUPS:
        yield rows
        return
    del rows
    if depth >= len(GRAIN):
        raise ConflictError("daily projection cannot partition its source grain")
    key = keys[depth]
    after = None
    while True:
        values_query = (
            select(key)
            .where(
                p.company_id == cut.company_id,
                p.epoch_id == cut.epoch_id,
                p.valid_from_sequence == cut.sequence,
                *predicates,
            )
            .distinct()
            .order_by(key)
            .limit(100)
        )
        if after is not None:
            values_query = values_query.where(key > after)
        values = list(await reader.scalars(values_query))
        if not values:
            return
        selected = list(
            (
                await reader.execute(
                    query.where(key.in_(values)).order_by(*keys).limit(MAXIMUM_GROUPS + 1)
                )
            ).mappings()
        )
        if len(selected) <= MAXIMUM_GROUPS:
            yield selected
            del selected
        else:
            del selected
            for value in values:
                async for chunk in partitions(reader, cut, (*predicates, key == value), depth + 1):
                    yield chunk
                    del chunk
        after = values[-1]
        if len(values) < 100:
            return


async def build(factory: async_sessionmaker[AsyncSession], cut: ReportSourceCut) -> None:
    async with factory() as reader:
        async for groups in partitions(reader, cut):
            await persist(factory, cut, groups)
            del groups


async def persist(
    factory: async_sessionmaker[AsyncSession], cut: ReportSourceCut, groups: list[Any]
) -> None:
    d = ReportDailyBalance
    for batch in itertools.batched(groups, 200):
        async with factory() as writer, writer.begin():
            await company_lock(writer, cut.tenant_id, cut.company_id)
            keys = [tuple(row[key] for key in GRAIN) for row in batch]
            existing = set(
                (
                    await writer.execute(
                        select(*(getattr(d, key) for key in GRAIN)).where(
                            d.company_id == cut.company_id,
                            d.epoch_id == cut.epoch_id,
                            d.valid_from_sequence == cut.sequence,
                            tuple_(*(getattr(d, key) for key in GRAIN)).in_(keys),
                        )
                    )
                ).tuples()
            )
            for row, key in zip(batch, keys, strict=True):
                if key not in existing:
                    writer.add(
                        d(
                            id=uuid7(),
                            tenant_id=cut.tenant_id,
                            company_id=cut.company_id,
                            cut_id=cut.id,
                            **dict(row),
                        )
                    )


async def verify(
    db: AsyncSession, cut: ReportSourceCut, expected_count: int, evidence: dict[str, Any]
) -> None:
    d = ReportDailyBalance
    groups = (
        await db.execute(
            select(
                d.base_currency,
                d.side,
                func.sum(d.line_count),
                cast(func.sum(d.base_amount), Numeric(38, 4)),
            )
            .where(
                d.company_id == cut.company_id,
                d.epoch_id == cut.epoch_id,
                d.valid_from_sequence <= cut.sequence,
            )
            .group_by(d.base_currency, d.side)
        )
    ).all()
    actual: dict[str, dict[str, str]] = {}
    for currency, side, _, value in groups:
        if not isinstance(value, Decimal):
            raise ConflictError("daily projection must return exact Decimal totals")
        actual.setdefault(currency, {"DEBIT": "0.0000", "CREDIT": "0.0000"})[side] = fixed(value)
    expected = {
        currency: {side: fixed(money(value)) for side, value in totals.items()}
        for currency, totals in evidence["base_totals"].items()
    }
    if sum(row[2] for row in groups) != expected_count or actual != expected:
        raise ConflictError("daily query projection does not reconcile with source evidence")
