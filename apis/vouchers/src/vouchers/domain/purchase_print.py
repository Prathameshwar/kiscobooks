"""Versioned, escaped Purchase presentation. No tax or payable is calculated here.

The only derived figures are display arithmetic over authoritative, already-frozen amounts: a
bill's credit period (due date minus invoice date) and the balance left after the settlements
saved on the bill (payable minus tenders and advances), which Accounting has already enforced as
non-negative. Everything printed is read from the frozen snapshot, so a re-render is identical.
"""

import datetime as dt
import hashlib
import html
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from billing_platform.display import DisplayConfiguration, date, number
from billing_platform.errors import ConflictError, ValidationFailedError
from voucher_execution.invoice import InvoiceCalculationDetail, InvoiceInput, InvoiceSupply
from voucher_execution.printing import PurchasePrintFacts

from vouchers.domain.amount_words import amount_in_words
from vouchers.domain.canvas_print import (
    canvas_document,
    custom_problems,
    exactly,
    rate_text,
    roll_width,
)

# Bump the renderer version whenever the PDF's content or its rendering changes, and the layout
# version whenever the printed presentation (blocks, labels, order) changes. Both are frozen into
# every job; a job under another version fails as SOURCE_INTEGRITY instead of printing differently.
RENDERER_VERSION = "purchase-pdf@4"
LAYOUT_VERSION = "purchase-a4@3"
# Exit status of a renderer process that ended itself on its own deadline.
RENDER_DEADLINE_EXIT_CODE = 75


def snapshot_hash(value: dict[str, Any]) -> str:
    # The only floating point values are Design's validated display geometry.
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > 5_242_880:
        raise ValidationFailedError("print document exceeds the supported size")
    return hashlib.sha256(raw).hexdigest()


def labels_unchanged(frozen: dict[str, Any], latest: dict[str, Any]) -> bool:
    """Whether every name and number the frozen print carries is still readable and the same.

    Accounting returns a name or the voucher number only while the actor may read it, and ``None``
    when that read is denied. A label the frozen print does not carry is not compared: it prints
    nothing, so a value that has become readable since discloses nothing. A label it does carry
    must come back unchanged, so a read denied after generation stops the old PDF from being
    delivered with the name still on it.
    """
    for key in ("supplier", "voucher_number"):
        if frozen.get(key) is not None and latest.get(key) != frozen[key]:
            return False
    for group in ("ledgers", "units"):
        newest = latest.get(group) or {}
        if any(
            newest.get(key) != name
            for key, name in (frozen.get(group) or {}).items()
            if name is not None
        ):
            return False
    return True


#: HSN (goods) or SAC (services): digits only, as Accounting's tax evidence records them.
CODE = re.compile(r"[0-9]{4,8}")


def escaped(value: object) -> str:
    return html.escape(str(value if value is not None else "—"), quote=True)


def exact(raw: object, what: str) -> Decimal:
    """A frozen non-negative exact decimal string, or a refusal."""
    try:
        value = Decimal(raw) if isinstance(raw, str) and len(raw) <= 40 else None
    except InvalidOperation:
        value = None
    if value is None or not value.is_finite() or value < 0:
        raise ValidationFailedError(f"{what} is invalid")
    return value


def settlement_amount(row: dict[str, Any], currency: str) -> Decimal:
    """One frozen tender or advance: a positive exact amount in the bill's own currency."""
    if row.get("currency") != currency:
        raise ValidationFailedError("print settlement currency differs from the bill's currency")
    raw = row.get("amount")
    try:
        amount = Decimal(raw) if isinstance(raw, str) and len(raw) <= 40 else None
    except InvalidOperation:
        amount = None
    if amount is None or not amount.is_finite() or amount <= 0:
        raise ValidationFailedError("print settlement amount is invalid")
    return amount


def settled_total(invoice: dict[str, Any], currency: str) -> Decimal:
    tenders, allocations = invoice.get("tenders", []), invoice.get("allocations", [])
    if len(tenders) > 100 or len(allocations) > 100:
        raise ValidationFailedError("print settlements exceed their bound")
    return sum((settlement_amount(row, currency) for row in [*tenders, *allocations]), Decimal(0))


def validate_snapshot(value: dict[str, Any]) -> None:
    document, calculation = value["document"], value["calculation"]
    display = DisplayConfiguration.model_validate(value["display"])
    if document.get("currency") != display.base_currency:
        # Accounting calculates and posts base-currency invoices only (a foreign-currency bill
        # cannot be previewed or posted), so there is nothing authoritative to print for one.
        raise ValidationFailedError(
            "Purchase printing supports bills in the company's base currency only; this bill is "
            f"in {document.get('currency')}, the base currency is {display.base_currency}"
        )
    InvoiceCalculationDetail.model_validate(calculation)
    if document.get("kind") != "PURCHASE" or document.get("currency") != calculation["currency"]:
        raise ValidationFailedError("print source is not a matching Purchase calculation")
    supplies = document.get("invoice", {}).get("supplies", [])
    calculated = calculation.get("lines", [])
    keys = [str(row["line_key"]) for row in supplies]
    if (
        not 1 <= len(keys) <= 200
        or len(set(keys)) != len(keys)
        or len(calculated) != len(keys)
        or set(keys) != {str(row["key"]) for row in calculated}
    ):
        raise ValidationFailedError("print lines do not match the authoritative calculation")
    invoice = document["invoice"]
    labels = value.get("labels", {})
    number_value = labels.get("voucher_number")
    if number_value is not None and (
        value.get("calculation_source") != "POSTED"
        or not isinstance(number_value, str)
        or not 1 <= len(number_value) <= 100
    ):
        raise ValidationFailedError("a voucher number can only come from a posted bill")
    ledgers = labels.get("ledgers", {})
    owned = keys + [str(row["tender_key"]) for row in invoice.get("tenders", [])]
    if (
        not isinstance(ledgers, dict)
        or len(ledgers) > 400
        or not set(ledgers) <= set(owned)
        or any(
            name is not None and not (isinstance(name, str) and 1 <= len(name) <= 200)
            for name in ledgers.values()
        )
    ):
        raise ValidationFailedError("print ledger names do not match the bill's lines")
    goods = {str(row["line_key"]) for row in supplies if row.get("supply_kind") == "GOODS"}
    for row in supplies:
        code = row.get("hsn_sac")
        if code is not None and not (isinstance(code, str) and CODE.fullmatch(code)):
            raise ValidationFailedError("print HSN/SAC code is invalid")
        for key in ("quantity", "rate"):
            if (key in row) != (str(row["line_key"]) in goods):
                raise ValidationFailedError("print quantity and rate belong to goods lines only")
            if key in row:
                exact(row[key], "print quantity or rate")
        if "per" in row and ("rate" not in row or exact(row["per"], "print pricing unit") <= 0):
            raise ValidationFailedError("print pricing unit belongs to a goods rate")
    units = labels.get("units", {})
    if (
        not isinstance(units, dict)
        or not set(units) <= goods
        or any(not (isinstance(name, str) and 1 <= len(name) <= 20) for name in units.values())
    ):
        raise ValidationFailedError("print unit labels do not match the bill's goods lines")
    if settled_total(invoice, document["currency"]) > Decimal(calculation["payable"]):
        raise ValidationFailedError("print settlements exceed the supplier payable")
    layout = value["layout"]
    if layout.get("preview") and (
        layout["source"] != "CUSTOM"
        or not layout.get("template_id")
        or not layout.get("version_id")
    ):
        raise ValidationFailedError("a layout preview names one saved designed version")
    if layout["source"] == "BUILTIN" and (
        layout["version"] != LAYOUT_VERSION
        or layout["layout_digest"] != hashlib.sha256(LAYOUT_VERSION.encode()).hexdigest()
    ):
        raise ValidationFailedError("Purchase standard layout version is unavailable")
    if layout["source"] == "CUSTOM":
        # One list decides what a designed layout may use (print_capabilities.PURCHASE); the
        # designer blocks publishing against the same list.
        found = custom_problems(value)
        if found:
            reasons = "; ".join(dict.fromkeys(reason for _, reason in found))
            raise ValidationFailedError(
                f"this custom layout cannot be printed: {reasons}. Change it in the designer, "
                "or return Purchase to its standard layout"
            )
        # Every number, colour and font in it is checked before a job is admitted.
        canvas_document(value, DisplayConfiguration.model_validate(value["display"]), "")


def voucher_number(value: dict[str, Any]) -> str:
    """The number printed on the bill: Vouchers' own if it ever issues one, else Accounting's.

    Accounting's journal number is allocated on posting only and arrives in the frozen facts, so
    a draft, an approval in progress or a preview honestly says "Not allocated".
    """
    return str(
        value["document"].get("issue_number")
        or value.get("labels", {}).get("voucher_number")
        or "Not allocated"
    )


def credit_period(document_date: object, due_date: object) -> int | None:
    """Whole days from the supplier's invoice date to the due date, when that is a period."""
    try:
        start, end = dt.date.fromisoformat(str(document_date)), dt.date.fromisoformat(str(due_date))
    except ValueError:
        return None
    return (end - start).days if 0 <= (end - start).days <= 3650 else None


def assemble_snapshot(
    *,
    document: dict[str, Any],
    invoice: InvoiceInput,
    facts: PurchasePrintFacts,
    display: dict[str, Any],
    layout: dict[str, Any],
) -> dict[str, Any]:
    """Freeze everything a print shows: saved bill, owner facts, names and display formats.

    `document` is the saved voucher's printable header; `invoice` its saved invoice; `facts` what
    Accounting returned under the actor's own rights. Nothing is read later, so a retry, a
    re-render and the integrity hash all see exactly this.
    """
    if facts.voucher_number is not None and facts.source != "POSTED":
        raise ConflictError("a voucher number exists only for a posted bill")
    printable = dict(document)
    owned = {row.key: row for row in facts.lines}
    if not set(owned) <= {line.line_key for line in invoice.supplies}:
        raise ConflictError("print line facts do not match the bill's lines")

    def supply(line: InvoiceSupply) -> dict[str, Any]:
        row: dict[str, Any] = {
            "line_key": str(line.line_key),
            "description": line.description,
            # Which line table a designed layout prints it in (plan D2).
            "supply_kind": line.supply_kind,
            "hsn_sac": owned[line.line_key].classification_code if line.line_key in owned else None,
        }
        if line.supply_kind == "GOODS":
            # Billed in the item's base unit at the saved rate; the accepted calculation
            # covers both (Accounting's check_line).
            billed = next((row for row in line.quantities if row.basis == "BILLED"), None)
            if billed is None or line.unit_price is None:
                raise ConflictError("a goods line needs its billed quantity and rate to print")
            row |= {
                "quantity": format(billed.quantity, ".4f"),
                "rate": format(line.unit_price, ".4f"),
            }
            # Accounting prices the line per this many units; a rate per 100 prints as such.
            if line.price_denominator != 1:
                row["per"] = format(line.price_denominator, ".4f")
        return row

    printable["invoice"] = {
        "bill_reference": invoice.bill_reference,
        "due_date": invoice.due_date.isoformat(),
        "supplies": [supply(line) for line in invoice.supplies],
        "components": [
            {
                "component_key": str(row.component_key),
                "purpose": row.purpose,
                "source_evidence": row.source_evidence,
            }
            for row in invoice.components
        ],
        "tenders": [
            {
                "tender_key": str(row.tender.tender_key),
                "mode": row.tender.mode,
                "amount": format(row.tender.amount, ".4f"),
                "currency": row.tender.currency,
                "reference": row.tender.reference,
                "instrument_date": row.tender.instrument_date.isoformat()
                if row.tender.instrument_date
                else None,
            }
            for row in invoice.tenders
        ],
        "allocations": [
            {
                "allocation_key": str(row.allocation_key),
                "amount": format(row.amount, ".4f"),
                "currency": row.currency,
            }
            for row in invoice.allocations
        ],
    }
    snapshot = {
        "renderer_version": RENDERER_VERSION,
        "document": printable,
        "calculation": facts.calculation.model_dump(
            mode="json", exclude={"allocations", "tax_evidence"}
        )
        | {"allocations": [], "tax_evidence": []},
        "calculation_source": facts.source,
        "display": display,
        "labels": {
            "supplier": facts.supplier_name,
            "voucher_number": facts.voucher_number,
            "ledgers": {str(row.key): row.name for row in facts.ledgers},
            # A goods line's unit symbol, read under the actor's rights like every name here.
            "units": {str(row.key): row.unit_label for row in facts.lines if row.unit_label},
        },
        "layout": layout,
    }
    validate_snapshot(snapshot)
    return snapshot


def render_html(value: dict[str, Any]) -> str:
    validate_snapshot(value)
    config = DisplayConfiguration.model_validate(value["display"])
    document, calculation = value["document"], value["calculation"]
    invoice = document["invoice"]
    currency = escaped(document["currency"])

    def amount_class(amount: str | Decimal) -> str:
        return "amount amount-compact" if len(number(amount, config)) > 13 else "amount"

    def money(amount: Decimal | str | int | None) -> str:
        return escaped(number(amount, config))

    def field_date(day: str | None) -> str:
        return escaped(date(day, config))

    status = str(document["status"])
    warning = (
        "Draft — not posted to the accounts"
        if status in {"DRAFT", "REJECTED"}
        else "Cancelled — do not use for payment"
        if status == "CANCELLED"
        else "Reversed — refer to the linked correction"
        if status == "REVERSED"
        else "Approval in progress — not posted"
        if status in {"SUBMITTED", "APPROVED"}
        else "Posted purchase record"
        if status == "POSTED"
        else "Saved purchase record — not posted"
    )
    rows = []
    wide_amounts = False
    amounts = {str(row["key"]): row for row in calculation["lines"]}
    labels = value.get("labels", {})
    ledgers = labels.get("ledgers", {})
    units = labels.get("units", {})
    # A bill with goods prints what was bought: HSN/SAC, quantity with its unit, and rate, in
    # place of the base amount that quantity times rate already shows.
    goods = any(row.get("supply_kind") == "GOODS" for row in invoice["supplies"])
    for index, supply in enumerate(invoice["supplies"], 1):
        row = amounts[str(supply["line_key"])]
        ledger = ""
        if str(supply["line_key"]) in ledgers:
            name = ledgers[str(supply["line_key"])]
            ledger = (
                f'<div class="ledger">{escaped("Ledger: " + name)}</div>'
                if name
                else '<div class="ledger">Ledger restricted</div>'
            )
        charged = sum(
            (Decimal(tax["amount"]) for tax in row["taxes"] if tax["supplier_charged"]), Decimal(0)
        )
        wide_amounts |= any(
            len(number(amount, config)) > 13
            for amount in (
                row["entered"],
                row["commercial"],
                charged,
                row["payable"],
            )
        )
        if goods:
            quantity = "—"
            if "quantity" in supply:
                unit = units.get(str(supply["line_key"]))
                quantity = exactly(supply["quantity"], config, quantity=True) + (
                    f" {unit}" if unit else ""
                )
            middle = (
                f'<td>{escaped(supply.get("hsn_sac"))}</td>'
                f'<td class="amount">{escaped(quantity)}</td>'
                f'<td class="amount">'
                f"{escaped(rate_text(supply, config) if 'rate' in supply else None)}</td>"
            )
        else:
            middle = f'<td class="{amount_class(row["entered"])}">{money(row["entered"])}</td>'
        rows.append(
            f'<tr><td class="row-number">{index}</td><td class="description">'
            f'<div>{escaped(supply.get("description") or "Purchase line")}</div>{ledger}</td>'
            + middle
            + f'<td class="{amount_class(row["commercial"])}">{money(row["commercial"])}</td>'
            f'<td class="{amount_class(charged)}">{money(charged)}</td>'
            f'<td class="{amount_class(row["payable"])}">{money(row["payable"])}</td></tr>'
        )
    heading = (
        '<th scope="col">HSN/SAC</th><th scope="col" class="amount">Qty</th>'
        '<th scope="col" class="amount">Rate</th>'
        if goods
        else '<th scope="col" class="amount">Base amount</th>'
    )
    kind = " ".join(name for name, on in (("goods", goods), ("wide-amounts", wide_amounts)) if on)
    table = (
        f'<table class="{kind}" aria-label="Purchase lines">'
        '<thead><tr><th scope="col">#</th><th scope="col">Particulars</th>'
        + heading
        + '<th scope="col" class="amount">Net amount</th>'
        '<th scope="col" class="amount">Supplier tax</th>'
        '<th scope="col" class="amount">Line total</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )
    component_results = {str(row["key"]): row for row in calculation.get("components", [])}
    adjustment_rows = []
    for component in invoice.get("components", []):
        result = component_results.get(str(component["component_key"]))
        if result is None:
            raise ValidationFailedError("print adjustment has no authoritative result")
        adjustment_rows.append(
            f'<div><dt>{escaped(component.get("source_evidence") or component["purpose"])}</dt>'
            f'<dd>{money(result["amount"])}</dd></div>'
        )
    adjustments = (
        (
            '<section class="adjustments"><h2>Bill adjustments</h2><dl>'
            + "".join(adjustment_rows)
            + "</dl></section>"
        )
        if adjustment_rows
        else ""
    )
    is_posted = value.get("calculation_source") == "POSTED"
    settlement_rows = []
    tenders, advances = invoice.get("tenders", []), invoice.get("allocations", [])
    for tender in tenders:
        parts = ["Paid at posting" if is_posted else "To be paid at posting", str(tender["mode"])]
        if str(tender["tender_key"]) in ledgers:
            parts.append(ledgers[str(tender["tender_key"])] or "Ledger restricted")
        if tender.get("reference"):
            parts.append("Ref " + str(tender["reference"]))
        if tender.get("instrument_date"):
            parts.append(date(tender["instrument_date"], config))
        settlement_rows.append(
            f'<div><dt>{escaped(" · ".join(parts))}</dt><dd>{money(tender["amount"])}</dd></div>'
        )
    if advances:
        label = "Advances and credits applied" if is_posted else "Advances and credits to apply"
        advance_total = sum((Decimal(row["amount"]) for row in advances), Decimal(0))
        settlement_rows.append(f"<div><dt>{label}</dt><dd>{money(advance_total)}</dd></div>")
    settlement = ""
    if settlement_rows:
        balance = Decimal(calculation["payable"]) - settled_total(invoice, document["currency"])
        settlement = (
            '<dl class="settlement">'
            + "".join(settlement_rows)
            + '<div class="balance"><dt>Balance payable after settlement</dt>'
            f"<dd>{money(balance)}</dd></div></dl>"
        )
    totals = (
        '<section class="totals" aria-label="Purchase totals"><h2>Bill summary</h2><dl>'
        f'<div><dt>Commercial total</dt><dd>{money(calculation["commercial_total"])}</dd></div>'
        f'<div><dt>Total tax</dt><dd>{money(calculation["tax_total"])}</dd></div>'
        '<div><dt>Supplier-charged tax</dt>'
        f'<dd>{money(calculation["charged_tax_total"])}</dd></div>'
        f'<div><dt>Rounding</dt><dd>{money(calculation["rounding"])}</dd></div>'
        f'<div class="grand-total"><dt>Supplier payable · {currency}</dt>'
        f'<dd>{money(calculation["payable"])}</dd></div></dl>'
        '<p class="in-words">'
        f"{escaped(amount_in_words(calculation['payable'], document['currency'], config))}</p>"
        + settlement
        + "<p>Payable is calculated from the saved invoice, before settlements. "
        "This copy does not confirm payment.</p></section>"
    )
    supplier = escaped(labels.get("supplier") or "Supplier details restricted")
    company = escaped(config.company_label)
    period = credit_period(document.get("document_date"), invoice.get("due_date"))
    terms = (
        f'<div><dt>Credit period</dt><dd>{period} day{"" if period == 1 else "s"}</dd></div>'
        if period is not None
        else ""
    )
    header = (
        f'<header><p class="eyebrow">{company}</p><div class="title-row">'
        f'<h1>Purchase voucher</h1><span class="status">{escaped(status)}</span></div>'
        '<p class="subtitle">Internal purchase record · Not a supplier tax invoice</p>'
        f'<p class="state-note">{escaped(warning)}</p></header>'
    )
    identity = (
        '<section class="bill-identity"><div><h2>Supplier</h2>'
        f'<p class="supplier">{supplier}</p><dl>'
        f'<div><dt>Supplier invoice no.</dt><dd>{escaped(invoice.get("bill_reference"))}</dd></div>'
        '<div><dt>Supplier invoice date</dt>'
        f'<dd>{field_date(document.get("document_date"))}</dd></div>'
        '</dl></div><div><h2>Our purchase record</h2><dl>'
        f'<div><dt>Voucher no.</dt><dd>{escaped(voucher_number(value))}</dd></div>'
        f'<div><dt>Posting date</dt><dd>{field_date(document.get("posting_date"))}</dd></div>'
        f'<div><dt>Payment due</dt><dd>{field_date(invoice.get("due_date"))}</dd></div>'
        + terms
        + f"<div><dt>Currency</dt><dd>{currency}</dd></div></dl></div></section>"
    )
    narration = (
        (
            f'<section class="notes"><h2>Narration</h2><p>{escaped(document["narration"])}</p>'
            '</section>'
        )
        if document.get("narration")
        else ""
    )
    source = (
        f'<footer class="evidence"><p>Saved revision {int(document["revision_number"])} · '
        f'{escaped(value["layout"]["name"])} · {escaped(value["layout"]["version"])}</p>'
        f'<p class="reference">Voucher reference: {escaped(document["id"])}</p></footer>'
    )
    body = (
        header
        + identity
        + table
        + '<div class="closing">'
        + adjustments
        + totals
        + "</div>"
        + narration
    )
    css = Path(__file__).with_name("purchase_print.css").read_text(encoding="utf-8")
    # Pictures are embedded only by a designed layout, only as checked data: URIs.
    images = "'none'"
    if value["layout"]["source"] == "CUSTOM":
        # A designed layout is the whole page, printed as drawn; every page's footer still
        # names the bill and its status.
        page, body = canvas_document(value, config, voucher_number(value))
        css += page
        images = "data:"
        if roll_width(value["layout"]) is not None:
            # A roll is one page with no page footer, so it names its bill at its end.
            body += f'<p class="roll-identity">{identity_line(value)}</p>'
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="referrer" content="no-referrer">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        f"style-src 'unsafe-inline'; img-src {images}\">"
        "<title>Purchase voucher</title><style>" + css + "</style></head><body>"
        "<main>" + body + source + "</main></body></html>"
    )


def identity_line(value: dict[str, Any]) -> str:
    """What every printed page says about its bill: kind, status, number and supplier."""
    preview = "Layout preview · " if value["layout"].get("preview") else ""
    supplier = escaped(value.get("labels", {}).get("supplier") or "Supplier details restricted")
    return (
        f"{preview}Purchase voucher · {escaped(value['document']['status'])} · "
        f"Voucher no. {escaped(voucher_number(value))} · {supplier}"
    )


def page_templates(value: dict[str, Any]) -> tuple[str, str]:
    """Header and footer for EVERY page, so a loose continuation page still names its bill.

    Chromium injects these into each page's margin box as HTML, so every value is escaped
    exactly like the body's and the structure is fixed, inline-styled and script-free. The
    footer is two compact lines and sits in the bottom margin, never over the content.
    """
    validate_snapshot(value)
    config = DisplayConfiguration.model_validate(value["display"])
    document, invoice = value["document"], value["document"]["invoice"]
    line = "min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;flex:1 1 auto"
    left, right = 15.0, 15.0
    if value["layout"]["source"] == "CUSTOM":
        margins = (value["layout"]["layout_definition"].get("page") or {}).get("margins") or {}
        left, right = float(margins.get("left", 10)), float(margins.get("right", 10))
    footer = (
        '<div style="font:7.5px Arial,sans-serif;color:#4a5c70;width:100%;'
        f'box-sizing:border-box;padding:0 {right:g}mm 0 {left:g}mm">'
        '<div style="display:flex;justify-content:space-between;gap:4mm">'
        f'<span style="{line}">{identity_line(value)}</span>'
        '<span style="white-space:nowrap">Page <span class="pageNumber"></span> of '
        '<span class="totalPages"></span></span></div>'
        f'<div style="{line}">Supplier invoice {escaped(invoice.get("bill_reference"))} · '
        f"Dated {escaped(date(document.get('document_date'), config))}</div></div>"
    )
    return "<span></span>", footer
