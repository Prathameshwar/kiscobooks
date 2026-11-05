import datetime as dt
from typing import Any, cast

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models.masters import PartyBankAccount
from tests.conftest import COMPANY, TENANT, headers

BASE = f"/v1/companies/{COMPANY}"


async def post(
    client: httpx.AsyncClient,
    path: str,
    body: dict[str, Any],
    *,
    h: dict[str, str] | None = None,
    status: int = 201,
) -> dict[str, Any]:
    authority = h or headers()
    for _ in range(3):
        response = await client.post(BASE + path, json=body, headers=authority)
        if (
            response.status_code != 409
            or response.json().get("error", {}).get("message")
            != "request is busy; retry with the same idempotency key"
        ):
            break
    assert response.status_code == status, response.text
    return cast(dict[str, Any], response.json())


async def prepare(client: httpx.AsyncClient, *, h: dict[str, str] | None = None) -> dict[str, str]:
    await post(client, "/accounting-setup/initialize", {}, h=h, status=200)
    result = await post(
        client, "/accounting-setup/install", {"business_accounts": True}, h=h, status=200
    )
    # Initialization already created the fixed business chart. Install reuses it.
    assert result["groups_created"] == 0
    assert result["accounts_created"] == 0
    groups = (await client.get(BASE + "/account-groups", headers=h or headers())).json()["items"]
    return {row["code"]: row["id"] for row in groups}


async def activate(
    client: httpx.AsyncClient, path: str, row: dict[str, Any], *, h: dict[str, str] | None = None
) -> dict[str, Any]:
    return await post(
        client,
        path + "/" + row["id"] + "/activate",
        {"expected_version": row["row_version"]},
        h=h,
        status=200,
    )


async def new_party(
    client: httpx.AsyncClient,
    *,
    code: str = "ABC",
    role: str = "SUPPLIER",
    h: dict[str, str] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """An active party in one role, with that role's account: the only way a test creates a party.

    `fields` override the identity (name, legal_name, country_code, party_type, notes) and may
    carry `ledger`, `address`, `contact` or `tax_registration`. Needs `prepare` first.
    """
    body = {
        "code": code,
        "name": f"{code} Traders",
        "legal_name": f"{code} Traders Limited",
        "country_code": "IN",
        "role": role,
    } | fields
    return await post(client, "/parties/create-with-details", body, h=h)


async def party_accounts(
    client: httpx.AsyncClient, party_id: str, *, h: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """The party's accounts in full detail (the list item has no `party_role`), by code."""
    authority = h or headers()
    page = await client.get(BASE + "/accounts", headers=authority, params={"party_id": party_id})
    assert page.status_code == 200, page.text
    rows = []
    for item in page.json()["items"]:
        detail = await client.get(BASE + "/accounts/" + item["id"], headers=authority)
        assert detail.status_code == 200, detail.text
        rows.append(detail.json())
    return sorted(rows, key=lambda row: str(row["code"]))


async def party(client: httpx.AsyncClient, *, h: dict[str, str] | None = None) -> dict[str, Any]:
    """An active party with both commercial roles, each active with its own account.

    A party never exists without its account (docs/party-ledger-mandatory-plan.md): the
    customer role arrives with the party, the supplier role is added and activated after it, and
    each activation creates that role's account ("ABC" and "ABC-SUPP"). Needs `prepare` first.
    """
    row = await post(
        client,
        "/parties/create-with-details",
        {
            "code": "ABC",
            "name": "ABC Traders",
            "legal_name": "ABC Traders Limited",
            "country_code": "IN",
            "role": "CUSTOMER",
        },
        h=h,
    )
    item = await post(client, "/party-roles", {"party_id": row["id"], "role": "SUPPLIER"}, h=h)
    await activate(client, "/party-roles", item, h=h)
    return row


async def test_account_list_filters_code_order_and_bound_cursor(client: httpx.AsyncClient) -> None:
    await prepare(client)
    h = headers()
    path = BASE + "/accounts"
    first = await client.get(
        path, headers=h, params={"sort": "code", "limit": 1, "currency_mode": "BASE"}
    )
    assert first.status_code == 200, first.text
    assert first.json()["page"]["has_more"]
    assert first.json()["items"][0]["code"]
    assert first.json()["items"][0]["currency_mode"] == "BASE"
    cursor = first.json()["page"]["next_cursor"]
    second = await client.get(
        path,
        headers=h,
        params={"sort": "code", "limit": 1, "currency_mode": "BASE", "cursor": cursor},
    )
    assert second.status_code == 200, second.text
    assert first.json()["items"][0]["code"] < second.json()["items"][0]["code"]
    changed_filter = await client.get(
        path, headers=h, params={"sort": "code", "limit": 1, "cursor": cursor}
    )
    assert changed_filter.status_code == 422
    assert (await client.get(path, headers=h, params={"sort": "-code"})).status_code == 200
    assert (await client.get(path, headers=h, params={"currency": "USD"})).json()["items"] == []
    assert (await client.get(path, headers=h, params={"currency": "US"})).status_code == 422
    assert (await client.get(path, headers=h, params={"q": "A"})).status_code == 422
    denied = headers(
        policies=[
            {
                "entity_type": "accounting.account",
                "field_key": "currency_mode",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
                "condition": None,
            }
        ]
    )
    assert (
        await client.get(path, headers=denied, params={"currency_mode": "BASE"})
    ).status_code == 403


async def test_shared_party_accounts_details_terms_and_credit(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    abc = await party(client)
    pid = abc["id"]
    # The party arrives with one active account per role (docs/party-ledger-mandatory-plan.md):
    # nothing in this test creates them, and a second one for a role is refused.
    ledgers = {row["party_role"]: row for row in await party_accounts(client, pid)}
    assert {role: (row["code"], row["status"]) for role, row in ledgers.items()} == {
        "CUSTOMER": ("ABC", "ACTIVE"),
        "SUPPLIER": ("ABC-SUPP", "ACTIVE"),
    }
    assert {role: row["group_id"] for role, row in ledgers.items()} == {
        "CUSTOMER": groups["DEBTORS"],
        "SUPPLIER": groups["CREDITORS"],
    }
    for role, group in [("CUSTOMER", "DEBTORS"), ("SUPPLIER", "CREDITORS")]:
        duplicate = await client.post(
            BASE + "/accounts",
            json={
                "code": "SECOND-" + role,
                "name": "ABC second " + role,
                "group_id": groups[group],
                "kind": "PARTY",
                "party_id": pid,
                "party_role": role,
            },
            headers=headers(),
        )
        assert duplicate.status_code == 409, duplicate.text
        assert duplicate.json()["error"]["message"] == (
            "this party already has an account for this role"
        )
    address = await post(
        client,
        "/party-addresses",
        {
            "party_id": pid,
            "label": "Head Office",
            "mailing_name": "ABC",
            "line1": "1 Example Road",
            "city": "Mumbai",
            "country_code": "IN",
            "state_code": "IN-MH",
            "postal_code": "400001",
        },
    )
    address = await activate(client, "/party-addresses", address)
    for purpose in ("BILLING", "SHIPPING"):
        use = await post(
            client,
            "/party-address-uses",
            {"party_id": pid, "address_id": address["id"], "purpose": purpose, "is_default": True},
        )
        await activate(client, "/party-address-uses", use)
    contact = await post(
        client,
        "/party-contacts",
        {"party_id": pid, "name": "Accounts Office", "email": "accounts@example.test"},
    )
    contact = await activate(client, "/party-contacts", contact)
    use = await post(
        client,
        "/party-contact-uses",
        {"party_id": pid, "contact_id": contact["id"], "purpose": "INVOICING", "is_default": True},
    )
    await activate(client, "/party-contact-uses", use)
    start = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    registration = await post(
        client,
        "/party-tax-registrations",
        {
            "party_id": pid,
            "scheme": "GST_IN",
            "registration_number": "27ABCDE1234F1Z0",
            "country_code": "IN",
            "state_code": "IN-MH",
            "valid_from": start,
        },
    )
    await post(
        client,
        "/party-identifiers",
        {
            "party_id": pid,
            "scheme": "PAN",
            "value": "ABCDE1234F",
            "country_code": "IN",
            "valid_from": start,
        },
    )
    await post(
        client,
        "/party-registration-addresses",
        {
            "party_id": pid,
            "registration_id": registration["id"],
            "address_id": address["id"],
            "valid_from": start,
        },
    )
    term = await post(client, "/payment-terms", {"code": "NET30", "name": "Net 30"})
    await post(
        client,
        "/payment-term-lines",
        {"payment_term_id": term["id"], "sequence": 1, "percentage": "100", "days": 30},
    )
    term = await activate(client, "/payment-terms", term)
    await post(
        client,
        "/party-accounting-policies",
        {
            "party_id": pid,
            "role": "CUSTOMER",
            "payment_term_id": term["id"],
            "settlement_currency": "INR",
            "valid_from": start,
        },
    )
    await post(
        client,
        "/party-credit-policies",
        {"party_id": pid, "limit_amount": "100000.0000", "currency": "INR", "valid_from": start},
    )
    classification = await post(
        client,
        "/party-commercial-types",
        {"code": "WHOLESALE", "name": "Wholesale", "role": "CUSTOMER"},
    )
    classification = await activate(client, "/party-commercial-types", classification)
    await post(
        client,
        "/party-commercial-type-memberships",
        {"party_id": pid, "commercial_type_id": classification["id"], "valid_from": start},
    )
    bank = await post(
        client,
        "/party-bank-accounts",
        {
            "party_id": pid,
            "label": "Primary",
            "beneficiary_name": "ABC Traders",
            "bank_name": "Example Bank",
            "country_code": "IN",
            "currency": "INR",
            "account_number": "123456789012",
        },
    )
    assert bank["account_number_last4"] == "9012"
    assert "account_number" not in bank and "account_number_ciphertext" not in bank
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            record = await db.scalar(select(PartyBankAccount))
            assert b"123456789012" not in record.account_number_ciphertext
            events = list(await db.scalars(select(Outbox)))
            assert "Example Road" not in str([row.payload for row in events])
            assert "123456789012" not in str([row.payload for row in events])


async def test_templates_gst_idempotency_and_conflicts(client: httpx.AsyncClient) -> None:
    registration = uuid7()
    h = headers(
        registrations=[
            {
                "id": str(registration),
                "tax_system": "gst_in",
                "regime": "regular",
                "jurisdiction_code": "IN-MH",
                "valid_from": "2020-01-01",
                "valid_to": None,
            }
        ]
    )
    await post(client, "/accounting-setup/initialize", {}, h=h, status=200)
    selection = {
        "business_accounts": True,
        "gst_registration_id": str(registration),
        "local_component": "SGST",
    }
    preview = await post(client, "/accounting-setup/preview", selection, h=h, status=200)
    assert len(preview["groups"]) == 29 and len(preview["accounts"]) == 28
    installed = await post(client, "/accounting-setup/install", selection, h=h, status=200)
    assert installed["groups_created"] == 1 and installed["accounts_created"] == 6
    again = await post(client, "/accounting-setup/install", selection, h=h, status=200)
    assert again == installed
    repeat = await post(
        client,
        "/accounting-setup/install",
        selection,
        h=headers(
            registrations=[
                {
                    "id": str(registration),
                    "tax_system": "gst_in",
                    "regime": "regular",
                    "valid_from": "2020-01-01",
                    "valid_to": None,
                }
            ]
        ),
        status=200,
    )
    assert repeat["accounts_created"] == 0
    result = await client.post(
        BASE + "/accounting-setup/install",
        json={"gst_registration_id": str(registration), "local_component": "SGST"},
        headers=headers(),
    )
    assert result.status_code == 422


async def test_scope_policy_paging_and_conflicts(client: httpx.AsyncClient) -> None:
    groups = await prepare(client)
    abc = await party(client)
    other = uuid7()
    result = await client.get(
        f'/v1/companies/{other}/parties/{abc["id"]}', headers=headers(company=other)
    )
    assert result.status_code == 403
    result = await client.get(BASE + "/parties/" + abc["id"], headers=headers(tenant=uuid7()))
    assert result.status_code == 404
    policy: dict[str, Any] = {
        "entity_type": "accounting.party",
        "field_key": "legal_name",
        "access": "read",
        "effect": "deny",
        "scope_type": "company",
        "scope_id": str(COMPANY),
        "condition": None,
    }
    result = await client.get(BASE + "/parties/" + abc["id"], headers=headers(policies=[policy]))
    assert result.status_code == 200 and "legal_name" not in result.json()
    policy["access"] = "write"
    result = await client.patch(
        BASE + "/parties/" + abc["id"],
        json={"expected_version": abc["row_version"], "legal_name": "Changed"},
        headers=headers(policies=[policy]),
    )
    assert result.status_code == 403, result.text
    result = await client.patch(
        BASE + "/parties/" + abc["id"],
        json={"expected_version": 99, "name": "Changed"},
        headers=headers(),
    )
    assert result.status_code == 409
    page = await client.get(BASE + "/account-groups?limit=2", headers=headers())
    assert page.status_code == 200, page.text
    cursor = page.json()["page"]["next_cursor"]
    following = await client.get(
        BASE + "/account-groups", params={"limit": 2, "cursor": cursor}, headers=headers()
    )
    assert following.status_code == 200, following.text
    assert page.json()["items"][0]["id"] != following.json()["items"][0]["id"]
    bad = await client.get(
        BASE + "/account-groups", params={"limit": 3, "cursor": cursor}, headers=headers()
    )
    assert bad.status_code == 422
    assert (await client.get(BASE + "/accounts?unknown=1", headers=headers())).status_code == 422
    assert (
        await client.get(BASE + "/accounts?limit=1&limit=2", headers=headers())
    ).status_code == 422
    assert (
        await client.post(
            BASE + "/accounts",
            json={
                "code": "BAD",
                "name": "Bad",
                "kind": "PARTY",
                "group_id": groups["INDIRECT_EXPENSES"],
                "party_id": abc["id"],
                "party_role": "CUSTOMER",
            },
            headers=headers(),
        )
    ).status_code == 422


async def test_tax_bank_mapping_and_profile_activation(client: httpx.AsyncClient) -> None:
    bank_id = uuid7()
    h = headers(bank_ids={bank_id})
    groups = await prepare(client, h=h)
    bank = await post(
        client,
        "/accounts",
        {"code": "MYBANK", "name": "Main Bank", "group_id": groups["BANKS"], "kind": "BANK"},
        h=h,
    )
    response = await client.post(
        BASE + "/accounts/" + bank["id"] + "/activate", json={"expected_version": 1}, headers=h
    )
    assert response.status_code == 409
    # Different operations use distinct keys; retries for an operation keep its key.
    h = headers(bank_ids={bank_id})
    await post(
        client,
        "/account-bank-profiles",
        {"account_id": bank["id"], "company_bank_id": str(bank_id)},
        h=h,
    )
    await activate(client, "/accounts", bank, h=h)
    start = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    mapping = await post(
        client,
        "/posting-mappings",
        {
            "purpose": "BANK_RECEIPT",
            "account_id": bank["id"],
            "currency": "INR",
            "valid_from": start,
        },
        h=h,
    )
    assert mapping["purpose"] == "BANK_RECEIPT"
    duplicate = await client.post(
        BASE + "/posting-mappings",
        json={
            "purpose": "BANK_RECEIPT",
            "account_id": bank["id"],
            "currency": "INR",
            "valid_from": start,
        },
        headers=headers(bank_ids={bank_id}),
    )
    assert duplicate.status_code == 409
