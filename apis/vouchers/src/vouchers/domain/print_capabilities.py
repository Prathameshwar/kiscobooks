"""What each voucher kind's printer prints from a designed layout (designer plan P3, 2026-11-03).

One manifest per kind, read by the renderer to refuse a layout before any browser starts and
published to the designer (`GET /print-capabilities`) so it blocks publishing the same layout
for the same reason. The two cannot disagree because there is one list.
"""

import uuid
from typing import Any

MANIFEST_VERSION = "print-capabilities@2"

#: The default column headings, as the designer's column catalogue shows them.
COLUMN_LABELS = {
    "serial_no": "#",
    "description": "Description",
    "hsn_sac": "HSN/SAC",
    "batch": "Batch",
    "expiry": "Expiry",
    "quantity": "Qty",
    "unit": "Unit",
    "rate": "Rate",
    "mrp": "MRP",
    "discount": "Discount",
    "taxable_value": "Taxable value",
    "cgst_rate": "CGST %",
    "cgst_amount": "CGST",
    "sgst_rate": "SGST %",
    "sgst_amount": "SGST",
    "igst_rate": "IGST %",
    "igst_amount": "IGST",
    "cess": "Cess",
    "amount": "Amount",
    "account": "Account",
}
TOTALS_LABELS = {
    "subtotal": "Subtotal",
    "discount": "Discount",
    "taxable_value": "Taxable value",
    "cgst": "CGST",
    "sgst": "SGST",
    "igst": "IGST",
    "cess": "Cess",
    "round_off": "Round off",
    "grand_total": "Grand total",
    "amount_in_words": "Amount in words",
    "outstanding_balance": "Outstanding balance",
}

PURCHASE: dict[str, Any] = {
    "kind": "PURCHASE",
    "version": MANIFEST_VERSION,
    "paper_sizes": ["A4", "A5", "LETTER", "CUSTOM", "THERMAL_80MM", "THERMAL_58MM"],
    "orientations": ["PORTRAIT", "LANDSCAPE"],
    "element_types": [
        "TEXT",
        "FIELD_BINDING",
        "IMAGE",
        "ITEM_TABLE",
        "ACCOUNT_TABLE",
        "TOTALS_BLOCK",
        "TAX_SUMMARY",
        "DIVIDER",
        "SHAPE",
        "SIGNATURE",
    ],
    #: What a Purchase bill's frozen print facts can answer. A field outside this list has
    #: nothing behind it to print.
    "bindings": [
        "company.name",
        "company.display_name",
        "party.name",
        "voucher.title",
        "voucher.document_number",
        "voucher.issue_number",
        "voucher.document_date",
        "voucher.posting_date",
        "voucher.due_date",
        "voucher.bill_reference",
        "voucher.currency",
        "voucher.status",
        "voucher.narration",
        "voucher.receiving_summary",
        "totals.subtotal",
        "totals.discount",
        "totals.taxable_value",
        "totals.tax_total",
        "totals.cgst",
        "totals.sgst",
        "totals.igst",
        "totals.cess",
        "totals.round_off",
        "totals.grand_total",
        "totals.amount_in_words",
    ],
    "item_columns": [
        "serial_no",
        "description",
        "hsn_sac",
        "quantity",
        "unit",
        "rate",
        "discount",
        "taxable_value",
        "cgst_rate",
        "cgst_amount",
        "sgst_rate",
        "sgst_amount",
        "igst_rate",
        "igst_amount",
        "cess",
        "amount",
        "account",
    ],
    "totals_rows": [
        "subtotal",
        "discount",
        "taxable_value",
        "cgst",
        "sgst",
        "igst",
        "cess",
        "round_off",
        "grand_total",
        "amount_in_words",
    ],
    "tax_groupings": ["by_rate", "none"],
    #: A bill always prints its lines: at least one line table — a product table, an accounts
    #: table, or one of each (plan D2) — each in a zone of its own, wherever it is placed.
    "line_tables": {"min": 1, "max_each": 1},
    "options": {
        "copies": True,
        "copy_marks": True,
        "pre_printed_stationery": True,
        "free_placement": True,
        "styles": True,
        "images": True,
        "components": False,
    },
    #: Pictures travel inside the signed layout resolution (bounded at 1 MiB in all), so each
    #: one and all of one layout's together are bounded; the designer warns against the same.
    "images": {
        "max_bytes": 524_288,
        "total_max_bytes": 655_360,
        "media_types": ["image/png", "image/jpeg", "image/webp"],
    },
}

MANIFESTS: dict[str, dict[str, Any]] = {"PURCHASE": PURCHASE}

_TYPE_NAMES = {
    "IMAGE": "images",
    "QR_CODE": "QR codes",
    "BARCODE": "barcodes",
    "TAX_SUMMARY": "tax summaries",
    "SHAPE": "boxes",
    "SIGNATURE": "signatures",
    "TOTALS_BLOCK": "totals blocks",
}


def asset_key(value: object) -> str:
    """An asset id in one spelling, so an upper-case id in a layout finds its picture."""
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        return str(value)


#: Why Design sent an image without its picture, as the sentence the person reads.
_IMAGE_REFUSALS = {
    "WITHDRAWN": "an image on this layout has been withdrawn; choose another picture",
    "TOO_LARGE": "an image on this layout is larger than 512 KB; upload a smaller picture",
    "OVER_BUDGET": "the images on this layout are larger than 640 KB together; use smaller "
    "pictures",
    "MISSING": "an image on this layout is no longer available; choose its picture again",
    "UNAVAILABLE": "an image on this layout cannot be read from storage; ask your administrator",
}


def problems(layout: dict[str, Any], manifest: dict[str, Any]) -> list[tuple[str, str]]:
    """Everything in a resolved layout the kind cannot print, as ``(target id, reason)``.

    ``layout`` is Design's resolution: the row's paper and the stored canvas. Reasons finish the
    sentence "… does not support …", so the designer and the refusal read the same.
    """
    kind = manifest["kind"].title()
    found: list[tuple[str, str]] = []
    canvas = layout.get("layout_definition") or {}
    sections = canvas.get("sections") or []
    first = str(sections[0].get("id", "")) if sections else ""

    def refuse(target: object, reason: str) -> None:
        found.append((str(target or first), f"{kind} printing does not support {reason} yet"))

    # A resolved layout carries its pictures (or why each is absent); a stored layout read by
    # the designer does not, and only its shape is judged here.
    resolved = (
        {asset_key(row.get("asset_id")): row for row in layout.get("assets") or []}
        if "assets" in layout
        else None
    )

    if canvas.get("schema_version") != "1.1.0":
        refuse(first, "layouts saved in an older format")
    if layout.get("paper_size", "A4") not in manifest["paper_sizes"]:
        refuse(first, f"{str(layout.get('paper_size')).replace('_', ' ').lower()} paper")
    if str(layout.get("page_orientation", "PORTRAIT")).upper() not in manifest["orientations"]:
        refuse(first, "this page orientation")
    options = manifest["options"]
    print_options = canvas.get("print_options") or {}
    if len(print_options.get("copies") or []) > 1 and not options["copies"]:
        refuse(first, "more than one printed copy")
    if print_options.get("copy_mark_position") and not options["copy_marks"]:
        refuse(first, "copy marks")
    if print_options.get("pre_printed_stationery") and not options["pre_printed_stationery"]:
        refuse(first, "pre-printed stationery")
    tables: dict[str, int] = {"ITEM_TABLE": 0, "ACCOUNT_TABLE": 0}
    for section in sections:
        if section.get("component_code") and not options["components"]:
            refuse(section.get("id"), "shared components in a zone")
        if section.get("free_placement") and not options["free_placement"]:
            refuse(section.get("id"), "freely placed zones")
        here = [row for row in section.get("elements") or [] if row.get("type") in tables]
        receiving = [
            row for row in section.get("elements") or []
            if row.get("type") == "FIELD_BINDING"
            and row.get("binding_path") == "voucher.receiving_summary"
        ]
        if receiving and (
            len(section.get("elements") or []) != 1 or section.get("type") == "HEADER"
        ):
            found.append(
                (
                    str(receiving[0].get("id") or section.get("id") or first),
                    "the receiving summary needs its own zone outside the header",
                )
            )
        if receiving:
            start, height = section.get("y"), section.get("height")
            if isinstance(start, int | float) and isinstance(height, int | float):
                for other in sections:
                    if other is section:
                        continue
                    other_start, other_height = other.get("y"), other.get("height")
                    if (
                        isinstance(other_start, int | float)
                        and isinstance(other_height, int | float)
                        and other_start < start + height
                        and start < other_start + other_height
                    ):
                        found.append(
                            (
                                str(receiving[0].get("id") or section.get("id") or first),
                                "the receiving summary needs its own vertical band",
                            )
                        )
                        break
        if len(here) > 1:
            refuse(section.get("id"), "two line tables in the same zone")
        for element in section.get("elements") or []:
            kind_name = element.get("type")
            target = element.get("id")
            if kind_name not in manifest["element_types"]:
                refuse(target, _TYPE_NAMES.get(kind_name, str(kind_name).lower()))
                continue
            if kind_name == "IMAGE" and not element.get("asset_id"):
                found.append((str(target), "an image on this layout has no picture chosen"))
            if element.get("asset_id"):
                if not options["images"]:
                    refuse(target, "images in a signature")
                elif resolved is not None:
                    status = (resolved.get(asset_key(element["asset_id"])) or {}).get("status")
                    if status != "READY":
                        found.append(
                            (
                                str(target),
                                _IMAGE_REFUSALS.get(str(status), _IMAGE_REFUSALS["MISSING"]),
                            )
                        )
            if any(value is not None for value in (element.get("style") or {}).values()):
                if not options["styles"]:
                    refuse(target, "element styles")
            binding = element.get("binding_path")
            if kind_name == "FIELD_BINDING" and binding not in manifest["bindings"]:
                refuse(target, f"the field {binding}")
            if kind_name in tables:
                tables[kind_name] += 1
                for column in element.get("columns") or []:
                    key = column.get("key")
                    if column.get("show", True) and key not in manifest["item_columns"]:
                        refuse(target, f"the {COLUMN_LABELS.get(key, str(key))} column")
            if kind_name == "TOTALS_BLOCK":
                for row in element.get("totals_rows") or []:
                    if row not in manifest["totals_rows"]:
                        refuse(target, f"the {TOTALS_LABELS.get(row, row).lower()} total")
            if kind_name == "TAX_SUMMARY":
                grouping = element.get("tax_grouping") or "by_rate"
                if grouping not in manifest["tax_groupings"]:
                    refuse(target, "a tax summary grouped by HSN")
    limits = manifest["line_tables"]
    if sum(tables.values()) < limits["min"]:
        refuse(first, "a layout without a line table, which is where the bill's lines print")
    if tables["ITEM_TABLE"] > limits["max_each"]:
        refuse(first, "more than one product table")
    if tables["ACCOUNT_TABLE"] > limits["max_each"]:
        refuse(first, "more than one accounts table")
    return found
