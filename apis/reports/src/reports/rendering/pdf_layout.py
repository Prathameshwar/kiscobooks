"""Trusted PDF layout, imported only after the child's hard memory boundary."""

# ReportLab 4.5.1 has no PEP 561 marker. Keep its untyped boundary in this adapter.
# mypy: disable-error-code=import-untyped
import html
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from billing_platform.display import DisplayConfiguration
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from reports.domain.reporting.contracts import Column
from reports.rendering.presentation import ASSETS, Document, bundle, cell, row_style


def register_fonts() -> None:
    bundle()  # Verify every packaged font before handing bytes to the font parser.
    for prefix in ("NotoSans", "NotoSansDevanagari"):
        for weight in ("Regular", "Bold"):
            name = f"{prefix}-{weight}"
            pdfmetrics.registerFont(
                TTFont(name, str(ASSETS / "fonts" / (name + ".ttf")), shapable=True)
            )


def markup(text: str, *, bold: bool = False) -> str:
    """Select registered font runs; business text never becomes ReportLab markup."""
    suffix = "Bold" if bold else "Regular"
    groups: list[tuple[str, str]] = []
    for character in text:
        if character == "\n":
            groups.append(("break", ""))
            continue
        if character == "\t":
            character = " "
        code = ord(character)
        prefix = (
            "NotoSansDevanagari"
            if 0x0900 <= code <= 0x097F or code in {0x200C, 0x200D}
            else "NotoSans"
        )
        font = f"{prefix}-{suffix}"
        if code not in pdfmetrics.getFont(font).face.charToGlyph and code not in {0x200C, 0x200D}:
            raise ValueError("PDF font bundle does not support a required character")
        if groups and groups[-1][0] == font:
            groups[-1] = (font, groups[-1][1] + character)
        else:
            groups.append((font, character))
    return "".join(
        "<br/>" if font == "break" else f'<font name="{font}">{html.escape(text)}</font>'
        for font, text in groups
    )


def render(lines: Iterable[str], output: Path, settings: dict[str, Any]) -> dict[str, int]:
    register_fonts()
    raw = settings["document"]
    document = Document(**(raw | {"display": DisplayConfiguration.model_validate(raw["display"])}))
    columns = tuple(Column(**column) for column in settings["columns"])
    if not columns or len(columns) > 200:
        raise ValueError("PDF column budget exceeded")
    rows: list[dict[str, Any]] = []
    for line in lines:
        if len(line) > 1048576 or len(rows) >= min(5000, settings["rows"]):
            raise ValueError("PDF row budget exceeded")
        rows.append(json.loads(line))
        if len(rows) * len(columns) > min(200000, settings["cells"]):
            raise ValueError("PDF cell budget exceeded")
    tokens = bundle()["tokens"]
    ink = colors.HexColor(tokens["--janso-ink"])
    brand = colors.HexColor(tokens["--janso-brand"])
    line_color = colors.HexColor(tokens["--janso-line"])
    margin = float(tokens["--report-pdf-margin"])
    body_size = float(tokens["--report-pdf-body-size"])
    leading = float(tokens["--report-pdf-leading"])
    body = ParagraphStyle(
        "ReportBody",
        fontName="NotoSans-Regular",
        fontSize=body_size,
        leading=leading,
        textColor=ink,
        shaping=True,
    )
    right = ParagraphStyle("ReportNumber", parent=body, alignment=2)
    heading = ParagraphStyle(
        "ReportHeading",
        parent=body,
        fontSize=float(tokens["--report-pdf-heading-size"]),
        leading=26,
    )
    page_size = (
        landscape(A4)
        if document.orientation == "LANDSCAPE"
        or (document.orientation == "AUTO" and len(columns) > 5)
        else A4
    )
    available = page_size[0] - 2 * margin
    doc = SimpleDocTemplate(
        str(output),
        pagesize=page_size,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=margin,
        bottomMargin=margin + 12,
        title=document.title,
        author=document.display.company_label,
    )
    story: list[Any] = [
        Paragraph(markup(document.title, bold=True), heading),
        Spacer(1, 10),
        Paragraph(markup(document.display.company_label), body),
        Spacer(1, 10),
    ]
    metadata = (
        f"{document.period}  |  Base currency {document.display.base_currency}\n"
        f"Source as of {document.source_as_of}"
    )
    story.extend([Paragraph(markup(metadata), body), Spacer(1, 12)])
    if document.filters:
        story.extend(
            [
                Paragraph(
                    markup("; ".join(f"{key}: {text}" for key, text in document.filters)), body
                ),
                Spacer(1, 12),
            ]
        )
    # Repeat a business reference and an unambiguous row number on every wide band.
    # "Period" and "Row kind" alone cannot identify the corresponding amounts.
    wide = len(columns) > 8
    identity_keys = (
        "bill_reference",
        "reference",
        "number",
        "account_code",
        "account_name",
        "label",
        "item_code",
    )
    identities = [
        next(index for index, column in enumerate(columns) if column.key == key)
        for key in identity_keys
        if any(column.key == key for column in columns)
    ][:1]
    identities = identities or [0]
    remaining = [index for index in range(len(columns)) if index not in identities]
    # Every registered value appears; no column is silently dropped or shrunk below body size.
    bands = (
        [list(range(len(columns)))]
        if len(columns) <= 8
        else [identities + remaining[start : start + 6] for start in range(0, len(remaining), 6)]
    )
    for band_index, band in enumerate(bands):
        if band_index:
            story.extend(
                [
                    PageBreak(),
                    Paragraph(markup(document.title, bold=True), heading),
                    Paragraph(markup(document.display.company_label + " | " + metadata), body),
                    Spacer(1, 12),
                ]
            )
        if len(bands) > 1:
            story.extend(
                [
                    Paragraph(
                        f"Column band {band_index + 1} of {len(bands)}; "
                        f"all {len(rows)} rows repeated",
                        body,
                    ),
                    Spacer(1, 8),
                ]
            )
        cells = [[Paragraph(markup(columns[index].title, bold=True), body) for index in band]]
        if wide:
            cells[0].insert(0, Paragraph("Row", body))
        styles: list[tuple[Any, ...]] = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(tokens["--janso-brand-tint"])),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, brand),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, line_color),
            ("TOPPADDING", (0, 0), (-1, -1), float(tokens["--report-pdf-padding"])),
            ("BOTTOMPADDING", (0, 0), (-1, -1), float(tokens["--report-pdf-padding"])),
        ]
        repeat = 1
        if document.column_groups and len(bands) == 1:
            grouped = []
            offset = 0
            for title, span in document.column_groups:
                grouped.extend([Paragraph(markup(title, bold=True), body), *([""] * (span - 1))])
                styles.append(("SPAN", (offset, 0), (offset + span - 1, 0)))
                offset += span
            if offset != len(columns):
                raise ValueError("grouped report header differs from columns")
            cells.insert(0, grouped)
            repeat = 2
            styles.extend(
                [
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor(tokens["--janso-brand-tint"])),
                    ("LINEBELOW", (0, 1), (-1, 1), 0.7, brand),
                ]
            )
        for ordinal, row in enumerate(rows, 1):
            semantic = row_style(row)
            rendered = [cell(columns[index], row, document.display) for index in band]
            cells.append(
                [
                    Paragraph(
                        markup(item.text, bold=bool(semantic)), right if item.numeric else body
                    )
                    for item in rendered
                ]
            )
            if wide:
                cells[-1].insert(0, Paragraph(str(ordinal), body))
            if semantic:
                styles.append(
                    (
                        "BACKGROUND",
                        (0, len(cells) - 1),
                        (-1, len(cells) - 1),
                        colors.HexColor(tokens["--janso-surface-2"]),
                    )
                )
        if not rows:
            cells.append(
                [Paragraph("No rows for the selected parameters.", body)]
                + [""] * (len(band) - 1 + int(wide))
            )
        weights = [1.65 if columns[index].kind in {"TEXT", "IDENTIFIER"} else 1 for index in band]
        if wide:
            weights.insert(0, 0.5)
        widths = [available * weight / sum(weights) for weight in weights]
        table = LongTable(cells, colWidths=widths, repeatRows=repeat, hAlign="LEFT")
        table.setStyle(TableStyle(styles))
        story.append(table)
    story.extend(
        [
            Spacer(1, 12),
            Paragraph(
                "Amounts use the retained company display precision. "
                "Exact values are available in CSV and the report API.",
                body,
            ),
        ]
    )

    def footer(canvas: Any, current: Any) -> None:
        if current.page > min(200, settings["pages"]):
            raise ValueError("PDF page budget exceeded")
        canvas.saveState()
        canvas.setStrokeColor(line_color)
        canvas.line(margin, margin, page_size[0] - margin, margin)
        canvas.setFont("NotoSans-Regular", 7)
        canvas.setFillColor(ink)
        canvas.drawString(margin, margin - 12, f"Report {document.run_id}")
        canvas.drawRightString(page_size[0] - margin, margin - 12, f"Page {current.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return {"rows": len(rows), "pages": int(doc.page)}
