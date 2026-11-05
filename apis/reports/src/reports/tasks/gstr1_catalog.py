"""GSTR-1 versioned definition and frozen statutory context."""

import datetime as dt
import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.errors import ValidationFailedError
from reporting_contract.contract import Control, Fact
from reporting_contract.gst_outward import MONEY

from reports.domain.gstr1 import calculate
from reports.domain.gstr1_rules import applicable, bounds
from reports.domain.reporting.contracts import (
    Column,
    DatasetDefinition,
    ReportDefinition,
    View,
    fingerprint,
)
from reports.domain.reporting.registry import Registration
from reports.schemas.gstr1 import Gstr1Parameters
from reports.tasks.access import INPUT_PERMISSIONS
from reports.tasks.gstr3b_catalog import context as filing_context
from reports.tasks.report_catalog import ReferenceAdapter

TEXT_FIELDS = (
    ("table", "Table"),
    ("table_label", "Table description"),
    ("row_role", "Record role"),
    ("supply_location", "Inter / intra-state supply"),
    ("nil_rated", "Nil-rated supplies"),
    ("exempt", "Exempt supplies"),
    ("non_gst", "Non-GST supplies"),
    ("source_records", "Contributing evidence IDs"),
    ("source_line_id", "Native source line ID"),
    ("source_line_ids", "Grouped native source line IDs"),
    ("original_taxable", "Original taxable value"),
    ("differential_taxable", "Taxable differential"),
    ("source_currency", "Original currency"),
    ("source_invoice_value", "Original invoice value"),
    ("conversion_rate", "INR conversion rate"),
    ("conversion_date", "Conversion date"),
    ("conversion_reference", "Conversion evidence"),
    ("document_number", "Document number"),
    ("document_date", "Document date"),
    ("return_date", "Return date"),
    ("kind", "Document type"),
    ("recipient_gstin", "Recipient GSTIN/UIN"),
    ("recipient_name", "Recipient name"),
    ("recipient_type", "Recipient type"),
    ("place_of_supply", "Place of supply"),
    ("supply_type", "Supply type"),
    ("reverse_charge", "Reverse charge"),
    ("rate", "Rate (%)"),
    ("currency", "Currency"),
    ("hsn", "HSN/SAC"),
    ("uqc", "UQC"),
    ("quantity", "Quantity"),
    ("treatment", "Treatment"),
    ("operator_gstin", "Operator GSTIN"),
    ("supplier_gstin", "Supplier GSTIN"),
    ("eco_scheme", "ECO provision"),
    ("shipping_bill_number", "Shipping bill number"),
    ("shipping_bill_date", "Shipping bill date"),
    ("port_code", "Port code"),
    ("original_document_number", "Original document number"),
    ("original_document_date", "Original document date"),
    ("amendment_chain", "Amendment baseline history"),
    ("prior_filed_channel", "Previously furnished"),
    ("reference", "Evidence reference"),
    ("evidence_hash", "Evidence SHA-256"),
    ("explanation", "Explanation"),
    ("serial_from", "Serial from"),
    ("serial_to", "Serial to"),
    ("total_count", "Total issued"),
    ("cancelled_count", "Cancelled"),
    ("net_count", "Net issued"),
    ("source_count", "Source count"),
    ("liability_included", "Primary contribution"),
    ("record_id", "Evidence ID"),
    ("original_record_id", "Original evidence ID"),
    ("source_entity", "Owner source"),
    ("source_id", "Owner source ID"),
    ("voucher_id", "Voucher ID"),
    ("journal_id", "Journal ID"),
)
COLUMNS = tuple(Column(key, label) for key, label in TEXT_FIELDS) + tuple(
    Column(key, "Invoice value" if key == "invoice_value" else key.upper(), "MONEY", "currency")
    for key in ("invoice_value", *MONEY)
)
DATASET = DatasetDefinition(
    "gst_outward",
    1,
    "one statutory table contribution",
    ("id",),
    ("id", "record_id", "table", "document_number", "return_date"),
    MONEY,
    ("RETURN_PERIOD",),
)


def context(registrations: tuple[dict[str, Any], ...], values: dict[str, Any]) -> dict[str, Any]:
    eligible = tuple(row for row in registrations if applicable(row))
    captured = filing_context(eligible, values)
    captured["preparation_date"] = dt.date.today().isoformat()
    try:
        bounds(values["period"], captured["frequency"])
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return captured


def result(
    records: list[dict[str, Any]],
    values: Mapping[str, Any],
    sequence: int | None = None,
    unresolved: list[str] | None = None,
    originals: dict[str, dict[str, Any]] | None = None,
    comparison: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    captured = values["_gst_context"]
    rows, evidence = calculate(
        records,
        captured["registration"],
        dt.date.fromisoformat(captured["date_from"]),
        dt.date.fromisoformat(captured["date_to"]),
        sequence=sequence,
        as_of=dt.date.fromisoformat(captured["preparation_date"])
        if captured.get("preparation_date")
        else None,
        unresolved_sources=unresolved,
        originals=originals,
        comparison=comparison,
    )
    if values.get("comparison_job_id"):
        evidence["comparison_job_id"] = values["comparison_job_id"]
    return rows, {"gstr1": evidence, "row_count": len(rows)}


class GstOutwardAdapter(ReferenceAdapter):
    def execute(
        self,
        facts: list[Fact],
        generation_id: uuid.UUID,
        values: Mapping[str, Any],
        control: Control,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        records = [
            row.data | {"id": str(row.source_id)}
            for row in facts
            if row.entity == "gst_outward_record" and row.data
        ]
        return result(records, values)


def registration(implementation_hash: str) -> Registration[ReferenceAdapter]:
    handler = GstOutwardAdapter("GSTR1", Gstr1Parameters)
    return Registration(
        ReportDefinition(
            "GSTR1",
            1,
            "GSTR-1",
            (
                "GSTIN and period outward supplies, statutory tables, HSN, issued "
                "documents and reconciliation."
            ),
            implementation_hash,
            fingerprint(handler.parameters()),
            ("gst_outward",),
            (),
            tuple(sorted(INPUT_PERMISSIONS)),
            (View("default", "Statutory table records", COLUMNS),),
            resource_class="BULK",
        ),
        handler,
    )
