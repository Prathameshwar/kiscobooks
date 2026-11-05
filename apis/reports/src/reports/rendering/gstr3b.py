"""Statutory form artifacts from the same frozen preparation as the workspace."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from reports.domain.gstr3b import FIELDS, FORM_ROWS
from reports.domain.reporting.contracts import Column
from reports.rendering.pdf import PdfWriter
from reports.rendering.presentation import Document
from reports.rendering.tabular import Budget, XlsxWriter


class GstPdfWriter(PdfWriter):
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
            preparation = {
                key: value
                for key, value in self.preparation.items()
                if key not in {"issues", "registration"}
            }
            preparation["registration"] = {
                key: self.preparation["registration"].get(key)
                for key in ("number", "legal_name", "jurisdiction_code")
            }
            preparation["issues"] = self.preparation["issues"][:100]
            preparation["issue_count"] = len(self.preparation["issues"])
            settings["gstr3b"] = preparation
            text = json.dumps(settings, ensure_ascii=False, allow_nan=False) + "\n"
            if len(text) > 65536:
                raise ValueError("GSTR-3B form exceeds its bounded PDF header")
        super().write(text)


class GstXlsxWriter(XlsxWriter):
    def __init__(
        self,
        path: Path,
        columns: tuple[Column, ...],
        budget: Budget,
        document: Document | None,
        preparation: dict[str, Any],
    ):
        super().__init__(path, columns, budget, document)
        self.sheet.name = "Contributing records"
        self.preparation = preparation

    def finish(self) -> None:
        preparation = self.preparation

        def sheet(name: str, headers: list[str], rows: Iterable[list[Any]]) -> None:
            target = self.book.add_worksheet(name)
            target.freeze_panes(1, 0)
            for column, label in enumerate(headers):
                target.write_string(0, column, label, self.header)
                target.set_column(column, column, 24 if column else 48)
            for index, row in enumerate(rows, 1):
                for column, raw in enumerate(row):
                    # Exact statutory decimals remain strings, avoiding Excel's 15-digit loss.
                    target.write_string(index, column, "" if raw is None else str(raw), self.text)
            target.set_landscape()
            target.fit_to_pages(1, 0)

        sheet(
            "GSTR-3B form",
            ["Table", "Description", *[head.upper() for head in FIELDS]],
            (
                [
                    key,
                    preparation["labels"][key],
                    *[preparation["form"][key][head] for head in FIELDS],
                ]
                for key in preparation.get("row_order", list(FORM_ROWS))
            ),
        )
        sheet(
            "Table 3.2",
            ["Recipient", "Place of supply", "Taxable value", "IGST"],
            (
                [row["recipient"], row["place_of_supply"], row["taxable"], row["igst"]]
                for row in preparation["pos_rows"]
            ),
        )
        sheet(
            "Table 5 inward supplies",
            ["Nature", "Interstate supplies", "Intrastate supplies"],
            (
                [row["nature"], row["interstate"], row["intrastate"]]
                for row in preparation["inward_rows"]
            ),
        )
        statutory_keys = [
            "tax_payable",
            "paid_igst",
            "paid_cgst",
            "paid_sgst",
            "paid_cess",
            "paid_cash",
            "interest_paid",
            "late_fee_paid",
        ]
        sheet(
            "Table 6.1 payments",
            ["Liability", "Tax head", *statutory_keys],
            (
                [row["liability_kind"], row["tax_head"], *[row[key] for key in statutory_keys]]
                for row in preparation["payment_rows"]
            ),
        )
        payment_keys = list(next(iter(preparation["payment"].values())))
        sheet(
            "Prior period liability breakup",
            ["Source period date", "Reference", "IGST", "CGST", "SGST / UTGST", "Cess"],
            (
                [row["event_date"], row["reference"], *[row[head] for head in FIELDS[1:]]]
                for row in preparation["prior_liability_rows"]
            ),
        )
        sheet(
            "Payment ledger workings",
            ["Tax head", *payment_keys],
            (
                [head, *[values[key] for key in payment_keys]]
                for head, values in preparation["payment"].items()
            ),
        )
        sheet(
            "ITC utilisation",
            ["Credit head", "Liability head", "Amount"],
            (
                [row["credit_head"], row["liability_head"], row["amount"]]
                for row in preparation["itc_offsets"]
            ),
        )
        sheet(
            "Exceptions",
            ["Code", "Issue", "Source"],
            ([row["code"], row["message"], row["source_id"]] for row in preparation["issues"]),
        )
        sheet(
            "Reconciliation",
            ["Source", "Tax head", "Return amount", "Source amount", "Difference"],
            (
                [
                    row[key]
                    for key in ("source", "head", "return_amount", "source_amount", "difference")
                ]
                for row in preparation["reconciliation"]
            ),
        )
        sheet(
            "Preparation identity",
            ["Field", "Value"],
            [
                ["GSTIN", preparation["registration"]["number"]],
                ["Legal name", preparation["registration"]["legal_name"]],
                ["From", preparation["date_from"]],
                ["To", preparation["date_to"]],
                ["Statutory financial year", preparation["financial_year"]],
                ["Rule version", preparation["rule_version"]],
                ["Calculation revision", preparation.get("calculation_version", "Legacy")],
                ["State", preparation["status"]],
                ["Currency", "INR"],
                ["Nil", str(preparation["nil"])],
                ["Portal JSON", preparation["portal_json_reason"]],
            ],
        )
        sheet(
            "Verification",
            ["Field", "Preparation copy"],
            [
                [
                    "Declaration",
                    "I hereby solemnly affirm and declare that the information given herein "
                    "above is true and correct to the best of my knowledge and belief and "
                    "nothing has been concealed therefrom.",
                ],
                ["Name of authorised signatory", ""],
                ["Designation / status", ""],
                ["Place", ""],
                ["Date", ""],
                [
                    "Filing",
                    "Complete verification on the GST Portal. "
                    "Internal review is not statutory filing.",
                ],
            ],
        )
        super().finish()
