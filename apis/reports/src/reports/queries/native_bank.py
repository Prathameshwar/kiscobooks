"""Bank evidence and tender registers load indexed, bounded financial components."""

import itertools
import uuid
from decimal import localcontext
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.listing import SortColumn, SortTerm, seek_after
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.registers import register
from reports.domain.statements import calculation_evidence
from reports.models.posted_lines import ReportPostedLine
from reports.models.source_versions import ReportFactVersion
from reports.queries.native_components import ComponentFacts, ComponentLoader
from reports.queries.native_context import NativeContext
from reports.queries.native_ledger import LedgerQuery
from reports.queries.native_statements import reduced
from reports.schemas.requests import RunRequest

TENDERS = frozenset({"PAYMENT_REGISTER", "RECEIPT_REGISTER"})
CODES = TENDERS | {
    "BANK_RECONCILIATION",
    "BANK_RECONCILIATION_EVIDENCE",
    "BANK_RECONCILIATION_WORKLIST",
}


async def bank_data(db: AsyncSession, context: NativeContext, query: RunRequest) -> ComponentFacts:
    p = ReportFactVersion
    loader = ComponentLoader(db, context.view)
    assert query.account_id and query.date_from and query.date_to
    if query.code == "BANK_RECONCILIATION_EVIDENCE":
        assert query.session_id
        await loader.identities("bank_reconciliation_session", [query.session_id])
        session = loader.records["bank_reconciliation_session", query.session_id].data
        assert session is not None
        for entity, key in (
            ("bank_statement_entry", "entry_ids"),
            ("bank_instrument", "instrument_ids"),
        ):
            await loader.identities(
                entity, [uuid.UUID(value) for value in session["snapshot"].get(key, [])]
            )
    else:
        await loader.matching(
            "bank_instrument",
            p.account_id == query.account_id,
            p.data["booking_date"].as_string() <= query.date_to.isoformat(),
            *([p.currency == query.currency] if query.basis == "TRANSACTION" else []),
        )
        if query.code == "BANK_RECONCILIATION_WORKLIST":
            await loader.matching(
                "bank_statement_entry",
                p.account_id == query.account_id,
                p.currency == query.currency,
                p.data["transaction_date"].as_string() >= query.date_from.isoformat(),
                p.data["transaction_date"].as_string() <= query.date_to.isoformat(),
            )
        else:
            ledger = LedgerQuery(context, query.model_copy(update={"code": "ACCOUNT_LEDGER"}))
            line = ReportPostedLine
            identities = list(
                await db.scalars(
                    ledger.source(line.line_id)
                    .where(line.posting_date <= query.date_to)
                    .limit(20001)
                )
            )
            if len(identities) > 20000:
                raise ConflictError(
                    "bank reconciliation detail exceeds its supported component bound"
                )
            await loader.identities("journal_line", identities)
    instruments = [key for entity, key in loader.records if entity == "bank_instrument"]
    entries = [key for entity, key in loader.records if entity == "bank_statement_entry"]
    for batch in itertools.batched(instruments, 200):
        await loader.matching("bank_instrument_event", p.relation_id.in_(batch))
    if query.code != "BANK_RECONCILIATION":
        for batch in itertools.batched(sorted(set(instruments + entries)), 200):
            await loader.matching(
                "bank_match_event", or_(p.relation_id.in_(batch), p.origin_id.in_(batch))
            )
    component = await loader.finish()
    grouped = None
    if query.code == "BANK_RECONCILIATION_EVIDENCE":
        # Session membership supplies detail; its book control needs only exact daily sums.
        grouped = (await reduced(db, context, query, 100000)).aggregated
    return ComponentFacts(context.data, component, {}, grouped_lines=grouped)


async def tenders(
    db: AsyncSession, context: NativeContext, query: RunRequest, maximum: int
) -> list[dict[str, Any]]:
    p, line = ReportFactVersion, ReportPostedLine
    selected = query.model_copy(update={"code": "ACCOUNT_LEDGER", "party_id": None, "role": None})
    ledger = LedgerQuery(context, selected)
    accounts = [
        key
        for key in ledger.accounts
        if context.data.accounts[str(key)]["kind"] in {"CASH", "BANK"}
    ]
    base = (
        ledger.source(line.journal_id, line.posting_date)
        .where(
            line.account_id.in_(accounts),
            line.posting_date >= query.date_from,
            line.posting_date <= query.date_to,
        )
        .group_by(line.posting_date, line.journal_id)
    )
    terms = [
        SortTerm("date", False, SortColumn(line.posting_date, "date")),
        SortTerm("journal", False, SortColumn(line.journal_id, "uuid")),
    ]
    after = None
    ordered: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    size = 0
    while True:
        statement = base if after is None else base.where(seek_after(terms, after))
        selected_rows = (
            await db.execute(statement.order_by(line.posting_date, line.journal_id).limit(10))
        ).all()
        if not selected_rows:
            break
        loader = ComponentLoader(db, context.view)
        await loader.identities("journal", [row.journal_id for row in selected_rows])
        initial = await loader.finish()
        journals = [uuid.UUID(key) for entity, key in initial if entity == "journal"]
        await loader.identities("journal", journals)
        for batch in itertools.batched(journals, 200):
            await loader.matching("journal_line", p.relation_id.in_(batch))
            await loader.matching("voucher_money_intent", p.relation_id.in_(batch))
        lines = [key for entity, key in loader.records if entity == "journal_line"]
        for batch in itertools.batched(lines, 200):
            await loader.matching("bank_instrument", p.relation_id.in_(batch))
        component = await loader.finish()
        lineage = {}
        for batch in itertools.batched(journals, 200):
            lineage.update(await ledger.lineage(db, list(batch)))
        data = ComponentFacts(
            context.data,
            component,
            lineage,
            selected_journals={str(row.journal_id) for row in selected_rows},
        )
        with localcontext() as arithmetic:
            arithmetic.prec = 48
            values = register(data, query)
        for row in values:
            size += len(canonical_json(row))
            if len(ordered) >= maximum or size > 32 * 1024 * 1024:
                raise ConflictError("native tender result exceeds its materialization bound")
            order = (
                row["posting_date"],
                row["journal_id"],
                data.rows["journal_line"][row["line_id"]]["sequence"],
                row["line_id"],
                row["instrument_id"] is None,
                row["instrument_id"] or "",
            )
            ordered.append((order, row))
        last = selected_rows[-1]
        after = [last.posting_date, last.journal_id]
    ordered.sort(key=lambda pair: pair[0])
    return [row for _, row in ordered]


async def execute(
    db: AsyncSession, context: NativeContext, query: RunRequest, maximum: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if query.code not in CODES:
        raise ValueError("unsupported native bank definition")
    current = query.model_copy(update={"comparative_from": None, "comparative_to": None})
    periods = [("CURRENT", current)]
    if query.comparative_from and query.comparative_to:
        periods.append(
            (
                "COMPARATIVE",
                current.model_copy(
                    update={"date_from": query.comparative_from, "date_to": query.comparative_to}
                ),
            )
        )
    rows: list[dict[str, Any]] = []
    size = 0
    for period, selection in periods:
        await context.validate(db, selection)
        if selection.code in TENDERS:
            values = await tenders(db, context, selection, maximum - len(rows))
        else:
            data = await bank_data(db, context, selection)
            with localcontext() as arithmetic:
                arithmetic.prec = 48
                values = register(data, selection)
        for row in values:
            row["period"] = period
            size += len(canonical_json(row))
            if len(rows) >= maximum or size > 32 * 1024 * 1024:
                raise ConflictError("native bank result exceeds its materialization bound")
            rows.append(row)
    return rows, calculation_evidence(context.data, query, context.coverage, rows)
