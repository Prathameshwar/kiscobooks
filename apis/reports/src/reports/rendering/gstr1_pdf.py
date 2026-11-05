"""Prescribed section tables, complete source rows and a separate 3B bridge."""

# mypy: disable-error-code=import-untyped
import itertools
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from reporting_contract.gst_outward import MONEY
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from reports.domain.gstr1 import AGGREGATE_TABLES
from reports.domain.gstr1_rules import TABLES
from reports.rendering.gstr1 import section_fields
from reports.rendering.pdf_layout import markup, register_fonts
from reports.rendering.presentation import bundle
from reports.tasks.gstr1_catalog import COLUMNS


def render(lines: Iterable[str], output: Path, settings: dict[str, Any]) -> dict[str, int]:
    register_fonts()
    evidence = settings["gstr1"]
    tokens = bundle()["tokens"]
    body = ParagraphStyle("gstr1", fontName="NotoSans-Regular", fontSize=7, leading=10)
    numeric = ParagraphStyle("gstr1-numeric", parent=body, alignment=TA_RIGHT)
    heading = ParagraphStyle(
        "gstr1-heading",
        parent=body,
        fontName="NotoSans-Bold",
        fontSize=12,
        leading=16,
        keepWithNext=True,
    )
    story: list[Any] = []
    summary_heading = ParagraphStyle("gstr1-summary-heading", parent=heading, keepWithNext=False)
    compact = ParagraphStyle("gstr1-compact", parent=body, fontSize=6.5, leading=8.5)
    compact_numeric = ParagraphStyle("gstr1-compact-numeric", parent=compact, alignment=TA_RIGHT)
    width = landscape(A4)[0] - 64
    labels = {column.key: column.title for column in COLUMNS}

    def text(value: object, bold: bool = False) -> Any:
        style = heading if bold else numeric if re.fullmatch(r"-?\d+\.\d+", str(value)) else body
        return Paragraph(markup("" if value is None else str(value)), style)

    def table(headers: list[str], rows: Iterable[list[Any]], *, compact_rows: bool = False) -> None:
        summary = len(headers) == 7 and headers[1] == "Description"

        def cell(value: object) -> Any:
            if not summary:
                return text(value)
            style = compact_numeric if re.fullmatch(r"-?\d+\.\d+", str(value)) else compact
            return Paragraph(markup("" if value is None else str(value)), style)

        data = [[cell(value) for value in headers]]
        data.extend([cell(value) for value in row] for row in rows)
        widths = (
            [width * 0.08, width * 0.34, *[width * 0.116] * 5]
            if summary
            else [width / len(headers)] * len(headers)
        )
        target = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        target.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(tokens["--janso-line"])),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(tokens["--janso-brand-tint"])),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 1 if summary or compact_rows else 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1 if summary or compact_rows else 3),
                ]
            )
        )
        story.extend([target, Spacer(1, 12)])

    story.append(text("FORM GSTR-1 — Outward supplies preparation", True))
    story.append(
        text(
            f"GSTIN {evidence['registration']['number']} | "
            f"{evidence['registration'].get('legal_name', '')}"
        )
    )
    story.append(
        text(
            f"{evidence['date_from']} to {evidence['date_to']} | "
            f"GST FY {evidence['financial_year']} | INR"
        )
    )
    story.append(
        text(
            f"{evidence['status']} | NIL {evidence['nil']} | Rule {evidence['rule_version']}"
            f" | Calculation revision {evidence.get('calculation_version', 'Legacy')}"
        )
    )
    story.append(text(settings["document"]["source_as_of"]))
    story.append(Paragraph("Statutory table summary", summary_heading))
    table(
        ["Table", "Description", *[head.upper() for head in MONEY]],
        (
            [key, label, *["—" if key == "13" else evidence["form"][key][head] for head in MONEY]]
            for key, label in TABLES.items()
        ),
    )
    story.append(text("GSTR-3B bridge — includes previously furnished IFF evidence", True))
    table(
        ["Category", "Description", *[head.upper() for head in MONEY]],
        (
            [key, evidence["bridge_labels"][key], *[values[head] for head in MONEY]]
            for key, values in evidence["bridge"].items()
        ),
    )
    decoded = (json.loads(line) for line in lines if line.strip())
    count = 0
    for key, members in itertools.groupby(decoded, key=lambda row: row["table"]):
        story.append(text(key + " " + TABLES[key], True))
        fields = section_fields(key)
        retained = list(members)
        count += len(retained)
        retained = [row for row in retained if row.get("row_role") != "LINE"]
        if key in AGGREGATE_TABLES:
            retained = [row for row in retained if row.get("row_role") == "STATUTORY"]
        # Repeat the document identity when wide prescribed tables need a second band.
        for offset in range(0, len(fields), 9):
            band = fields[offset : offset + 9]
            if offset and "document_number" in fields and "document_number" not in band:
                band = ("document_number", *band)
            if offset and key.startswith("12_"):
                band = ("hsn", "uqc", "rate", *band)
            table(
                [labels.get(field, field) for field in band],
                ([row.get(field) for field in band] for row in retained),
            )
    story.append(text("Readiness and reconciliation", True))
    table(
        ["Area", "Status", "Covered sequence", "Reference"],
        (
            [area, proof["status"], proof["covered_sequence"], proof["reference"]]
            for area, proof in evidence.get("coverage_details", {}).items()
        ),
    )
    table(
        ["Code", "Issue", "Source"],
        ([row["code"], row["message"], row["source_id"]] for row in evidence["issues"]),
    )
    if evidence["issue_count"] > len(evidence["issues"]):
        story.append(
            text("Additional exceptions are retained in the Excel workbook and workspace.")
        )
    table(
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
        compact_rows=True,
    )
    story.append(text(evidence["portal_json_reason"]))
    story.append(text("Verification", True))
    story.append(
        text(
            "I solemnly affirm that the information is true and correct to "
            "the best of my knowledge and belief and nothing has been "
            "concealed."
        )
    )
    story.append(
        text(
            "Authorised signatory: __________________   Designation: "
            "__________________   Place / Date: __________________"
        )
    )
    story.append(text("Preparation copy. Complete verification and filing on the GST Portal."))
    pages = 0

    def footer(canvas: Any, document: Any) -> None:
        nonlocal pages
        pages += 1
        canvas.saveState()
        canvas.setFont("NotoSans-Regular", 7)
        canvas.drawString(32, 20, "GSTR-1 | " + settings["document"]["run_id"])
        canvas.drawRightString(landscape(A4)[0] - 32, 20, str(document.page))
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(output),
        pagesize=landscape(A4),
        leftMargin=32,
        rightMargin=32,
        topMargin=32,
        bottomMargin=32,
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return {"pages": pages, "rows": count}
