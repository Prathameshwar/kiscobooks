"""Registered projections and exact party balances over canonical report rows."""

from collections import defaultdict
from dataclasses import replace
from decimal import Decimal, localcontext
from typing import Any

from reports.domain.reporting.contracts import Column, View


def select(views: list[dict[str, Any]], key: str) -> dict[str, Any]:
    matches = [view for view in views if view["key"] == key]
    if len(matches) != 1:
        raise ValueError("requested report view is unavailable")
    return matches[0]


def registered(
    code: str, title: str, output: tuple[Column, ...], default: View
) -> tuple[View, ...]:
    from reports.domain.reporting.control_views import registered_controls
    from reports.domain.reporting.finance_views import registered_finance

    controls = registered_controls(code, output)
    if controls is not None:
        return controls
    finance = registered_finance(code, output, default.layout)
    if finance is not None:
        return finance
    if code == "BALANCE_SHEET":
        statement = (
            Column("section", "Section"),
            Column("label", "Account / group"),
            Column("code", "Code", "IDENTIFIER"),
            Column("amount", "Current", "MONEY", "currency"),
            Column("currency", "Currency"),
        )
        return (
            View(
                "default",
                "Standard",
                statement,
                "STATEMENT",
                calculation="balance_standard",
                orientation="LANDSCAPE",
            ),
            View(
                "comparison",
                "Comparative",
                statement[:-1]
                + (
                    Column("previous_amount", "Previous", "MONEY", "currency"),
                    Column("change_amount", "Change", "MONEY", "currency"),
                    Column("change_percent", "Change %"),
                    statement[-1],
                ),
                "STATEMENT",
                calculation="balance_comparison",
                orientation="LANDSCAPE",
            ),
        )
    if code == "PROFIT_LOSS":
        statement = (
            Column("label", "Account / group"),
            Column("code", "Code", "IDENTIFIER"),
            Column("amount", "Current", "MONEY", "currency"),
            Column("imported_ytd_amount", "Included imported YTD", "MONEY", "currency"),
            Column("currency", "Currency"),
        )
        comparison = statement[:3] + (
            Column("previous_amount", "Previous", "MONEY", "currency"),
            Column("change_amount", "Change", "MONEY", "currency"),
            Column("change_percent", "Change %"),
            statement[3],
            Column("previous_imported_ytd_amount", "Previous imported YTD", "MONEY", "currency"),
            statement[4],
        )
        return (
            View("default", "Statement", statement, "STATEMENT", calculation="profit_statement"),
            View(
                "comparison",
                "Period comparison",
                comparison,
                "STATEMENT",
                calculation="profit_comparison",
                orientation="LANDSCAPE",
            ),
        )
    if code in {"INVOICE_TAX_REGISTER", "TAX_GL_BRIDGE"}:
        business_keys = (
            (
                "period",
                "posting_date",
                "bill_reference",
                "invoice_kind",
                "account_name",
                "tax_code",
                "component_taxable_basis",
                "tax_amount",
                "currency",
            )
            if code == "INVOICE_TAX_REGISTER"
            else (
                "period",
                "posting_date",
                "bill_reference",
                "account_name",
                "tax_code",
                "tax_purpose",
                "side",
                "amount",
                "currency",
            )
        )
        by_key = {column.key: column for column in output}

        def rename(column: Column) -> Column:
            if code == "TAX_GL_BRIDGE" and column.key == "account_name":
                return replace(column, title="Tax Ledger")
            return column

        business = tuple(rename(by_key[key]) for key in business_keys)
        full = tuple(rename(column) for column in output)
        return (
            View("default", title, business, default.layout),
            View("full", "Full recorded source details", full, default.layout),
        )
    if code == "INVOICE_CREDIT_REGISTER":
        position_keys = {
            "posting_date",
            "bill_reference",
            "invoice_id",
            "account_name",
            "tax_code",
            "component_id",
            "as_of",
            "currency",
            "recorded_tax",
            "pending",
            "eligible_unclaimed",
            "claimed",
            "suspended",
            "blocked",
            "rcm_discharged",
            "period",
        }
        position_business = {
            "period",
            "bill_reference",
            "account_name",
            "tax_code",
            "currency",
            "recorded_tax",
            "pending",
            "eligible_unclaimed",
            "claimed",
            "suspended",
            "blocked",
        }
        event_business = {
            "period",
            "posting_date",
            "bill_reference",
            "account_name",
            "tax_code",
            "event_date",
            "action",
            "event_amount",
            "currency",
        }
        event_keys = {
            "posting_date",
            "bill_reference",
            "invoice_id",
            "account_name",
            "tax_code",
            "component_id",
            "event_id",
            "event_date",
            "action",
            "reference",
            "event_amount",
            "currency",
            "period",
        }
        return (
            View(
                "default",
                "Closing positions",
                tuple(column for column in output if column.key in position_business),
                "REGISTER",
                calculation="credit_positions",
            ),
            View(
                "events",
                "Period events",
                tuple(column for column in output if column.key in event_business),
                "REGISTER",
                calculation="credit_events",
            ),
            View("all", "Positions and events", output, "REGISTER"),
            View(
                "positions_detail",
                "Position source details",
                tuple(column for column in output if column.key in position_keys),
                "REGISTER",
                calculation="credit_positions",
            ),
            View(
                "events_detail",
                "Event source details",
                tuple(column for column in output if column.key in event_keys),
                "REGISTER",
                calculation="credit_events",
            ),
        )
    compact = tuple(
        column
        for column in output
        if column.key
        not in {
            "row_kind",
            "source_id",
            "configuration_hash",
            "calculation_hash",
            "nature",
            "allocation_id",
            "component_id",
        }
    )
    result: tuple[View, ...] = (default, View("compact", "Compact", compact, default.layout))
    if code in {"OUTSTANDING_BILLS", "ADVANCES"}:
        result += (
            View(
                "party_balances",
                "Balances by party",
                (
                    Column("party_id", "Party", "IDENTIFIER"),
                    Column("account_id", "Account", "IDENTIFIER"),
                    Column("role", "Role"),
                    Column("currency", "Currency"),
                    Column("debt", "Debt", "MONEY", "currency"),
                    Column("unapplied_credit", "Unapplied Credit", "MONEY", "currency"),
                    Column("net_debt", "Net Debt", "MONEY", "currency"),
                ),
                "SUMMARY",
                calculation="party_balances",
            ),
        )
    return result


def party_balances(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    labels: dict[tuple[str, ...], dict[str, str]] = {}
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for row in rows:
            key = (
                str(row.get("period", "CURRENT")),
                str(row["party_id"]),
                str(row["account_id"]),
                row["role"],
                row["report_currency"],
            )
            labels[key] = {
                field: str(row.get(field) or "") for field in ("account_code", "account_name")
            }
            groups[key]["debt" if row["direction"] == "DEBT" else "credit"] += Decimal(
                row["report_amount"]
            )
        return [
            {
                "row_kind": "PARTY_BALANCE",
                **labels[key],
                "period": key[0],
                "party_id": key[1],
                "account_id": key[2],
                "role": key[3],
                "currency": key[4],
                "debt": format(values["debt"], ".4f"),
                "unapplied_credit": format(values["credit"], ".4f"),
                "net_debt": format(values["debt"] - values["credit"], ".4f"),
            }
            for key, values in sorted(groups.items())
        ]
