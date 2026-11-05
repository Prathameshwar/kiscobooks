"""B24: a Purchase bill's goods lines are taxed from their item's HSN bundle and costed.

Owner decisions 2026-11-03: the bill adds stock at landed cost; freight and other charges
on goods, and GST that cannot be claimed, are capitalised by value.
"""

from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from voucher_execution.invoice import InvoicePreviewCommand
from voucher_execution.stock_facts import ItemPurchaseTaxFact, StockItemFact

from accounting.models.masters import Account
from accounting.tasks import invoice_goods
from tests.conftest import COMPANY, TENANT, USER
from tests.test_catalog_tax_replica import classification_event, deliver
from tests.test_invoice_preview import authority, connection
from tests.test_openings_sources import party_accounts
from tests.test_stock_effects import configure
from tests.test_stock_ledger import item, warehouse
from tests.test_tax_mappings import register
from tests.test_voucher_tax import MH, START, tax_head, world

DAY = "2026-04-10"


async def goods_world(
    client, app, monkeypatch, *, supplier_state="IN-MH", registered=True, finalize_zero=False
):
    data = await world(client, app)
    for purpose in ("PENDING_CGST", "PENDING_SGST", "PENDING_IGST"):
        await tax_head(client, data["groups"], purpose, MH)
    accounts = await configure(app, finalize_zero=finalize_zero)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            inventory = await db.scalar(
                select(Account).where(Account.id == accounts["inventory_account_id"])
            )
    classification = uuid7()
    assert await deliver(
        app,
        classification_event(classification, 1, code="0402", code_system="HSN", item_kind="GOODS"),
    )
    party, _, supplier = await party_accounts(client)
    gstin = await register(
        client,
        party["id"],
        {
            "registration_type": "REGULAR",
            "registration_number": "27ABCDE1234F1Z0"
            if supplier_state == "IN-MH"
            else "24ABCDE1234F1Z6",
            "state_code": supplier_state,
            "valid_from": START,
        },
    )
    assert gstin.status_code == 201, gstin.text
    location = warehouse()
    tax = ItemPurchaseTaxFact(
        classification_id=classification,
        classification_version=1,
        code="0402",
        rule_id=data["goods_rule"],
        rule_version=1,
        treatment="TAXABLE",
    )

    def product(**changes):
        base = item()
        return StockItemFact.model_validate(
            base.model_dump()
            | {
                "warehouse_permissions": (
                    {
                        "warehouse_id": location.warehouse_id,
                        "allowed_operations": location.allowed_operations,
                    },
                ),
                "purchase_tax": tax,
            }
            | changes
        )

    milk, ghee = product(), product()
    catalog = {milk.item_id: milk, ghee.item_id: ghee}

    async def acquired(settings, command, *, labels=False):
        if command.stock is None:
            return None
        # Catalog answers the base unit's symbol only when a print asks for labels.
        return invoice_goods.GoodsFacts(
            {line.line_id: line for line in command.stock.lines},
            {
                line.item_id: catalog[line.item_id].model_copy(
                    update={"base_unit_label": "kg" if labels else None}
                )
                for line in command.stock.lines
            },
            {location.warehouse_id: location},
        )

    monkeypatch.setattr(invoice_goods, "acquire", acquired)
    delegated, company = authority(registrations=[MH] if registered else [])
    return {
        "data": data,
        "inventory": inventory,
        "supplier": supplier,
        "gstin": gstin.json()["id"],
        "milk": milk,
        "ghee": ghee,
        "catalog": catalog,
        "location": location,
        "authority": delegated,
        "company": company,
    }


def goods_line(product, location, quantity, rate, inventory, **changes):
    key = str(uuid7())
    supply = {
        "line_key": key,
        "item_line_key": key,
        "account_id": str(inventory.id),
        "account_version": inventory.row_version,
        "supply_kind": "GOODS",
        "description": "Goods",
        "amount": str(Decimal(quantity) * Decimal(rate)),
        "unit_price": rate,
        "quantities": [
            {"basis": "BILLED", "quantity": quantity, "unit_id": str(product.base_unit_id)}
        ],
    } | changes
    stock = {
        "line_id": key,
        "item_id": str(product.item_id),
        "warehouse_id": str(location.warehouse_id),
        "quantity": quantity,
    }
    return supply, stock


def bill(w, lines, *, components=(), profile="INDIA_DOMESTIC_GOODS"):
    tax = (
        {
            "profile": profile,
            "company_registration_id": MH["id"],
            "party_registration_id": w["gstin"],
            "place_of_supply": "IN-MH",
            "supplier_invoice_number": "SUP-GOODS-1",
            "supplier_invoice_date": DAY,
        }
        if profile == "INDIA_DOMESTIC_GOODS"
        else {"profile": profile}
    )
    return InvoicePreviewCommand.model_validate(
        {
            "tenant_id": TENANT,
            "company_id": COMPANY,
            "actor_user_id": USER,
            "authority": w["authority"],
            "kind": "PURCHASE",
            "currency": "INR",
            "document_date": DAY,
            "posting_date": DAY,
            "configuration_hash": "a" * 64,
            "company_configuration_hash": w["company"].finance.configuration_hash,
            "policy": {"manual_discounts_allowed": True, "charges_allowed": True},
            "invoice": {
                "party_line_key": uuid7(),
                "party_account_id": w["supplier"]["id"],
                "party_account_version": w["supplier"]["row_version"],
                "bill_reference": "SUP-GOODS-1",
                "due_date": "2026-05-10",
                "tax": tax,
                "supplies": [supply for supply, _ in lines],
                "components": list(components),
            },
            "stock": {
                "action": "PURCHASE_INVOICE",
                "stock_date": DAY,
                "currency": "INR",
                "reason": "Supplier bill SUP-GOODS-1",
                "lines": [stock for _, stock in lines],
            },
        }
    )


def freight(targets, **changes):
    return {
        "component_key": str(uuid7()),
        "purpose": "FREIGHT",
        "scope": "SELECTED_LINES",
        "effect": "ADD",
        "input_kind": "FIXED",
        "value": "150",
        "targets": targets,
        "source_evidence": "Freight on the supplier bill",
    } | changes


async def calculated(client, app, command):
    try:
        return await connection(client, app).preview(command)
    except httpx.HTTPStatusError as error:
        pytest.fail(error.response.text)


async def refused(client, app, command):
    with pytest.raises(httpx.HTTPStatusError) as error:
        await connection(client, app).preview(command)
    return error.value.response


async def test_intra_state_goods_charges_and_non_claimable_gst_are_landed_into_cost(
    client, app, monkeypatch
):
    w = await goods_world(client, app, monkeypatch)
    milk = goods_line(w["milk"], w["location"], "10", "100", w["inventory"])
    ghee = goods_line(
        w["ghee"],
        w["location"],
        "5",
        "100",
        w["inventory"],
        input_credit="INELIGIBLE",
        input_credit_reason="Used for the staff canteen",
    )
    command = bill(
        w, [milk, ghee], components=[freight([milk[0]["line_key"], ghee[0]["line_key"]])]
    )
    result = await calculated(client, app, command)
    lines = {str(row.key): row for row in result.lines}
    a, b = lines[milk[0]["line_key"]], lines[ghee[0]["line_key"]]
    assert {tax.code: tax.amount for tax in a.taxes} == {
        "CGST": Decimal("99"),
        "SGST": Decimal("99"),
    }
    assert {tax.code: tax.amount for tax in b.taxes} == {
        "CGST": Decimal("49.5"),
        "SGST": Decimal("49.5"),
    }
    # Freight 150 by value: 100 to milk (1000) and 50 to ghee (500); ghee's GST is capitalised.
    assert a.stock_cost == Decimal("1100") and b.stock_cost == Decimal("649")
    assert result.payable == Decimal("1947")
    assert all(isinstance(value, Decimal) for value in (a.stock_cost, b.stock_cost, result.payable))
    evidence = {row["line_key"]: row for row in result.tax_evidence}
    assert evidence[milk[0]["line_key"]]["hsn"] == "0402"
    assert evidence[milk[0]["line_key"]]["credit_state"] == "PENDING_EVIDENCE"
    assert evidence[ghee[0]["line_key"]]["credit_state"] == "INELIGIBLE"
    assert evidence[ghee[0]["line_key"]]["input_credit_reason"] == "Used for the staff canteen"
    # A service line on the same bill is unaffected and carries no stock cost.
    assert "stock_cost" not in {
        key for key, value in a.model_dump(mode="json").items() if value is None
    }


async def test_inter_state_goods_take_igst(client, app, monkeypatch):
    w = await goods_world(client, app, monkeypatch, supplier_state="IN-GJ")
    milk = goods_line(w["milk"], w["location"], "10", "100", w["inventory"])
    # A Gujarat supplier delivering into Maharashtra: the place of supply is the buyer's state.
    result = await calculated(client, app, bill(w, [milk]))
    assert [(tax.code, tax.amount) for tax in result.lines[0].taxes] == [("IGST", Decimal("180"))]
    assert result.lines[0].stock_cost == Decimal("1000")


async def test_a_company_without_gst_registration_bills_goods_untaxed_at_their_price(
    client, app, monkeypatch
):
    w = await goods_world(client, app, monkeypatch, registered=False)
    milk = goods_line(w["milk"], w["location"], "10", "118", w["inventory"])
    result = await calculated(client, app, bill(w, [milk], profile="UNTAXED_ACCOUNT"))
    assert result.tax_total == 0 and result.lines[0].stock_cost == Decimal("1180")


async def test_goods_refusals_name_what_to_fix(client, app, monkeypatch):
    w = await goods_world(client, app, monkeypatch)
    milk = goods_line(w["milk"], w["location"], "10", "100", w["inventory"])
    expense = w["data"]["stock"]
    wrong_account = goods_line(
        w["milk"],
        w["location"],
        "10",
        "100",
        w["inventory"],
        account_id=expense["id"],
        account_version=expense["row_version"],
    )
    response = await refused(client, app, bill(w, [wrong_account]))
    assert response.status_code == 422 and "inventory account" in response.text
    charged = freight(
        [milk[0]["line_key"]], account_id=expense["id"], account_version=expense["row_version"]
    )
    response = await refused(client, app, bill(w, [milk], components=[charged]))
    assert response.status_code == 422 and "part of their cost" in response.text
    response = await refused(client, app, bill(w, [milk], profile="UNTAXED_ACCOUNT"))
    assert response.status_code == 422 and "GST profile" in response.text
    w["catalog"][w["milk"].item_id] = w["milk"].model_copy(update={"purchase_tax": None})
    response = await refused(client, app, bill(w, [milk]))
    assert response.status_code == 422 and "HSN classification and GST rule" in response.text
    w["catalog"][w["milk"].item_id] = w["milk"].model_copy(update={"status": "DISCONTINUED"})
    response = await refused(client, app, bill(w, [milk]))
    assert response.status_code == 409 and "activate the product" in response.text
    w["catalog"][w["milk"].item_id] = w["milk"]
    wrong_quantity = goods_line(w["milk"], w["location"], "10", "100", w["inventory"])
    wrong_quantity[1]["quantity"] = "9"
    response = await refused(client, app, bill(w, [wrong_quantity]))
    assert response.status_code == 422 and "base unit" in response.text


def test_a_goods_command_must_send_one_stock_line_per_goods_supply():
    w = {
        "authority": authority(registrations=[MH])[0],
        "company": authority(registrations=[MH])[1],
        "supplier": {"id": str(uuid7()), "row_version": 1},
        "gstin": str(uuid7()),
    }
    product, location = item(), warehouse()
    inventory = type("Account", (), {"id": uuid7(), "row_version": 1})()
    supply, stock = goods_line(product, location, "1", "1", inventory)
    body = bill(w, [(supply, stock)]).model_dump(mode="json")
    body["stock"]["lines"][0]["line_id"] = str(uuid7())
    with pytest.raises(ValueError, match="exactly one stock line"):
        InvoicePreviewCommand.model_validate(body)
