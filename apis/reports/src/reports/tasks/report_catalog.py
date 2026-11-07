"""Composition root for definitions and adapters; no HTTP or database work at registration."""

import datetime as dt
import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any

from reporting_contract.contract import Control, Fact

from reports.domain.reconcile import reconcile
from reports.domain.reporting.contracts import (
    Column,
    DatasetDefinition,
    Layout,
    MetricDefinition,
    ReportDefinition,
    ValueKind,
    View,
    fingerprint,
)
from reports.domain.reporting.registry import Registration, Registry
from reports.domain.reporting.report_specs import OUTPUTS, drilldowns
from reports.domain.reporting.views import registered
from reports.domain.statements import STATEMENTS, calculate
from reports.runtimes import calculation_dependencies
from reports.schemas import report_parameters as p
from reports.schemas.requests import RunRequest
from reports.tasks.access import INPUT_PERMISSIONS


@dataclass(frozen=True)
class ReferenceAdapter:
    """Compatibility oracle for RF1; optimized plans replace this adapter per family."""

    code: str
    parameter_model: type[p.SourceParameters] | type[p.DateRange] | type[p.AsOfParameters]

    def normalize(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return self.parameter_model.model_validate(values).model_dump(
            mode="json", exclude_none=True
        )

    def parameters(self) -> dict[str, Any]:
        return self.parameter_model.model_json_schema()

    def request(
        self, generation_id: uuid.UUID, values: Mapping[str, Any], coverage_start: dt.date
    ) -> RunRequest:
        parameters = self.normalize(values)
        if issubclass(
            self.parameter_model, p.BalanceSheetParameters | p.InvoiceSettlementParameters
        ):
            parameters["date_from"] = coverage_start.isoformat()
            if parameters.get("comparative_to"):
                parameters["comparative_from"] = coverage_start.isoformat()
        if issubclass(self.parameter_model, p.AsOfParameters | p.BankReconciliationParameters):
            parameters["date_from"] = coverage_start.isoformat()
        if issubclass(
            self.parameter_model, p.InvoiceParameters | p.InvoiceSettlementParameters
        ) and parameters.get("currency"):
            parameters["basis"] = "TRANSACTION"
        return RunRequest.model_validate(
            parameters | {"code": self.code, "generation_id": generation_id}
        )

    def execute(
        self,
        facts: list[Fact],
        generation_id: uuid.UUID,
        values: Mapping[str, Any],
        control: Control,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        query = self.request(generation_id, values, control.coverage_start or dt.date.max)
        if self.code == "SOURCE_RECONCILIATION":
            _, _, evidence = reconcile(facts, control)
            rows = [
                {"row_kind": "SOURCE_COUNT", "kind": "SOURCE_COUNT", "source": key, "count": value}
                for key, value in sorted(evidence["counts"].items())
            ]
            rows.extend(
                {"row_kind": "GL_CONTROL", "kind": "GL_CONTROL", "currency": currency, **totals}
                for currency, totals in sorted(evidence["base_totals"].items())
            )
            return rows, evidence
        if control.coverage_start is None:
            raise ValueError("complete retained source coverage is required")
        return calculate(facts, query, control.coverage_start)


def columns(*keys: str) -> tuple[Column, ...]:
    monetary = {
        "taxable_value",
        "previous_closing",
        "next_opening",
        "previous_debit",
        "previous_credit",
        "next_debit",
        "next_credit",
        "debit",
        "credit",
        "balance",
        "opening",
        "closing",
        "balance_debit",
        "balance_credit",
        "amount",
        "imported_ytd_amount",
        "payable",
        "tax_total",
        "commercial_total",
        "report_amount",
        "original_amount",
        "allocated_amount",
        "remaining",
        "charged_tax_total",
        "rounding",
        "supplier_difference",
        "debt",
        "unapplied_credit",
        "CURRENT",
        "DAYS_1_30",
        "DAYS_31_60",
        "DAYS_61_90",
        "DAYS_OVER_90",
        "UNKNOWN",
        "net",
        "tax_amount",
        "component_amount",
        "allocation_amount",
        "basis_amount",
        "component_taxable_basis",
        "matched_amount",
        "residual",
        "book_balance",
        "statement_balance",
        "difference",
        "cleared_balance",
        "assets",
        "liabilities",
        "equity",
        "untransferred_earnings",
        "DEBIT",
        "CREDIT",
        "event_amount",
        "recorded_tax",
        "pending",
        "eligible_unclaimed",
        "claimed",
        "suspended",
        "blocked",
        "rcm_discharged",
        "settlement_amount",
        "signed_debit",
        "signed_amount",
        "opening_balance",
        "closing_balance",
        "outstanding_book_amount",
        "uncleared_signed",
        "expected_statement_balance",
    }
    result = []
    for key in keys:
        kind: ValueKind = "TEXT"
        if key in monetary:
            kind = "MONEY"
        elif key.endswith("_id") or key in {
            "account_code",
            "number",
            "reference",
            "bill_reference",
        }:
            kind = "IDENTIFIER"
        elif key.endswith("date") or key == "as_of":
            kind = "DATE"
        elif key in {"count", "age_days", "days_overdue"} or key.endswith("_count"):
            kind = "INTEGER"
        elif key in {"percentage", "basis_quantity"}:
            kind = "DECIMAL"
        elif key in {
            "active",
            "cleared",
            "reconciled",
            "balance_agrees",
            "derived",
            "supplier_charged",
        }:
            kind = "BOOLEAN"
        result.append(
            Column(
                key,
                key.replace("_", " ").title(),
                kind,
                ("report_currency" if key == "report_amount" else "currency")
                if kind == "MONEY"
                else None,
            )
        )
    return tuple(result)


LEDGER = columns(
    "row_kind",
    "period",
    "date",
    "number",
    "account_code",
    "account_name",
    "currency",
    "debit",
    "credit",
    "balance",
)
STATEMENT = columns(
    "row_kind",
    "period",
    "account_code",
    "account_name",
    "nature",
    "currency",
    "opening",
    "debit",
    "credit",
    "closing",
    "balance_debit",
    "balance_credit",
    "amount",
    "difference",
    "assets",
    "liabilities",
    "equity",
    "untransferred_earnings",
    "imported_ytd_amount",
)
BILLS = columns(
    "row_kind",
    "period",
    "reference",
    "account_id",
    "party_id",
    "role",
    "direction",
    "due_date",
    "report_currency",
    "currency",
    "report_amount",
    "days_overdue",
    "aging_bucket",
)
INVOICE = columns(
    "row_kind",
    "period",
    "bill_reference",
    "invoice_kind",
    "document_date",
    "posting_date",
    "due_date",
    "currency",
    "commercial_total",
    "tax_total",
    "payable",
)
BANK = columns(
    "row_kind",
    "period",
    "date",
    "source_id",
    "status",
    "currency",
    "amount",
    "matched_amount",
    "residual",
    "book_balance",
    "statement_balance",
    "difference",
    "transaction_date",
    "booking_date",
    "instrument_date",
    "instrument_id",
    "statement_entry_id",
    "mode",
    "reference",
    "state",
    "side",
    "signed_amount",
    "opening_balance",
    "closing_balance",
    "outstanding_book_amount",
    "uncleared_signed",
    "expected_statement_balance",
)

SETTLEMENT = columns(
    "row_kind",
    "period",
    "invoice_id",
    "bill_reference",
    "allocation_id",
    "posting_date",
    "reversal_date",
    "as_of",
    "active",
    "currency",
    "settlement_amount",
)
TENDER = columns(
    "row_kind",
    "period",
    "voucher_kind",
    "number",
    "posting_date",
    "account_id",
    "instrument_id",
    "mode",
    "reference",
    "instrument_date",
    "recognition",
    "side",
    "currency",
    "amount",
    "signed_amount",
)

DATASETS = (
    DatasetDefinition(
        "owner_fact",
        1,
        "one retained owner entity version",
        ("entity", "source_id"),
        ("entity", "source_id"),
        (),
        ("POSTING",),
    ),
    DatasetDefinition(
        "journal_line",
        1,
        "one posted journal line",
        ("source_id",),
        ("source_id", "journal_id", "account_id", "posting_date", "currency"),
        ("amount", "base_amount"),
        ("POSTING",),
    ),
    DatasetDefinition(
        "open_item",
        1,
        "one original bill with dated allocation history",
        ("source_id",),
        ("source_id", "account_id", "due_date", "currency"),
        ("amount", "base_amount"),
        ("POSTING",),
    ),
    DatasetDefinition(
        "invoice",
        1,
        "one invoice, with separately grained component views",
        ("source_id",),
        ("source_id", "invoice_id", "currency"),
        ("payable",),
        ("POSTING", "DOCUMENT", "TAX_POINT"),
    ),
    DatasetDefinition(
        "bank",
        1,
        "dated instrument, match and statement evidence",
        ("entity", "source_id"),
        ("entity", "source_id", "account_id", "currency"),
        ("amount",),
        ("BOOKING", "BANK"),
    ),
)
METRICS = (
    MetricDefinition(
        "debit",
        1,
        "Gross debit turnover without opening effects",
        "ADDITIVE",
        "SINGLE_CURRENCY",
        "POSTING",
        "POSITIVE_DEBIT",
    ),
    MetricDefinition(
        "credit",
        1,
        "Gross credit turnover without opening effects",
        "ADDITIVE",
        "SINGLE_CURRENCY",
        "POSTING",
        "POSITIVE_CREDIT",
    ),
    MetricDefinition(
        "balance",
        1,
        "As-of debit less credit; do not sum across dates",
        "BALANCE",
        "SINGLE_CURRENCY",
        "AS_OF_POSTING",
        "DEBIT_POSITIVE",
        ("debit", "credit"),
    ),
)


@lru_cache(maxsize=1)
def implementation_hash() -> str:
    # Hash packaged rule/schema source, not a manually maintained rule-name constant.
    root = files("reports")
    digest = hashlib.sha256()
    digest.update(calculation_dependencies().encode())
    digest.update(
        files("reporting_contract").joinpath("inventory.py").read_bytes().replace(b"\r\n", b"\n")
    )
    for name in (
        "domain/gstr3b.py",
        "schemas/gstr3b.py",
        "tasks/gstr3b_catalog.py",
        "tasks/gstr3b_source.py",
        "domain/statements.py",
        "domain/book_summaries.py",
        "domain/tax_summaries.py",
        "domain/balance_continuity.py",
        "domain/reporting/control_views.py",
        "queries/native_continuity.py",
        "domain/reporting/inventory.py",
        "domain/reporting/inventory_metrics.py",
        "domain/reporting/inventory_reorder.py",
        "domain/reporting/inventory_trace.py",
        "domain/reporting/inventory_valuation.py",
        "schemas/inventory.py",
        "tasks/inventory_catalog.py",
        "tasks/inventory_source.py",
        "domain/reporting/opening.py",
        "domain/reporting/opening_coverage.py",
        "domain/reporting/history_coverage.py",
        "domain/reporting/views.py",
        "domain/reporting/finance_views.py",
        "domain/reporting/navigation.py",
        "domain/reporting/report_specs.py",
        "tasks/result_query.py",
        "runtimes/ledger_v2/__init__.py",
        "runtimes/ledger_v2/context.py",
        "runtimes/ledger_v2/query.py",
        "runtimes/ledger_v2/source.py",
        "runtimes/ledger_v2/parameters.py",
        "tasks/bulk_summary.py",
        "queries/native_ledger.py",
        "queries/native_context.py",
        "queries/native_statements.py",
        "queries/native_invoices.py",
        "queries/native_open_items.py",
        "queries/native_components.py",
        "queries/native_bank.py",
        "runtimes/ledger_v1/__init__.py",
        "runtimes/ledger_v1/context.py",
        "runtimes/ledger_v1/parameters.py",
        "runtimes/ledger_v1/query.py",
        "runtimes/ledger_v1/source.py",
        "queries/native_reconciliation.py",
        "queries/projection.py",
        "models/posted_lines.py",
        "models/daily_balances.py",
        "tasks/daily_projection.py",
        "tasks/posted_projection.py",
        "tasks/native_execution.py",
        "domain/registers.py",
        "domain/invoice_registers.py",
        "domain/reconcile.py",
        "domain/invoice_reconciliation.py",
        "schemas/requests.py",
        "schemas/report_parameters.py",
        "tasks/report_catalog.py",
        "domain/reporting/contracts.py",
        "domain/reporting/profit_views.py",
        "domain/reporting/balance_views.py",
        "domain/reporting/registry.py",
        "domain/reporting/drilldowns.py",
    ):
        source = root.joinpath(name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode() + b"\0" + source + b"\0")
    return digest.hexdigest()


def registration(
    code: str,
    parameters: type[p.SourceParameters] | type[p.DateRange] | type[p.AsOfParameters],
    dataset: str,
    output: tuple[Column, ...],
    layout: Layout = "REGISTER",
) -> Registration[ReferenceAdapter]:
    handler = ReferenceAdapter(code, parameters)
    output = columns(*OUTPUTS[code])
    permissions = set(INPUT_PERMISSIONS)
    if dataset == "bank" or code in {"PAYMENT_REGISTER", "RECEIPT_REGISTER"}:
        permissions.add("accounting.bank.read")
    if code in {"BANK_RECONCILIATION_EVIDENCE", "BANK_RECONCILIATION_WORKLIST"}:
        permissions.add("accounting.statement.read")
    title = {
        "PROFIT_LOSS": "Profit and Loss",
        "BALANCE_CONTINUITY": "Balance continuity",
        "SOURCE_RECONCILIATION": "Source reconciliation",
        "INVOICE_GL_BRIDGE": "Invoice to ledger reconciliation",
        "INVOICE_TAX_REGISTER": "Invoice Tax Register",
        "INVOICE_CREDIT_REGISTER": "Input Tax Credit Register",
        "TAX_GL_BRIDGE": "Tax to Ledger Reconciliation",
    }.get(code, code.replace("_", " ").title())
    definition = ReportDefinition(
        code=code,
        version=6
        if code
        in {
            "BALANCE_CONTINUITY",
            "SOURCE_RECONCILIATION",
            "INVOICE_GL_BRIDGE",
            "PROFIT_LOSS",
            "INCOME_EXPENSE",
            "BANK_RECONCILIATION",
            "INVOICE_SETTLEMENT_REGISTER",
            "BALANCE_SHEET",
            "ACCOUNT_SUMMARY",
            "OUTSTANDING_BILLS",
            "ADVANCES",
            "INVOICE_TAX_REGISTER",
            "INVOICE_CREDIT_REGISTER",
            "TAX_GL_BRIDGE",
        }
        else 5,
        title=title,
        description=f"{title} from a reconciled, immutable company generation.",
        implementation_hash=implementation_hash(),
        parameter_schema_hash=fingerprint(handler.parameters()),
        datasets=(dataset,),
        metrics=tuple(metric.key for metric in METRICS),
        permissions=tuple(sorted(permissions)),
        views=registered(code, title, output, View("default", title, output, layout)),
        financial_statement=code in STATEMENTS,
        resource_class="BULK" if layout == "REGISTER" else "SHORT",
        drilldowns=drilldowns(code),
    )
    return Registration(definition, handler)


@lru_cache(maxsize=1)
def catalog() -> Registry[ReferenceAdapter]:
    """Add definitions here; the engine resolves handlers without adding dispatch branches."""
    from reports.tasks.day_book_catalog import registration as day_book_registration
    from reports.tasks.trial_balance_catalog import registration as trial_balance_registration

    entries = [
        day_book_registration(),
        trial_balance_registration(),
        registration(
            "TRIAL_BALANCE", p.StatementParameters, "journal_line", STATEMENT, "STATEMENT"
        ),
        registration(
            "BALANCE_CONTINUITY",
            p.ContinuityParameters,
            "journal_line",
            columns("row_kind"),
            "RECONCILIATION",
        ),
        registration(
            "SOURCE_RECONCILIATION",
            p.SourceParameters,
            "owner_fact",
            columns("kind", "source", "count", "currency", "DEBIT", "CREDIT"),
            "RECONCILIATION",
        ),
        *(
            registration(code, p.LedgerParameters, "journal_line", LEDGER)
            for code in ("ACCOUNT_LEDGER", "DAY_BOOK", "PARTY_LEDGER", "CASH_BOOK", "BANK_BOOK")
        ),
        *(
            registration(
                code,
                p.ProfitParameters
                if code in {"PROFIT_LOSS", "INCOME_EXPENSE"}
                else p.BalanceSheetParameters
                if code == "BALANCE_SHEET"
                else p.StatementParameters,
                "journal_line",
                STATEMENT,
                "STATEMENT",
            )
            for code in sorted(STATEMENTS - {"TRIAL_BALANCE"})
        ),
        registration(
            "ACCOUNT_SUMMARY",
            p.SummaryParameters,
            "journal_line",
            columns(
                "row_kind",
                "period",
                "account_id",
                "group_code",
                "date",
                "grain",
                "currency",
                "opening",
                "debit",
                "credit",
                "net",
                "closing",
            ),
            "SUMMARY",
        ),
        *(
            registration(code, p.AsOfParameters, "open_item", BILLS)
            for code in ("OUTSTANDING_BILLS", "ADVANCES")
        ),
        registration(
            "AGING",
            p.AsOfParameters,
            "open_item",
            columns(
                "row_kind",
                "party_id",
                "account_id",
                "currency",
                "debt",
                "unapplied_credit",
                "CURRENT",
                "DAYS_1_30",
                "DAYS_31_60",
                "DAYS_61_90",
                "DAYS_OVER_90",
                "UNKNOWN",
            ),
            "SUMMARY",
        ),
        registration(
            "BANK_RECONCILIATION", p.BankReconciliationParameters, "bank", BANK, "RECONCILIATION"
        ),
        registration(
            "BANK_RECONCILIATION_EVIDENCE", p.BankEvidenceParameters, "bank", BANK, "RECONCILIATION"
        ),
        registration(
            "BANK_RECONCILIATION_WORKLIST", p.BankWorklistParameters, "bank", BANK, "RECONCILIATION"
        ),
        *(
            registration(code, p.LedgerParameters, "bank", TENDER)
            for code in ("PAYMENT_REGISTER", "RECEIPT_REGISTER")
        ),
        *(
            registration(code, p.InvoiceDocumentParameters, "invoice", INVOICE)
            for code in ("SALES_REGISTER", "PURCHASE_REGISTER")
        ),
        registration(
            "INVOICE_COMPONENT_REGISTER",
            p.InvoiceParameters,
            "invoice",
            columns(
                "row_kind",
                "period",
                "invoice_id",
                "source_id",
                "currency",
                "component_amount",
                "allocation_amount",
            ),
        ),
        registration(
            "INVOICE_TAX_REGISTER",
            p.InvoiceTaxParameters,
            "invoice",
            columns(
                "row_kind",
                "period",
                "invoice_id",
                "component_id",
                "tax_code",
                "tax_point_date",
                "currency",
                "tax_amount",
            ),
        ),
        registration(
            "INVOICE_CREDIT_REGISTER",
            p.InvoiceCreditParameters,
            "invoice",
            columns(*OUTPUTS["INVOICE_CREDIT_REGISTER"]),
        ),
        registration(
            "INVOICE_SETTLEMENT_REGISTER", p.InvoiceSettlementParameters, "invoice", SETTLEMENT
        ),
        registration(
            "INVOICE_GL_BRIDGE",
            p.InvoiceParameters,
            "invoice",
            columns(*OUTPUTS["INVOICE_GL_BRIDGE"]),
            "RECONCILIATION",
        ),
        registration(
            "TAX_GL_BRIDGE",
            p.TaxBridgeParameters,
            "invoice",
            columns(*OUTPUTS["TAX_GL_BRIDGE"]),
            "RECONCILIATION",
        ),
    ]
    from reports.tasks.analytics_catalog import registrations as analytics_registrations
    from reports.tasks.gstr1_catalog import DATASET as GST1_DATASET
    from reports.tasks.gstr1_catalog import registration as gst1_registration
    from reports.tasks.gstr3b_catalog import DATASET as GST_DATASET
    from reports.tasks.gstr3b_catalog import registration as gst_registration
    from reports.tasks.inventory_catalog import DATASET, registrations

    return Registry(
        [
            *entries,
            gst_registration(implementation_hash()),
            gst1_registration(implementation_hash()),
            *registrations(implementation_hash()),
            *analytics_registrations(),
        ],
        (*DATASETS, DATASET, GST_DATASET, GST1_DATASET),
        METRICS,
    )
