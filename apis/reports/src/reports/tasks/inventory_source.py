"""Read only indexed stock evidence from a verified generation; no cross-service SQL."""

import datetime as dt
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.reporting.inventory import calculate
from reports.models.core import ReportFact, ReportGeneration
from reports.models.framework import ReportJob
from reports.models.posted_lines import ReportPostedLine
from reports.models.source_versions import ReportFactVersion, ReportSourceCut
from reports.queries.source_versions import SourceView, bounded_rows
from reports.tasks.capacity import CapacityExceededError

BALANCE_KINDS = ("COVERAGE", "ITEM", "LOCATION", "GROUP", "POSITION", "GL_CONTROL")


async def balance_budget_count(db: AsyncSession, generation: ReportGeneration, maximum: int) -> int:
    cut = await db.scalar(
        select(ReportSourceCut).where(
            ReportSourceCut.company_id == generation.company_id,
            ReportSourceCut.generation_id == generation.id,
        )
    )
    if cut is None or cut.verification is None:
        return maximum + 1
    view = SourceView(generation.company_id, cut.epoch_id, cut.sequence)
    return len(
        list(
            await db.scalars(
                view.rows("inventory_report_record")
                .with_only_columns(
                    ReportFactVersion.id,
                )
                .where(ReportFactVersion.inventory_kind.in_(BALANCE_KINDS))
                .limit(maximum + 1)
            )
        )
    )


async def verify_gl(
    db: AsyncSession,
    generation: ReportGeneration,
    values: list[dict[str, Any]],
    maximum: int,
) -> None:
    """Independently bind the stock bridge to the same generation's financial ledger."""
    import uuid
    from collections import defaultdict

    coverage = [value["payload"] for value in values if value["payload"]["kind"] == "COVERAGE"]
    if len(coverage) != 1 or not coverage[0]["gl_complete"]:
        return
    controls = {
        value["payload"]["account_id"]: value["payload"]
        for value in values
        if value["payload"]["kind"] == "GL_CONTROL"
    }
    if not controls:
        # Empty inventory can have empty controls; mapping checks run in the domain.
        return
    identities = [uuid.UUID(key) for key in controls]
    cut = await db.scalar(
        select(ReportSourceCut).where(
            ReportSourceCut.company_id == generation.company_id,
            ReportSourceCut.generation_id == generation.id,
        )
    )
    totals: dict[str, Decimal] = defaultdict(Decimal)
    as_of = coverage[0]["as_of"]
    if cut is not None:
        view = SourceView(generation.company_id, cut.epoch_id, cut.sequence)
        accounts = await view.lookup(db, "account", identities)
        if set(accounts) != set(identities):
            raise ConflictError("inventory control account is outside the frozen financial source")
        p = ReportPostedLine
        query = (
            select(p.account_id, p.side, cast(func.sum(p.base_amount), Numeric(38, 4)))
            .where(
                p.company_id == generation.company_id,
                p.epoch_id == cut.epoch_id,
                p.valid_from_sequence <= cut.sequence,
                p.posting_date <= dt.date.fromisoformat(as_of),
                p.account_id.in_(identities),
                p.base_currency == coverage[0]["currency"],
            )
            .group_by(p.account_id, p.side)
        )
        for identity, side, value in await db.execute(query):
            if not isinstance(value, Decimal):
                raise ConflictError("stock-to-GL aggregate must be exact")
            totals[str(identity)] += value if side == "DEBIT" else -value
    else:
        legacy_accounts = set(
            await db.scalars(
                select(ReportFact.source_id).where(
                    ReportFact.company_id == generation.company_id,
                    ReportFact.generation_id == generation.id,
                    ReportFact.entity == "account",
                    ReportFact.source_id.in_(identities),
                    ReportFact.data.is_not(None),
                )
            )
        )
        if legacy_accounts != set(identities):
            raise ConflictError("inventory control account is outside the frozen financial source")
        lines = list(
            await db.scalars(
                select(ReportFact)
                .where(
                    ReportFact.company_id == generation.company_id,
                    ReportFact.generation_id == generation.id,
                    ReportFact.entity == "journal_line",
                    ReportFact.data["account_id"].as_string().in_(controls),
                )
                .limit(maximum + 1)
            )
        )
        if len(lines) > maximum:
            raise CapacityExceededError("stock-to-GL reference source exceeds its bound")
        journals = {uuid.UUID(row.data["journal_id"]) for row in lines if row.data}
        posted = (
            {
                str(row.source_id)
                for row in await db.scalars(
                    select(ReportFact).where(
                        ReportFact.company_id == generation.company_id,
                        ReportFact.generation_id == generation.id,
                        ReportFact.entity == "journal",
                        ReportFact.source_id.in_(journals),
                        ReportFact.data["status"].as_string() == "POSTED",
                        ReportFact.data["posting_date"].as_string() <= as_of,
                    )
                )
            }
            if journals
            else set()
        )
        for row in lines:
            data = row.data
            if data and data["journal_id"] in posted:
                if data["base_currency"] != coverage[0]["currency"]:
                    raise ConflictError("stock-to-GL base currency differs")
                value = Decimal(data["base_amount"])
                totals[data["account_id"]] += value if data["side"] == "DEBIT" else -value
    if any(
        totals[key] != Decimal(value["balance"]) or value["currency"] != coverage[0]["currency"]
        for key, value in controls.items()
    ):
        raise ConflictError("stock GL control differs from frozen financial ledger")


async def records(
    db: AsyncSession,
    generation: ReportGeneration,
    code: str,
    maximum: int,
    *,
    include_history: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    movement = code in {"ITEM_LEDGER", "STOCK_MOVEMENT"} or include_history
    cut = await db.scalar(
        select(ReportSourceCut).where(
            ReportSourceCut.company_id == generation.company_id,
            ReportSourceCut.generation_id == generation.id,
        )
    )
    if cut is not None:
        if cut.verification is None:
            raise ConflictError("verified inventory source cutoff is required")
        view = SourceView(generation.company_id, cut.epoch_id, cut.sequence)
        query = view.rows("inventory_report_record")
        if not movement:
            query = query.where(ReportFactVersion.inventory_kind.in_(BALANCE_KINDS))
        rows = await bounded_rows(db, query.order_by(ReportFactVersion.source_id), maximum=maximum)
        data = [row.data for row in rows if row.data is not None]
        finance = list(
            await db.scalars(
                view.rows("financial_setup")
                .with_only_columns(
                    ReportFactVersion.data,
                )
                .limit(2)
            )
        )
    else:
        # Compatibility path is bounded and never used as a high-volume native plan.
        legacy = list(
            await db.scalars(
                select(ReportFact)
                .where(
                    ReportFact.company_id == generation.company_id,
                    ReportFact.generation_id == generation.id,
                    ReportFact.entity == "inventory_report_record",
                    ReportFact.data.is_not(None),
                )
                .order_by(ReportFact.source_id)
                .limit(maximum + 1)
            )
        )
        if len(legacy) > maximum:
            raise CapacityExceededError("inventory reference source exceeds its row bound")
        data = [row.data for row in legacy if row.data is not None]
        if sum(len(canonical_json(value)) for value in data) > 16 * 1024 * 1024:
            raise CapacityExceededError("inventory reference source exceeds its byte bound")
        movement = True  # Legacy payload contains every stock grain; verify all declared counts.
        finance = list(
            await db.scalars(
                select(ReportFact.data)
                .where(
                    ReportFact.company_id == generation.company_id,
                    ReportFact.generation_id == generation.id,
                    ReportFact.entity == "financial_setup",
                )
                .limit(2)
            )
        )
    coverage = [row["payload"] for row in data if row["payload"]["kind"] == "COVERAGE"]
    if (
        len(finance) != 1
        or finance[0] is None
        or len(coverage) != 1
        or (coverage[0]["currency"] != finance[0]["base_currency"])
    ):
        raise ConflictError("inventory and frozen financial source currency or coverage differs")
    return data, movement


async def execute(
    db: AsyncSession,
    generation: ReportGeneration,
    job: ReportJob,
    maximum: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import asyncio

    values, movements_loaded = await records(
        db,
        generation,
        job.definition["code"],
        maximum,
        include_history=bool(
            job.parameters.get("include_history") or job.parameters.get("include_cost_details")
        ),
    )
    if job.definition["code"] == "STOCK_VALUATION":
        await verify_gl(db, generation, values, maximum)
    return await asyncio.to_thread(
        calculate,
        job.definition["code"],
        values,
        job.parameters,
        movements_loaded=movements_loaded,
    )
