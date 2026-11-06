"""A designed Purchase layout prints as drawn (designer plan P3, 2026-11-03).

The renderer places zones and elements at their millimetres, styles them from the canvas's
typed fields only, lets the line table's band grow, and refuses — before any browser — what the
Purchase manifest does not list. The manifest is what the designer reads to block publishing.
"""

import copy
import re

import pytest
from billing_platform.errors import ValidationFailedError
from conftest import headers

from tests.test_purchase_print import snapshot
from vouchers.domain.print_capabilities import PURCHASE, problems
from vouchers.domain.purchase_print import render_html

MARGINS = {"top": 12, "right": 10, "bottom": 14, "left": 10, "unit": "mm"}


def element(kind: str, x: float, y: float, width: float, height: float, **extra: object) -> dict:
    return {
        "id": f"el-{kind.lower()}-{int(x)}-{int(y)}",
        "type": kind,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
    } | extra


def layout(*sections: dict, **page: object) -> dict:
    return {
        "source": "CUSTOM",
        "name": "Designed bill",
        "version": "3",
        "layout_digest": "b" * 64,
        "paper_size": "A4",
        "page_orientation": "PORTRAIT",
        **page,
        "layout_definition": {
            "schema_version": "1.1.0",
            "page": {"margins": MARGINS, "grid_snap": True, "grid_step_mm": 5},
            "theme": {"primary_color": "#1e40af", "font_family": "Inter, Arial", "font_size_pt": 9},
            "print_options": {"copies": ["ORIGINAL_FOR_RECIPIENT"]},
            "sections": list(sections),
        },
    }


def zone(
    identity: str, kind: str, x: float, y: float, width: float, height: float, *elements: dict
) -> dict:
    return {
        "id": identity,
        "type": kind,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "elements": list(elements),
    }


def designed() -> dict:
    return layout(
        zone(
            "head",
            "HEADER",
            10,
            12,
            190,
            30,
            element(
                "TEXT",
                0,
                0,
                80,
                8,
                content="Purchase <bill> & co",
                style={"font_weight": "bold", "color": "#112233"},
            ),
            element("FIELD_BINDING", 120, 0, 70, 6, binding_path="party.name", label="Supplier"),
            element(
                "SHAPE", 120, 8, 70, 18, style={"border_width_mm": 0.5, "border_style": "dashed"}
            ),
        ),
        zone("lines", "ITEM_TABLE", 10, 50, 190, 60, element("ITEM_TABLE", 0, 0, 190, 40)),
        zone(
            "foot",
            "FOOTER",
            10,
            120,
            190,
            40,
            element("TOTALS_BLOCK", 110, 0, 80, 20),
            element("SIGNATURE", 0, 20, 60, 18, content="For Sharma Traders"),
            element("DIVIDER", 0, 0, 100, 1),
        ),
    )


def printed(value_layout: dict, mutate=None) -> str:
    value = snapshot()
    value["layout"] = value_layout
    if mutate:
        mutate(value)
    return render_html(value)


def test_zones_and_elements_print_at_their_millimetres():
    html = printed(designed())
    # Page setup is the layout's, not the standard A4 profile's.
    assert "@page { size: 210mm 297mm; margin: 12mm 10mm 14mm 10mm; }" in html
    # The header band sits on the top margin; the supplier field is 120mm into its zone.
    assert "left:120mm;top:0mm;width:70mm;height:6mm" in html
    # Zone x is measured from the page edge, printed from the left margin.
    assert re.search(r'class="canvas-zone" style="left:0mm;top:0mm;width:190mm;height:30mm"', html)
    # The footer band keeps its drawn 10mm gap below the table band.
    assert "margin-top:10mm;height:40mm" in html


def test_text_is_escaped_and_styles_come_only_from_typed_fields():
    html = printed(designed())
    assert "Purchase &lt;bill&gt; &amp; co" in html and "<bill>" not in html
    assert "font-weight:700;color:#112233" in html
    assert "border:0.5mm dashed currentColor" in html
    assert '<span class="canvas-label">Supplier </span>' in html


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"color": "red;background:url(x)"}, "colour"),
        ({"font_size_pt": 400}, "font size"),
        ({"font_weight": "900"}, "font weight"),
    ],
)
def test_a_style_outside_its_vocabulary_is_refused_not_passed_through(patch, reason):
    value_layout = designed()
    value_layout["layout_definition"]["sections"][0]["elements"][0]["style"] = patch
    with pytest.raises(ValidationFailedError, match=reason):
        printed(value_layout)


def test_a_font_that_could_carry_css_is_refused():
    value_layout = designed()
    value_layout["layout_definition"]["theme"]["font_family"] = "Arial;}body{display:none"
    with pytest.raises(ValidationFailedError, match="font"):
        printed(value_layout)


def test_the_line_table_band_grows_and_prints_the_chosen_columns():
    value_layout = designed()
    table = value_layout["layout_definition"]["sections"][1]["elements"][0]
    table["columns"] = [
        {"key": "serial_no", "width_mm": 10, "show": True},
        {"key": "description", "label": "Particulars", "width_mm": 100, "show": True},
        {"key": "cgst_rate", "width_mm": 20, "show": True},
        {"key": "amount", "width_mm": 60, "show": True},
    ]
    table["row_options"] = {"zebra": True, "blank_rows": 2}

    def taxed(value):
        line = value["calculation"]["lines"][0]
        line["taxes"] = [
            {
                "key": "c",
                "code": "CGST",
                "basis": "1000.0000",
                "amount": "90.0000",
                "supplier_charged": True,
            },
        ]

    html = printed(value_layout, taxed)
    assert 'class="canvas-band canvas-band--grows" style="margin-top:8mm;min-height:60mm"' in html
    assert ">Particulars</th>" in html and ">CGST %</th>" in html
    assert ">9%</td>" in html and "Consulting &amp; support" in html
    assert html.count("<td>&nbsp;</td>") == 8
    assert '<col style="width:100mm">' in html
    # The header repeats on every page the table reaches.
    assert "<thead><tr>" in html


def test_a_table_without_chosen_columns_prints_the_default_set():
    html = printed(designed())
    for heading in ("#", "Description", "Taxable value", "Amount"):
        assert f">{heading}</th>" in html


def test_totals_and_tax_summary_read_the_authoritative_calculation():
    value_layout = designed()
    foot = value_layout["layout_definition"]["sections"][2]["elements"]
    foot[0]["totals_rows"] = ["subtotal", "round_off", "grand_total"]
    foot.append(element("TAX_SUMMARY", 0, 0, 100, 15))
    html = printed(value_layout)
    assert "<dt>Subtotal</dt>" in html and "<dt>Grand total</dt>" in html
    assert "123,456.79" in html or "1,23,456.79" in html
    assert "No tax on this bill" in html


def test_marked_copies_and_pre_printed_stationery():
    value_layout = designed()
    options = value_layout["layout_definition"]["print_options"]
    options.update(
        copies=["ORIGINAL_FOR_RECIPIENT", "DUPLICATE_FOR_TRANSPORTER"],
        copy_mark_position="watermark",
        pre_printed_stationery=True,
    )
    html = printed(value_layout)
    assert html.count('class="canvas-copy"') == 2
    assert "canvas-mark--watermark" in html and "Duplicate for Transporter" in html
    # The letterhead is on the paper: the header zone keeps its space and prints nothing.
    assert "Purchase &lt;bill&gt;" not in html


def test_custom_and_landscape_paper():
    html = printed(
        layout(
            zone("lines", "ITEM_TABLE", 10, 12, 100, 40, element("ITEM_TABLE", 0, 0, 100, 30)),
            paper_size="CUSTOM",
            page_width_mm="120.0000",
            page_height_mm="180.0000",
        )
    )
    assert "size: 120mm 180mm" in html
    html = printed(
        layout(
            zone("lines", "ITEM_TABLE", 10, 12, 100, 40, element("ITEM_TABLE", 0, 0, 100, 30)),
            page_orientation="LANDSCAPE",
        )
    )
    assert "size: 297mm 210mm" in html


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            lambda s: s[0]["elements"].append(element("IMAGE", 0, 0, 10, 10)),
            "has no picture chosen",
        ),
        (lambda s: s[0]["elements"].append(element("QR_CODE", 0, 0, 10, 10)), "QR codes"),
        (
            lambda s: s[0]["elements"].append(
                element("FIELD_BINDING", 0, 0, 10, 5, binding_path="party.gstin")
            ),
            "the field party.gstin",
        ),
        (
            lambda s: s[1]["elements"][0].update(
                columns=[{"key": "batch", "width_mm": 20, "show": True}]
            ),
            # A Purchase bill records no batches (designer plan §8).
            "the Batch column",
        ),
        (lambda s: s[1]["elements"].clear(), "without a line table"),
        (
            lambda s: s[1]["elements"].append(element("ITEM_TABLE", 0, 45, 190, 10)),
            "more than one product table",
        ),
        (
            lambda s: s[2]["elements"].append(
                element("TAX_SUMMARY", 0, 0, 10, 10, tax_grouping="by_hsn")
            ),
            "grouped by HSN",
        ),
        (
            lambda s: s[2]["elements"][0].update(totals_rows=["outstanding_balance"]),
            "outstanding balance total",
        ),
    ],
)
def test_what_purchase_cannot_print_is_named_before_any_browser_starts(change, reason):
    value_layout = designed()
    change(value_layout["layout_definition"]["sections"])
    with pytest.raises(ValidationFailedError, match="custom layout cannot be printed") as refused:
        printed(value_layout)
    assert reason in str(refused.value)
    assert any(reason in message for _, message in problems(value_layout, PURCHASE))


def test_unsupported_paper_is_named():
    found = problems(copy.deepcopy(designed()) | {"paper_size": "A3"}, PURCHASE)
    assert ("head", "Purchase printing does not support a3 paper yet") in found


def test_the_designed_layout_is_accepted_as_it_stands():
    assert problems(designed(), PURCHASE) == []


async def test_the_designer_reads_the_same_manifest(client, prefix):
    assert (await client.get(prefix + "/print-capabilities")).status_code == 401
    denied = await client.get(
        prefix + "/print-capabilities", headers=headers(permissions=frozenset())
    )
    assert denied.status_code == 403
    result = await client.get(prefix + "/print-capabilities", headers=headers())
    assert result.status_code == 200, result.text
    assert result.json()["kinds"] == [PURCHASE]


def test_the_published_contract_file_is_the_manifest():
    """The console's tests read this file; it must be exactly what the service publishes."""
    import json
    from pathlib import Path

    from vouchers.domain.print_capabilities import MANIFEST_VERSION, MANIFESTS

    stored = json.loads(
        (Path(__file__).parents[1] / "contracts/print-capabilities-v2.json").read_text("utf-8")
    )
    assert stored == {"version": MANIFEST_VERSION, "kinds": list(MANIFESTS.values())}


def test_an_accounts_table_prints_each_line_with_its_ledger():
    value_layout = designed()
    value_layout["layout_definition"]["sections"][1]["elements"][0]["type"] = "ACCOUNT_TABLE"

    def ledger(value):
        value["labels"]["ledgers"] = {
            value["document"]["invoice"]["supplies"][0]["line_key"]: "Rent & Co"
        }

    html = printed(value_layout, ledger)
    assert 'aria-label="Purchase accounts and expenses"' in html
    assert ">Account</th>" in html and ">Rent &amp; Co</td>" in html


def test_with_both_tables_goods_and_accounts_print_apart():
    value_layout = designed()
    sections = value_layout["layout_definition"]["sections"]
    sections.insert(
        2, zone("accounts", "CUSTOM", 10, 112, 190, 6, element("ACCOUNT_TABLE", 0, 0, 190, 6))
    )
    sections[3]["y"] = 125

    def two_kinds(value):
        supply = value["document"]["invoice"]["supplies"][0]
        goods = dict(
            supply,
            line_key="01a1a1eb-0000-7000-8000-00000000000a",
            description="Milk",
            supply_kind="GOODS",
            quantity="10.0000",
            rate="100.0000",
        )
        line = dict(value["calculation"]["lines"][0], key=goods["line_key"])
        value["document"]["invoice"]["supplies"].append(goods)
        value["calculation"]["lines"].append(line)
        supply["supply_kind"] = "ACCOUNT"

    html = printed(value_layout, two_kinds)
    products = html.split('aria-label="Purchase products"')[1].split("</table>")[0]
    accounts = html.split('aria-label="Purchase accounts and expenses"')[1].split("</table>")[0]
    assert "Milk" in products and "Consulting" not in products
    assert "Consulting" in accounts and "Milk" not in accounts


def test_two_line_tables_in_one_zone_are_named():
    value_layout = designed()
    value_layout["layout_definition"]["sections"][1]["elements"].append(
        element("ACCOUNT_TABLE", 0, 45, 190, 10)
    )
    assert any(
        "two line tables in the same zone" in reason
        for _, reason in problems(value_layout, PURCHASE)
    )
