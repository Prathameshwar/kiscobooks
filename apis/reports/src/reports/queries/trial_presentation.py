"""Validate hierarchy choices against a completed, scoped immutable result."""

from billing_platform.errors import ValidationFailedError
from sqlalchemy.ext.asyncio import AsyncSession

from reports.models.framework import ReportJob
from reports.models.hierarchy import ReportHierarchyNode
from reports.queries.hierarchy import source, summaries
from reports.schemas.trial_balance_options import TrialPresentation


async def validate(db: AsyncSession, job: ReportJob, options: TrialPresentation) -> None:
    periods = summaries(job)
    if options.period not in periods:
        raise ValidationFailedError("export period is outside this completed Trial Balance")
    keys = set(options.expanded) | set(options.collapsed)
    if not keys:
        return
    nodes = list(
        await db.scalars(
            source(job, options.period).where(ReportHierarchyNode.node_key.in_(keys)).limit(4000)
        )
    )
    if {node.node_key for node in nodes} != keys or any(
        node.node_key.startswith("account:") for node in nodes
    ):
        raise ValidationFailedError("export expansion is outside this Trial Balance hierarchy")
