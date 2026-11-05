"""Read immutable verification evidence instead of rescanning an already verified cut."""

import copy
import uuid
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.reconcile import RULE_HASH
from reports.models.source_versions import ReportSourceCut


async def execute(
    db: AsyncSession, company: uuid.UUID, generation: uuid.UUID, maximum: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cut = await db.scalar(
        select(ReportSourceCut).where(
            ReportSourceCut.company_id == company,
            ReportSourceCut.generation_id == generation,
        )
    )
    verified = cut.verification if cut is not None else None
    if (
        verified is None
        or verified.get("rule_hash") != RULE_HASH
        or verified.get("projection_version") != 1
        or verified.get("differences") != []
    ):
        raise ConflictError("source reconciliation requires compatible verified evidence")
    evidence = copy.deepcopy(
        {
            key: verified[key]
            for key in (
                "counts",
                "base_totals",
                "coverage_start",
                "coverage_kind",
                "rule_hash",
                "differences",
            )
        }
    )
    rows = [
        {"row_kind": "SOURCE_COUNT", "kind": "SOURCE_COUNT", "source": key, "count": count}
        for key, count in sorted(evidence["counts"].items())
    ]
    rows.extend(
        {"row_kind": "GL_CONTROL", "kind": "GL_CONTROL", "currency": currency, **totals}
        for currency, totals in sorted(evidence["base_totals"].items())
    )
    if len(rows) > maximum:
        raise ConflictError("source reconciliation result exceeds its configured row bound")
    return rows, evidence
