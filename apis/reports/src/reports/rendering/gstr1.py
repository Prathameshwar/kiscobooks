"""Complete frozen GSTR-1 working papers with prescribed section columns."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from reporting_contract.gst_outward import MONEY

from reports.domain.gstr1 import AGGREGATE_TABLES
from reports.domain.gstr1_rules import TABLES
from reports.domain.reporting.contracts import Column
from reports.rendering.pdf import PdfWriter
from reports.rendering.presentation import Document
from reports.rendering.tabular import Budget, XlsxWriter

SUPPLY_FIELDS = (
    "document_number",
    "document_date",
    "recipient_gstin",
    "place_of_supply",
    "invoice_value",
    "rate",
    *MONEY,
)


def export_rows(rows: list[dict[str, Any]], columns: tuple[Column, ...]) -> list[dict[str, Any]]:
    """Keep structured lineage in frozen results and encode it in portable text cells."""
    text_keys = {column.key for column in columns if column.kind == "TEXT"}
    return [
        {
            key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if key in text_keys and isinstance(value, list | dict)
            else value
            for key, value in row.items()
        }
        for row in rows
    ]


def section_fields(table: str) -> tuple[str, ...]:
    if table == "13":
        return (
            "kind",
            "serial_from",
            "serial_to",
            "total_count",
            "cancelled_count",
            "net_count",
            "reference",
        )
    if table.startswith("12_"):
        return ("hsn", "uqc", "quantity", "rate", "invoice_value", *MONEY)
    if table == "8":
        return ("recipient_type", "supply_location", "nil_rated", "exempt", "non_gst")
    if table in {"7", "10"}:
        return (
            "place_of_supply",
            "rate",
            "treatment",
            "taxable",
            "igst",
            "cgst",
            "sgst",
            "cess",
            "document_number",
        )
    if table.startswith("11"):
        return (
            "place_of_supply",
            "rate",
            "taxable",
            "igst",
            "cgst",
            "sgst",
            "cess",
            "document_number",
        )
    if table.startswith(("14", "15")):
        if table in {"14_TCS", "14_9_5"}:
            return ("operator_gstin", *MONEY, "source_count")
        return (
            "operator_gstin",
            "supplier_gstin",
            "recipient_gstin",
            "document_number",
            "place_of_supply",
            *MONEY,
        )
    if table == "6A" or table == "9A_EXP":
        return (
            *SUPPLY_FIELDS,
            "supply_type",
            "shipping_bill_number",
            "shipping_bill_date",
            "port_code",
        )
    if table.startswith(("9", "10")):
        return ("original_document_number", "original_document_date", *SUPPLY_FIELDS)
    return (*SUPPLY_FIELDS, "reverse_charge", "supply_type")


class GstOutwardPdfWriter(PdfWriter):
    def __init__(
        self,
        path: Path,
        columns: tuple[Column, ...],
        budget: Budget,
        document: Document,
        preparation: dict[str, Any],
    ):
        self.preparation = preparation
        super().__init__(path, columns, budget, document)

    def write(self, text: str) -> None:
        if self.written_bytes == 0:
            settings = json.loads(text)
            evidence = {
                key: value
                for key, value in self.preparation.items()
                if key not in {"registration", "issues"}
            }
            evidence["registration"] = {
                key: self.preparation["registration"].get(key, "")
                for key in ("number", "legal_name")
            }
            evidence["issues"] = self.preparation["issues"][:100]
            evidence["issue_count"] = len(self.preparation["issues"])
            settings["gstr1"] = evidence
            text = json.dumps(settings, ensure_ascii=False, allow_nan=False) + "\n"
            if len(text.encode("utf-8")) > 65536:
                raise ValueError("GSTR-1 preparation exceeds its bounded PDF header")
        super().write(text)


class GstOutwardXlsxWriter(XlsxWriter):
    def __init__(
        self,
        path: Path,
        columns: tuple[Column, ...],
        budget: Budget,
        document: Document | None,
        preparation: dict[str, Any],
    ):
        super().__init__(path, columns, budget, document)
        self.sheet.name = "All table records"
        self.preparation = preparation
        self.sections: dict[str, Any] = {}
        self.section_rows: dict[str, int] = {}
        self.extra_cells = 0
        self.labels = {column.key: column.title for column in columns}
        for table in TABLES:
            target = self.book.add_worksheet("Table " + table)
            self.sections[table], self.section_rows[table] = target, 1
            target.freeze_panes(1, 0)
            target.repeat_rows(0)
            target.set_landscape()
            target.fit_to_pages(1, 0)
            for index, key in enumerate(section_fields(table)):
                target.write_string(0, index, self.labels.get(key, key), self.header)
                target.set_column(index, index, 20)

    def append(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            super().append([row])
            table = row["table"]
            if row.get("row_role") == "LINE":
                continue
            if table in AGGREGATE_TABLES and row.get("row_role") != "STATUTORY":
                continue
            target, ordinal = self.sections[table], self.section_rows[table]
            fields = section_fields(table)
            self.extra_cells += len(fields)
            if self.count * len(self.columns) + self.extra_cells > self.budget.cells:
                raise ValueError("GSTR-1 worksheets exceed their cell budget")
            for index, key in enumerate(fields):
                value = row.get(key)
                status = target.write_string(
                    ordinal, index, "" if value is None else str(value), self.text
                )
                if status != 0:
                    raise ValueError("GSTR-1 worksheet cell cannot be retained without loss")
            self.section_rows[table] += 1

    def finish(self) -> None:
        for key, target in self.sections.items():
            target.autofilter(
                0, 0, max(1, self.section_rows[key]) - 1, len(section_fields(key)) - 1
            )

        def sheet(name: str, headers: list[str], rows: Iterable[list[Any]]) -> None:
            target = self.book.add_worksheet(name)
            target.freeze_panes(1, 0)
            for index, label in enumerate(headers):
                target.write_string(0, index, label, self.header)
                target.set_column(index, index, 26 if index else 48)
            for ordinal, row in enumerate(rows, 1):
                self.extra_cells += len(row)
                if self.count * len(self.columns) + self.extra_cells > self.budget.cells:
                    raise ValueError("GSTR-1 summary exceeds its cell budget")
                for index, value in enumerate(row):
                    if (
                        target.write_string(
                            ordinal, index, "" if value is None else str(value), self.text
                        )
                        != 0
                    ):
                        raise ValueError("GSTR-1 summary cell cannot be retained without loss")

        evidence = self.preparation
        sheet(
            "Coverage evidence",
            ["Area", "Status", "Covered sequence", "Evidence ID", "Reference", "SHA-256"],
            (
                [
                    area,
                    proof["status"],
                    proof["covered_sequence"],
                    proof["record_id"],
                    proof["reference"],
                    proof["evidence_hash"],
                ]
                for area, proof in evidence.get("coverage_details", {}).items()
            ),
        )
        sheet(
            "GSTR-1 summary",
            ["Table", "Description", *[head.upper() for head in MONEY]],
            (
                [
                    key,
                    TABLES[key],
                    *["—" if key == "13" else evidence["form"][key][head] for head in MONEY],
                ]
                for key in TABLES
            ),
        )
        sheet(
            "GSTR-3B bridge",
            ["Category", "Description", *[head.upper() for head in MONEY]],
            (
                [key, evidence["bridge_labels"][key], *[values[head] for head in MONEY]]
                for key, values in evidence["bridge"].items()
            ),
        )
        sheet(
            "Readiness exceptions",
            ["Code", "Issue", "Source"],
            ([row["code"], row["message"], row["source_id"]] for row in evidence["issues"]),
        )
        sheet(
            "Reconciliation",
            ["Source", "Category", "Tax head", "Return", "Compared", "Difference"],
            (
                [
                    row[key]
                    for key in (
                        "source",
                        "category",
                        "head",
                        "return_amount",
                        "source_amount",
                        "difference",
                    )
                ]
                for row in evidence["reconciliation"]
            ),
        )
        sheet(
            "Preparation identity",
            ["Field", "Value"],
            [
                ["GSTIN", evidence["registration"]["number"]],
                ["Legal name", evidence["registration"].get("legal_name", "")],
                ["From", evidence["date_from"]],
                ["To", evidence["date_to"]],
                ["GST financial year", evidence["financial_year"]],
                ["Rule version", evidence["rule_version"]],
                ["Calculation revision", evidence.get("calculation_version", "Legacy")],
                ["Status", evidence["status"]],
                ["Nil", evidence["nil"]],
                ["Previously furnished IFF documents", evidence["iff_count"]],
                ["Portal JSON", evidence["portal_json_reason"]],
                [
                    "Declaration",
                    (
                        "I solemnly affirm that the information is true and correct to "
                        "the best of my knowledge and belief and nothing has been "
                        "concealed."
                    ),
                ],
                ["Authorised signatory", ""],
                ["Designation", ""],
                ["Place", ""],
                ["Date", ""],
                [
                    "Filing",
                    (
                        "Complete statutory verification on the GST Portal. This is a "
                        "preparation copy."
                    ),
                ],
            ],
        )
        super().finish()
