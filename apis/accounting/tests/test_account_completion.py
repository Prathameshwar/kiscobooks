"""Ledger metadata and every supported duty have complete public lifecycle paths."""

from typing import Any

import httpx
import pytest
from billing_platform.ids import uuid7

from tests.conftest import headers
from tests.test_masters import BASE, activate, post, prepare


@pytest.mark.parametrize(
    ("kind", "group", "profile"),
    [
        ("GENERAL", "INDIRECT_EXPENSES", None),
        ("CASH", "CASH", None),
        ("BANK", "BANKS", "account-bank-profiles"),
        ("TAX", "TAX_PAYABLE", "account-tax-profiles"),
        ("INVENTORY_CONTROL", "STOCK", None),
        ("ASSET_CONTROL", "FIXED_ASSETS", None),
    ],
)
async def test_non_party_account_lifecycle(
    client: httpx.AsyncClient, kind: str, group: str, profile: str | None
) -> None:
    bank_id = uuid7()
    groups = await prepare(client)
    body = {
        "code": "REVIEW-" + kind,
        "name": kind + " review",
        "kind": kind,
        "group_id": groups[group],
        "posting_policy": "SOURCE_ONLY" if kind.endswith("CONTROL") else "MANUAL_ALLOWED",
    }
    row = await post(client, "/accounts", body)
    assert row["kind"] == kind and row["party_id"] is None and row["party_role"] is None
    if kind != "GENERAL":
        wrong_head = await client.post(
            BASE + "/accounts",
            json=body | {"code": "WRONG-" + kind, "group_id": groups["SALES"]},
            headers=headers(),
        )
        assert wrong_head.status_code == 422, wrong_head.text
    if profile:
        blocked = await client.post(
            BASE + "/accounts/" + row["id"] + "/activate",
            json={"expected_version": row["row_version"]},
            headers=headers(),
        )
        assert blocked.status_code == 409, blocked.text
        details = (
            {"company_bank_id": str(bank_id)}
            if kind == "BANK"
            else {
                "duty_type": "OTHER",
                "scheme": "OTHER",
                "component": "OTHER",
                "purpose": "OUTPUT_PAYABLE",
            }
        )
        await post(
            client,
            "/" + profile,
            {"account_id": row["id"]} | details,
            h=headers(bank_ids={bank_id}),
        )
    row = await activate(client, "/accounts", row, h=headers(bank_ids={bank_id}))
    assert row["status"] == "ACTIVE"
    edited = await client.patch(
        BASE + "/accounts/" + row["id"],
        json={"expected_version": row["row_version"], "name": kind + " updated"},
        headers=headers(bank_ids={bank_id}),
    )
    assert edited.status_code == 200, edited.text
    row = edited.json()
    forbidden = await client.patch(
        BASE + "/accounts/" + row["id"],
        json={"expected_version": row["row_version"], "kind": "PARTY"},
        headers=headers(bank_ids={bank_id}),
    )
    assert forbidden.status_code == 409, forbidden.text
    retired = await post(
        client,
        "/accounts/" + row["id"] + "/deactivate",
        {"expected_version": row["row_version"]},
        h=headers(bank_ids={bank_id}),
        status=200,
    )
    assert retired["status"] == "INACTIVE"


async def test_rounding_configuration_currency_precision_and_active_protection(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    body: dict[str, Any] = {
        "code": "ROUNDED",
        "name": "Rounded sales",
        "group_id": groups["SALES"],
        "inventory_affected": True,
        "rounding_method": "NORMAL",
        "rounding_limit": "0.5000",
        "sort_order": 17,
    }
    ledger = await post(client, "/accounts", body)
    assert ledger["rounding_limit"] == "0.5000"
    assert ledger["inventory_affected"] is True and ledger["sort_order"] == 17
    for extra in (
        {"rounding_limit": 0.5},
        {"rounding_limit": "0"},
        {"rounding_limit": "0.12345"},
        {"rounding_method": "NONE"},
        {"rounding_limit": None},
        {"currency_mode": "MULTI"},
        {"sort_order": -1},
        {"inventory_affected": "true"},
    ):
        result = await client.post(
            BASE + "/accounts",
            json=body | {"code": uuid7().hex} | extra,
            headers=headers(features={"multi_currency"}),
        )
        assert result.status_code == 422, result.text
    ledger = await activate(client, "/accounts", ledger)
    for values in (
        {"rounding_method": "UP"},
        {"rounding_limit": "1"},
        {"inventory_affected": False},
    ):
        result = await client.patch(
            BASE + "/accounts/" + ledger["id"],
            json={"expected_version": ledger["row_version"]} | values,
            headers=headers(),
        )
        assert result.status_code == 409, result.text
    result = await client.patch(
        BASE + "/accounts/" + ledger["id"],
        json={"expected_version": ledger["row_version"], "sort_order": 18},
        headers=headers(),
    )
    assert result.status_code == 200, result.text


async def test_all_duties_create_profile_and_activate_with_compatible_registration(
    client: httpx.AsyncClient,
) -> None:
    gst, vat = uuid7(), uuid7()
    registrations: list[dict[str, Any]] = [
        {
            "id": str(identifier),
            "tax_system": system,
            "regime": "regular",
            "valid_from": "2020-01-01",
            "valid_to": None,
        }
        for identifier, system in [(gst, "gst_in"), (vat, "vat")]
    ]
    h = headers(registrations=registrations)
    groups = await prepare(client, h=h)
    for duty, scheme, component, registration in [
        ("GST", "GST_IN", "CGST", str(gst)),
        ("VAT", "VAT", "VAT", str(vat)),
        ("TDS", "OTHER", "OTHER", None),
        ("TCS", "OTHER", "OTHER", None),
        ("CESS", "GST_IN", "CESS", str(gst)),
        ("EXCISE", "OTHER", "OTHER", None),
        ("OTHER", "OTHER", "OTHER", None),
    ]:
        ledger = await post(
            client,
            "/accounts",
            {"code": duty, "name": duty, "group_id": groups["TAX_PAYABLE"], "kind": "TAX"},
            h=headers(registrations=registrations),
        )
        profile = await post(
            client,
            "/account-tax-profiles",
            {
                "account_id": ledger["id"],
                "duty_type": duty,
                "scheme": scheme,
                "component": component,
                "purpose": "OUTPUT_PAYABLE",
                "company_registration_id": registration,
            },
            h=headers(registrations=registrations),
        )
        assert profile["duty_type"] == duty
        assert (
            await activate(client, "/accounts", ledger, h=headers(registrations=registrations))
        )["status"] == "ACTIVE"


async def test_duty_scheme_component_and_registration_conflicts(client: httpx.AsyncClient) -> None:
    groups = await prepare(client)
    ledger = await post(
        client,
        "/accounts",
        {"code": "DUTY", "name": "Duty", "kind": "TAX", "group_id": groups["TAX_PAYABLE"]},
    )
    baseline: dict[str, Any] = {
        "account_id": ledger["id"],
        "duty_type": "TDS",
        "scheme": "OTHER",
        "component": "OTHER",
        "purpose": "OUTPUT_PAYABLE",
    }
    for extra in (
        {"duty_type": "GST"},
        {"duty_type": "VAT"},
        {"component": "CGST"},
        {"scheme": "GST_IN", "component": "CGST", "duty_type": "GST"},
        {"company_registration_id": str(uuid7())},
    ):
        result = await client.post(
            BASE + "/account-tax-profiles", json=baseline | extra, headers=headers()
        )
        assert result.status_code == 422, result.text
    assert (await post(client, "/account-tax-profiles", baseline))["duty_type"] == "TDS"
