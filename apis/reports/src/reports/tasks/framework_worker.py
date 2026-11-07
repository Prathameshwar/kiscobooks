"""Process-owned execution over frozen input; authority and leases gate every publication."""

import asyncio
import hashlib
import itertools
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import asdict
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.errors import (
    ConflictError,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.idempotency import canonical_json
from reporting_contract.authority import ReportAuthority, fetch_authority, require_authority
from reporting_contract.contract import Manifest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.config import Settings
from reports.domain.reporting.contracts import QueryPlan, ResultManifest, fingerprint
from reports.domain.reporting.history_coverage import InsufficientHistoryError
from reports.domain.reporting.views import party_balances
from reports.domain.reporting.views import select as select_view
from reports.models.core import ReportGeneration
from reports.models.framework import ReportJob
from reports.tasks import framework_jobs as jobs
from reports.tasks import native_execution
from reports.tasks.capacity import CapacityExceededError
from reports.tasks.common import get
from reports.tasks.reference_source import load
from reports.tasks.report_catalog import catalog

AuthorityProvider = Callable[[ReportJob], Awaitable[ReportAuthority]]
PULSE_SECONDS = 5.0


class ImplementationUnavailableError(ValueError):
    """A deployment mismatch cannot be repaired by refreshing accounting data."""


async def supervised[T](
    operation: Coroutine[Any, Any, T], pulse: Callable[[], Awaitable[None]]
) -> T:
    """Renew ownership during work; join thread-backed operations before their cleanup."""
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=PULSE_SECONDS)
            if not task.done():
                await pulse()
        return await task
    finally:
        if not task.done():
            await asyncio.shield(task)


def permissions(row: ReportJob) -> frozenset[str]:
    return frozenset(row.definition["permissions"]) | (
        {"report.export"} if row.kind == "EXPORT" else set()
    )


def verify(proof: ReportAuthority, row: ReportJob) -> None:
    require_authority(
        proof,
        tenant=row.tenant_id,
        company=row.company_id,
        actor=row.actor_id,
        permissions=permissions(row),
    )


async def process(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    tenant: uuid.UUID,
    company: uuid.UUID,
    identity: uuid.UUID,
    authority: AuthorityProvider,
) -> None:
    """Calculate without job locks; authority pulses use separate short transactions."""
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            job = await jobs.claim(db, company, identity)
            if job is None:
                return
            attempt = job.attempt

        async def pulse() -> None:
            proof = await authority(job)
            async with factory() as db, db.begin():
                verify(proof, job)
                await jobs.heartbeat(db, company, identity, attempt)

        try:
            proof = await authority(job)
            verify(proof, job)
            if job.kind == "EXPORT":
                from reports.tasks.export_worker import process as export

                await export(factory, settings, job, authority)
                return
            entry = catalog().resolve(job.definition["code"], job.definition["version"])
            if fingerprint(job.definition) != entry.definition.identity:
                raise ImplementationUnavailableError(
                    "retained calculation implementation is unavailable"
                )
            if (job.options or {}).get("result_query") is not None:
                from reports.tasks.result_query import process as result_query

                async with asyncio.timeout(settings.bulk_timeout_seconds):
                    await supervised(result_query(factory, settings, job, authority), pulse)
                return
            if (job.options or {}).get("execution") == "BULK":
                from reports.tasks.bulk_summary import process as bulk

                async with asyncio.timeout(settings.bulk_timeout_seconds):
                    await supervised(bulk(factory, settings, job, authority), pulse)
                return
            async with factory() as db:
                generation = await get(db, company, ReportGeneration, job.generation_id)
                if generation.status != "READY" or generation.manifest is None:
                    raise ValueError("source generation is unavailable")
                manifest = Manifest.model_validate(generation.manifest)
                native = await native_execution.enabled(
                    db, settings, company, job.generation_id, job.definition["code"]
                )
                retained = None
                calculated = None
                from reports.domain.reporting.inventory import CODES as INVENTORY_CODES
                from reports.tasks.analytics_catalog import CODES as ANALYTICS_CODES

                if job.definition["code"] in ANALYTICS_CODES:
                    from reports.tasks.analytics_source import execute as analytics_execute

                    calculated = await supervised(
                        analytics_execute(db, generation, job, settings.native_result_limit), pulse
                    )
                elif job.definition["code"] in {"GSTR3B", "GSTR1"}:
                    if job.definition["code"] == "GSTR1":
                        from reports.tasks.gstr1_source import execute as gst_execute
                    else:
                        from reports.tasks.gstr3b_source import execute as gst_execute
                    calculated = await supervised(
                        gst_execute(db, generation, job, settings.native_result_limit), pulse
                    )
                elif job.definition["code"] in INVENTORY_CODES:
                    from reports.tasks.inventory_source import execute as inventory_execute

                    calculated = await supervised(
                        inventory_execute(db, generation, job, settings.native_result_limit), pulse
                    )
                elif native:
                    if job.definition["code"] in native_execution.CODES:
                        retained = await supervised(
                            native_execution.result(db, job, manifest), pulse
                        )
                    else:
                        calculated = await supervised(
                            native_execution.calculate(db, job, settings.native_result_limit),
                            pulse,
                        )
            if retained is not None:
                proof = await authority(job)
                async with factory() as db, db.begin():
                    verify(proof, job)
                    await jobs.complete(db, company, identity, attempt, retained)
                return
            if calculated is None:
                async with factory() as db:
                    facts = await supervised(
                        load(db, generation, settings.reference_fact_limit), pulse
                    )
                rows, evidence = await supervised(
                    asyncio.to_thread(
                        entry.handler.execute,
                        facts,
                        job.generation_id,
                        job.parameters,
                        manifest.control,
                    ),
                    pulse,
                )
                del facts
                view = select_view(
                    job.definition["views"], (job.options or {}).get("view", "default")
                )
                if view.get("calculation") == "party_balances":
                    rows = party_balances(rows)
                    evidence["row_count"] = len(rows)
                result_limit, plan_key = settings.reference_fact_limit, "reference"
            else:
                rows, evidence = calculated
                result_limit, plan_key = settings.native_result_limit, "native_financial"
            if job.definition["code"] == "INVOICE_CREDIT_REGISTER":
                from reports.domain.tax_summaries import credit_view
                from reports.domain.tax_summaries import summarize as tax_summary

                chosen = select_view(
                    job.definition["views"], (job.options or {}).get("view", "default")
                )
                calculation = chosen.get("calculation", "detail")
                rows = credit_view(rows, calculation)
                evidence["row_count"] = len(rows)
                evidence["tax_summary"] = tax_summary("INVOICE_CREDIT_REGISTER", rows) | {
                    "mode": {"credit_positions": "POSITIONS", "credit_events": "EVENTS"}.get(
                        calculation, "BOTH"
                    )
                }
            if job.definition["code"] == "BALANCE_SHEET" and job.definition["version"] == 6:
                from reports.domain.reporting.balance_views import present as balance_present

                rows, summary = balance_present(
                    rows,
                    comparison=(job.options or {}).get("view") == "comparison",
                    show_zero=bool(job.parameters.get("show_zero", False)),
                )
                evidence["balance_summary"] = summary
                evidence["row_count"] = len(rows)
            if job.definition["code"] == "PROFIT_LOSS" and job.definition["version"] == 6:
                from reports.domain.reporting.profit_views import present

                selected = select_view(
                    job.definition["views"], (job.options or {}).get("view", "default")
                )
                comparing = selected.get("calculation") == "profit_comparison"
                rows, summary = present(
                    rows,
                    comparison=comparing,
                    show_zero=bool(job.parameters.get("show_zero", False)),
                )
                evidence["profit_summary"] = summary
                evidence["row_count"] = len(rows)
            from reports.domain.book_summaries import summarize

            if job.definition["code"] == "TRIAL_BALANCE" and job.definition["version"] == 6:
                from billing_platform.display import DisplayConfiguration

                from reports.domain.trial_balance import display_residuals

                display = DisplayConfiguration.model_validate(job.display)
                display_residuals(rows, evidence, display.amount_precision, display.rounding_mode)

            book_summary = summarize(job.definition["code"], rows)
            if book_summary is not None:
                evidence["book_summary"] = book_summary
            if len(rows) > result_limit:
                raise ValueError("result exceeds enabled plan capacity")
            content = hashlib.sha256()
            count = 0
            for batch in itertools.batched(rows, 200):
                # Refresh outside SQL, then check its lifetime again inside the publication unit.
                proof = await authority(job)
                async with factory() as db, db.begin():
                    verify(proof, job)
                    await jobs.append(db, company, identity, attempt, count + 1, list(batch))
                for row in batch:
                    content.update(canonical_json(row) + b"\n")
                count += len(batch)
            plan = QueryPlan(
                plan_key,
                1,
                str(job.generation_id),
                "MATERIALIZED",
                entry.definition.datasets,
                fingerprint({"parameters": job.parameters, "options": job.options}),
                job.permission_hash,
                ("ordinal",),
                result_limit,
            )
            result = ResultManifest(
                str(identity),
                entry.definition.identity,
                str(job.generation_id),
                plan,
                fingerprint([asdict(view) for view in entry.definition.views]),
                count,
                content.hexdigest(),
            )
            proof = await authority(job)
            async with factory() as db, db.begin():
                verify(proof, job)
                await jobs.complete(
                    db,
                    company,
                    identity,
                    attempt,
                    asdict(result)
                    | {
                        "logical_fingerprint": result.logical_fingerprint,
                        "evidence": evidence,
                        "owner_manifest": manifest.model_dump(mode="json"),
                    },
                )
        except (PlatformError, ValueError, KeyError, httpx.HTTPError, OSError) as exc:
            blocked = isinstance(
                exc,
                PermissionDeniedError
                | ValueError
                | KeyError
                | ConflictError
                | ValidationFailedError,
            )
            code = (
                "AUTHORITY_REVOKED"
                if isinstance(exc, PermissionDeniedError)
                else (
                    "REPORT_CAPACITY_EXCEEDED"
                    if isinstance(exc, CapacityExceededError)
                    else (
                        "REPORT_IMPLEMENTATION_UNAVAILABLE"
                        if isinstance(exc, ImplementationUnavailableError)
                        else "INSUFFICIENT_ACCOUNTING_HISTORY"
                        if isinstance(exc, InsufficientHistoryError)
                        else "REPORT_VERIFICATION_FAILED"
                        if blocked
                        else "DEPENDENCY_UNAVAILABLE"
                    )
                )
            )
            # Cancellation or another worker may already have invalidated this lease.
            try:
                async with factory() as db, db.begin():
                    await jobs.fail(db, company, identity, attempt, code, blocked=blocked)
                if not blocked:
                    async with factory() as db, db.begin():
                        await jobs.retry(db, company, identity)
            except (ConflictError, jobs.QuotaExceededError):
                return


async def execute(
    settings: Settings, tenant: uuid.UUID, company: uuid.UUID, identity: uuid.UUID
) -> None:
    from billing_platform.db import create_engine, create_session_factory

    engine = create_engine(settings.database_url)
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:

            async def authority(row: ReportJob) -> ReportAuthority:
                source = next(
                    (
                        item
                        for item in settings.authority_sources
                        if item.allow_enrolled_companies
                        or any(
                            scope.tenant_id == tenant and scope.company_id == company
                            for scope in item.scopes
                        )
                    ),
                    None,
                )
                if source is None:
                    raise PermissionDeniedError("worker authority source is not configured")
                return await fetch_authority(
                    client,
                    source,
                    tenant=tenant,
                    company=company,
                    actor=row.actor_id,
                    permissions=permissions(row),
                )

            await process(
                create_session_factory(engine, guarded=True),
                settings,
                tenant,
                company,
                identity,
                authority,
            )
    finally:
        await engine.dispose()
