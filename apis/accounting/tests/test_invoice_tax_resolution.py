"""Version-two line tax facts use owner masters and legal dates, never caller rates."""

import datetime as dt
from decimal import Decimal

import httpx
import pytest
from billing_platform.ids import uuid7
from voucher_execution.invoice import InvoicePreviewCommand

from tests.conftest import COMPANY, TENANT, USER
from tests.test_invoice_preview import authority, connection
from tests.test_openings_sources import party_accounts
from tests.test_tax_mappings import register
from tests.test_voucher_tax import MH, START, tax_head, world


async def test_native_service_rates_discounts_line_dates_and_rcm_credit_evidence(client, app):
    data = await world(client, app)
    # A calculation is offered only when it can post, so pending input credit needs its mapping.
    await tax_head(client, data["groups"], "PENDING_IGST", MH)
    party, customer, supplier = await party_accounts(client)
    delegated, company = authority(registrations=[MH])
    line_key = str(uuid7())
    command = InvoicePreviewCommand.model_validate(
        {
            "tenant_id": TENANT,
            "company_id": COMPANY,
            "actor_user_id": USER,
            "authority": delegated,
            "kind": "SALES",
            "currency": "INR",
            "document_date": "2026-04-05",
            "posting_date": "2026-05-05",
            "configuration_hash": "a" * 64,
            "company_configuration_hash": company.finance.configuration_hash,
            "policy": {"manual_discounts_allowed": True},
            "invoice": {
                "party_line_key": uuid7(),
                "party_account_id": customer["id"],
                "party_account_version": customer["row_version"],
                "bill_reference": "SERVICE-GST-1",
                "due_date": "2026-05-31",
                "tax": {
                    "profile": "INDIA_DOMESTIC_SERVICE",
                    "company_registration_id": MH["id"],
                    "place_of_supply": "IN-MH",
                    "service_completion_date": "2026-04-02",
                },
                "supplies": [
                    {
                        "line_key": line_key,
                        "account_id": data["income"]["id"],
                        "account_version": data["income"]["row_version"],
                        "supply_kind": "SERVICE",
                        "description": "Taxable services",
                        "amount": "1000",
                    }
                ],
                "components": [
                    {
                        "component_key": uuid7(),
                        "purpose": "DISCOUNT",
                        "scope": "LINE",
                        "effect": "DEDUCT",
                        "input_kind": "PERCENT",
                        "value": "10",
                        "targets": [line_key],
                        "source_evidence": "Agreed at supply",
                    }
                ],
            },
        }
    )
    transport = connection(client, app)

    async def preview(body):
        try:
            return await transport.preview(body)
        except httpx.HTTPStatusError as error:
            pytest.fail(error.response.text)

    result = await preview(command)
    assert result.payable == Decimal("1062") and result.commercial_total == 900
    assert {r.code: r.amount for r in result.lines[0].taxes} == {"CGST": 81, "SGST": 81}
    assert result.tax_evidence[0]["tax_point"]["tax_point_date"] == "2026-04-05"
    assert result.tax_evidence[0]["credit_state"] == "NOT_APPLICABLE"
    assert result.tax_evidence[0]["rule_version"] > 0
    assert result.tax_evidence[0]["components"][0]["source_version"] > 0
    late = command.model_copy(update={"document_date": dt.date(2026, 5, 5)})
    late_result = await preview(late)
    assert late_result.tax_evidence[0]["tax_point"]["tax_point_date"] == "2026-04-02"
    assert late_result.tax_evidence[0]["tax_point"]["legal_basis"] == "CGST_13_2_B"
    assert late_result.calculation_hash != result.calculation_hash
    interstate = command.invoice.supplies[0].model_copy(
        update={"tax": command.invoice.tax.model_copy(update={"place_of_supply": "IN-KA"})}
    )
    other = command.model_copy(
        update={"invoice": command.invoice.model_copy(update={"supplies": (interstate,)})}
    )
    assert [r.code for r in (await preview(other)).lines[0].taxes] == ["IGST"]

    for tax, expected in (
        (command.invoice.tax.model_copy(update={"profile": "UNTAXED_ACCOUNT"}), 422),
        (command.invoice.tax.model_copy(update={"company_registration_id": uuid7()}), 422),
        (command.invoice.tax.model_copy(update={"payment_date": dt.date(2026, 4, 1)}), 422),
        (command.invoice.tax.model_copy(update={"service_completion_date": None}), 422),
        (command.invoice.tax.model_copy(update={"profile": "INDIA_DOMESTIC_SERVICE_RCM"}), 422),
        (command.invoice.tax.model_copy(update={"withholding_section_id": uuid7()}), 409),
    ):
        with pytest.raises(httpx.HTTPStatusError) as error:
            await transport.preview(
                command.model_copy(
                    update={"invoice": command.invoice.model_copy(update={"tax": tax})}
                )
            )
        assert error.value.response.status_code == expected, error.value.response.text

    gstin = await register(
        client,
        party["id"],
        {
            "registration_type": "REGULAR",
            "registration_number": "24ABCDE1234F1Z6",
            "state_code": "IN-GJ",
            "valid_from": START,
        },
    )
    assert gstin.status_code == 201, gstin.text
    purchase = command.model_dump(mode="json")
    purchase["kind"] = "PURCHASE"
    purchase["invoice"].update(
        party_account_id=supplier["id"], party_account_version=supplier["row_version"]
    )
    purchase["invoice"]["tax"].update(
        profile="INDIA_DOMESTIC_SERVICE_RCM",
        party_registration_id=gstin.json()["id"],
        supplier_invoice_date="2026-04-01",
        supplier_invoice_number="SUP-1",
    )
    purchase["invoice"]["supplies"][0].update(
        account_id=data["rcm"]["id"], account_version=data["rcm"]["row_version"]
    )
    rcm = await preview(InvoicePreviewCommand.model_validate(purchase))
    assert rcm.payable == 900 and rcm.tax_total == 162 and rcm.charged_tax_total == 0
    assert rcm.tax_evidence[0]["tax_point"]["tax_point_date"] == "2026-06-01"
    assert rcm.tax_evidence[0]["credit_state"] == "PENDING_EVIDENCE"
    purchase["invoice"]["supplies"][0].update(
        account_id=data["blocked"]["id"], account_version=data["blocked"]["row_version"]
    )
    assert (await preview(InvoicePreviewCommand.model_validate(purchase))).tax_evidence[0][
        "credit_state"
    ] == "INELIGIBLE"
