"""Business report definitions reuse source authority and private result delivery."""

import hashlib
import uuid
from collections.abc import Mapping
from importlib.resources import files
from typing import Any

from reporting_contract.contract import Control, Fact

from reports.domain.reporting.contracts import (
    Column,
    Drilldown,
    ReportDefinition,
    ValueKind,
    View,
    fingerprint,
)
from reports.domain.reporting.registry import Registration
from reports.schemas.analytics import (
    AnalyticsParameters,
    BuyerProfitParameters,
    CashParameters,
    CustomerParameters,
    ExpenseParameters,
    ProductProfitParameters,
    ProfitParameters,
)
from reports.tasks.access import INPUT_PERMISSIONS
from reports.tasks.report_catalog import ReferenceAdapter

CODES = frozenset(
    {
        "SALES_PERFORMANCE",
        "PROFIT_MARGIN_ANALYSIS",
        "CUSTOMER_INSIGHTS",
        "EXPENSE_PROFIT_LEAKAGE",
        "CASH_WORKING_CAPITAL",
        "BUYER_PROFIT",
        "PRODUCT_PROFIT",
    }
)
TITLES = {
    "SALES_PERFORMANCE": "Sales performance",
    "PROFIT_MARGIN_ANALYSIS": "Profit and margin analysis",
    "CUSTOMER_INSIGHTS": "Customer insights",
    "EXPENSE_PROFIT_LEAKAGE": "Expense and profit leakage",
    "CASH_WORKING_CAPITAL": "Cash and working capital",
    "BUYER_PROFIT": "Party (buyer) wise profit",
    "PRODUCT_PROFIT": "Product wise profit",
}
MONEY = {
    "gross_sales",
    "returns",
    "net_sales",
    "discounts",
    "average_invoice",
    "comparison_amount",
    "change_amount",
    "cost",
    "gross_profit",
    "posted_income",
    "direct_income",
    "direct_costs",
    "operating_expenses",
    "other_income",
    "net_profit",
    "amount",
    "recorded_sales",
    "total_expenses",
    "purchases",
    "purchase_returns",
    "opening",
    "closing",
    "net_movement",
    "report_amount",
    "receivables",
    "payables",
}
RATIOS = {"contribution_percent", "change_percent", "return_rate", "margin_percent"}


def column(key: str) -> Column:
    kind: ValueKind = (
        "MONEY"
        if key in MONEY
        else "DECIMAL"
        if key in RATIOS or key.endswith("_percent") or key in {"quantity", "average_gap_days"}
        else "INTEGER"
        if key.endswith("_count")
        or key
        in {
            "days_since_purchase",
            "days_overdue",
            "active_customers",
            "repeat_customers",
            "first_observed_customers",
            "inactive_customers",
        }
        else "DATE"
        if key == "date" or key.endswith("_date")
        else "IDENTIFIER"
        if key.endswith("_id")
        else "TEXT"
    )
    return Column(
        key, key.replace("_", " ").capitalize(), kind, "currency" if kind == "MONEY" else None
    )


def implementation() -> str:
    root = files("reports")
    digest = hashlib.sha256()
    for name in (
        "domain/analytics_common.py",
        "domain/analytics_sales.py",
        "domain/analytics_profit.py",
        "domain/analytics_dimension_profit.py",
        "domain/reporting/drilldowns.py",
        "rendering/analytics.py",
        "domain/analytics_customers.py",
        "domain/analytics_expenses.py",
        "domain/analytics_cash.py",
        "queries/analytics_cash.py",
        "schemas/analytics.py",
        "tasks/analytics_catalog.py",
        "tasks/analytics_source.py",
        "queries/native_invoices.py",
        "queries/native_statements.py",
        "queries/native_open_items.py",
        "domain/invoice_registers.py",
        "domain/statements.py",
        "domain/reporting/inventory.py",
    ):
        digest.update(
            name.encode() + b"\0" + root.joinpath(name).read_bytes().replace(b"\r\n", b"\n")
        )
    return digest.hexdigest()


class AnalyticsAdapter(ReferenceAdapter):
    def execute(
        self,
        facts: list[Fact],
        generation_id: uuid.UUID,
        values: Mapping[str, Any],
        control: Control,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        raise ValueError("business analytics requires a verified native source cut")


def registrations() -> list[Registration[ReferenceAdapter]]:
    entries: list[Registration[ReferenceAdapter]] = []
    for code in sorted(CODES):
        adapter = AnalyticsAdapter(
            code,
            ProductProfitParameters
            if code == "PRODUCT_PROFIT"
            else BuyerProfitParameters
            if code == "BUYER_PROFIT"
            else CustomerParameters
            if code == "CUSTOMER_INSIGHTS"
            else CashParameters
            if code == "CASH_WORKING_CAPITAL"
            else ExpenseParameters
            if code == "EXPENSE_PROFIT_LEAKAGE"
            else ProfitParameters
            if code == "PROFIT_MARGIN_ANALYSIS"
            else AnalyticsParameters,
        )
        main = (
            "period",
            "label",
            "net_sales",
            "invoice_count",
            "returns",
            "discounts",
            "average_invoice",
            "contribution_percent",
            "comparison_amount",
            "change_amount",
            "change_percent",
            "currency",
            "party_id",
        )
        views: tuple[View, ...] = (
            View("default", "Customers", tuple(column(key) for key in main), "SUMMARY"),
            View(
                "products",
                "Products",
                tuple(
                    column(key)
                    for key in (
                        "period",
                        "label",
                        "net_sales",
                        "quantity",
                        "unit",
                        "invoice_count",
                        "contribution_percent",
                        "comparison_amount",
                        "change_amount",
                        "change_percent",
                        "currency",
                        "item_id",
                    )
                ),
                "SUMMARY",
            ),
            View(
                "categories",
                "Supply categories",
                tuple(
                    column(key)
                    for key in (
                        "period",
                        "label",
                        "net_sales",
                        "invoice_count",
                        "contribution_percent",
                        "comparison_amount",
                        "change_amount",
                        "change_percent",
                        "currency",
                    )
                ),
                "SUMMARY",
            ),
            View(
                "periods",
                "Period trend",
                tuple(
                    column(key)
                    for key in (
                        "period",
                        "date",
                        "net_sales",
                        "invoice_count",
                        "returns",
                        "discounts",
                        "average_invoice",
                        "currency",
                    )
                ),
                "SUMMARY",
            ),
            View(
                "invoices",
                "Invoices and returns",
                tuple(
                    column(key)
                    for key in (
                        "period",
                        "posting_date",
                        "bill_reference",
                        "account_name",
                        "invoice_kind",
                        "net_sales",
                        "currency",
                        "invoice_id",
                        "party_id",
                    )
                ),
            ),
        )
        if code == "PROFIT_MARGIN_ANALYSIS":
            views = (
                View(
                    "default",
                    "Profit drivers",
                    tuple(
                        column(key)
                        for key in (
                            "period",
                            "label",
                            "amount",
                            "comparison_amount",
                            "change_amount",
                            "change_percent",
                            "currency",
                        )
                    ),
                    "SUMMARY",
                ),
                View(
                    "products",
                    "Product gross margins",
                    tuple(
                        column(key)
                        for key in (
                            "period",
                            "label",
                            "net_sales",
                            "cost",
                            "gross_profit",
                            "margin_percent",
                            "cost_status",
                            "unit",
                            "currency",
                            "item_id",
                        )
                    ),
                    "SUMMARY",
                ),
                View(
                    "accounts",
                    "P&L accounts",
                    tuple(
                        column(key)
                        for key in (
                            "period",
                            "account_name",
                            "group_name",
                            "nature",
                            "amount",
                            "comparison_amount",
                            "change_amount",
                            "change_percent",
                            "currency",
                            "account_id",
                        )
                    ),
                    "SUMMARY",
                ),
                View(
                    "periods",
                    "Period trend",
                    tuple(
                        column(key)
                        for key in (
                            "period",
                            "date",
                            "posted_income",
                            "direct_costs",
                            "gross_profit",
                            "operating_expenses",
                            "net_profit",
                            "gross_margin_percent",
                            "currency",
                        )
                    ),
                    "SUMMARY",
                ),
            )
        if code == "CUSTOMER_INSIGHTS":
            views = (
                View(
                    "default",
                    "Customer activity",
                    tuple(
                        column(key)
                        for key in (
                            "period",
                            "label",
                            "net_sales",
                            "purchase_count",
                            "last_purchase_date",
                            "segment",
                            "comparison_amount",
                            "change_amount",
                            "change_percent",
                            "currency",
                            "party_id",
                        )
                    ),
                    "SUMMARY",
                ),
                View(
                    "history",
                    "Observed customer history",
                    tuple(
                        column(key)
                        for key in (
                            "period",
                            "label",
                            "recorded_sales",
                            "recorded_purchase_count",
                            "first_observed_date",
                            "last_purchase_date",
                            "days_since_purchase",
                            "average_gap_days",
                            "average_invoice",
                            "currency",
                            "party_id",
                        )
                    ),
                    "SUMMARY",
                ),
                View(
                    "purchases",
                    "Invoices and returns",
                    tuple(
                        column(key)
                        for key in (
                            "period",
                            "posting_date",
                            "bill_reference",
                            "account_name",
                            "invoice_kind",
                            "net_sales",
                            "currency",
                            "invoice_id",
                            "party_id",
                        )
                    ),
                ),
            )
        if code == "EXPENSE_PROFIT_LEAKAGE":
            account_keys = (
                "period",
                "label",
                "classification",
                "amount",
                "comparison_amount",
                "change_amount",
                "change_percent",
                "exception",
                "currency",
                "account_id",
            )
            views = tuple(
                View(name, title, tuple(column(key) for key in keys), "SUMMARY")
                for name, title, keys in (
                    ("default", "Expense accounts", account_keys),
                    (
                        "groups",
                        "Expense groups",
                        (
                            "period",
                            "label",
                            "amount",
                            "comparison_amount",
                            "change_amount",
                            "change_percent",
                            "currency",
                            "group_id",
                        ),
                    ),
                    ("exceptions", "Material spending changes", account_keys),
                    (
                        "suppliers",
                        "Supplier purchase spending",
                        (
                            "period",
                            "label",
                            "amount",
                            "purchases",
                            "purchase_returns",
                            "invoice_count",
                            "currency",
                            "party_id",
                        ),
                    ),
                    (
                        "periods",
                        "Expense trend",
                        (
                            "period",
                            "date",
                            "amount",
                            "direct_costs",
                            "operating_expenses",
                            "posted_income",
                            "currency",
                        ),
                    ),
                )
            )
        if code == "CASH_WORKING_CAPITAL":
            bill_keys = (
                "period",
                "label",
                "reference",
                "direction",
                "amount",
                "due_date",
                "days_overdue",
                "aging_bucket",
                "currency",
                "document_currency",
                "account_id",
                "party_id",
            )
            views = tuple(
                View(name, title, tuple(column(key) for key in keys), "SUMMARY")
                for name, title, keys in (
                    (
                        "default",
                        "Cash and bank balances",
                        (
                            "period",
                            "label",
                            "opening",
                            "net_movement",
                            "closing",
                            "comparison_amount",
                            "change_amount",
                            "currency",
                            "account_id",
                        ),
                    ),
                    ("customers", "Customer collections and credits", bill_keys),
                    ("suppliers", "Supplier dues and credits", bill_keys),
                    (
                        "stock",
                        "Owned stock tied up",
                        (
                            "period",
                            "label",
                            "amount",
                            "quantity",
                            "unit",
                            "stock_status",
                            "currency",
                            "item_id",
                            "position_id",
                        ),
                    ),
                    (
                        "movements",
                        "Net cash effects by journal",
                        (
                            "period",
                            "date",
                            "label",
                            "movement_kind",
                            "amount",
                            "currency",
                            "journal_id",
                        ),
                    ),
                )
            )
        if code == "EXPENSE_PROFIT_LEAKAGE":
            views += (
                View(
                    "reductions",
                    "Sales returns and discounts",
                    tuple(
                        column(key)
                        for key in (
                            "period",
                            "label",
                            "amount",
                            "comparison_amount",
                            "change_amount",
                            "currency",
                        )
                    ),
                    "SUMMARY",
                ),
                View(
                    "writeoffs",
                    "Recorded stock losses",
                    tuple(
                        column(key)
                        for key in (
                            "period",
                            "date",
                            "label",
                            "action",
                            "amount",
                            "currency",
                            "item_id",
                        )
                    ),
                    "SUMMARY",
                ),
            )
        if code in {"BUYER_PROFIT", "PRODUCT_PROFIT"}:
            views = tuple(
                View(
                    key,
                    title,
                    tuple(
                        Column("label", label) if name == "label" else column(name)
                        for name in (
                            (
                                "period",
                                "label",
                                "currency",
                                "net_sales",
                                "cost",
                                "gross_profit",
                                "margin_percent",
                                "cost_status",
                                "account_name",
                                "posting_date",
                            )
                            if key == "invoices"
                            else (
                                "period",
                                "label",
                                "currency",
                                "net_sales",
                                "cost",
                                "gross_profit",
                                "margin_percent",
                                "cost_status",
                            )
                        )
                    ),
                    "SUMMARY",
                )
                for key, title, label in (
                    (
                        ("default", "Buyers", "Buyer"),
                        ("invoices", "Invoices and returns", "Invoice / return"),
                    )
                    if code == "BUYER_PROFIT"
                    else (
                        ("default", "Products", "Product"),
                        ("groups", "Product groups", "Product group"),
                    )
                )
            )
        definition = ReportDefinition(
            code,
            2 if code in {"BUYER_PROFIT", "PRODUCT_PROFIT"} else 1,
            TITLES[code],
            TITLES[code] + " from verified posted and commercial evidence.",
            implementation(),
            fingerprint(adapter.parameters()),
            ("invoice", "inventory", "journal_line"),
            (),
            tuple(
                sorted(
                    INPUT_PERMISSIONS
                    | (set() if code == "CUSTOMER_INSIGHTS" else {"item.read", "warehouse.read"})
                    | ({"accounting.bank.read"} if code == "CASH_WORKING_CAPITAL" else set())
                )
            ),
            views,
            resource_class="BULK",
            drilldowns=(
                *(
                    (
                        Drilldown(
                            "profit_group_products", "Products in this group", "PRODUCT_PROFIT"
                        ),
                    )
                    if code == "PRODUCT_PROFIT"
                    else ()
                ),
                Drilldown("row_detail", "Frozen row details", code),
                Drilldown(
                    "analytics_purchases", "Purchase invoices and returns", "PURCHASE_REGISTER"
                )
                if code == "EXPENSE_PROFIT_LEAKAGE"
                else Drilldown("analytics_sales", "Sales invoices and returns", "SALES_REGISTER"),
                Drilldown("invoice_components", "Invoice components", "INVOICE_COMPONENT_REGISTER"),
                Drilldown("account_entries", "Account ledger", "ACCOUNT_LEDGER"),
                Drilldown("journal_entries", "Journal entries", "DAY_BOOK"),
                Drilldown("party_bills", "Outstanding bills", "OUTSTANDING_BILLS"),
            ),
        )
        entries.append(Registration(definition, adapter))
    return entries
