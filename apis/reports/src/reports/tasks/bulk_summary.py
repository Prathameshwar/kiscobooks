"""Period-sized native calculation with immutable batches and fenced checkpoint replay."""

import datetime as dt
import hashlib
import itertools
from collections.abc import Iterator
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from reporting_contract.contract import Manifest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.config import Settings
from reports.domain.reporting.contracts import QueryPlan, ResultManifest, fingerprint
from reports.domain.statements import calculation_evidence
from reports.models.core import ReportGeneration
from reports.models.framework import ReportJob, ReportResultBatch
from reports.queries.native_context import NativeContext
from reports.queries.native_statements import execute
from reports.queries.results import verify_batch
from reports.schemas.requests import RunRequest
from reports.tasks import framework_jobs as jobs
from reports.tasks.capacity import CapacityExceededError
from reports.tasks.common import get
from reports.tasks.report_catalog import catalog

if TYPE_CHECKING:
    from reports.tasks.framework_worker import AuthorityProvider


def units(query: RunRequest) -> Iterator[tuple[RunRequest, str]]:
    for phase, start, end in (
        ("CURRENT", query.date_from, query.date_to),
        ("COMPARATIVE", query.comparative_from, query.comparative_to),
    ):
        if start is None or end is None:
            continue
        while start <= end:
            stop = start
            if query.grain == "MONTH":
                following = (
                    dt.date(start.year + 1, 1, 1)
                    if start.month == 12 and start.year < 9999
                    else dt.date(start.year, start.month + 1, 1)
                    if start.month < 12
                    else None
                )
                stop = min(end, following - dt.timedelta(days=1)) if following else end
            yield (
                query.model_copy(
                    update={
                        "date_from": start,
                        "date_to": stop,
                        "comparative_from": None,
                        "comparative_to": None,
                    }
                ),
                phase,
            )
            if stop == end:
                break
            start = stop + dt.timedelta(days=1)


async def process(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    job: ReportJob,
    authority: "AuthorityProvider",
) -> None:
    from reports.tasks.framework_worker import supervised, verify

    entry = catalog().resolve(job.definition["code"], job.definition["version"])
    if job.definition["code"] != "ACCOUNT_SUMMARY":
        raise ConflictError("bulk summary definition is unavailable")
    maximum = min(
        (job.options or {}).get("result_limit", settings.bulk_result_limit),
        settings.bulk_result_limit,
    )
    async with factory() as db:
        generation = await get(db, job.company_id, ReportGeneration, job.generation_id)
        if generation.status != "READY" or generation.manifest is None:
            raise ConflictError("bulk summary requires a ready frozen source")
        manifest = Manifest.model_validate(generation.manifest)
        context = await NativeContext.load(db, job.company_id, job.generation_id)
        query = entry.handler.request(job.generation_id, job.parameters, context.coverage)
        await context.validate(db, query)
        if query.comparative_from and query.comparative_to:
            await context.validate(
                db,
                query.model_copy(
                    update={"date_from": query.comparative_from, "date_to": query.comparative_to}
                ),
            )
    accounts = context.accounts(query)
    groups = {
        group
        for account in accounts
        for group in context.data.ancestry(context.data.accounts[str(account)]["group_id"])
    }
    cardinality = len(accounts) + len(groups)

    def period_count(start: dt.date | None, end: dt.date | None) -> int:
        if start is None or end is None:
            return 0
        return (
            (end - start).days + 1
            if query.grain == "DAY"
            else (end.year - start.year) * 12 + end.month - start.month + 1
        )

    periods = period_count(query.date_from, query.date_to) + period_count(
        query.comparative_from, query.comparative_to
    )
    if cardinality * periods > maximum:
        raise CapacityExceededError("bulk summary exceeds its total row budget")
    binding = fingerprint(
        {
            "definition": job.definition,
            "generation": str(job.generation_id),
            "parameters": job.parameters,
            "options": job.options,
        }
    )
    checkpoint = job.checkpoint or {}
    count, next_unit, content = 0, 0, hashlib.sha256()

    async def pulse() -> None:
        proof = await authority(job)
        async with factory() as db, db.begin():
            verify(proof, job)
            await jobs.heartbeat(db, job.company_id, job.id, job.attempt)

    async def append(values: list[dict[str, Any]]) -> None:
        nonlocal count
        if count + len(values) > maximum:
            raise CapacityExceededError("bulk summary exceeds its total row budget")
        proof = await authority(job)
        async with factory() as db, db.begin():
            verify(proof, job)
            await jobs.append(db, job.company_id, job.id, job.attempt, count + 1, values)
        for value in values:
            content.update(canonical_json(value) + b"\n")
        count += len(values)

    if checkpoint:
        if (
            checkpoint.get("binding") != binding
            or type(checkpoint.get("row_count")) is not int
            or type(checkpoint.get("next_unit")) is not int
            or not 0 <= checkpoint["next_unit"] <= periods
            or not 0 <= checkpoint["row_count"] <= maximum
            or type(checkpoint.get("attempt")) is not int
            or not 0 < checkpoint["attempt"] < job.attempt
        ):
            raise ConflictError("bulk checkpoint identity is invalid")
        while count < checkpoint["row_count"]:
            async with factory() as db:
                batch = await db.scalar(
                    select(ReportResultBatch).where(
                        ReportResultBatch.company_id == job.company_id,
                        ReportResultBatch.job_id == job.id,
                        ReportResultBatch.attempt == checkpoint["attempt"],
                        ReportResultBatch.first_ordinal == count + 1,
                    )
                )
                if batch is None or count + batch.row_count > checkpoint["row_count"]:
                    raise ConflictError("bulk checkpoint batch continuity differs")
                verify_batch(batch)
                values = batch.rows
            await append(values)
        if content.hexdigest() != checkpoint.get("content_hash"):
            raise ConflictError("bulk checkpoint content differs")
        next_unit = checkpoint["next_unit"]
        if count != next_unit * cardinality:
            raise ConflictError("bulk checkpoint period count differs")

    async def mark(unit: int) -> None:
        proof = await authority(job)
        async with factory() as db, db.begin():
            verify(proof, job)
            owned = await jobs.owned(db, job.company_id, job.id, job.attempt)
            if owned.completed_rows != count:
                raise ConflictError("bulk checkpoint count differs")
            owned.checkpoint = {
                "binding": binding,
                "attempt": job.attempt,
                "next_unit": unit,
                "row_count": count,
                "content_hash": content.hexdigest(),
            }

    if next_unit:
        await mark(next_unit)
    for index, (unit, phase) in enumerate(
        itertools.islice(units(query), next_unit, None) if cardinality else [], next_unit
    ):
        async with factory() as db:
            boundary = query.comparative_from if phase == "COMPARATIVE" else query.date_from
            values, _ = await supervised(
                execute(db, context, unit, 100000, opening_boundary=boundary), pulse
            )
        if phase == "COMPARATIVE":
            values = [value | {"period": phase} for value in values]
        for output_batch in itertools.batched(values, 200):
            await append(list(output_batch))
        await mark(index + 1)
    plan = QueryPlan(
        "bulk_account_summary",
        1,
        str(job.generation_id),
        "MATERIALIZED",
        entry.definition.datasets,
        fingerprint({"parameters": job.parameters, "options": job.options}),
        job.permission_hash,
        ("period", "date", "row_kind", "ordinal"),
        maximum,
    )
    result = ResultManifest(
        str(job.id),
        entry.definition.identity,
        str(job.generation_id),
        plan,
        fingerprint(job.definition["views"]),
        count,
        content.hexdigest(),
    )
    evidence = calculation_evidence(context.data, query, context.coverage, []) | {
        "row_count": count
    }
    proof = await authority(job)
    async with factory() as db, db.begin():
        verify(proof, job)
        await jobs.complete(
            db,
            job.company_id,
            job.id,
            job.attempt,
            asdict(result)
            | {"evidence": evidence, "owner_manifest": manifest.model_dump(mode="json")},
        )
