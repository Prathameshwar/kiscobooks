"""Bounded compatibility reader for legacy and versioned generations; RF4 supplies large plans."""

from reporting_contract.contract import Fact, Manifest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.models.core import ReportGeneration
from reports.models.source_versions import ReportFactVersion, ReportSourceCut
from reports.queries.source_versions import SourceView, bounded_rows
from reports.tasks.ingest import current_facts
from reports.tasks.source_versions import fact

LEGACY_FACT_LIMIT = 100000


def source_count(manifest: Manifest) -> int:
    return max(manifest.fact_count, sum(manifest.control.counts.values()))


async def load(
    db: AsyncSession, generation: ReportGeneration, maximum: int, *, bound_legacy: bool = True
) -> list[Fact]:
    if generation.status != "READY" or generation.manifest is None:
        raise ValueError("source generation is unavailable")
    manifest = Manifest.model_validate(generation.manifest)
    cut = await db.scalar(
        select(ReportSourceCut).where(
            ReportSourceCut.company_id == generation.company_id,
            ReportSourceCut.generation_id == generation.id,
        )
    )
    if (bound_legacy or cut is not None) and source_count(manifest) > maximum:
        raise ValueError("source exceeds enabled reference capacity")
    if cut is None:
        return await current_facts(db, generation)
    if cut.verification is None:
        raise ValueError("source cutoff is not verified")
    view = SourceView(generation.company_id, cut.epoch_id, cut.sequence)
    rows = await bounded_rows(
        db,
        select(ReportFactVersion)
        .where(view.predicate())
        .order_by(ReportFactVersion.entity, ReportFactVersion.source_id),
        maximum=maximum,
    )
    return [fact(row) for row in rows]
