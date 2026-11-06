"""A designed layout, printed as drawn (designer plan P3, 2026-11-03).

The canvas is millimetre geometry: zones placed on the page, elements placed inside their zone.
This prints exactly that, in Chromium's own millimetres, with one concession to paper: the zone
band holding the line table grows with the bill, carries onto further pages with its header
repeated, and pushes whatever is below it down by the same amount. Everything above the table
and every bill that fits its table prints where it was drawn.

Nothing here is trusted because Design validated it: every number is re-checked against its
bound, every colour and font against its pattern, and every text value is escaped. Styles are
composed from typed fields; no CSS, markup or URL from a layout reaches the page.
"""

import base64
import binascii
import hashlib
import html
import re
from decimal import Decimal
from typing import Any

from billing_platform.display import DisplayConfiguration, date, number
from billing_platform.errors import ValidationFailedError

from vouchers.domain.amount_words import amount_in_words
from vouchers.domain.print_capabilities import COLUMN_LABELS, PURCHASE, TOTALS_LABELS, asset_key

PAPER = {"A4": (210.0, 297.0), "A5": (148.0, 210.0), "LETTER": (215.9, 279.4)}
#: Continuous rolls: a width, and a page as long as what is printed on it (designer plan R3).
ROLLS = {"THERMAL_80MM": 80.0, "THERMAL_58MM": 58.0}
#: The first bytes each embeddable picture type starts with; a mismatch is refused.
MAGIC = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
FITS = {"contain", "cover", "fill"}
COPY_LABELS = {
    "ORIGINAL_FOR_RECIPIENT": "Original for Recipient",
    "DUPLICATE_FOR_TRANSPORTER": "Duplicate for Transporter",
    "TRIPLICATE_FOR_SUPPLIER": "Triplicate for Supplier",
    "EXTRA_COPY": "Extra Copy",
}
DEFAULT_COLUMNS = {
    "ITEM_TABLE": (
        ("serial_no", 0.08),
        ("description", 0.52),
        ("taxable_value", 0.2),
        ("amount", 0.2),
    ),
    "ACCOUNT_TABLE": (
        ("serial_no", 0.08),
        ("account", 0.3),
        ("description", 0.37),
        ("amount", 0.25),
    ),
}
#: The line tables, and which supplies each prints when a layout carries both (plan D2).
LINE_TABLES = {"ITEM_TABLE": "Purchase products", "ACCOUNT_TABLE": "Purchase accounts and expenses"}
DEFAULT_TOTALS = ("subtotal", "cgst", "sgst", "igst", "round_off", "grand_total")
COLOUR = re.compile(r"#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})")
FONT = re.compile(r"[A-Za-z][A-Za-z0-9 \-]{0,63}(?:, ?[A-Za-z][A-Za-z0-9 \-]{0,63}){0,3}")
WEIGHTS = {"normal": 400, "medium": 500, "semibold": 600, "bold": 700}
NUMERIC = {"quantity", "rate", "mrp", "discount", "taxable_value", "amount", "cess"}


def escaped(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def bounded(value: object, low: float, high: float, what: str) -> float:
    """A layout number inside its bound, or a refusal: nothing unchecked reaches the page."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValidationFailedError(f"the layout's {what} is not a number")
    result = float(value)
    if not low <= result <= high:
        raise ValidationFailedError(f"the layout's {what} is out of range")
    return result


def exactly(raw: str, config: DisplayConfiguration, *, quantity: bool = False) -> str:
    """A rate or quantity at the company's places, or exactly when it carries more.

    The display places are a floor, never a rounding: a 1.125 kg line on a two-place company
    prints 1.125, so quantity times rate still reads as the amount beside it.
    """
    value = Decimal(raw)
    places = config.quantity_precision if quantity else config.amount_precision
    exponent = value.normalize().as_tuple().exponent
    if isinstance(exponent, int) and value != value.quantize(Decimal(1).scaleb(-places)):
        places = min(max(-exponent, places), 4)
    key = "quantity_precision" if quantity else "amount_precision"
    return number(value, config.model_copy(update={key: places}), quantity=quantity)


def rate_text(supply: dict[str, Any], config: DisplayConfiguration) -> str:
    """A goods line's rate, with its pricing unit when it is priced per more than one."""
    text = exactly(supply["rate"], config)
    per = supply.get("per")
    return f"{text} / {exactly(per, config, quantity=True)}" if per else text


def mm(value: float) -> str:
    return f"{round(value, 3):g}mm"


def colour(value: object, what: str) -> str:
    if not isinstance(value, str) or not COLOUR.fullmatch(value):
        raise ValidationFailedError(f"the layout's {what} is not a colour")
    return value


def style_css(style: dict[str, Any] | None) -> str:
    """CSS composed from the canvas's typed style fields, each re-checked."""
    rules: list[str] = []
    style = style or {}
    if style.get("font_size_pt") is not None:
        rules.append(f"font-size:{bounded(style['font_size_pt'], 4, 72, 'font size'):g}pt")
    if style.get("font_weight") is not None:
        if style["font_weight"] not in WEIGHTS:
            raise ValidationFailedError("the layout's font weight is not supported")
        rules.append(f"font-weight:{WEIGHTS[style['font_weight']]}")
    if style.get("font_style") is not None:
        if style["font_style"] not in {"normal", "italic"}:
            raise ValidationFailedError("the layout's font style is not supported")
        rules.append(f"font-style:{style['font_style']}")
    if style.get("color") is not None:
        rules.append(f"color:{colour(style['color'], 'text colour')}")
    if style.get("background_color") is not None:
        rules.append(f"background-color:{colour(style['background_color'], 'fill')}")
    if style.get("text_align") is not None:
        if style["text_align"] not in {"left", "center", "right", "justify"}:
            raise ValidationFailedError("the layout's alignment is not supported")
        rules.append(f"text-align:{style['text_align']}")
    if style.get("vertical_align") is not None:
        place = {"top": "flex-start", "middle": "center", "bottom": "flex-end"}
        if style["vertical_align"] not in place:
            raise ValidationFailedError("the layout's vertical alignment is not supported")
        rules.append(
            f"display:flex;flex-direction:column;justify-content:{place[style['vertical_align']]}"
        )
    border = style.get("border_style")
    if border is not None and border not in {"none", "solid", "dashed", "dotted"}:
        raise ValidationFailedError("the layout's border style is not supported")
    if style.get("border_width_mm") or border not in {None, "none"}:
        width = bounded(style.get("border_width_mm") or 0.3, 0, 10, "border width")
        line = border if border not in {None, "none"} else "solid"
        tint = (
            colour(style["border_color"], "border colour")
            if style.get("border_color")
            else "currentColor"
        )
        rules.append(f"border:{mm(width)} {line} {tint}")
    if style.get("padding_mm") is not None:
        rules.append(f"padding:{mm(bounded(style['padding_mm'], 0, 50, 'padding'))}")
    if style.get("opacity") is not None:
        rules.append(f"opacity:{bounded(style['opacity'], 0, 1, 'opacity'):g}")
    if style.get("line_height") is not None:
        rules.append(f"line-height:{bounded(style['line_height'], 0.5, 4, 'line height'):g}")
    if style.get("uppercase"):
        rules.append("text-transform:uppercase")
    return ";".join(rules)


def roll_width(layout: dict[str, Any]) -> float | None:
    """The roll's width when the layout prints on a continuous roll, else None."""
    if layout.get("source") != "CUSTOM":
        return None
    return ROLLS.get(str(layout.get("paper_size")))


def picture(row: dict[str, Any], manifest: dict[str, Any]) -> str:
    """One resolved picture as a ``data:`` URI, after its bytes prove what they claim.

    Design read the bytes by its own key and digest; they are checked again here, because the
    renderer embeds them in a document: decoded strictly, within the bound, matching their
    digest and starting as their type must. Nothing else a layout says reaches ``src``.
    """
    bounds = manifest["images"]
    mime = row.get("mime_type")
    raw = row.get("content_base64")
    if mime not in bounds["media_types"] or not isinstance(raw, str):
        raise ValidationFailedError("a layout picture is not an image this print can embed")
    try:
        data = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValidationFailedError("a layout picture is not valid") from error
    valid = (
        data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        if mime == "image/webp"
        else data.startswith(MAGIC[str(mime)])
    )
    if (
        not 0 < len(data) <= bounds["max_bytes"]
        or len(data) != row.get("size_bytes")
        or hashlib.sha256(data).hexdigest() != row.get("sha256")
        or not valid
    ):
        raise ValidationFailedError("a layout picture does not match its evidence")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def page_box(layout: dict[str, Any]) -> tuple[float, float]:
    size = layout.get("paper_size", "A4")
    if size in ROLLS:
        # The length is measured after layout (print_child); this is only the drawing area.
        return ROLLS[size], 5000.0
    if size == "CUSTOM":
        try:
            width = float(layout["page_width_mm"])
            height = float(layout["page_height_mm"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValidationFailedError("a custom page needs its width and height") from error
        width = bounded(width, 20, 2000, "page width")
        height = bounded(height, 20, 2000, "page height")
    elif size in PAPER:
        width, height = PAPER[size]
    else:
        raise ValidationFailedError("this paper size cannot be printed yet")
    if str(layout.get("page_orientation", "PORTRAIT")).upper() == "LANDSCAPE":
        width, height = height, width
    return width, height


class Facts:
    """The frozen bill, read for one print: field values, line rows and totals, formatted."""

    def __init__(self, value: dict[str, Any], config: DisplayConfiguration, number_text: str):
        self.config = config
        document, calculation = value["document"], value["calculation"]
        invoice = document["invoice"]
        labels = value.get("labels", {})
        self.ledgers: dict[str, Any] = labels.get("ledgers", {})
        rows = {str(row["key"]): row for row in calculation["lines"]}
        self.lines = [(supply, rows[str(supply["line_key"])]) for supply in invoice["supplies"]]
        tables = {
            element.get("type")
            for section in (value["layout"].get("layout_definition") or {}).get("sections") or []
            for element in section.get("elements") or []
        }
        #: With a product table and an accounts table, goods go in one and the rest in the
        #: other; a layout with one line table prints every line in it.
        self.split = {"ITEM_TABLE", "ACCOUNT_TABLE"} <= tables
        taxes: dict[str, Decimal] = {
            "CGST": Decimal(0),
            "SGST": Decimal(0),
            "IGST": Decimal(0),
            "CESS": Decimal(0),
        }
        discount = Decimal(0)
        taxable = Decimal(0)
        for _, row in self.lines:
            discount += max(Decimal(row["entered"]) - Decimal(row["commercial"]), Decimal(0))
            taxable += Decimal(row["taxable"])
            for tax in row["taxes"]:
                code = "SGST" if tax["code"] == "UTGST" else tax["code"]
                taxes[code] += Decimal(tax["amount"])
        self.totals: dict[str, Decimal | str] = {
            "subtotal": calculation["commercial_total"],
            "discount": discount,
            "taxable_value": taxable,
            "tax_total": calculation["tax_total"],
            "cgst": taxes["CGST"],
            "sgst": taxes["SGST"],
            "igst": taxes["IGST"],
            "cess": taxes["CESS"],
            "round_off": calculation["rounding"],
            "grand_total": calculation["payable"],
        }
        self.units: dict[str, str] = labels.get("units", {})
        total = 0
        self.pictures: dict[str, str] = {}
        for row in value["layout"].get("assets") or []:
            if row.get("status") == "READY":
                self.pictures[asset_key(row["asset_id"])] = picture(row, PURCHASE)
                total += int(row["size_bytes"])
        if total > PURCHASE["images"]["total_max_bytes"]:
            raise ValidationFailedError("the layout's pictures exceed their combined bound")
        self.words = amount_in_words(calculation["payable"], str(document["currency"]), config)
        restricted = "Restricted"
        self.fields: dict[str, str] = {
            "company.name": config.company_label,
            "company.display_name": config.company_label,
            "party.name": labels.get("supplier") or restricted,
            "voucher.title": "Purchase voucher",
            "voucher.document_number": number_text,
            "voucher.issue_number": number_text,
            "voucher.document_date": date(document.get("document_date"), config),
            "voucher.posting_date": date(document.get("posting_date"), config),
            "voucher.due_date": date(invoice.get("due_date"), config),
            "voucher.bill_reference": str(invoice.get("bill_reference") or ""),
            "voucher.currency": str(document.get("currency") or ""),
            "voucher.status": str(document.get("status") or ""),
            "voucher.narration": str(document.get("narration") or ""),
        } | {f"totals.{key}": number(amount, config) for key, amount in self.totals.items()}
        self.fields["totals.amount_in_words"] = self.words
        receipt = document.get("stock_receipt", [])
        if receipt:
            descriptions = {
                str(line["line_key"]): str(line.get("description") or "Purchase line")
                for line in invoice["supplies"]
            }
            self.fields["voucher.receiving_summary"] = "\n".join(
                " · ".join(
                    [descriptions[row["line_key"]], "Warehouse reference " + row["warehouse_id"]]
                    + (["Bin reference " + row["bin_id"]] if row["bin_id"] else [])
                    + (["Batch reference " + row["lot_id"]] if row["lot_id"] else [])
                    + (["Serial references " + ", ".join(row["unit_ids"])] if row["unit_ids"] else [])
                )
                for row in receipt
            )
        else:
            self.fields["voucher.receiving_summary"] = ""

    def lines_for(self, table: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        if not self.split:
            return self.lines
        goods = table == "ITEM_TABLE"
        return [line for line in self.lines if (line[0].get("supply_kind") == "GOODS") == goods]

    def money(self, amount: Decimal | str) -> str:
        return number(amount, self.config)

    def cell(self, key: str, index: int, supply: dict[str, Any], row: dict[str, Any]) -> str:
        """One table cell for one line, escaped."""
        if key == "serial_no":
            return str(index)
        if key == "description":
            text = escaped(supply.get("description") or "Purchase line")
            line = str(supply["line_key"])
            if line in self.ledgers:
                name = self.ledgers[line]
                ledger = f"Ledger: {name}" if name else "Ledger restricted"
                text += f'<div class="canvas-ledger">{escaped(ledger)}</div>'
            return text
        if key == "account":
            name = self.ledgers.get(str(supply["line_key"]))
            return escaped(name or "Restricted")
        if key == "hsn_sac":
            return escaped(supply.get("hsn_sac") or "—")
        # Quantity, unit and rate are a goods line's own; other lines print a dash.
        if key in {"quantity", "unit", "rate"} and "quantity" not in supply:
            return "—"
        if key == "quantity":
            return escaped(exactly(supply["quantity"], self.config, quantity=True))
        if key == "unit":
            return escaped(self.units.get(str(supply["line_key"])) or "—")
        if key == "rate":
            return escaped(rate_text(supply, self.config))
        if key == "discount":
            return escaped(
                self.money(max(Decimal(row["entered"]) - Decimal(row["commercial"]), Decimal(0)))
            )
        if key == "taxable_value":
            return escaped(self.money(row["taxable"]))
        if key == "amount":
            return escaped(self.money(row["payable"]))
        code, _, part = key.partition("_")
        codes = {"cgst": {"CGST"}, "sgst": {"SGST", "UTGST"}, "igst": {"IGST"}, "cess": {"CESS"}}[
            code
        ]
        taxes = [tax for tax in row["taxes"] if tax["code"] in codes]
        if part == "rate":
            rates = {self.rate(tax) for tax in taxes}
            return escaped(", ".join(sorted(rates)) if rates else "—")
        return escaped(self.money(sum((Decimal(tax["amount"]) for tax in taxes), Decimal(0))))

    @staticmethod
    def rate(tax: dict[str, Any]) -> str:
        basis = Decimal(tax["basis"])
        if basis == 0:
            return "0%"
        value = (Decimal(tax["amount"]) * 100 / basis).quantize(Decimal("0.01"))
        return f"{value.normalize():f}%"

    def tax_rows(self, grouping: str) -> list[tuple[str, str, Decimal, Decimal]]:
        """Tax, rate, taxable basis and amount, grouped by rate or by tax alone."""
        grouped: dict[tuple[str, str], list[Decimal]] = {}
        for _, row in self.lines:
            for tax in row["taxes"]:
                key = (tax["code"], self.rate(tax) if grouping == "by_rate" else "")
                entry = grouped.setdefault(key, [Decimal(0), Decimal(0)])
                entry[0] += Decimal(tax["basis"])
                entry[1] += Decimal(tax["amount"])
        return [
            (code, rate, basis, amount) for (code, rate), (basis, amount) in sorted(grouped.items())
        ]


def element_html(element: dict[str, Any], facts: Facts, *, flow: bool = False) -> str:
    """One element. Placed absolutely in its zone, or in flow when it is the growing table."""
    kind = element.get("type")
    x = bounded(element.get("x", 0), -1000, 2000, "element position")
    y = bounded(element.get("y", 0), -1000, 2000, "element position")
    width = bounded(element.get("width", 1), 0.01, 2000, "element width")
    height = bounded(element.get("height", 1), 0.01, 2000, "element height")
    css = style_css(element.get("style"))
    if flow:
        place = f"position:relative;margin-left:{mm(x)};width:{mm(width)}"
    else:
        place = f"position:absolute;left:{mm(x)};top:{mm(y)};width:{mm(width)};height:{mm(height)}"
    box = f'style="{escaped(place + (";" + css if css else ""))}"'
    if kind == "TEXT":
        return f'<div class="canvas-el canvas-text" {box}>{escaped(element.get("content"))}</div>'
    if kind == "FIELD_BINDING":
        label = element.get("label")
        prefix = f'<span class="canvas-label">{escaped(label)} </span>' if label else ""
        value = facts.fields.get(str(element.get("binding_path")), "")
        special = " canvas-receiving" if element.get("binding_path") == "voucher.receiving_summary" else ""
        return f'<div class="canvas-el canvas-text{special}" {box}>{prefix}{escaped(value)}</div>'
    if kind == "DIVIDER":
        return f'<div class="canvas-el canvas-divider" {box}></div>'
    if kind == "SHAPE":
        return f'<div class="canvas-el" {box}></div>'
    if kind == "IMAGE":
        return f'<div class="canvas-el canvas-picture" {box}>{image(element, facts)}</div>'
    if kind == "SIGNATURE":
        caption = escaped(element.get("content") or "Authorised signatory")
        label = element.get("label")
        under = f'<span class="canvas-label">{escaped(label)}</span>' if label else ""
        signed = image(element, facts) if element.get("asset_id") else ""
        return (
            f'<div class="canvas-el canvas-sign" {box}>{signed}'
            '<span class="canvas-sign-line"></span>'
            f"<span>{caption}</span>{under}</div>"
        )
    if kind in LINE_TABLES:
        return f'<div class="canvas-el canvas-table-box" {box}>{item_table(element, facts)}</div>'
    if kind == "TOTALS_BLOCK":
        rows = element.get("totals_rows") or [
            key
            for key in DEFAULT_TOTALS
            if key in {"subtotal", "round_off", "grand_total"} or facts.totals[key]
        ]
        items = "".join(
            f'<div class="canvas-words"><dt>{escaped(TOTALS_LABELS[key])}</dt>'
            f"<dd>{escaped(facts.words)}</dd></div>"
            if key == "amount_in_words"
            else f'<div class="{"canvas-grand" if key == "grand_total" else ""}">'
            f"<dt>{escaped(TOTALS_LABELS[key])}</dt>"
            f"<dd>{escaped(facts.money(facts.totals[key]))}</dd></div>"
            for key in rows
        )
        return f'<dl class="canvas-el canvas-totals" {box}>{items}</dl>'
    if kind == "TAX_SUMMARY":
        grouping = element.get("tax_grouping") or "by_rate"
        body = (
            "".join(
                f"<tr><td>{escaped(code)}</td><td>{escaped(rate or '—')}</td>"
                f'<td class="canvas-num">{escaped(facts.money(basis))}</td>'
                f'<td class="canvas-num">{escaped(facts.money(amount))}</td></tr>'
                for code, rate, basis, amount in facts.tax_rows(grouping)
            )
            or '<tr><td colspan="4">No tax on this bill</td></tr>'
        )
        return (
            f'<div class="canvas-el" {box}><table class="canvas-table" aria-label="Tax summary">'
            '<thead><tr><th>Tax</th><th>Rate</th><th class="canvas-num">Taxable</th>'
            f'<th class="canvas-num">Amount</th></tr></thead><tbody>{body}</tbody></table></div>'
        )
    raise ValidationFailedError(f"this element cannot be printed yet: {escaped(kind)}")


def image(element: dict[str, Any], facts: Facts) -> str:
    """The element's picture, fitted as the layout says; refused if it was not resolved."""
    source = facts.pictures.get(asset_key(element.get("asset_id")))
    if source is None:
        raise ValidationFailedError("a layout picture was not resolved for this print")
    fit = element.get("image_fit") or "contain"
    if fit not in FITS:
        raise ValidationFailedError("the layout's picture fit is not supported")
    alt = escaped(element.get("label") or element.get("content") or "")
    return f'<img class="canvas-img canvas-img--{fit}" src="{source}" alt="{alt}">'


def item_table(element: dict[str, Any], facts: Facts) -> str:
    width = bounded(element.get("width", 1), 0.01, 2000, "table width")
    kind = str(element.get("type"))
    columns = [column for column in element.get("columns") or [] if column.get("show", True)] or [
        {"key": key, "width_mm": width * share} for key, share in DEFAULT_COLUMNS[kind]
    ]
    options = element.get("row_options") or {}
    head = "".join(
        f'<th class="{"canvas-num" if numeric(column["key"]) else ""}"'
        f' style="{escaped(align(column))}">'
        f'{escaped(column.get("label") or COLUMN_LABELS.get(column["key"], column["key"]))}</th>'
        for column in columns
    )
    widths = "".join(
        f'<col style="width:{mm(bounded(column["width_mm"], 0.01, 500, "column width"))}">'
        for column in columns
    )
    rows = []
    for index, (supply, row) in enumerate(facts.lines_for(kind), 1):
        cells = "".join(
            f'<td class="{"canvas-num" if numeric(column["key"]) else ""}" '
            f'style="{escaped(align(column))}">{facts.cell(column["key"], index, supply, row)}</td>'
            for column in columns
        )
        rows.append(
            f'<tr class="{"canvas-zebra" if options.get("zebra") and index % 2 == 0 else ""}">'
            f"{cells}</tr>"
        )
    blank = int(bounded(options.get("blank_rows") or 0, 0, 50, "blank rows"))
    rows.extend("<tr>" + "<td>&nbsp;</td>" * len(columns) + "</tr>" for _ in range(blank))
    # A repeated header is the browser's default for a table header group; turned off, the
    # header is an ordinary first row and prints once.
    group = "thead" if options.get("repeat_header", True) is not False else "tbody"
    return (
        f'<table class="canvas-table" aria-label="{LINE_TABLES[kind]}">'
        f"<colgroup>{widths}</colgroup>"
        f"<{group}><tr>{head}</tr></{group}><tbody>{''.join(rows)}</tbody></table>"
    )


def numeric(key: str) -> bool:
    return key in NUMERIC or key.endswith(("_amount", "_rate"))


def align(column: dict[str, Any]) -> str:
    value = column.get("align")
    if value is None:
        return ""
    if value not in {"left", "center", "right"}:
        raise ValidationFailedError("the layout's column alignment is not supported")
    return f"text-align:{value}"


def zone_html(section: dict[str, Any], facts: Facts, left: float, top: float, blank: bool) -> str:
    """A zone at its place. The one holding the line table grows; the rest keep their size."""
    width = bounded(section.get("width", 1), 0.01, 2000, "zone width")
    height = bounded(section.get("height", 1), 0.01, 2000, "zone height")
    elements = sorted(
        section.get("elements") or [], key=lambda row: (row.get("y", 0), row.get("x", 0))
    )
    receiving = next(
        (row for row in elements if row.get("binding_path") == "voucher.receiving_summary"),
        None,
    )
    table = next((row for row in elements if row.get("type") in LINE_TABLES), None)
    if blank and table is None:
        # Pre-printed stationery: the letterhead is on the paper, so the zone keeps its space.
        place = f"left:{mm(left)};top:{mm(top)};width:{mm(width)};height:{mm(height)}"
        return f'<div class="canvas-zone" style="{escaped(place)}"></div>'
    if receiving is not None:
        if len(elements) != 1 or section.get("type") == "HEADER":
            raise ValidationFailedError("the receiving summary needs its own zone outside the header")
        offset = bounded(receiving.get("y", 0), 0, 2000, "receiving position")
        place = f"margin-left:{mm(left)};margin-top:{mm(top)};width:{mm(width)};min-height:{mm(height)}"
        return (
            f'<div class="canvas-zone canvas-zone--grows" style="{escaped(place)}">'
            f'<div style="height:{mm(offset)}"></div>'
            + element_html(receiving, facts, flow=True)
            + "</div>"
        )
    if table is None:
        place = f"left:{mm(left)};top:{mm(top)};width:{mm(width)};height:{mm(height)}"
        inner = "".join(element_html(element, facts) for element in elements)
        return f'<div class="canvas-zone" style="{escaped(place)}">{inner}</div>'
    table_top = bounded(table.get("y", 0), 0, 2000, "table position")
    table_bottom = table_top + bounded(table.get("height", 1), 0.01, 2000, "table height")
    above = [row for row in elements if row is not table and row.get("y", 0) < table_bottom]
    below = [row for row in elements if row is not table and row.get("y", 0) >= table_bottom]
    rest = max((row.get("y", 0) + row.get("height", 0) for row in below), default=table_bottom)
    after = "".join(
        element_html({**row, "y": row.get("y", 0) - table_bottom}, facts) for row in below
    )
    style = f"margin-left:{mm(left)};margin-top:{mm(top)};width:{mm(width)};min-height:{mm(height)}"
    return (
        f'<div class="canvas-zone canvas-zone--grows" style="{escaped(style)}">'
        + "".join(element_html(row, facts) for row in above)
        + f'<div style="height:{mm(table_top)}"></div>'
        + element_html(table, facts, flow=True)
        + f'<div class="canvas-after" style="height:{mm(max(rest - table_bottom, 0))}">'
        + after
        + "</div>"
        + "</div>"
    )


def canvas_document(
    value: dict[str, Any], config: DisplayConfiguration, number_text: str
) -> tuple[str, str]:
    """``(page css, body html)`` for the resolved custom layout in ``value``."""
    layout = value["layout"]
    canvas = layout["layout_definition"]
    width, height = page_box(layout)
    roll = roll_width(layout) is not None
    margins = (canvas.get("page") or {}).get("margins") or {}
    top, right, bottom, left = (
        bounded(margins.get(side, 10), 0, 100, "margin")
        for side in ("top", "right", "bottom", "left")
    )
    theme = canvas.get("theme") or {}
    font = theme.get("font_family", "Arial")
    if not isinstance(font, str) or not FONT.fullmatch(font):
        raise ValidationFailedError("the layout's font is not supported")
    primary = colour(theme.get("primary_color", "#263c58"), "primary colour")
    size = bounded(theme.get("font_size_pt", 10), 6, 24, "font size")
    facts = Facts(value, config, number_text)
    options = canvas.get("print_options") or {}
    blank_header = bool(options.get("pre_printed_stationery"))
    sections = sorted(
        canvas.get("sections") or [], key=lambda row: (row.get("y", 0), row.get("x", 0))
    )
    # Zones overlapping in height share a band; the band holding the line table is the one
    # that grows, and every band keeps its drawn gap to the one above.
    bands: list[list[dict[str, Any]]] = []
    for section in sections:
        y = bounded(section.get("y", 0), -1000, 2000, "zone position")
        if bands and y < max(row["y"] + row["height"] for row in bands[-1]):
            bands[-1].append(section)
        else:
            bands.append([section])
    blocks, cursor = [], top
    for band in bands:
        if len(band) > 1 and any(
            element.get("binding_path") == "voucher.receiving_summary"
            for row in band for element in row.get("elements") or []
        ):
            raise ValidationFailedError("the receiving summary needs its own vertical band")
        band_top = min(row["y"] for row in band)
        band_bottom = max(row["y"] + row["height"] for row in band)
        gap = max(band_top - cursor, 0)
        grows = any(
            element.get("type") in LINE_TABLES
            or element.get("binding_path") == "voucher.receiving_summary"
            for row in band
            for element in row.get("elements") or []
        )
        zones = [
            zone_html(
                section,
                facts,
                bounded(section.get("x", 0), -1000, 2000, "zone position") - left,
                section["y"] - band_top,
                blank_header and section.get("type") == "HEADER",
            )
            for section in band
        ]
        kind = "canvas-band canvas-band--grows" if grows else "canvas-band"
        band_style = f"margin-top:{mm(gap)};" + (
            f"min-height:{mm(band_bottom - band_top)}"
            if grows
            else f"height:{mm(band_bottom - band_top)}"
        )
        blocks.append(f'<div class="{kind}" style="{escaped(band_style)}">{"".join(zones)}</div>')
        cursor = band_bottom
    page = "".join(blocks)
    copies = [copy for copy in options.get("copies") or [] if copy in COPY_LABELS]
    position = options.get("copy_mark_position")
    marked = len(copies) > 1 or position is not None
    # A preview of a saved version says so on every copy, so it is never used as the bill.
    preview = (
        '<span class="canvas-mark canvas-mark--preview">Layout preview · not for use</span>'
        if layout.get("preview")
        else ""
    )
    if marked:
        body = "".join(
            f'<div class="canvas-copy">{preview}'
            f'<span class="canvas-mark canvas-mark--{escaped(position or "top-right")}">'
            f"{escaped(COPY_LABELS[copy])}</span>{page}</div>"
            for copy in copies or ["ORIGINAL_FOR_RECIPIENT"]
        )
    else:
        body = f'<div class="canvas-copy">{preview}{page}</div>'
    if roll:
        # One continuous page: the margins become the roll's own padding, and print_child
        # sets the page length to what was printed.
        css = (
            # Copies follow one another down the same strip instead of starting new pages.
            ".canvas-copy + .canvas-copy { break-before: auto; margin-top: 6mm; }"
            f"@page {{ size: {mm(width)} {mm(height)}; margin: 0; }}"
            f"main {{ width: {mm(width)}; padding: {mm(top)} {mm(right)} {mm(bottom)} "
            f"{mm(left)}; }}"
        )
    else:
        css = (
            f"@page {{ size: {mm(width)} {mm(height)}; "
            f"margin: {mm(top)} {mm(right)} {mm(bottom)} {mm(left)}; }}"
        )
    css += (
        f"html {{ font: {size:g}pt {font}, sans-serif; }}:root {{ --canvas-primary: {primary}; }}"
    )
    return css, body


def custom_problems(value: dict[str, Any]) -> list[tuple[str, str]]:
    from vouchers.domain.print_capabilities import PURCHASE, problems

    return problems(value["layout"], PURCHASE)
