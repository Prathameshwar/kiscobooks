"""Bounded asynchronous result selection retains canonical balances and parent evidence."""

import asyncio
import hashlib
import itertools
import uuid
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.config import Settings
from reports.domain.reporting.contracts import QueryPlan, ResultManifest, fingerprint
from reports.domain.reporting.navigation import normalize, predicate, select_rows
from reports.models.framework import ReportJob
from reports.queries.results import batches
from reports.schemas.framework import ResultQuery
from reports.tasks import framework_jobs as jobs
from reports.tasks.capacity import CapacityExceededError
from reports.tasks.common import get
from reports.tasks.report_catalog import catalog

if TYPE_CHECKING:
    from reports.tasks.framework_worker import AuthorityProvider


async def process(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    job: ReportJob,
    authority: "AuthorityProvider",
) -> None:
    from reports.tasks.framework_worker import verify

    if job.origin is None or job.origin.get("mapping") != "result_query":
        raise ConflictError("result selection requires retained parent provenance")
    definition = catalog().resolve(job.definition["code"], job.definition["version"]).definition
    query = normalize(definition, ResultQuery.model_validate((job.options or {})["result_query"]))
    accept = predicate(definition, query)
    values: list[tuple[int, dict[str, Any]]] = []
    scanned, size = 0, 0
    maximum = min(settings.bulk_result_limit, (job.options or {})["result_limit"])
    async with factory() as db:
        parent = await get(db, job.company_id, ReportJob, uuid.UUID(job.origin["parent_id"]))
        if (
            parent.status != "COMPLETE"
            or parent.attempt != job.origin["parent_attempt"]
            or parent.generation_id != job.generation_id
            or parent.permission_hash != job.permission_hash
            or parent.actor_id != job.actor_id
            or fingerprint(parent.definition) != fingerprint(job.definition)
        ):
            raise ConflictError("result selection parent identity differs")
        async for batch in batches(db, parent):
            for row in batch:
                scanned += 1
                if scanned > settings.bulk_result_limit:
                    raise CapacityExceededError("result query exceeds its source row budget")
                if accept(row):
                    size += len(canonical_json(row))
                    if len(values) >= maximum or size > 32 * 1024 * 1024:
                        raise CapacityExceededError(
                            "result query exceeds its retained output budget"
                        )
                    values.append((scanned, row))
    selected = await asyncio.to_thread(select_rows, definition, query, values)
    content, count = hashlib.sha256(), 0
    for output_batch in itertools.batched(selected, 200):
        output = [row | {"_source_ordinal": ordinal} for ordinal, row in output_batch]
        proof = await authority(job)
        async with factory() as db, db.begin():
            verify(proof, job)
            await jobs.append(db, job.company_id, job.id, job.attempt, count + 1, output)
        for value in output:
            content.update(canonical_json(value) + b"\n")
        count += len(output)
    plan = QueryPlan(
        "result_selection",
        1,
        str(job.generation_id),
        "MATERIALIZED",
        definition.datasets,
        fingerprint(job.options),
        job.permission_hash,
        ("ordinal",),
        maximum,
    )
    result = ResultManifest(
        str(job.id),
        definition.identity,
        str(job.generation_id),
        plan,
        fingerprint(job.definition["views"]),
        count,
        content.hexdigest(),
    )
    proof = await authority(job)
    async with factory() as db, db.begin():
        verify(proof, job)
        await jobs.complete(
            db,
            job.company_id,
            job.id,
            job.attempt,
            asdict(result)
            | {
                "owner_manifest": (parent.result or {}).get("owner_manifest"),
                "selection": {
                    "parent_id": str(parent.id),
                    "parent_attempt": parent.attempt,
                    "parent_result_hash": fingerprint(parent.result),
                    "query": query.model_dump(mode="json"),
                    "source_rows": scanned,
                    "row_count": count,
                    "balance_semantics": "ORIGINAL_RESULT",
                    "reconciliation_scope": "PARENT_RESULT",
                },
                "evidence": {
                    "classification": "SELECTED_RESULT",
                    "row_count": count,
                    "parent_evidence": (parent.result or {}).get("evidence"),
                    "reconciliation_scope": "PARENT_RESULT",
                },
            },
        )
