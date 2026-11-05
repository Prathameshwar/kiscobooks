"""One bounded frozen-result reader for every renderer; never discover columns from rows."""

import hashlib
from collections.abc import AsyncIterator
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.models.framework import ReportJob, ReportResultBatch
from reports.runtimes.ledger_v1.context import NativeContext
from reports.runtimes.ledger_v1.parameters import RunRequest
from reports.runtimes.ledger_v1.query import batches as ledger_batches
from reports.tasks.native_execution import require_retained_runtime


def verify_batch(batch: ReportResultBatch) -> None:
    if (
        len(batch.rows) != batch.row_count
        or not 1 <= batch.row_count <= 200
        or hashlib.sha256(canonical_json(batch.rows)).hexdigest() != batch.content_hash
    ):
        raise ConflictError("retained result batch evidence differs")


async def batches(db: AsyncSession, job: ReportJob) -> AsyncIterator[list[dict[str, Any]]]:
    if job.kind != "RUN" or job.status != "COMPLETE" or job.result is None:
        raise ConflictError("completed frozen report result required")
    if job.result.get("plan", {}).get("mode") == "PINNED_QUERY":
        require_retained_runtime(job)
        if job.result["plan"]["version"] == 2:
            from reports.runtimes.ledger_v2.context import NativeContext as CurrentContext
            from reports.runtimes.ledger_v2.parameters import RunRequest as CurrentRequest
            from reports.runtimes.ledger_v2.query import batches as current_batches

            current_context = await CurrentContext.load(db, job.company_id, job.generation_id)
            current_query = CurrentRequest.model_validate(
                job.parameters
                | {"generation_id": job.generation_id, "code": job.definition["code"]}
            )
            async for values in current_batches(db, current_context, current_query):
                yield values
            return
        context = await NativeContext.load(db, job.company_id, job.generation_id)
        query = RunRequest.model_validate(
            job.parameters
            | {
                "generation_id": job.generation_id,
                "code": job.definition["code"],
            }
        )
        async for values in ledger_batches(db, context, query):
            yield values
        return
    count, content = 0, hashlib.sha256()
    while True:
        batch = await db.scalar(
            select(ReportResultBatch)
            .where(
                ReportResultBatch.company_id == job.company_id,
                ReportResultBatch.job_id == job.id,
                ReportResultBatch.attempt == job.attempt,
                ReportResultBatch.first_ordinal > count,
            )
            .order_by(ReportResultBatch.first_ordinal)
            .limit(1)
        )
        if batch is None:
            break
        verify_batch(batch)
        if batch.first_ordinal != count + 1:
            raise ConflictError("retained result batch evidence differs")
        for row in batch.rows:
            content.update(canonical_json(row) + b"\n")
        count += batch.row_count
        yield batch.rows
    if count != job.result.get("row_count") or content.hexdigest() != job.result.get(
        "content_hash"
    ):
        raise ConflictError("retained result count or content differs")
