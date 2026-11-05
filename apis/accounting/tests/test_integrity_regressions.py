"""Regression coverage for master ownership, dependencies and effective history."""

import datetime as dt
from typing import Any

import httpx
import pytest
from billing_platform.ids import uuid7

from tests.conftest import headers
from tests.test_masters import BASE, activate, party, post, prepare
from tests.test_workflows import party_account, retire_account, roles_of


def day(offset: int) -> str:
    return (dt.date.today() + dt.timedelta(days=offset)).isoformat()


async def patch(
    client: httpx.AsyncClient,
    path: str,
    row: dict[str, Any],
    values: dict[str, Any],
    *,
    h: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.patch(
        BASE + path + "/" + row["id"],
        json={"expected_version": row["row_version"]} | values,
        headers=h or headers(),
    )


async def term_with_line(client: httpx.AsyncClient) -> tuple[dict[str, Any], dict[str, Any]]:
    term = await post(client, "/payment-terms", {"code": "NET30", "name": "Net 30"})
    line = await post(
        client,
        "/payment-term-lines",
        {
            "payment_term_id": term["id"],
            "sequence": 1,
            "percentage": "100",
            "days": 30,
        },
    )
    return await activate(client, "/payment-terms", term), line


async def test_active_term_cannot_lose_its_line_to_another_term(client: httpx.AsyncClient) -> None:
    await prepare(client)
    _, line = await term_with_line(client)
    other = await post(client, "/payment-terms", {"code": "OTHER", "name": "Other"})
    response = await patch(client, "/payment-term-lines", line, {"payment_term_id": other["id"]})
    assert response.status_code == 409, response.text


async def test_term_retirement_preserves_owned_lines(client: httpx.AsyncClient) -> None:
    await prepare(client)
    term, line = await term_with_line(client)
    retired = await post(
        client,
        f'/payment-terms/{term["id"]}/deactivate',
        {"expected_version": term["row_version"]},
        status=200,
    )
    assert retired["status"] == "INACTIVE"
    saved = await client.get(BASE + f'/payment-term-lines/{line["id"]}', headers=headers())
    assert saved.json()["payment_term_id"] == term["id"]


async def test_bank_retirement_preserves_owned_profile(client: httpx.AsyncClient) -> None:
    bank_id = uuid7()
    h = headers(bank_ids={bank_id})
    groups = await prepare(client, h=h)
    bank = await post(
        client,
        "/accounts",
        {
            "code": "BANK",
            "name": "Bank",
            "group_id": groups["BANKS"],
            "kind": "BANK",
        },
        h=h,
    )
    profile = await post(
        client,
        "/account-bank-profiles",
        {
            "account_id": bank["id"],
            "company_bank_id": str(bank_id),
        },
        h=h,
    )
    bank = await activate(client, "/accounts", bank, h=h)
    retired = await post(
        client,
        f'/accounts/{bank["id"]}/deactivate',
        {"expected_version": bank["row_version"]},
        h=h,
        status=200,
    )
    assert retired["status"] == "INACTIVE"
    saved = await client.get(BASE + f'/account-bank-profiles/{profile["id"]}', headers=h)
    assert saved.status_code == 200


async def test_role_identity_cannot_change_under_an_account(client: httpx.AsyncClient) -> None:
    await prepare(client)
    abc = await party(client)
    # The customer role came with its own live account; that account is what pins the role.
    assert (await party_account(client, abc["id"], "CUSTOMER"))["status"] == "ACTIVE"
    role = (await roles_of(client))["CUSTOMER"]
    response = await patch(client, "/party-roles", role, {"role": "OTHER"})
    assert response.status_code == 409, response.text


async def test_commercial_membership_blocks_role_retirement_and_reclassification(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    abc = await party(client)
    commercial = await post(
        client,
        "/party-commercial-types",
        {
            "code": "TRADE",
            "name": "Trade",
            "role": "CUSTOMER",
        },
    )
    commercial = await activate(client, "/party-commercial-types", commercial)
    await post(
        client,
        "/party-commercial-type-memberships",
        {
            "party_id": abc["id"],
            "commercial_type_id": commercial["id"],
            "valid_from": day(1),
        },
    )
    # The role's live account would block its retirement first; retire it so the membership
    # guard is the one under test.
    await retire_account(client, abc["id"], "CUSTOMER")
    role = (await roles_of(client))["CUSTOMER"]
    response = await client.post(
        BASE + f'/party-roles/{role["id"]}/deactivate',
        json={"expected_version": role["row_version"]},
        headers=headers(),
    )
    assert response.status_code == 409, response.text
    assert "commercial memberships" in response.text
    response = await patch(client, "/party-commercial-types", commercial, {"role": "SUPPLIER"})
    assert response.status_code == 409, response.text


async def test_group_head_cannot_change_under_an_active_account(client: httpx.AsyncClient) -> None:
    await prepare(client)
    heads = {
        row["code"]: row["id"]
        for row in (await client.get(BASE + "/account-heads", headers=headers())).json()["items"]
    }
    group = await post(
        client,
        "/account-groups",
        {
            "code": "CUSTOM",
            "name": "Cash group",
            "head_id": heads["ASSET"],
        },
    )
    group = await activate(client, "/account-groups", group)
    account = await post(
        client,
        "/accounts",
        {
            "code": "CASH",
            "name": "Cash",
            "kind": "CASH",
            "group_id": group["id"],
        },
    )
    await activate(client, "/accounts", account)
    response = await patch(client, "/account-groups", group, {"head_id": heads["INCOME"]})
    assert response.status_code == 409, response.text


async def test_expired_history_cannot_be_reopened(client: httpx.AsyncClient) -> None:
    await prepare(client)
    abc = await party(client)
    row = await post(
        client,
        "/party-credit-policies",
        {
            "party_id": abc["id"],
            "limit_amount": "100",
            "currency": "INR",
            "valid_from": day(-10),
            "valid_to": day(-1),
        },
    )
    response = await patch(client, "/party-credit-policies", row, {"valid_to": None})
    assert response.status_code == 409, response.text


async def address_and_registration(
    client: httpx.AsyncClient, start: str, end: str | None
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    abc = await party(client)
    address = await post(
        client,
        "/party-addresses",
        {
            "party_id": abc["id"],
            "label": "Office",
            "mailing_name": "ABC",
            "line1": "1 Road",
            "city": "Mumbai",
            "country_code": "IN",
            "state_code": "IN-MH",
            "postal_code": "400001",
        },
    )
    address = await activate(client, "/party-addresses", address)
    registration = await post(
        client,
        "/party-tax-registrations",
        {
            "party_id": abc["id"],
            "scheme": "GST_IN",
            "registration_number": "27ABCDE1234F1Z0",
            "country_code": "IN",
            "state_code": "IN-MH",
            "valid_from": start,
            "valid_to": end,
        },
    )
    return abc, address, registration


async def test_dependent_interval_must_fit_its_registration(client: httpx.AsyncClient) -> None:
    await prepare(client)
    abc, address, registration = await address_and_registration(client, day(-10), day(-1))
    response = await client.post(
        BASE + "/party-registration-addresses",
        json={
            "party_id": abc["id"],
            "address_id": address["id"],
            "registration_id": registration["id"],
            "valid_from": day(0),
        },
        headers=headers(),
    )
    assert response.status_code == 409, response.text


async def test_registration_cannot_be_shortened_past_its_child_interval(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    abc, address, registration = await address_and_registration(client, day(1), None)
    await post(
        client,
        "/party-registration-addresses",
        {
            "party_id": abc["id"],
            "address_id": address["id"],
            "registration_id": registration["id"],
            "valid_from": day(1),
            "valid_to": day(10),
        },
    )
    response = await patch(client, "/party-tax-registrations", registration, {"valid_to": day(5)})
    assert response.status_code == 409, response.text


async def test_active_use_cannot_retarget_an_inactive_contact(client: httpx.AsyncClient) -> None:
    await prepare(client)
    abc = await party(client)
    active = await post(
        client,
        "/party-contacts",
        {
            "party_id": abc["id"],
            "name": "Active",
            "email": "active@example.test",
        },
    )
    active = await activate(client, "/party-contacts", active)
    inactive = await post(
        client,
        "/party-contacts",
        {
            "party_id": abc["id"],
            "name": "Inactive",
            "email": "inactive@example.test",
        },
    )
    use = await post(
        client,
        "/party-contact-uses",
        {
            "party_id": abc["id"],
            "contact_id": active["id"],
            "purpose": "INVOICING",
        },
    )
    use = await activate(client, "/party-contact-uses", use)
    response = await patch(client, "/party-contact-uses", use, {"contact_id": inactive["id"]})
    assert response.status_code == 409, response.text


@pytest.mark.parametrize("edit", [{"component": "IGST"}, {"purpose": "ADJUSTMENT"}])
async def test_tax_profile_semantics_are_frozen_while_account_is_active(
    client: httpx.AsyncClient, edit: dict[str, Any]
) -> None:
    registration = uuid7()
    h = headers(
        registrations=[
            {
                "id": str(registration),
                "tax_system": "gst_in",
                "regime": "regular",
                "jurisdiction_code": "IN-MH",
                "valid_from": day(-10),
                "valid_to": None,
            }
        ]
    )
    groups = await prepare(client, h=h)
    account = await post(
        client,
        "/accounts",
        {
            "code": "OUTPUT",
            "name": "Output tax",
            "kind": "TAX",
            "group_id": groups["TAX_PAYABLE"],
        },
        h=h,
    )
    profile = await post(
        client,
        "/account-tax-profiles",
        {
            "account_id": account["id"],
            "company_registration_id": str(registration),
            "scheme": "GST_IN",
            "component": "CGST",
            "purpose": "OUTPUT_PAYABLE",
        },
        h=h,
    )
    account = await activate(client, "/accounts", account, h=h)
    await post(
        client,
        "/posting-mappings",
        {
            "purpose": "OUTPUT_CGST",
            "company_registration_id": str(registration),
            "account_id": account["id"],
            "currency": "INR",
            "valid_from": day(0),
        },
        h=h,
    )
    response = await patch(client, "/account-tax-profiles", profile, edit, h=h)
    assert response.status_code == 409, response.text


async def test_mapping_interval_must_fit_company_registration(client: httpx.AsyncClient) -> None:
    registration = uuid7()
    valid = {
        "id": str(registration),
        "tax_system": "gst_in",
        "regime": "regular",
        "jurisdiction_code": "IN-MH",
        "valid_from": day(-10),
        "valid_to": day(-1),
    }
    h = headers(registrations=[valid])
    await prepare(client, h=h)
    cash = next(
        row
        for row in (await client.get(BASE + "/accounts", headers=h)).json()["items"]
        if row["system_key"] == "account.CASH_MAIN"
    )
    response = await client.post(
        BASE + "/posting-mappings",
        json={
            "purpose": "CASH_RECEIPT",
            "company_registration_id": str(registration),
            "account_id": cash["id"],
            "currency": "INR",
            "valid_from": day(0),
        },
        headers=h,
    )
    assert response.status_code == 409, response.text
