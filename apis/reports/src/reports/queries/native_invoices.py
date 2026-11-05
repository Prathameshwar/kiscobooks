"""Bounded invoice components reuse the financial register rules over verified history."""

import itertools
import uuid
from decimal import localcontext
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.invoice_registers import CODES as CODES
from reports.domain.invoice_registers import register
from reports.domain.statements import Facts, calculation_evidence
from reports.models.source_versions import ReportFactVersion
from reports.queries.native_components import ComponentFacts
from reports.queries.native_context import NativeContext
from reports.queries.native_ledger import LedgerQuery
from reports.queries.source_versions import COMPONENT_BYTES, bounded_rows, fact_pages
from reports.schemas.requests import RunRequest
from reports.tasks.source_verification import invoice_component

RESULT_BYTES = 32 * 1024 * 1024


class DocumentFacts(ComponentFacts):
    def __init__(
        self,
        dimensions: Facts,
        component: dict[tuple[str, str], dict[str, Any]],
        selected: set[str],
        lineage: dict[str, dict[str, Any]],
    ):
        super().__init__(
            dimensions,
            {
                key: value
                for key, value in component.items()
                if key[0] != "invoice_record" or key[1] in selected
            },
            lineage,
        )


def order(row: dict[str, Any], data: DocumentFacts) -> tuple[Any, ...]:
    kind = row["row_kind"]
    if kind == "INVOICE":
        return (row["invoice_id"],)
    if kind in {"COMPONENT", "ALLOCATION"}:
        return (0 if kind == "COMPONENT" else 1, row["source_id"])
    if kind == "TAX_COMPONENT":
        return (row["component_id"],)
    if kind == "CREDIT_EVENT":
        return (0, row["event_id"])
    if kind == "CREDIT_POSITION":
        return (1, row["component_id"])
    if kind == "SETTLEMENT":
        source = data.rows["allocation"][row["allocation_id"]]
        return (row["allocation_id"], 0 if row["bill_item_id"] == source["debt_item_id"] else 1)
    if kind == "GL_ENTRY":
        return (row["posting_date"], row["journal_id"], row["line_id"])
    raise ConflictError("invoice result contains an unsupported source grain")


async def execute(
    db: AsyncSession, context: NativeContext, query: RunRequest, maximum: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if query.code not in CODES:
        raise ValueError("unsupported native invoice definition")
    current = query.model_copy(update={"comparative_from": None, "comparative_to": None})
    periods = [("CURRENT", current)]
    if query.comparative_from and query.comparative_to:
        periods.append(
            (
                "COMPARATIVE",
                current.model_copy(
                    update={
                        "date_from": query.comparative_from,
                        "date_to": query.comparative_to,
                    }
                ),
            )
        )
    result: list[dict[str, Any]] = []
    size = 0
    for period, selected_query in periods:
        await context.validate(db, selected_query)
        statement = context.view.rows("invoice_record")
        p = ReportFactVersion
        if query.invoice_id:
            statement = statement.where(p.source_id == query.invoice_id)
        if query.currency:
            statement = statement.where(p.currency == query.currency)
        if query.code in {"SALES_REGISTER", "PURCHASE_REGISTER"}:
            kinds = (
                ("SALES", "CREDIT_NOTE")
                if query.code == "SALES_REGISTER"
                else ("PURCHASE", "DEBIT_NOTE")
            )
            date = (
                p.posting_date
                if query.date_basis == "POSTING"
                else p.data["document_date"].as_string()
            )
            statement = statement.where(
                p.data["kind"].as_string().in_(kinds),
                date >= selected_query.date_from,
                date <= selected_query.date_to,
            )
        if query.account_id or query.group_id or query.party_id or query.role:
            statement = statement.where(p.account_id.in_(context.accounts(query)))
        ordered: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        async for headers in fact_pages(db, statement):
            for batch in itertools.batched(headers, 10):
                component = await invoice_component(db, context.view, list(batch))
                if query.code == "INVOICE_SETTLEMENT_REGISTER":
                    item_ids = [
                        uuid.UUID(key) for entity, key in component if entity == "open_item"
                    ]
                    component_size = len(canonical_json(component_values(component)))
                    # Both allocation sides have an indexed native relation; never scan all credits.
                    for items in itertools.batched(item_ids, 200):
                        allocations = await bounded_rows(
                            db,
                            context.view.rows("allocation").where(
                                or_(p.relation_id.in_(items), p.origin_id.in_(items))
                            ),
                        )
                        for allocation in allocations:
                            key = ("allocation", str(allocation.source_id))
                            if key not in component and allocation.data is not None:
                                component_size += allocation.wire_bytes
                                if len(component) >= 20000 or component_size > COMPONENT_BYTES:
                                    raise ConflictError(
                                        "invoice settlement component exceeds its supported bound"
                                    )
                                component[key] = allocation.data
                journals = [uuid.UUID(key) for entity, key in component if entity == "journal"]
                ledger = LedgerQuery(
                    context, selected_query.model_copy(update={"code": "ACCOUNT_LEDGER"})
                )
                links = {}
                for journal_ids in itertools.batched(journals, 200):
                    links.update(await ledger.lineage(db, list(journal_ids)))
                data = DocumentFacts(
                    context.data, component, {str(row.source_id) for row in batch}, links
                )
                with localcontext() as arithmetic:
                    arithmetic.prec = 48
                    rows = register(data, selected_query)
                for row in rows:
                    row["period"] = period
                    size += len(canonical_json(row))
                    if len(result) + len(ordered) >= maximum or size > RESULT_BYTES:
                        raise ConflictError(
                            "native invoice result exceeds its configured materialization bound"
                        )
                    ordered.append((order(row, data), row))
        ordered.sort(key=lambda pair: pair[0])
        result.extend(row for _, row in ordered)
    return result, calculation_evidence(context.data, query, context.coverage, result)


def component_values(component: dict[tuple[str, str], dict[str, Any]]) -> list[Any]:
    return [[entity, identity, value] for (entity, identity), value in component.items()]
