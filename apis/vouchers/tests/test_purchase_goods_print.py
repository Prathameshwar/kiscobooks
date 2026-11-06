"""Product and Mixed Purchase bills print what was bought (designer plan §8 R1, 2026-11-04).

A goods line prints its HSN, quantity with its unit, and rate; every bill prints its amount in
words. Quantities and rates come from the saved bill the accepted calculation covers; HSN and
the unit's label come from the owner, under the actor's rights.
"""

import copy
import secrets
from decimal import Decimal

import pytest
from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.display import DisplayConfiguration, number
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.service_auth import CompanyServiceScope
from conftest import COMPANY, SECRET, TENANT
from pydantic import SecretStr
from sqlalchemy import select
from test_canvas_print import designed, element, printed, zone
from test_purchase_goods_capture import goods_bill, stocked
from test_purchase_print import snapshot
from voucher_execution.invoice import InvoiceCalculationDetail, InvoiceInput
from voucher_execution.printing import PrintLine, PurchasePrintFacts
from voucher_execution.transport import ExecutionClient

from vouchers.domain.amount_words import amount_in_words
from vouchers.domain.purchase_print import (
    assemble_snapshot,
    labels_unchanged,
    render_html,
    validate_snapshot,
)
from vouchers.models.printing import VoucherPrintJob
from vouchers.schemas.owners import Owner
from vouchers.tasks import purchase_print

DISPLAY = DisplayConfiguration.model_validate(snapshot()["display"])
GOODS_KEY = "01a1a1eb-0000-7000-8000-00000000000a"


def with_goods(value, *, unit="kg", hsn="0402"):
    """The fixture bill plus one goods line, as assemble_snapshot freezes it."""
    supply = value["document"]["invoice"]["supplies"][0]
    supply |= {"supply_kind": "SERVICE", "hsn_sac": "998313"}
    value["document"]["invoice"]["supplies"].append(
        {
            "line_key": GOODS_KEY,
            "description": "Milk powder 1kg",
            "supply_kind": "GOODS",
            "hsn_sac": hsn,
            "quantity": "12.5000",
            "rate": "80.1250",
        }
    )
    value["calculation"]["lines"].append(
        dict(value["calculation"]["lines"][0], key=GOODS_KEY, entered="1001.5600")
    )
    if unit:
        value["labels"]["units"] = {GOODS_KEY: unit}
    return value


# --- amount in words ---


@pytest.mark.parametrize(
    ("amount", "grouping", "words"),
    [
        ("0", "indian", "Rupees Zero Only"),
        ("1947.00", "indian", "Rupees One Thousand Nine Hundred Forty-Seven Only"),
        (
            "123456.79",
            "indian",
            "Rupees One Lakh Twenty-Three Thousand Four Hundred "
            "Fifty-Six and Seventy-Nine Paise Only",
        ),
        ("25000000", "indian", "Rupees Two Crore Fifty Lakh Only"),
        ("12000000000", "indian", "Rupees One Thousand Two Hundred Crore Only"),
        ("25000000", "western", "Rupees Twenty-Five Million Only"),
        ("100.05", "indian", "Rupees One Hundred and Five Paise Only"),
        ("-12.50", "indian", "Minus Rupees Twelve and Fifty Paise Only"),
    ],
)
def test_an_amount_is_written_out_in_the_companys_grouping(amount, grouping, words):
    config = DISPLAY.model_copy(update={"digit_grouping": grouping})
    assert amount_in_words(Decimal(amount), "INR", config) == words


def test_other_currencies_and_precisions_keep_every_digit():
    assert amount_in_words("10.5", "USD", DISPLAY) == "Dollars Ten and Fifty Cents Only"
    three = DISPLAY.model_copy(update={"amount_precision": 3})
    assert amount_in_words("7.125", "KWD", three) == "KWD Seven Point One Two Five Only"
    whole = DISPLAY.model_copy(update={"amount_precision": 0})
    assert amount_in_words("7.6", "JPY", whole) == "JPY Eight Only"
    with pytest.raises(ValueError):
        amount_in_words("1e30", "INR", DISPLAY)


# --- the standard layout ---


def test_a_goods_bill_prints_hsn_quantity_with_unit_and_rate_on_the_standard_layout():
    html = render_html(with_goods(snapshot()))
    table = html.split('aria-label="Purchase lines"')[1].split("</table>")[0]
    assert "HSN/SAC" in table and "Qty" in table and "Rate" in table
    assert "Base amount" not in table.split("</thead>")[0]
    assert "0402" in table and "998313" in table
    assert "12.500 kg" in table  # the company's quantity places, then the unit
    assert "80.125" in table  # a rate with more places than amounts keeps them
    assert "Rupees One Lakh" in html


def test_standard_mixed_bill_keeps_the_account_lines_entered_amount():
    value = with_goods(snapshot())
    html = render_html(value)
    account_row = next(row for row in html.split("<tr") if "Consulting" in row)
    account = value["calculation"]["lines"][0]
    assert "Base amount" in html
    assert number(account["entered"], DISPLAY) in account_row


def test_standard_goods_prints_its_saved_receiving_references():
    value = with_goods(snapshot())
    key = next(row["line_key"] for row in value["document"]["invoice"]["supplies"] if row["supply_kind"] == "GOODS")
    warehouse, batch, serial = (str(uuid7()) for _ in range(3))
    value["document"]["stock_receipt"] = [{
        "line_key": key, "warehouse_id": warehouse, "bin_id": None,
        "lot_id": batch, "unit_ids": [serial],
    }]
    html = render_html(value)
    assert "Receiving details" in html
    assert warehouse in html and batch in html and serial in html


def test_designed_purchase_can_bind_receiving_details():
    layout = designed()
    layout["layout_definition"]["sections"].append(
        zone("receiving", "CUSTOM", 10, 170, 190, 20,
             element("FIELD_BINDING", 0, 0, 190, 10, binding_path="voucher.receiving_summary"))
    )
    warehouse = str(uuid7())

    def with_receipt(value):
        with_goods(value)
        key = next(row["line_key"] for row in value["document"]["invoice"]["supplies"] if row["supply_kind"] == "GOODS")
        value["document"]["stock_receipt"] = [{"line_key": key, "warehouse_id": warehouse, "bin_id": None, "lot_id": None, "unit_ids": []}]
        return value

    html = printed(layout, with_receipt)
    assert warehouse in html
    assert 'canvas-band canvas-band--grows' in html
    assert 'canvas-zone canvas-zone--grows' in html
    assert 'height:10mm' not in html.split(warehouse)[0].split('canvas-zone canvas-zone--grows')[-1]


def test_receiving_summary_refuses_a_shared_zone():
    layout = designed()
    layout["layout_definition"]["sections"][2]["elements"].append(
        element("FIELD_BINDING", 0, 0, 120, 20, binding_path="voucher.receiving_summary")
    )
    with pytest.raises(ValidationFailedError, match="receiving summary.*own zone"):
        printed(layout)


def test_receiving_summary_refuses_an_overlapping_zone():
    layout = designed()
    layout["layout_definition"]["sections"].extend([
        zone("receiving", "CUSTOM", 10, 170, 190, 20,
             element("FIELD_BINDING", 0, 0, 190, 10, binding_path="voucher.receiving_summary")),
        zone("overlap", "CUSTOM", 10, 175, 190, 10,
             element("TEXT", 0, 0, 100, 5, content="Overlapping note")),
    ])
    with pytest.raises(ValidationFailedError, match="receiving summary.*vertical band"):
        printed(layout)


def test_an_account_bill_keeps_its_base_amount_column():
    html = render_html(snapshot())
    table = html.split('aria-label="Purchase lines"')[1].split("</table>")[0]
    assert "Base amount" in table and "HSN/SAC" not in table
    assert 'class="in-words"' in html


def test_a_goods_line_without_a_readable_unit_prints_its_quantity_alone():
    html = render_html(with_goods(snapshot(), unit=None))
    assert "12.500<" in html.split('aria-label="Purchase lines"')[1]


# --- a designed layout ---


def goods_columns(value_layout, *keys):
    value_layout["layout_definition"]["sections"][1]["elements"][0]["columns"] = [
        {"key": key, "width_mm": 20, "show": True} for key in keys
    ]
    return value_layout


def test_a_designed_table_prints_goods_columns_and_a_dash_for_other_lines():
    value_layout = goods_columns(designed(), "description", "hsn_sac", "quantity", "unit", "rate")
    html = printed(value_layout, with_goods)
    rows = html.split('aria-label="Purchase products"')[1].split("</table>")[0].split("<tr")
    goods = next(row for row in rows if "Milk powder" in row)
    other = next(row for row in rows if "Consulting" in row)
    assert all(text in goods for text in ("0402", "12.500", ">kg<", "80.125"))
    assert "998313" in other and other.count(">—<") == 3


def test_amount_in_words_prints_as_a_field_and_as_a_totals_row():
    value_layout = designed()
    sections = value_layout["layout_definition"]["sections"]
    sections[0]["elements"].append(
        element("FIELD_BINDING", 0, 10, 100, 5, binding_path="totals.amount_in_words")
    )
    sections[2]["elements"][0]["totals_rows"] = ["grand_total", "amount_in_words"]
    html = printed(value_layout)
    assert html.count("Rupees One Lakh Twenty-Three Thousand") == 2
    assert 'class="canvas-words"' in html


# --- the frozen source ---


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["document"]["invoice"]["supplies"][0].update(quantity="1.0000"),
        lambda value: value["document"]["invoice"]["supplies"][1].pop("rate"),
        lambda value: value["document"]["invoice"]["supplies"][1].update(quantity="-1"),
        lambda value: value["document"]["invoice"]["supplies"][1].update(hsn_sac="04<b>"),
        lambda value: value["labels"]["units"].update(
            {value["document"]["invoice"]["supplies"][0]["line_key"]: "kg"}
        ),
        lambda value: value["labels"]["units"].update({GOODS_KEY: "x" * 21}),
    ],
    ids=["account-qty", "no-rate", "negative", "markup-hsn", "unit-on-service", "long-unit"],
)
def test_a_malformed_goods_source_is_refused(change):
    value = with_goods(snapshot())
    change(value)
    with pytest.raises(ValidationFailedError):
        validate_snapshot(value)


def test_a_unit_label_withheld_or_changed_after_generation_stops_delivery():
    frozen = with_goods(snapshot())["labels"]
    assert labels_unchanged(frozen, copy.deepcopy(frozen))
    assert not labels_unchanged(frozen, frozen | {"units": {}})
    assert not labels_unchanged(frozen, frozen | {"units": {GOODS_KEY: "g"}})
    # A label the frozen copy never carried is not compared.
    assert labels_unchanged(frozen | {"units": {}}, frozen)


def facts_for(invoice: InvoiceInput, lines=()) -> PurchasePrintFacts:
    value = snapshot()
    rows = [
        dict(value["calculation"]["lines"][0], key=str(supply.line_key))
        for supply in invoice.supplies
    ]
    return PurchasePrintFacts(
        calculation=InvoiceCalculationDetail.model_validate(value["calculation"] | {"lines": rows}),
        supplier_name="Native supplier",
        source="PREVIEW",
        lines=lines,
    )


def goods_invoice(**changes) -> InvoiceInput:
    from test_invoice_capture import invoice_body

    body = invoice_body()
    body["components"] = []
    body["supplies"][0].update(
        {
            "supply_kind": "GOODS",
            "item_line_key": body["supplies"][0]["line_key"],
            "unit_price": "80.125",
            "quantities": [{"basis": "BILLED", "quantity": "12.5", "unit_id": str(uuid7())}],
        }
        | changes
    )
    return InvoiceInput.model_validate(body)


def test_assembly_freezes_the_saved_quantity_and_rate_and_the_owners_labels():
    invoice = goods_invoice()
    key = invoice.supplies[0].line_key
    value = snapshot()
    frozen = assemble_snapshot(
        document=value["document"] | {"invoice": {}},
        invoice=invoice,
        facts=facts_for(invoice, [PrintLine(key=key, classification_code="0402", unit_label="kg")]),
        display=value["display"],
        layout=value["layout"],
    )
    row = frozen["document"]["invoice"]["supplies"][0]
    assert (row["hsn_sac"], row["quantity"], row["rate"]) == ("0402", "12.5000", "80.1250")
    assert frozen["labels"]["units"] == {str(key): "kg"}


def test_assembly_refuses_owner_lines_for_another_bill_and_goods_without_a_rate():
    invoice = goods_invoice()
    value = snapshot()
    arguments = {
        "document": value["document"] | {"invoice": {}},
        "display": value["display"],
        "layout": value["layout"],
    }
    with pytest.raises(ConflictError, match="do not match"):
        assemble_snapshot(
            invoice=invoice,
            facts=facts_for(invoice, [PrintLine(key=uuid7(), classification_code="0402")]),
            **arguments,
        )
    priceless = goods_invoice(unit_price=None)
    with pytest.raises(ConflictError, match="billed quantity and rate"):
        assemble_snapshot(invoice=priceless, facts=facts_for(priceless), **arguments)


# --- preparation, end to end through the API ---


def configure(app, tmp_path):
    scope = CompanyServiceScope(tenant_id=TENANT, company_id=COMPANY)
    app.state.settings.print_file_root = tmp_path
    app.state.settings.print_broker_url = SecretStr("amqp://127.0.0.1")
    app.state.settings.print_scopes = [scope]
    app.state.settings.execution_owner = Owner(
        owner="accounting",
        origin="http://127.0.0.1",
        key_id="print-test",
        secret=SecretStr(secrets.token_hex(32)),
        scopes=(scope,),
    )


def displayed(*, deny_stock=False):
    result = stocked()
    company = verify_company_context(
        result["X-Company-Context"], result["X-Company-Signature"], SECRET.encode()
    )
    policies = list(company.policies)
    if deny_stock:
        policies.append({
            "entity_type": "vouchers.voucher_item", "field_key": "warehouse_id",
            "access": "read", "effect": "deny", "scope_type": "company",
            "scope_id": str(COMPANY),
        })
    result["X-Company-Context"], result["X-Company-Signature"] = sign_company_context(
        company.model_copy(update={"report_display": DISPLAY, "policies": policies}), SECRET.encode()
    )
    return result


@pytest.mark.parametrize("mixed", [False, True], ids=["product", "mixed"])
@pytest.mark.parametrize("deny_stock", [False, True], ids=["stock-readable", "stock-denied"])
async def test_a_goods_bill_prints_with_its_stock_lines_sent_to_the_owner(
    client, prefix, app, tmp_path, monkeypatch, mixed, deny_stock
):
    created, request = await goods_bill(client, prefix, app, mixed=mixed)
    assert created.status_code == 201, created.text
    saved = created.json()
    configure(app, tmp_path)
    observed = []
    goods_key = request["invoice"]["supplies"][0]["line_key"]

    async def owner(self, command):
        observed.append(command)
        lines = [
            PrintLine(
                key=supply.line_key,
                classification_code="0402" if supply.supply_kind == "GOODS" else "996719",
                unit_label="kg" if supply.supply_kind == "GOODS" else None,
            )
            for supply in command.preview.invoice.supplies
        ]
        return facts_for(command.preview.invoice, lines)

    async def layout(*args):
        return snapshot()["layout"]

    monkeypatch.setattr(ExecutionClient, "purchase_print", owner)
    monkeypatch.setattr(purchase_print, "resolve", layout)
    url = prefix + "/vouchers/" + saved["id"] + "/print-jobs"
    body = {"expected_version": saved["row_version"], "revision_id": saved["revision_id"]}
    result = await client.post(url, headers=displayed(deny_stock=deny_stock), json=body)
    assert result.status_code == 202, result.text
    sent = observed[0].preview
    assert sent.stock is not None and sent.stock.action == "PURCHASE_INVOICE"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            job = await db.scalar(select(VoucherPrintJob))
    supplies = {row["line_key"]: row for row in job.snapshot["document"]["invoice"]["supplies"]}
    assert supplies[goods_key]["quantity"] == "10.0000"
    assert supplies[goods_key]["rate"] == "100.0000"
    assert supplies[goods_key]["hsn_sac"] == "0402"
    assert job.snapshot["labels"]["units"] == {goods_key: "kg"}
    if deny_stock:
        assert "stock_receipt" not in job.snapshot["document"]
    else:
        receipt = job.snapshot["document"]["stock_receipt"]
        assert len(receipt) == 1 and receipt[0]["line_key"] == goods_key
        assert receipt[0]["warehouse_id"] == request["stock"]["lines"][0]["warehouse_id"]
    if mixed:
        service = next(row for key, row in supplies.items() if key != goods_key)
        assert "quantity" not in service and service["hsn_sac"] == "996719"
    assert "10.000 kg" in render_html(job.snapshot)


async def test_a_goods_bill_without_its_stock_lines_is_refused_before_the_owner(
    client, prefix, app, tmp_path, monkeypatch
):
    created, _ = await goods_bill(client, prefix, app, stock=False)
    assert created.status_code == 201, created.text
    saved = created.json()
    configure(app, tmp_path)
    called = []

    async def owner(self, command):
        called.append(command)
        raise AssertionError("the owner must not be asked")

    monkeypatch.setattr(ExecutionClient, "purchase_print", owner)
    result = await client.post(
        prefix + "/vouchers/" + saved["id"] + "/print-jobs",
        headers=displayed(),
        json={"expected_version": saved["row_version"], "revision_id": saved["revision_id"]},
    )
    assert result.status_code == 409
    assert "do not match its stock lines" in result.text
    assert called == []


def test_a_rate_per_more_than_one_unit_prints_its_pricing_unit():
    value = with_goods(snapshot())
    value["document"]["invoice"]["supplies"][1]["per"] = "100.0000"
    html = render_html(value)
    assert "80.125 / 100.000" in html
    value["document"]["invoice"]["supplies"][0]["per"] = "100.0000"
    with pytest.raises(ValidationFailedError, match="pricing unit"):
        validate_snapshot(value)


def test_assembly_freezes_a_pricing_unit_other_than_one():
    invoice = goods_invoice(price_denominator="100")
    value = snapshot()
    frozen = assemble_snapshot(
        document=value["document"] | {"invoice": {}},
        invoice=invoice,
        facts=facts_for(invoice),
        display=value["display"],
        layout=value["layout"],
    )
    assert frozen["document"]["invoice"]["supplies"][0]["per"] == "100.0000"
    plain = goods_invoice()
    frozen = assemble_snapshot(
        document=value["document"] | {"invoice": {}},
        invoice=plain,
        facts=facts_for(plain),
        display=value["display"],
        layout=value["layout"],
    )
    assert "per" not in frozen["document"]["invoice"]["supplies"][0]


def test_a_quantity_finer_than_the_company_places_prints_exactly():
    value = with_goods(snapshot())
    value["display"]["quantity_precision"] = 2
    value["document"]["invoice"]["supplies"][1]["quantity"] = "1.1250"
    assert "1.125 kg" in render_html(value)
    value["document"]["invoice"]["supplies"][1]["quantity"] = "2.5000"
    assert "2.50 kg" in render_html(value)


def test_the_words_round_as_the_printed_total_does():
    even = DisplayConfiguration.model_validate(
        snapshot()["display"] | {"rounding_mode": "half_even"}
    )
    assert amount_in_words("10.125", "INR", even) == "Rupees Ten and Twelve Paise Only"
    assert amount_in_words("10.125", "INR", DISPLAY) == "Rupees Ten and Thirteen Paise Only"
