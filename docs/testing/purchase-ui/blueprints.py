"""Build/verify static P1 design references. No application or service imports.

Run from the repository root: python docs/testing/purchase-ui/blueprints.py
Tax components are fixture evidence. This is not an invoice/tax calculator.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from html import escape
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AMOUNT = re.compile(r"^(?:0|[1-9]\d{0,14})\.\d{4}$")


def verify_examples() -> list[dict]:
    data = json.loads((HERE / "examples.json").read_text(encoding="utf-8"))
    examples = data["examples"]
    assert [row["id"] for row in examples] == [f"PU{n:02}" for n in range(1, 10)]

    def value(raw: str) -> Decimal:
        assert isinstance(raw, str) and AMOUNT.fullmatch(raw), raw
        return Decimal(raw)

    for row in examples:
        subtotal = sum((value(line["amount"]) for line in row["lines"]), Decimal(0))
        discount = sum((value(line["discount"]) for line in row["lines"]), Decimal(0))
        for line in row["lines"]:
            if line["kind"] == "ITEM":
                assert value(line["billed_quantity"]) * value(line["rate"]) == value(line["amount"])
                value(line["receipt_quantity"])
            else:
                assert all(line[key] is None for key in ("billed_quantity", "receipt_quantity", "rate", "unit"))
        charges = sum((value(charge["amount"]) for charge in row["supplier_charges"]), Decimal(0))
        base = subtotal - discount - value(row["document_discount"]) + charges
        supplier_tax = sum((value(tax["amount"]) for tax in row["tax_components"] if tax["supplier_charged"]), Decimal(0))
        recipient_tax = sum((value(tax["amount"]) for tax in row["tax_components"] if not tax["supplier_charged"]), Decimal(0))
        total = base + supplier_tax + Decimal(row["rounding"])
        advance, payment = value(row["advance_to_apply"]), value(row["payment_to_record"])
        assert 0 <= advance + payment <= total
        actual = {
            "subtotal": subtotal, "line_discount": discount, "pre_supplier_tax_total": base,
            "supplier_tax": supplier_tax, "recipient_tax": recipient_tax,
            "bill_total": total, "difference": value(row["supplier_declared_total"]) - total,
            "remaining_if_applied": total - advance - payment,
        }
        assert actual == {key: Decimal(raw) for key, raw in row["expected"].items()}, row["id"]
        if row["receipt_intent"] == "REFERENCE_EXISTING":
            source = row["source_receipt"]
            assert value(source["eligible_quantity"]) - value(source["selected_quantity"]) == value(source["remaining_quantity"])
        if row["id"] == "PU05":
            assert row["quantity_difference_purpose"] == "MANUAL_PAID_BUNDLE"
        if row["id"] == "PU08":
            assert total == subtotal and recipient_tax > 0
    return examples


def palette(theme: str) -> dict[str, str]:
    source = (ROOT / f"mfes/packages/ui/src/styles/theme-{theme}.css").read_text(encoding="utf-8")
    return dict(re.findall(r"--janso-([\w-]+):\s*(#[0-9a-fA-F]+)\s*;", source))


def amount(raw: str) -> str:
    return f"{Decimal(raw):,.2f}"


class Composition:
    def __init__(self, width: int, height: int, theme: str, title: str):
        self.colors = palette(theme)
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title>',
            '<desc id="desc">Phase 1 static Purchase UI design reference. Synthetic example PU02. Provisional values, no persistence, financial execution or functional controls.</desc>',
            '<style>text{font-family:Inter,"Segoe UI",sans-serif;font-variant-numeric:tabular-nums}</style>',
        ]
        self.box(0, 0, width, height, "paper", radius=0)

    def box(self, x: int, y: int, w: int, h: int, fill: str = "surface", stroke: str | None = None, radius: int = 8):
        border = f' stroke="{self.colors[stroke]}"' if stroke else ""
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{self.colors[fill]}"{border}/>')

    def text(self, x: int, y: int, text: str, size: int = 14, color: str = "ink", weight: int = 400, anchor: str = "start"):
        self.parts.append(f'<text x="{x}" y="{y}" fill="{self.colors[color]}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(text)}</text>')

    def rule(self, x: int, y: int, w: int):
        self.parts.append(f'<path d="M{x} {y}h{w}" stroke="{self.colors["line"]}"/>')

    def field(self, x: int, y: int, w: int, label: str, content: str, hint: str | None = None):
        self.text(x, y, label, 12, "ink-soft", 500)
        self.box(x, y + 10, w, 40, stroke="control-line", radius=6)
        self.text(x + 12, y + 35, content, 14)
        if hint:
            self.text(x, y + 69, hint, 12, "ink-soft")

    def pill(self, x: int, y: int, w: int, content: str, tone: str = "neutral"):
        self.box(x, y, w, 26, tone + "-tint", tone + "-line", radius=13)
        self.text(x + w // 2, y + 18, content, 12, tone + "-ink", 500, "middle")

    def button(self, x: int, y: int, w: int, content: str, primary: bool = False, height: int = 40):
        # Brand ink against the surface colour remains readable in all palettes.
        self.box(x, y, w, height, "brand-ink" if primary else "surface", None if primary else "control-line", 6)
        ink = "surface" if primary else "ink"
        self.text(x + w // 2, y + height // 2 + 5, content, 13, ink, 600, "middle")

    def save(self, name: str):
        self.parts.append("</svg>")
        output = "\n".join(self.parts) + "\n"
        ElementTree.fromstring(output)
        (HERE / name).write_text(output, encoding="utf-8")


def desktop(theme: str, sample: dict):
    s = Composition(1440, 1080, theme, f"Purchase workspace blueprint - {theme}")
    s.box(0, 0, 76, 1080, "surface", "line", 0)
    s.text(38, 38, "KB", 18, "brand-ink", 700, "middle")
    for y, glyph in ((118, "H"), (178, "P"), (238, "S"), (298, "A")):
        if glyph == "P":
            s.box(16, y - 28, 44, 44, "brand-tint", radius=8)
        s.text(38, y, glyph, 16, "brand-ink" if glyph == "P" else "ink-soft", 600, "middle")
    s.text(38, 1038, "?", 18, "ink-soft", 500, "middle")
    s.box(76, 0, 1364, 64, "surface", "line", 0)
    s.text(108, 39, "Kisco", 19, "brand-ink", 650)
    s.text(157, 39, "Books", 19, "wordmark-books", 650)
    s.text(270, 38, "Northstar Trading · sample company", 13, "ink-soft", 500)
    s.text(1388, 38, "FY 2026–27     /     INR", 13, "ink-soft", 500, "end")
    s.text(108, 102, "PURCHASES  /  NEW BILL", 11, "ink-soft", 600)
    s.text(108, 145, "New purchase", 28, weight=650)
    s.pill(313, 122, 84, "Unsaved")
    s.text(108, 175, "Capture the supplier’s bill. Keep quantities, costs and payment in view.", 14, "ink-soft")
    s.pill(1150, 123, 238, "Design preview · sample data", "info")
    s.box(108, 202, 1280, 216, "surface", "line", 10)
    s.field(132, 230, 396, "Supplier", sample["supplier"]["name"] + "   ⌄")
    s.text(132, 298, "SUP-001  ·  Pune, Maharashtra", 12, "ink-soft")
    s.field(552, 230, 242, "Supplier invoice number", sample["supplier"]["invoice_number"])
    s.field(818, 230, 242, "Supplier invoice date", "31 Oct 2026")
    s.field(1084, 230, 280, "Posting date", "31 Oct 2026")
    s.rule(132, 317, 1232)
    s.text(132, 346, "Purchase type", 12, "ink-soft", 500)
    s.text(132, 375, "Standard purchase  ⌄", 14, weight=500)
    s.text(430, 346, "Payment terms", 12, "ink-soft", 500)
    s.text(430, 375, "30 days · due 30 Nov 2026", 14)
    s.text(783, 346, "Receipt intent", 12, "ink-soft", 500)
    s.text(783, 375, "Receive with bill  ⌄", 14)
    s.text(1127, 346, "Internal reference", 12, "ink-soft", 500)
    s.text(1127, 375, "Unassigned", 14, "ink-soft")
    s.box(108, 442, 938, 300, "surface", "line", 10)
    s.text(132, 477, "Purchase lines", 17, weight=600)
    s.pill(294, 456, 66, "2 lines")
    for x, w, label, selected in ((743, 80, "Items", True), (823, 112, "Accounts", False), (935, 87, "Mixed", False)):
        s.box(x, 456, w, 34, "brand-tint" if selected else "surface-2", radius=6)
        s.text(x + w // 2, 478, label, 12, "brand-ink" if selected else "ink-soft", 600 if selected else 400, "middle")
    s.box(109, 506, 936, 38, "surface-2", radius=0)
    for x, label, anchor in ((132, "PRODUCT / DESCRIPTION", "start"), (534, "RECEIPT QTY", "end"), (607, "BILLED QTY", "end"), (653, "UNIT", "end"), (757, "RATE", "end"), (862, "DISCOUNT", "end"), (1022, "NET AMOUNT", "end")):
        s.text(x, 530, label, 11, "ink-soft", 600, anchor)
    for n, (row, y) in enumerate(zip(sample["lines"], (579, 653)), 1):
        s.text(132, y, f"{n:02}", 12, "ink-soft")
        s.text(163, y, row["name"], 13, weight=500)
        s.text(163, y + 22, "Details: tax, location and tracking  ›", 11, "brand-ink")
        for x, raw in ((534, row["receipt_quantity"]), (607, row["billed_quantity"])):
            s.text(x, y, str(int(Decimal(raw))), 14, anchor="end")
        s.text(653, y, "pcs", 12, "ink-soft", anchor="end")
        s.text(757, y, amount(row["rate"]), 14, anchor="end")
        s.text(862, y, "5%", 14, anchor="end")
        s.text(1022, y, amount(str(Decimal(row["amount"]) - Decimal(row["discount"]))), 14, weight=600, anchor="end")
        s.rule(132, y + 38, 890)
    s.text(132, 723, "+  Add line", 13, "brand-ink", 600)
    s.text(1022, 723, "Ctrl + Enter adds a line", 11, "ink-soft", anchor="end")
    for x, y, w, title, detail, trailing in (
        (108, 766, 456, "Discounts & charges", "5% line discount · freight INR 100.00", "Edit  ›"),
        (588, 766, 458, "Goods receipt", "Receive with this bill · no stock recorded", "Review  ›"),
        (108, 862, 456, "Payment & terms", "Advance to apply INR 1,000.00 · no payment", "Edit  ›"),
        (588, 862, 458, "Notes & attachments", "Add the supplier’s bill and supporting notes", "Add  ›"),
    ):
        s.box(x, y, w, 76, "surface", "line", 10)
        s.text(x + 20, y + 28, title, 14, weight=600)
        s.text(x + 20, y + 54, detail, 11, "ink-soft")
        s.text(x + w - 18, y + 28, trailing, 11, "brand-ink", 500, "end")
    s.text(108, 970, "Receipt quantities are proposed. This sample records no stock or payment.", 12, "ink-soft")
    s.box(1070, 442, 318, 542, "surface", "line", 10)
    s.text(1094, 479, "Bill summary", 17, weight=600)
    s.pill(1261, 458, 103, "Provisional", "info")
    for y, label, value in (
        (521, "Line amounts", "5,000.00"), (555, "Line discounts", "−250.00"),
        (589, "Freight", "+100.00"), (635, "Taxable amount", "4,850.00"),
        (669, "CGST · sample", "436.50"), (703, "SGST · sample", "436.50"),
    ):
        s.text(1094, y, label, 12, "ink-soft")
        s.text(1364, y, value, 13, anchor="end")
    s.rule(1094, 610, 270)
    s.rule(1094, 726, 270)
    s.text(1094, 759, "BILL TOTAL · INR", 11, "ink-soft", 600)
    s.text(1364, 801, amount(sample["expected"]["bill_total"]), 32, weight=650, anchor="end")
    s.text(1094, 836, "Supplier total", 12, "ink-soft")
    s.text(1364, 836, "5,723.00", 13, anchor="end")
    s.text(1094, 863, "Difference", 12, "ink-soft")
    s.text(1364, 863, "0.00 · Matches", 12, "success-ink", 500, "end")
    s.rule(1094, 883, 270)
    s.text(1094, 911, "Advance to apply", 12, "ink-soft")
    s.text(1364, 911, "1,000.00", 13, anchor="end")
    s.text(1094, 951, "Remaining if applied", 12, weight=600)
    s.text(1364, 951, "4,723.00", 16, weight=650, anchor="end")
    s.box(76, 1008, 1364, 72, "surface", "line", 0)
    s.text(108, 1039, "UI preview only · changes are not saved", 13, "ink-soft", 500)
    s.text(108, 1060, "Design reference / P1 / " + theme + " / PU02", 11, "ink-soft")
    s.button(1070, 1024, 142, "Review bill")
    s.button(1228, 1024, 160, "Save demo draft", True)
    s.save(f"desktop-{theme}.svg")


def mobile(sample: dict):
    s = Composition(390, 1400, "light", "Purchase workspace blueprint - mobile")
    s.box(0, 0, 390, 58, "surface", "line", 0)
    s.text(20, 35, "KiscoBooks", 18, "brand-ink", 650)
    s.text(370, 25, "Northstar · sample", 11, "ink-soft", 500, "end")
    s.text(370, 45, "FY 2026–27 · INR", 11, "ink-soft", 500, "end")
    s.text(20, 88, "PURCHASES  /  NEW BILL", 11, "ink-soft", 600)
    s.text(20, 124, "New purchase", 25, weight=650)
    s.pill(278, 103, 92, "Unsaved")
    s.box(20, 148, 350, 39, "info-tint", "info-line", 6)
    s.text(195, 172, "Design preview · sample data", 12, "info-ink", 500, "middle")
    s.box(20, 203, 350, 350, "surface", "line", 10)
    s.field(36, 230, 318, "Supplier", sample["supplier"]["name"] + "  ⌄")
    s.text(36, 294, "SUP-001 · Pune, Maharashtra", 11, "ink-soft")
    s.field(36, 324, 318, "Supplier invoice number", sample["supplier"]["invoice_number"])
    s.field(36, 407, 148, "Supplier invoice date", "31 Oct 2026")
    s.field(200, 407, 154, "Posting date", "31 Oct 2026")
    s.text(36, 505, "Due 30 Nov 2026 · Receive with bill", 12, "ink-soft")
    s.text(36, 532, "More bill details  ›", 12, "brand-ink", 500)
    s.text(20, 590, "Purchase lines", 17, weight=600)
    s.pill(282, 570, 88, "Items  ⌄", "info")
    for n, (row, y) in enumerate(zip(sample["lines"], (610, 772)), 1):
        s.box(20, y, 350, 144, "surface", "line", 10)
        s.text(36, y + 29, f"{n:02}  " + row["name"], 14, weight=600)
        s.text(36, y + 59, f'Receipt {int(Decimal(row["receipt_quantity"]))} · Billed {int(Decimal(row["billed_quantity"]))} pcs', 12, "ink-soft")
        s.text(36, y + 85, "Rate " + amount(row["rate"]) + " · Discount 5%", 12, "ink-soft")
        s.text(36, y + 119, "Edit line  ›", 12, "brand-ink", 500)
        s.text(354, y + 119, "INR " + amount(str(Decimal(row["amount"]) - Decimal(row["discount"]))), 16, weight=600, anchor="end")
    s.text(20, 945, "+  Add line", 13, "brand-ink", 600)
    s.box(20, 970, 350, 67, "surface", "line", 10)
    s.text(36, 997, "Charges, receipt & payment", 14, weight=600)
    s.text(36, 1021, "Freight 100.00 · Advance to apply 1,000.00  ›", 11, "ink-soft")
    s.box(20, 1053, 350, 203, "surface", "line", 10)
    s.text(36, 1083, "Bill summary  ›", 16, weight=600)
    s.pill(250, 1064, 104, "Provisional", "info")
    s.text(36, 1118, "Before supplier tax", 12, "ink-soft")
    s.text(354, 1118, "4,850.00", 13, anchor="end")
    s.text(36, 1148, "Supplier tax · sample", 12, "ink-soft")
    s.text(354, 1148, "873.00", 13, anchor="end")
    s.rule(36, 1167, 318)
    s.text(36, 1196, "Bill total · INR", 13, weight=600)
    s.text(354, 1196, "5,723.00", 23, weight=650, anchor="end")
    s.text(36, 1230, "Supplier total matches · Difference 0.00", 11, "success-ink")
    s.text(20, 1280, "Remaining if applied: INR 4,723.00", 13, weight=600)
    s.box(0, 1300, 390, 100, "surface", "line", 0)
    s.text(20, 1325, "UI preview only · changes are not saved", 11, "ink-soft")
    s.button(20, 1343, 162, "Review bill", height=44)
    s.button(198, 1343, 172, "Save demo draft", True, height=44)
    s.save("mobile-light.svg")


def verify_documents():
    count = 0
    primary_sources = {
        "https://html.spec.whatwg.org/multipage/nav-history-apis.html#the-navigate-event",
        "https://www.w3.org/WAI/WCAG22/Understanding/reflow.html",
        "https://github.com/dequelabs/axe-core/blob/v4.10.3/doc/API.md",
        "https://playwright.dev/docs/browsers",
        "https://raw.githubusercontent.com/chromium/chromium/main/chrome/browser/ui/zoom/chrome_zoom_level_prefs.cc",
    }
    for document in (ROOT / "docs/purchase-ui-blueprint.md", ROOT / "docs/purchase-ui-todo.md", ROOT / "docs/purchase-ui-readiness.md", HERE / "README.md"):
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if target in primary_sources:
                continue  # Reviewed primary contracts; never fetched or embedded in SVGs.
            assert "://" not in target, "Docs must link repository evidence or a reviewed primary contract"
            assert (document.parent / target.split("#")[0]).is_file(), target
            count += 1
    for file in [ROOT / "docs/purchase-ui-blueprint.md", ROOT / "docs/purchase-ui-todo.md", *HERE.iterdir()]:
        if file.suffix in {".md", ".json", ".py", ".cjs", ".svg"}:
            assert all(line == line.rstrip() for line in file.read_text(encoding="utf-8").splitlines()), file
    for file in HERE.glob("*.svg"):
        root = ElementTree.parse(file).getroot()
        assert root.find("{http://www.w3.org/2000/svg}title") is not None
        assert root.find("{http://www.w3.org/2000/svg}desc") is not None
        for node in root.iter():
            assert not node.tag.endswith("script")
            assert not any("href" in key or key.startswith("on") for key in node.attrib)
    return count


def main():
    examples = verify_examples()
    sample = examples[1]
    for theme in ("light", "dark", "ledger"):
        desktop(theme, sample)
    mobile(sample)
    links = verify_documents()
    print(f"PASS: {len(examples)} exact-decimal fixture examples, 4 SVG compositions, {links} documentation links.")
    print("Scope: static P1 references only; no application interaction, API, tax-law or accessibility certification.")


if __name__ == "__main__":
    main()
