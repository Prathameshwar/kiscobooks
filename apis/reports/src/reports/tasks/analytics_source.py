"""Business components are bounded and pinned to the verified financial cut."""

import calendar
import datetime as dt
import itertools
import uuid
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from reports.domain.analytics_cash import calculate as cash
from reports.domain.analytics_common import periods, stock_index
from reports.domain.analytics_customers import calculate as customers
from reports.domain.analytics_dimension_profit import calculate as dimension_profit
from reports.domain.analytics_expenses import calculate as expenses
from reports.domain.analytics_profit import calculate as profitability
from reports.domain.analytics_profit import figures as profit_figures
from reports.domain.analytics_sales import calculate as sales
from reports.domain.invoice_registers import register
from reports.domain.statements import profit
from reports.models.core import ReportGeneration
from reports.models.framework import ReportJob
from reports.models.source_versions import ReportFactVersion
from reports.queries.analytics_cash import inputs as cash_inputs
from reports.queries.native_context import NativeContext
from reports.queries.native_invoices import DocumentFacts
from reports.queries.native_statements import reduced
from reports.queries.source_versions import COMPONENT_BYTES, bounded_rows, fact_pages
from reports.schemas.requests import RunRequest
from reports.tasks.source_verification import invoice_component


async def documents(
    db: AsyncSession,
    context: NativeContext,
    values: dict[str, Any],
    maximum: int,
    *,
    history: bool = False,
    purchases: bool = False,
    retained_only: bool = False,
) -> list[dict[str, Any]]:
    begin = (
        context.coverage.isoformat() if history else min(period[1] for period in periods(values))
    )
    end = max(period[2] for period in periods(values))
    if retained_only:
        begin = max(begin, context.coverage.isoformat())
        if end < begin:
            return []
    query = RunRequest.model_validate(
        {
            "code": "PURCHASE_REGISTER" if purchases else "SALES_REGISTER",
            "generation_id": "00000000-0000-0000-0000-000000000001",
            "date_from": begin,
            "date_to": end,
            **(
                {"currency": values["currency"], "basis": "TRANSACTION"}
                if values.get("currency")
                else {}
            ),
        }
    )
    await context.validate(db, query)
    p = ReportFactVersion
    source = context.view.rows("invoice_record").where(
        p.data["kind"]
        .as_string()
        .in_(("PURCHASE", "DEBIT_NOTE") if purchases else ("SALES", "CREDIT_NOTE")),
        p.posting_date >= query.date_from,
        p.posting_date <= query.date_to,
    )
    if not history:
        source = source.where(
            or_(
                *(
                    and_(
                        p.posting_date >= dt.date.fromisoformat(begin),
                        p.posting_date <= dt.date.fromisoformat(end),
                    )
                    for _, begin, end in periods(values)
                )
            )
        )
    if values.get("currency"):
        source = source.where(p.currency == values["currency"])
    result: list[dict[str, Any]] = []
    width = 0
    async for page in fact_pages(db, source):
        for headers in itertools.batched(page, 10):
            component = await invoice_component(db, context.view, list(headers))
            data = DocumentFacts(
                context.data, component, {str(row.source_id) for row in headers}, {}
            )
            for row in register(data, query):
                invoice = data.rows["invoice_record"][row["invoice_id"]]
                intent = data.rows["voucher_money_intent"][invoice["intent_id"]]
                party = data.rows["party"].get(row["party_id"])
                document = row | {
                    "voucher_id": intent["voucher_id"],
                    "customer_name": party["name"] if party else row["account_name"],
                    "supplies": [
                        value | {"id": key}
                        for key, value in data.rows["invoice_supply_fact"].items()
                        if value["invoice_id"] == row["invoice_id"]
                    ],
                    "components": [
                        value
                        for value in data.rows["invoice_component_fact"].values()
                        if value["invoice_id"] == row["invoice_id"]
                    ],
                }
                width += len(canonical_json(document))
                if len(result) >= maximum or width > COMPONENT_BYTES:
                    raise ConflictError(
                        "analytics invoice/history component exceeds its supported bound"
                    )
                result.append(document)
    return result


async def inventory(
    db: AsyncSession, context: NativeContext, generation: ReportGeneration, maximum: int
) -> dict[str, Any]:
    rows = await bounded_rows(db, context.view.rows("inventory_report_record"), maximum=maximum)
    values = [row.data for row in rows if row.data]
    if not any(row["payload"]["kind"] == "COVERAGE" for row in values):
        return stock_index([])
    from reports.tasks.inventory_source import verify_gl

    await verify_gl(db, generation, values, maximum)
    try:
        return stock_index(values)
    except ValueError as exc:
        raise ConflictError(str(exc)) from exc


async def financials(
    db: AsyncSession,
    context: NativeContext,
    generation: ReportGeneration,
    values: dict[str, Any],
    maximum: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    statements: list[dict[str, Any]] = []
    trends: list[dict[str, Any]] = []
    for period, begin, end in periods(values):
        detail_begin = max(begin, context.coverage.isoformat())
        query = RunRequest.model_validate(
            {
                "code": "ACCOUNT_SUMMARY" if detail_begin <= end else "PROFIT_LOSS",
                "generation_id": generation.id,
                "date_from": detail_begin if detail_begin <= end else begin,
                "date_to": end,
                **({"grain": "MONTH"} if detail_begin <= end else {}),
            }
        )
        data = await reduced(db, context, query, maximum)
        statement_query = query.model_copy(
            update={"code": "PROFIT_LOSS", "date_from": dt.date.fromisoformat(begin)}
        )
        statements.extend(row | {"period": period} for row in profit(data, statement_query))
        cursor = dt.date.fromisoformat(detail_begin)
        finish = dt.date.fromisoformat(end)
        while cursor <= finish:
            last = min(
                finish, cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1])
            )
            monthly = profit(
                data, statement_query.model_copy(update={"date_from": cursor, "date_to": last})
            )
            figures = profit_figures(monthly)
            trends.append(
                figures
                | {
                    "period": period,
                    "date": cursor.isoformat(),
                    "currency": context.data.currency,
                    "amount": figures["net_profit"],
                }
            )
            if last == finish:
                break
            cursor = last + dt.timedelta(days=1)
    return statements, trends


async def execute(
    db: AsyncSession,
    generation: ReportGeneration,
    job: ReportJob,
    maximum: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    context = await NativeContext.load(db, generation.company_id, generation.id)
    values = job.parameters
    code = job.definition["code"]
    financial = code in {"PROFIT_MARGIN_ANALYSIS", "EXPENSE_PROFIT_LEAKAGE"}
    for _period, begin, end in periods(values):
        await context.validate(
            db,
            RunRequest.model_validate(
                {
                    "code": "PROFIT_LOSS" if financial else "ACCOUNT_SUMMARY",
                    "generation_id": generation.id,
                    "date_from": begin,
                    "date_to": end,
                }
            ),
        )
    items = (
        await documents(
            db,
            context,
            values,
            maximum,
            history=code == "CUSTOMER_INSIGHTS",
            purchases=code == "EXPENSE_PROFIT_LEAKAGE",
            retained_only=financial,
        )
        if code != "CASH_WORKING_CAPITAL"
        else []
    )
    stock = (
        await inventory(db, context, generation, maximum)
        if code != "CUSTOMER_INSIGHTS"
        else stock_index([])
    )
    view = (job.options or {}).get("view", "default")
    if code in {"BUYER_PROFIT", "PRODUCT_PROFIT"}:
        result, evidence = dimension_profit(code, items, values, stock, view=view)
        # The lean financial context does not load party masters. Resolve only the
        # selected party from this immutable cut, including when no invoices match.
        parties = {
            str(identity): row.data
            for identity, row in (
                await context.view.lookup(db, "party", [uuid.UUID(values["party_id"])])
                if values.get("party_id")
                else {}
            ).items()
            if row.data
        }
        selected_filters = {}
        for key, objects in (
            ("party_id", parties),
            ("item_id", stock["items"]),
            ("group_id", stock["groups"]),
        ):
            if values.get(key):
                identity = values[key]
                label = objects.get(identity, {}).get("name", "Unavailable reference")
                selected_filters[key] = f"{label} ({identity})"
        if values.get("currency"):
            selected_filters["currency"] = values["currency"]
        evidence["analytics"]["selected_filters"] = selected_filters
    elif code == "CUSTOMER_INSIGHTS":
        result, evidence = customers(items, values, context.coverage.isoformat(), view=view)
    elif code == "CASH_WORKING_CAPITAL":
        data = await cash_inputs(db, context, generation, values, maximum)
        result, evidence = cash(data, values, stock, context.data.currency, view=view)
    elif code == "EXPENSE_PROFIT_LEAKAGE":
        statements, trends = await financials(db, context, generation, values, maximum)
        sales_items = await documents(db, context, values, maximum, retained_only=True)
        result, evidence = expenses(
            statements,
            trends,
            items,
            values,
            context.data.currency,
            view=view,
            sales_documents=sales_items,
            stock=stock,
        )
    elif code == "PROFIT_MARGIN_ANALYSIS":
        statements, trends = await financials(db, context, generation, values, maximum)
        result, evidence = profitability(
            statements, trends, items, values, stock, context.data.currency, view=view
        )
    else:
        result, evidence = sales(items, values, stock, view=view)
    evidence["analytics"].update(
        coverage_start=context.coverage.isoformat(),
        source_sequence=context.view.sequence,
        inventory_as_of=stock["coverage"]["as_of"] if stock["coverage"] else None,
    )
    if financial and any(begin < context.coverage.isoformat() for _, begin, _ in periods(values)):
        evidence["analytics"]["notices"].append(
            "Company totals include verified imported YTD. Invoice, supplier and product "
            "breakdowns and trends cover retained detail only, from "
            + context.coverage.isoformat()
            + "; imported aggregates are not allocated to customers, products or months."
        )
    return result, evidence
