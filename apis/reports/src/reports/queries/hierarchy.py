"""Bounded indexed branch reads verified against their immutable result batches."""

import uuid
from typing import Any, cast

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from pydantic import ValidationError
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.models.framework import ReportJob, ReportResultBatch
from reports.models.hierarchy import ReportHierarchyNode
from reports.queries.results import verify_batch
from reports.schemas.trial_balance import TrialNode, TrialTotals
from reports.schemas.trial_balance_options import Period

MAX_BATCHES = 8


def summaries(job: ReportJob) -> dict[Period, TrialTotals]:
    if (
        job.kind != "RUN"
        or job.status != "COMPLETE"
        or job.definition["code"] != "TRIAL_BALANCE"
        or job.definition["version"] != 6
    ):
        raise ConflictError("select a completed Trial Balance with hierarchy support")
    try:
        result = job.result or {}
        evidence = result["evidence"]["trial_balance"]
        if evidence["version"] != 6 or result["row_count"] != job.completed_rows:
            raise ValueError("hierarchy evidence differs")
        periods = evidence["periods"]
        if (
            not isinstance(periods, dict)
            or "CURRENT" not in periods
            or set(periods) - {"CURRENT", "COMPARATIVE"}
        ):
            raise ValueError("hierarchy periods differ")
        return {
            cast(Period, period): TrialTotals.model_validate(value)
            for period, value in periods.items()
        }
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise ConflictError("verified Trial Balance summary is unavailable") from exc


def source(job: ReportJob, period: Period) -> Select[tuple[ReportHierarchyNode]]:
    return select(ReportHierarchyNode).where(
        ReportHierarchyNode.company_id == job.company_id,
        ReportHierarchyNode.job_id == job.id,
        ReportHierarchyNode.attempt == job.attempt,
        ReportHierarchyNode.period == period,
    )


async def branch(
    db: AsyncSession,
    job: ReportJob,
    period: Period,
    parent: str,
    show_zero: bool,
    limit: int,
    after: int,
) -> tuple[list[tuple[int, dict[str, Any]]], bool]:
    totals = summaries(job)
    if period not in totals:
        raise ValidationFailedError("period is outside this frozen Trial Balance")
    if not 1 <= limit <= 200 or not 0 <= after <= job.completed_rows:
        raise ValidationFailedError("invalid hierarchy page bounds")
    if parent != "root":
        selected = await db.scalar(
            source(job, period).where(ReportHierarchyNode.node_key == parent)
        )
        if selected is None:
            raise ValidationFailedError("parent is outside this frozen Trial Balance")
    selection = source(job, period).where(
        ReportHierarchyNode.parent_key == parent, ReportHierarchyNode.ordinal > after
    )
    if not show_zero:
        selection = selection.where(ReportHierarchyNode.is_zero.is_(False))
    nodes = list(await db.scalars(selection.order_by(ReportHierarchyNode.ordinal).limit(limit + 1)))
    selected_nodes = []
    batch_ids: set[uuid.UUID] = set()
    for node in nodes[:limit]:
        if node.batch_id not in batch_ids and len(batch_ids) == MAX_BATCHES:
            break
        batch_ids.add(node.batch_id)
        selected_nodes.append(node)
    batches = (
        list(
            await db.scalars(
                select(ReportResultBatch)
                .where(
                    ReportResultBatch.company_id == job.company_id,
                    ReportResultBatch.job_id == job.id,
                    ReportResultBatch.attempt == job.attempt,
                    ReportResultBatch.id.in_(batch_ids),
                )
                .limit(MAX_BATCHES)
            )
        )
        if batch_ids
        else []
    )
    mapping = {batch.id: batch for batch in batches}
    for retained_batch in batches:
        verify_batch(retained_batch)
        if len(canonical_json(retained_batch.rows)) > 1024 * 1024:
            raise ConflictError("hierarchy result batch exceeds its byte bound")
    values = []
    for node in selected_nodes:
        batch = mapping.get(node.batch_id)
        if (
            batch is None
            or not batch.first_ordinal <= node.ordinal < batch.first_ordinal + batch.row_count
        ):
            raise ConflictError("hierarchy result locator is unavailable")
        if batch.first_ordinal + batch.row_count - 1 > job.completed_rows:
            raise ConflictError("hierarchy batch exceeds the completed result")
        raw = batch.rows[node.ordinal - batch.first_ordinal]
        if any(
            getattr(node, key) != raw.get(key)
            for key in ("node_key", "parent_key", "depth", "is_zero", "period")
        ):
            raise ConflictError("hierarchy locator differs from retained output")
        try:
            TrialNode.model_validate(
                {key: raw[key] for key in TrialNode.model_fields if key in raw}
            )
        except ValidationError as exc:
            raise ConflictError("retained hierarchy node is invalid") from exc
        values.append((node.ordinal, raw))
    return values, len(nodes) > len(selected_nodes)
