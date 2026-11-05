"""Fixed statutory sections, independent of generic register column bands."""

# mypy: disable-error-code=import-untyped
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from reports.domain.gstr3b import FIELDS, FORM_ROWS
from reports.rendering.pdf_layout import markup, register_fonts
from reports.rendering.presentation import bundle


def render(lines: Iterable[str], output: Path, settings: dict[str, Any]) -> dict[str, int]:
    register_fonts()
    preparation = settings["gstr3b"]
    tokens = bundle()["tokens"]
    style = ParagraphStyle("gst", fontName="NotoSans-Regular", fontSize=8, leading=11)
    numeric = ParagraphStyle("gst-numeric", parent=style, alignment=TA_RIGHT)
    heading = ParagraphStyle(
        "gst-heading",
        parent=style,
        fontName="NotoSans-Bold",
        fontSize=12,
        leading=16,
        keepWithNext=True,
    )
    story: list[Any] = []
    width = landscape(A4)[0] - 64

    def text(value: object, bold: bool = False) -> Any:
        return Paragraph(markup(str(value), bold=bold), heading if bold else style)

    def table(headers: list[str], rows: Iterable[list[Any]], widths: list[float]) -> None:
        values = [[text(value) for value in headers]]
        values.extend(
            [
                Paragraph(markup(str(value)), numeric)
                if re.fullmatch(r"-?[0-9]+\.[0-9]{2,4}", str(value))
                else text("—" if value is None else value)
                for value in row
            ]
            for row in rows
        )
        target = LongTable(values, colWidths=widths, repeatRows=1, hAlign="LEFT")
        target.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(tokens["--janso-line"])),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(tokens["--janso-brand-tint"])),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([target, Spacer(1, 12)])

    story.append(text("FORM GSTR-3B — Return preparation", True))
    story.append(
        text(
            f'GSTIN: {preparation["registration"]["number"]} | '
            f'{preparation["registration"]["legal_name"]}'
        )
    )
    story.append(
        text(
            f'Period: {preparation["date_from"]} to {preparation["date_to"]} | '
            f'FY {preparation["financial_year"]} | INR'
        )
    )
    story.append(
        text(
            f'{preparation["status"]} | Rule {preparation["rule_version"]} | '
            f'Calculation revision {preparation.get("calculation_version", "Legacy")} | '
            f'Nil: {preparation["nil"]}'
        )
    )
    story.append(text(settings["document"]["source_as_of"]))
    for section in ("3.1", "3.1.1"):
        keys = [
            key
            for key in preparation.get("row_order", list(FORM_ROWS))
            if key.startswith(section) and (section != "3.1" or not key.startswith("3.1.1"))
        ]
        story.append(
            text(
                {
                    "3.1": "3.1 Outward supplies and reverse charge",
                    "3.1.1": "3.1.1 Section 9(5) supplies",
                    "4": "4 Eligible ITC",
                    "5": "5 Exempt, nil rated and non-GST inward supplies",
                }[section],
                True,
            )
        )
        table(
            ["Nature of supplies", "Taxable value", "IGST", "CGST", "SGST / UTGST", "Cess"],
            (
                [
                    key + " " + preparation["labels"][key],
                    *[preparation["form"][key][head] for head in FIELDS],
                ]
                for key in keys
            ),
            [width * 0.45, *[width * 0.11] * 5],
        )
    story.append(
        text(
            "3.2 Interstate supplies to unregistered persons, "
            "composition taxpayers and UIN holders",
            True,
        )
    )
    table(
        ["Recipient", "Place of supply", "Taxable value", "IGST"],
        (
            [row["recipient"], row["place_of_supply"], row["taxable"], row["igst"]]
            for row in preparation["pos_rows"]
        ),
        [width * 0.4, *[width * 0.2] * 3],
    )
    story.append(text("4 Eligible ITC", True))
    table(
        ["Nature of ITC", "Integrated tax", "Central tax", "State / UT tax", "Cess"],
        (
            [
                key + " " + preparation["labels"][key],
                *[preparation["form"][key][head] for head in FIELDS[1:]],
            ]
            for key in preparation.get("row_order", list(FORM_ROWS))
            if key.startswith("4")
        ),
        [width * 0.48, *[width * 0.13] * 4],
    )
    story.append(text("5 Exempt, nil rated and non-GST inward supplies", True))
    table(
        ["Nature of supplies", "Interstate supplies", "Intrastate supplies"],
        (
            [row["nature"], row["interstate"], row["intrastate"]]
            for row in preparation["inward_rows"]
        ),
        [width * 0.6, width * 0.2, width * 0.2],
    )
    story.append(text("5.1 Interest and late fee payable", True))
    table(
        ["Nature", "IGST", "CGST", "SGST / UTGST", "Cess"],
        (
            [preparation["labels"][key], *[preparation["form"][key][head] for head in FIELDS[1:]]]
            for key in ("INTEREST", "LATE_FEE")
        ),
        [width * 0.4, *[width * 0.15] * 4],
    )
    story.append(text("6.1 Payment of tax", True))
    for kind, label in (
        ("OTHER_THAN_REVERSE_CHARGE", "Other than reverse charge (including section 9(5) ECO)"),
        ("REVERSE_CHARGE", "Reverse charge"),
    ):
        story.append(text(label))
        table(
            [
                "Tax head",
                "Tax payable",
                "ITC: IGST",
                "ITC: CGST",
                "ITC: SGST/UT",
                "ITC: Cess",
                "Paid cash",
                "Interest paid",
                "Late fee paid",
            ],
            (
                [
                    row["tax_head"],
                    *[
                        row[key]
                        for key in (
                            "tax_payable",
                            "paid_igst",
                            "paid_cgst",
                            "paid_sgst",
                            "paid_cess",
                            "paid_cash",
                            "interest_paid",
                            "late_fee_paid",
                        )
                    ],
                ]
                for row in preparation["payment_rows"]
                if row["liability_kind"] == kind
            ),
            [width / 9] * 9,
        )
    story.append(text("Prior-period liability breakup", True))
    table(
        ["Source period date", "Reference", "IGST", "CGST", "SGST / UTGST", "Cess"],
        (
            [row["event_date"], row["reference"], *[row[head] for head in FIELDS[1:]]]
            for row in preparation["prior_liability_rows"]
        ),
        [width * 0.16, width * 0.36, *[width * 0.12] * 4],
    )
    story.append(text("Verification and authorised signatory", True))
    story.append(
        text(
            "I hereby solemnly affirm and declare that the information given herein above "
            "is true and correct to the best of my knowledge and belief and nothing "
            "has been concealed therefrom."
        )
    )
    story.append(
        text(
            "Name of authorised signatory: ____________________ | "
            "Designation / status: ____________________"
        )
    )
    story.append(text("Place: ____________________ | Date: ____________________"))
    story.append(
        text(
            "Preparation copy: the authorised signatory completes verification and filing "
            "on the GST Portal. Internal review does not constitute statutory filing."
        )
    )
    story.append(text(f'Readiness exceptions: {preparation["issue_count"]}', True))
    for row in preparation["issues"]:
        story.append(text(row["code"] + ": " + row["message"]))
    if preparation["issue_count"] > len(preparation["issues"]):
        story.append(text("Additional exceptions are included in the Excel preparation package."))
    story.append(text("Contributing records", True))
    contributors: list[list[str]] = []
    for line in lines:
        row = json.loads(line)
        if len(contributors) >= settings["rows"]:
            raise ValueError("PDF contributor capacity exceeded")
        contributors.append(
            [row["category"] + " " + row["reference"], *[row[head] for head in FIELDS]]
        )
    table(
        ["Source", "Taxable value", "IGST", "CGST", "SGST / UTGST", "Cess"],
        contributors,
        [width * 0.45, *[width * 0.11] * 5],
    )
    pages = 0
    # A trailing spacer can overflow an otherwise full last page into a blank page.
    if story and isinstance(story[-1], Spacer):
        story.pop()

    def footer(canvas: Any, document: Any) -> None:
        nonlocal pages
        pages += 1
        if pages > settings["pages"]:
            raise ValueError("GSTR-3B PDF page capacity exceeded")
        canvas.setFont("NotoSans-Regular", 8)
        canvas.drawString(32, 20, "Return preparation — review on GST Portal before filing")
        canvas.drawRightString(landscape(A4)[0] - 32, 20, str(pages))

    SimpleDocTemplate(
        str(output),
        pagesize=landscape(A4),
        leftMargin=32,
        rightMargin=32,
        topMargin=32,
        bottomMargin=32,
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return {"pages": pages, "rows": len(contributors)}
