"""Populate exact immutable posted lines only after source verification succeeds."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.reconcile import fixed, money
from reports.models.posted_lines import ReportPostedLine
from reports.models.source_versions import ReportFactVersion, ReportSourceCut


async def append(
    db: AsyncSession,
    cut: ReportSourceCut,
    lines: list[ReportFactVersion],
    journals: dict[uuid.UUID, ReportFactVersion],
) -> int:
    selected = [
        (line, journals.get(line.relation_id) if line.relation_id else None) for line in lines
    ]
    posted = [
        (line, journal)
        for line, journal in selected
        if journal is not None and journal.source_status == "POSTED"
    ]
    if not posted:
        return 0
    existing = set(
        await db.scalars(
            select(ReportPostedLine.line_id).where(
                ReportPostedLine.company_id == cut.company_id,
                ReportPostedLine.epoch_id == cut.epoch_id,
                ReportPostedLine.line_id.in_([line.source_id for line, _ in posted]),
            )
        )
    )
    for line, journal in posted:
        if line.source_id not in existing:
            db.add(
                ReportPostedLine(
                    id=uuid7(),
                    tenant_id=cut.tenant_id,
                    company_id=cut.company_id,
                    cut_id=cut.id,
                    epoch_id=cut.epoch_id,
                    line_version_id=line.id,
                    journal_version_id=journal.id,
                )
            )
    return len(posted)


async def count(db: AsyncSession, cut: ReportSourceCut, sequence: int) -> int:
    return int(
        await db.scalar(
            select(func.count(ReportPostedLine.id)).where(
                ReportPostedLine.company_id == cut.company_id,
                ReportPostedLine.epoch_id == cut.epoch_id,
                ReportPostedLine.valid_from_sequence <= sequence,
            )
        )
        or 0
    )


async def verify(
    db: AsyncSession, cut: ReportSourceCut, expected_count: int, evidence: dict[str, Any]
) -> None:
    p = ReportPostedLine
    rows = (
        await db.execute(
            select(
                p.base_currency,
                p.side,
                func.count(p.id),
                cast(func.sum(p.base_amount), Numeric(38, 4)),
            )
            .where(
                p.company_id == cut.company_id,
                p.epoch_id == cut.epoch_id,
                p.valid_from_sequence <= cut.sequence,
            )
            .group_by(p.base_currency, p.side)
        )
    ).all()
    actual: dict[str, dict[str, str]] = {}
    for currency, side, _, value in rows:
        if not isinstance(value, Decimal):
            raise ConflictError("posted projection aggregate must be exact")
        actual.setdefault(currency, {"DEBIT": "0.0000", "CREDIT": "0.0000"})[side] = fixed(value)
    expected = {
        currency: {side: fixed(money(value)) for side, value in totals.items()}
        for currency, totals in evidence["base_totals"].items()
    }
    if sum(row[2] for row in rows) != expected_count or actual != expected:
        raise ConflictError("posted query projection does not reconcile with source evidence")
