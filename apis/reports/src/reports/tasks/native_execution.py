"""Native plan admission and retained implementation identity, separate from HTTP."""

import uuid
from dataclasses import asdict
from typing import Any

from billing_platform.errors import ConflictError
from reporting_contract.contract import Manifest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.config import Settings
from reports.domain.reporting.contracts import QueryPlan, ResultManifest, fingerprint
from reports.domain.reporting.views import select as select_view
from reports.models.framework import ReportJob
from reports.models.source_versions import ReportSourceCut, ReportSourceEpoch
from reports.queries.native_bank import CODES as BANK_CODES
from reports.queries.native_bank import execute as bank_execute
from reports.queries.native_context import NativeContext
from reports.queries.native_continuity import execute as continuity_execute
from reports.queries.native_invoices import CODES as INVOICE_CODES
from reports.queries.native_invoices import execute as invoice_execute
from reports.queries.native_ledger import CODES as CODES
from reports.queries.native_open_items import CODES as OPEN_ITEM_CODES
from reports.queries.native_open_items import aged, controls, positions
from reports.queries.native_open_items import execute as open_item_execute
from reports.queries.native_reconciliation import execute as reconciliation_execute
from reports.queries.native_statements import CODES as FINANCIAL_CODES
from reports.queries.native_statements import execute as financial_execute
from reports.queries.projection import QUERY_VERSION
from reports.runtimes import ledger_v1, ledger_v2
from reports.tasks.reference_source import source_count
from reports.tasks.report_catalog import catalog


def implementation_identity() -> str:
    return ledger_v2.identity()


async def enabled(
    db: AsyncSession, settings: Settings, company: uuid.UUID, generation: uuid.UUID, code: str
) -> bool:
    if not settings.native_queries_enabled or code not in (
        CODES
        | FINANCIAL_CODES
        | set(INVOICE_CODES)
        | OPEN_ITEM_CODES
        | BANK_CODES
        | {"SOURCE_RECONCILIATION", "BALANCE_CONTINUITY"}
    ):
        return False
    version = await db.scalar(
        select(ReportSourceEpoch.query_version)
        .join(
            ReportSourceCut,
            ReportSourceCut.epoch_id == ReportSourceEpoch.id,
        )
        .where(
            ReportSourceEpoch.company_id == company,
            ReportSourceCut.company_id == company,
            ReportSourceCut.generation_id == generation,
            ReportSourceCut.verification.is_not(None),
        )
    )
    return version == QUERY_VERSION


async def result(db: AsyncSession, job: ReportJob, manifest: Manifest) -> dict[str, Any]:
    entry = catalog().resolve(job.definition["code"], job.definition["version"])
    context = await NativeContext.load(db, job.company_id, job.generation_id)
    query = entry.handler.request(job.generation_id, job.parameters, context.coverage)
    await context.validate(db, query)
    if query.comparative_from and query.comparative_to:
        await context.validate(
            db,
            query.model_copy(
                update={
                    "date_from": query.comparative_from,
                    "date_to": query.comparative_to,
                }
            ),
        )
    plan = QueryPlan(
        "native_ledger",
        ledger_v2.VERSION,
        str(job.generation_id),
        "PINNED_QUERY",
        entry.definition.datasets,
        fingerprint(job.parameters),
        job.permission_hash,
        ("period", "phase", "date", "journal_id", "sequence", "line_id"),
        max(1, source_count(manifest) * 2),
    )
    retained = ResultManifest(
        str(job.id),
        entry.definition.identity,
        str(job.generation_id),
        plan,
        fingerprint([asdict(view) for view in entry.definition.views]),
    )
    from reports.domain.book_summaries import BOOK_CODES, BookSummary

    evidence: dict[str, Any] = {}
    if job.definition["code"] in BOOK_CODES:
        from reports.runtimes.ledger_v2.context import NativeContext as LedgerContext
        from reports.runtimes.ledger_v2.parameters import RunRequest as LedgerRequest
        from reports.runtimes.ledger_v2.query import batches

        summary = BookSummary(job.definition["code"])
        ledger_context = await LedgerContext.load(db, job.company_id, job.generation_id)
        ledger_query = LedgerRequest.model_validate(
            job.parameters | {"generation_id": job.generation_id, "code": job.definition["code"]}
        )
        async for values in batches(db, ledger_context, ledger_query):
            for value in values:
                summary.add(value)
        evidence["book_summary"] = summary.finish()
    value = asdict(retained) | {
        "logical_fingerprint": retained.logical_fingerprint,
        "implementation_identity": implementation_identity(),
        "owner_manifest": manifest.model_dump(mode="json"),
    }
    return value | ({"evidence": evidence} if evidence else {})


def require_retained_runtime(job: ReportJob) -> None:
    retained = job.result or {}
    if (
        retained.get("implementation_identity")
        != (
            ledger_v1.identity()
            if retained.get("plan", {}).get("version") == 1
            else ledger_v2.identity()
        )
        or fingerprint(job.definition) != retained.get("definition_identity")
        or retained.get("plan", {}).get("key") != "native_ledger"
        or retained.get("plan", {}).get("version") not in {1, 2}
    ):
        raise ConflictError("retained native query implementation is unavailable")


async def rows(
    db: AsyncSession,
    job: ReportJob,
    limit: int,
    cursor: dict[str, Any] | None,
    *,
    include_positions: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    require_retained_runtime(job)
    if (job.result or {})["plan"]["version"] == 1:
        return await ledger_v1.rows(
            db,
            job.company_id,
            job.generation_id,
            job.definition["code"],
            job.parameters,
            limit,
            cursor,
        )
    return await ledger_v2.rows(
        db,
        job.company_id,
        job.generation_id,
        job.definition["code"],
        job.parameters,
        limit,
        cursor,
        include_positions=include_positions,
    )


async def calculate(
    db: AsyncSession, job: ReportJob, maximum: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if job.definition["code"] == "SOURCE_RECONCILIATION":
        return await reconciliation_execute(db, job.company_id, job.generation_id, maximum)
    entry = catalog().resolve(job.definition["code"], job.definition["version"])
    context = await NativeContext.load(db, job.company_id, job.generation_id)
    query = entry.handler.request(job.generation_id, job.parameters, context.coverage)
    view = select_view(job.definition["views"], (job.options or {}).get("view", "default"))
    if view.get("calculation") == "party_balances":
        from decimal import Decimal, localcontext

        from reports.domain.statements import calculation_evidence

        await context.validate(db, query)
        source = positions(context, query)
        await controls(db, context, query, source)
        if query.code == "ADVANCES":
            source = source.where(source.selected_columns.direction == "CREDIT")
        values = await aged(db, source, query, maximum)
        with localcontext() as arithmetic:
            arithmetic.prec = 48
            rows = [
                value
                | {
                    "row_kind": "PARTY_BALANCE",
                    "account_code": context.data.accounts[value["account_id"]]["code"],
                    "account_name": context.data.accounts[value["account_id"]]["name"],
                    "period": "CURRENT",
                    "currency": query.currency or context.data.currency,
                    "net_debt": format(
                        Decimal(value["debt"]) - Decimal(value["unapplied_credit"]), ".4f"
                    ),
                }
                for value in values
            ]
        return rows, calculation_evidence(context.data, query, context.coverage, rows)
    if query.code == "BALANCE_CONTINUITY":
        return await continuity_execute(db, context, query, maximum)
    if query.code in INVOICE_CODES:
        return await invoice_execute(db, context, query, maximum)
    if query.code in OPEN_ITEM_CODES:
        return await open_item_execute(db, context, query, maximum)
    if query.code in BANK_CODES:
        return await bank_execute(db, context, query, maximum)
    if query.code == "TRIAL_BALANCE" and job.definition["version"] >= 6:
        from reports.queries.trial_balance import execute as trial_execute

        return await trial_execute(db, context, query, maximum)
    return await financial_execute(db, context, query, maximum)
