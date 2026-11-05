"""An export owns a separate attempt and cannot invalidate its completed source run."""

import asyncio
import json
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING

from billing_platform.display import DisplayConfiguration, date, number
from billing_platform.errors import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reports.config import Settings
from reports.domain.day_book import export_metadata
from reports.domain.reporting.contracts import Column
from reports.models.framework import ReportJob
from reports.queries.results import batches
from reports.rendering.analytics import metadata as analytics_metadata
from reports.rendering.html import HtmlWriter
from reports.rendering.packaged import PackageWriter
from reports.rendering.pdf import PdfWriter
from reports.rendering.presentation import Document
from reports.rendering.stock_summary import metadata as stock_metadata
from reports.rendering.tabular import Budget, CsvWriter, Writer, XlsxWriter
from reports.rendering.tax import metadata as tax_metadata
from reports.tasks import export_artifacts as artifacts
from reports.tasks import framework_jobs as jobs
from reports.tasks.common import get
from reports.tasks.framework_worker import supervised

if TYPE_CHECKING:
    from reports.tasks.framework_worker import AuthorityProvider


async def process(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    job: ReportJob,
    authority: "AuthorityProvider",
) -> None:
    from reports.tasks.framework_worker import verify

    if job.parent_id is None:
        raise ConflictError("export requires a completed report result")
    renderer = artifacts.definition(job.parameters["format"], settings)
    if job.parameters.get("renderer") != asdict(renderer):
        raise ConflictError("retained export renderer or budget is unavailable")
    storage = artifacts.store(settings)
    async with factory() as db:
        parent = await get(db, job.company_id, ReportJob, job.parent_id)
        views = [
            view for view in parent.definition["views"] if view["key"] == job.parameters["view"]
        ]
        if len(views) != 1 or parent.status != "COMPLETE":
            raise ConflictError("completed export view is unavailable")
        columns = tuple(Column(**value) for value in views[0]["columns"])
        balance_print = (
            parent.definition["code"] == "BALANCE_SHEET"
            and parent.definition["version"] == 6
            and job.parameters["view"] == "default"
            and renderer.format in {"PDF", "HTML"}
        )
        if balance_print:
            if job.parameters.get("delivery") == "PACKAGE":
                raise ConflictError("Standard Balance Sheet print requires a single document")
            from reports.rendering.balance_sheet import PRINT_COLUMNS

            columns = PRINT_COLUMNS
        trial_selection = None
        if parent.definition["code"] == "TRIAL_BALANCE" and parent.definition["version"] == 6:
            from reports.queries.trial_presentation import validate as validate_trial
            from reports.rendering.trial_balance import Selection
            from reports.rendering.trial_balance import columns as trial_columns
            from reports.schemas.trial_balance_options import TrialPresentation

            options = TrialPresentation.model_validate(job.parameters.get("trial_balance", {}))
            await validate_trial(db, parent, options)
            trial_selection = Selection(options)
            columns = trial_columns(columns, renderer.format)
        document = None
        if renderer.format in {"HTML", "PDF", "XLSX"} and "company_label" in parent.display:
            display = DisplayConfiguration.model_validate(parent.display)
            period = "All retained periods"
            end = parent.parameters.get("date_to") or parent.parameters.get("as_of")
            if end:
                cumulative = parent.definition["code"] in {
                    "BANK_RECONCILIATION",
                    "INVOICE_SETTLEMENT_REGISTER",
                    "BALANCE_SHEET",
                }
                period = (
                    "As of " if cumulative or parent.parameters.get("as_of") else "Through "
                ) + date(end, display)
                if parent.parameters.get("date_from") and not cumulative:
                    period = (
                        date(parent.parameters["date_from"], display)
                        + " \u2013 "
                        + date(end, display)
                    )
            sequence = (parent.result or {}).get("owner_manifest", {}).get("sequence")
            if type(sequence) is not int or sequence < 0:
                raise ConflictError("retained report source provenance is unavailable")
            document = Document(
                parent.definition["title"]
                + (" - Selected rows" if (parent.result or {}).get("selection") else ""),
                display,
                period,
                f"Accounting sequence {sequence}; generation {parent.generation_id}",
                str(parent.id),
                views[0]["layout"],
                analytics_metadata(parent.result["evidence"], parent.parameters, display)
                if parent.result and "analytics" in parent.result.get("evidence", {})
                else tax_metadata(parent.result["evidence"], parent.parameters, display)
                if parent.result and "tax_summary" in parent.result.get("evidence", {})
                else stock_metadata(parent.result["evidence"], display, parent.parameters)
                if parent.result and "inventory_coverage" in parent.result.get("evidence", {})
                else export_metadata(
                    parent.parameters, parent.result["evidence"]["day_book"], display
                )
                if parent.definition["code"] == "DAY_BOOK_ACTIVITY" and parent.result
                else tuple(
                    (key.replace("_", " ").title(), json.dumps(value, ensure_ascii=False))
                    for key, value in parent.parameters.items()
                    if value is not None and key not in {"code", "date_from", "date_to"}
                ),
                orientation=views[0].get("orientation", "AUTO"),
                category="Business analytics"
                if parent.result and "analytics" in parent.result.get("evidence", {})
                else "Tax report"
                if parent.result and "tax_summary" in parent.result.get("evidence", {})
                else "Inventory report"
                if parent.result and "inventory_coverage" in parent.result.get("evidence", {})
                else "Financial report",
            )
            if parent.definition["code"] == "PROFIT_LOSS" and parent.definition["version"] == 6:
                summary = (parent.result or {}).get("evidence", {}).get("profit_summary", {})
                imported = summary.get("imported_ytd", {})
                document = replace(
                    document,
                    filters=(
                        *document.filters,
                        ("View", views[0]["title"]),
                        (
                            "Zero accounts",
                            "Shown" if parent.parameters.get("show_zero") else "Hidden",
                        ),
                        (
                            "Imported YTD",
                            "Included in labelled account amounts; earlier detail unavailable"
                            if any(imported.values())
                            else "Not included",
                        ),
                    ),
                )
            if parent.definition["code"] == "BALANCE_SHEET" and parent.definition["version"] == 6:
                document = replace(
                    document,
                    period="As at " + date(parent.parameters["date_to"], display),
                    filters=(
                        ("View", views[0]["title"]),
                        (
                            "Comparison date",
                            date(parent.parameters["comparative_to"], display)
                            if parent.parameters.get("comparative_to")
                            else "None",
                        ),
                        (
                            "Zero accounts",
                            "Shown" if parent.parameters.get("show_zero") else "Hidden",
                        ),
                        (
                            "Balance check",
                            "Assets equal liabilities and equity, including earnings",
                        ),
                        (
                            "Totals",
                            "Sections and groups include detail; do not add overlapping rows.",
                        ),
                        ("Basis", "Management Balance Sheet; company base currency"),
                    ),
                    column_groups=(("Liabilities and equity", 3), ("Assets", 3))
                    if balance_print
                    else (),
                )
            if trial_selection is not None:
                from reports.queries.hierarchy import summaries

                options = trial_selection.options
                residual = summaries(parent)[options.period].display_residual
                rounding = "; ".join(
                    column.title + " " + number(residual[column.key], display)
                    for column in columns
                    if column.key in residual
                )
                document = replace(
                    document,
                    column_groups=(
                        ("Account / group", 1),
                        ("Opening balance", 2),
                        ("Period movement", 2),
                        ("Closing balance", 2),
                        ("Currency", 1),
                    )
                    if job.parameters["view"] == "detailed" and renderer.format in {"HTML", "PDF"}
                    else (),
                    filters=(
                        ("Layout", views[0]["title"]),
                        (
                            "Hierarchy",
                            "All ledgers" if options.hierarchy == "ALL" else "Current hierarchy",
                        ),
                        ("Statement period", options.period.title()),
                        ("Zero rows", "Shown" if options.show_zero else "Quiet rows hidden"),
                        ("Totals", "Full-company account totals; parent rows overlap descendants."),
                    )
                    + (
                        (
                            (
                                "Display rounding",
                                "Totals minus rounded ledger sums: "
                                + rounding
                                + ". Exact balances reconcile.",
                            ),
                        )
                        if rounding
                        else ()
                    ),
                )
    async with factory() as db, db.begin():
        artifact = await artifacts.begin(db, job, renderer)
    path = await asyncio.to_thread(storage.begin, artifact.storage_key)
    writer: Writer | None = None
    finished = False
    last_pulse = time.monotonic()

    async def pulse() -> None:
        proof = await authority(job)
        async with factory() as db, db.begin():
            verify(proof, job)
            await jobs.heartbeat(db, job.company_id, job.id, job.attempt)

    try:
        budget = Budget(
            renderer.max_rows, renderer.max_cells, renderer.max_bytes, renderer.timeout_seconds
        )
        if job.parameters.get("delivery") == "PACKAGE" and document is not None:
            policy = job.parameters["package"]
            budget = replace(
                budget,
                rows=min(
                    budget.rows,
                    job.parameters.get("part_rows")
                    or (1000 if renderer.format == "PDF" else 10000),
                ),
            )

            def part(output: Path, limits: Budget, first: int) -> Writer:
                assert document is not None
                selected = replace(
                    document, first_ordinal=first, title=document.title + f" — Rows from {first}"
                )
                if renderer.format == "PDF":
                    return PdfWriter(output, columns, limits, selected)
                return HtmlWriter(output, columns, limits, selected)

            writer = PackageWriter(
                path,
                columns,
                Budget(
                    policy["max_rows"],
                    policy["max_rows"] * len(columns),
                    policy["max_bytes"],
                    policy["timeout_seconds"],
                ),
                budget,
                renderer.format,
                part,
                {
                    "run_id": str(parent.id),
                    "generation_id": str(parent.generation_id),
                    "definition_identity": (parent.result or {}).get("definition_identity"),
                    "view": job.parameters["view"],
                    "source": (parent.result or {}).get("owner_manifest"),
                    "columns": views[0]["columns"],
                },
                policy["max_parts"],
            )
        elif renderer.format == "CSV":
            writer = CsvWriter(path, columns, budget)
        elif renderer.format in {"PDF", "XLSX"} and parent.definition["code"] in {
            "GSTR3B",
            "GSTR1",
        }:
            if parent.result is None:
                raise ConflictError("frozen GST preparation is unavailable")
            if parent.definition["code"] == "GSTR1":
                from reports.rendering.gstr1 import GstOutwardPdfWriter, GstOutwardXlsxWriter

                preparation = parent.result["evidence"]["gstr1"]
                if renderer.format == "PDF" and document is not None:
                    writer = GstOutwardPdfWriter(path, columns, budget, document, preparation)
                elif renderer.format == "XLSX":
                    writer = GstOutwardXlsxWriter(path, columns, budget, document, preparation)
                else:
                    raise ConflictError("GSTR-1 statutory presentation is unavailable")
            else:
                from reports.rendering.gstr3b import GstPdfWriter, GstXlsxWriter

                preparation = parent.result["evidence"]["gstr3b"]
                if renderer.format == "PDF" and document is not None:
                    writer = GstPdfWriter(path, columns, budget, document, preparation)
                elif renderer.format == "XLSX":
                    writer = GstXlsxWriter(path, columns, budget, document, preparation)
                else:
                    raise ConflictError("GSTR-3B statutory presentation is unavailable")
        elif renderer.format == "XLSX":
            writer = XlsxWriter(path, columns, budget, document)
        elif renderer.format == "HTML" and document is not None:
            writer = HtmlWriter(path, columns, budget, document)
        elif renderer.format == "PDF" and document is not None:
            writer = PdfWriter(path, columns, budget, document)
        else:
            raise ConflictError("requested export renderer is unavailable")
        if balance_print:
            from reports.rendering.balance_sheet import BalanceSheetWriter

            writer = BalanceSheetWriter(writer, budget)
        async with factory() as db:
            async for values in batches(db, parent):
                if trial_selection is not None:
                    values = trial_selection.rows(values)
                if parent.definition["code"] == "GSTR1":
                    from reports.rendering.gstr1 import export_rows

                    values = export_rows(values, columns)
                await supervised(asyncio.to_thread(writer.append, values), pulse)
                if time.monotonic() - last_pulse >= 5:
                    await pulse()
                    last_pulse = time.monotonic()
        await pulse()
        await supervised(asyncio.to_thread(writer.finish), pulse)
        finished = True
        maximum_bytes = job.parameters.get("package", {}).get("max_bytes", renderer.max_bytes)
        output = await supervised(
            asyncio.to_thread(storage.publish, artifact.storage_key, maximum_bytes),
            pulse,
        )
        proof = await authority(job)
        async with factory() as db, db.begin():
            verify(proof, job)
            await artifacts.publish(db, job, artifact.id, output, writer.count)
    finally:
        if writer is not None and not finished:
            writer.abort()
        # Filesystem failure here must not turn a successfully published export into a retry.
        try:
            await asyncio.to_thread(storage.discard_temporary, artifact.storage_key)
        except OSError:
            pass  # The scoped temporary cleanup command retries this after terminal completion.
