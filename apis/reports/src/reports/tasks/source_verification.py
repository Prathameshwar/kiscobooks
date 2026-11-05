"""Bounded financial verification over a pinned epoch; publication follows all checks."""

import itertools
import uuid
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from billing_platform.db.types import Money
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from reporting_contract.contract import FACT_MODELS, Control, Manifest
from reporting_contract.invoice import INVOICE_FACT_MODELS
from sqlalchemy import case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from reports.domain.invoice_reconciliation import reconcile_invoices
from reports.domain.reconcile import RULE_HASH, fixed, money, validate_source_record, validated_line
from reports.domain.reporting.opening_coverage import OpeningControls
from reports.domain.reporting.source_references import references
from reports.models.source_versions import ReportFactVersion, ReportSourceCut
from reports.queries.source_versions import COMPONENT_BYTES, SourceView, bounded_rows, fact_pages
from reports.tasks.source_incremental import verify_append

Live = dict[tuple[str, str], dict[str, Any]]


async def closure(
    db: AsyncSession,
    view: SourceView,
    rows: Iterable[ReportFactVersion],
    *,
    maximum: int = 20000,
) -> Live:
    live = {(row.entity, str(row.source_id)): row.data for row in rows if row.data is not None}
    size = sum(len(canonical_json(data)) + 256 for data in live.values())
    if len(live) > maximum or size > COMPONENT_BYTES:
        raise ConflictError("source reference component exceeds its supported memory bound")
    inspected: set[tuple[str, str]] = set()
    while True:
        wanted: dict[str, set[uuid.UUID]] = defaultdict(set)
        for key, data in live.items():
            if key in inspected:
                continue
            inspected.add(key)
            for entity, identity in references(key[0], data):
                if (entity, identity) not in live:
                    wanted[entity].add(uuid.UUID(identity))
        if not wanted:
            return live
        for entity, identities in wanted.items():
            for batch in itertools.batched(sorted(identities), 200):
                found = await view.lookup(db, entity, batch)
                if len(found) != len(batch):
                    raise ConflictError("required source reference is missing")
                for found_id, row in found.items():
                    assert row.data is not None
                    live[entity, str(found_id)] = row.data
                    size += len(canonical_json(row.data)) + 256
                    if len(live) > maximum or size > COMPONENT_BYTES:
                        raise ConflictError(
                            "source reference component exceeds its supported bound"
                        )


async def verify_records(db: AsyncSession, view: SourceView, control: Control) -> None:
    if control.coverage_kind != "RETAINED_LEDGER" or control.coverage_start is None:
        raise ConflictError("financial history coverage is unavailable")
    opening_controls = OpeningControls()
    async for opening_rows in view.pages(db, "opening_batch"):
        retained = await closure(db, view, opening_rows)

        def opening_require(kind: str, identity: Any, values: Live = retained) -> dict[str, Any]:
            value = values.get((kind, str(identity)))
            if value is None:
                raise ConflictError("required opening provenance is missing")
            return value

        for opening in opening_rows:
            assert opening.data is not None
            opening_controls.register(opening.data, opening_require)
    for entity in sorted(FACT_MODELS):
        async for rows in view.pages(db, entity):
            live = await closure(db, view, rows)

            def require(kind: str, identity: Any, values: Live = live) -> dict[str, Any]:
                row = values.get((kind, str(identity)))
                if row is None:
                    raise ConflictError("required source reference is missing")
                return row

            for row in rows:
                assert row.data is not None
                validate_source_record(entity, str(row.source_id), row.data, require)
                if entity == "journal_line":
                    projected = validated_line(
                        str(row.source_id), row.data, require, control.coverage_start
                    )
                    if projected is not None:
                        opening_controls.add(row.data, require)
    opening_controls.finish()


async def journal_controls(
    db: AsyncSession,
    view: SourceView,
    expected: Control,
    *,
    identities: set[uuid.UUID] | None = None,
) -> dict[str, dict[str, str]]:
    journal, line = aliased(ReportFactVersion), aliased(ReportFactVersion)
    debit = func.coalesce(
        func.sum(case((line.side == "DEBIT", line.base_amount), else_=Decimal(0))), Decimal(0)
    )
    credit = func.coalesce(
        func.sum(case((line.side == "CREDIT", line.base_amount), else_=Decimal(0))), Decimal(0)
    )
    query = (
        select(journal.source_id, debit, credit)
        .outerjoin(
            line,
            (line.relation_id == journal.source_id)
            & (line.entity == "journal_line")
            & view.predicate(line),
        )
        .where(
            view.predicate(journal), journal.entity == "journal", journal.source_status == "POSTED"
        )
        .group_by(journal.id)
    )
    headers = view.rows("journal").where(ReportFactVersion.source_status == "POSTED")
    if identities is not None:
        headers = headers.where(ReportFactVersion.source_id.in_(identities))
    totals: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"DEBIT": Decimal(0), "CREDIT": Decimal(0)}
    )
    async for page in fact_pages(db, headers):
        evidence = {row.source_id: row.data for row in page}
        sums = await db.execute(query.where(journal.source_id.in_(evidence)))
        for identity, dr, cr in sums:
            data = evidence.pop(identity)
            assert data is not None
            if not isinstance(dr, Decimal) or not isinstance(cr, Decimal):
                raise ConflictError("financial aggregate did not return an exact Decimal")
            if (
                dr <= 0
                or dr != cr
                or dr != money(data["total_debit"])
                or cr != money(data["total_credit"])
            ):
                raise ConflictError("posted journal does not reconcile")
            totals[data["base_currency"]]["DEBIT"] += dr
            totals[data["base_currency"]]["CREDIT"] += cr
        if evidence:
            raise ConflictError("journal control page is incomplete")
    actual = {
        currency: {side: fixed(value) for side, value in sides.items()}
        for currency, sides in totals.items()
    }
    wanted = {
        currency: {side: fixed(money(value)) for side, value in sides.items()}
        for currency, sides in expected.base_totals.items()
    }
    if actual != wanted:
        raise ConflictError("owner control totals differ")
    return actual


async def verify(db: AsyncSession, cut: ReportSourceCut) -> dict[str, Any]:
    incremental = await verify_append(db, cut)
    if incremental is not None:
        return incremental
    manifest = Manifest.model_validate(cut.manifest)
    view = SourceView(cut.company_id, cut.epoch_id, cut.sequence)
    counted = await db.execute(
        select(ReportFactVersion.entity, func.count(ReportFactVersion.id))
        .where(view.predicate())
        .group_by(ReportFactVersion.entity)
    )
    observed = dict(counted.tuples().all())
    counts = {entity: observed.get(entity, 0) for entity in FACT_MODELS}
    if counts != {key: manifest.control.counts.get(key, 0) for key in FACT_MODELS} or (
        set(manifest.control.counts) - FACT_MODELS.keys()
    ):
        raise ConflictError("source grain counts differ")
    await verify_records(db, view, manifest.control)
    totals = await journal_controls(db, view, manifest.control)
    if counts["invoice_record"]:
        await verify_invoices(db, view)
    return {
        "counts": counts,
        "base_totals": totals,
        "coverage_kind": manifest.control.coverage_kind,
        "coverage_start": str(manifest.control.coverage_start),
        "rule_hash": RULE_HASH,
        "differences": [],
        "projection_version": 1,
    }


async def invoice_component(
    db: AsyncSession,
    view: SourceView,
    headers: list[ReportFactVersion],
    *,
    maximum: int = 20000,
) -> Live:
    """At most ten invoices plus their original-document/GL components in memory."""
    records = {(row.entity, row.source_id): row for row in headers}
    expanded: set[uuid.UUID] = set()
    children = set(INVOICE_FACT_MODELS) - {"invoice_record"}
    while True:
        live = await closure(db, view, records.values(), maximum=maximum)
        invoice_ids = {
            uuid.UUID(key) for entity, key in live if entity == "invoice_record"
        } - expanded
        if not invoice_ids:
            break
        expanded |= invoice_ids
        for batch in itertools.batched(sorted(invoice_ids), 200):
            selected = await bounded_rows(
                db,
                select(ReportFactVersion)
                .where(
                    view.predicate(),
                    ReportFactVersion.entity.in_(children),
                    ReportFactVersion.relation_id.in_(batch),
                )
                .limit(maximum + 1),
                maximum=maximum,
            )
            for row in selected:
                records[row.entity, row.source_id] = row
            # Retain original headers brought in by the reference closure too.
            originals = await view.lookup(db, "invoice_record", batch)
            records.update({("invoice_record", key): row for key, row in originals.items()})
            if len(records) > maximum:
                raise ConflictError("invoice source component exceeds its supported bound")
    journal_ids = {uuid.UUID(key) for entity, key in live if entity == "journal"}
    for batch in itertools.batched(sorted(journal_ids), 200):
        rows = await bounded_rows(
            db,
            view.rows("journal_line")
            .where(ReportFactVersion.relation_id.in_(batch))
            .limit(maximum + 1),
            maximum=maximum,
        )
        records.update({("journal_line", row.source_id): row for row in rows})
        if len(records) > maximum:
            raise ConflictError("invoice journal component exceeds its supported bound")
    line_ids = {key for entity, key in records if entity == "journal_line"}
    for batch in itertools.batched(sorted(line_ids), 200):
        rows = await bounded_rows(
            db,
            view.rows("open_item")
            .where(ReportFactVersion.relation_id.in_(batch))
            .limit(maximum + 1),
            maximum=maximum,
        )
        records.update({("open_item", row.source_id): row for row in rows})
        if len(records) > maximum:
            raise ConflictError("invoice bill component exceeds its supported bound")
    return await closure(db, view, records.values(), maximum=maximum)


async def verify_invoices(db: AsyncSession, view: SourceView) -> None:
    async for headers in view.pages(db, "invoice_record"):
        for batch in itertools.batched(headers, 10):
            reconcile_invoices(await invoice_component(db, view, list(batch)))
    await verify_note_entitlements(db, view)


async def verify_note_entitlements(
    db: AsyncSession, view: SourceView, originals: list[uuid.UUID] | None = None
) -> None:
    # A component may include only some notes. Check their cumulative entitlement in native SQL.
    note, supply, original, intent = (aliased(ReportFactVersion) for _ in range(4))
    total = func.sum(cast(supply.data["commercial"].as_string(), Money))
    query = (
        select(original.id)
        .select_from(note)
        .join(
            supply,
            (supply.relation_id == note.source_id)
            & (supply.entity == "invoice_supply_fact")
            & view.predicate(supply),
        )
        .join(
            intent,
            (intent.source_id == note.relation_id)
            & (intent.entity == "voucher_money_intent")
            & view.predicate(intent),
        )
        .join(
            original,
            (original.relation_id == note.origin_id)
            & (original.entity == "invoice_supply_fact")
            & (original.data["line_key"].as_string() == supply.data["line_key"].as_string())
            & view.predicate(original),
        )
        .where(
            view.predicate(note),
            note.entity == "invoice_record",
            note.origin_id.is_not(None),
            intent.source_status != "CANCELLED",
        )
        .group_by(original.id)
        .having(total > func.max(cast(original.data["commercial"].as_string(), Money)))
        .limit(1)
    )
    if originals is not None:
        query = query.where(note.origin_id.in_(originals))
    if await db.scalar(query) is not None:
        raise ConflictError("financial notes exceed their original supply entitlement")
