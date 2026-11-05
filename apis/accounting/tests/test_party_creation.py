from typing import Any

import httpx
import pytest

from tests.conftest import COMPANY, PERMISSIONS, headers
from tests.test_masters import party_accounts, prepare

BASE = f"/v1/companies/{COMPANY}"


def draft() -> dict[str, Any]:
    return {
        "code": "WIZARD",
        "name": "Wizard supplier",
        "legal_name": "Wizard supplier",
        "country_code": "IN",
        "role": "SUPPLIER",
        "address": {
            "label": "Primary",
            "mailing_name": "Wizard supplier",
            "line1": "Road 1",
            "city": "Mumbai",
            "state_code": "IN-MH",
            "country_code": "IN",
        },
        "contact": {"name": "Accounts", "email": "accounts@example.test"},
    }


async def test_ready_defaults_and_exact_replay(client: httpx.AsyncClient) -> None:
    await prepare(client)
    h = headers()
    first = await client.post(BASE + "/parties/create-with-details", json=draft(), headers=h)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "ACTIVE"
    again = await client.post(BASE + "/parties/create-with-details", json=draft(), headers=h)
    assert again.status_code == 201, again.text
    assert again.json() == first.json()
    assert again.headers["Idempotency-Replayed"] == "true"
    pid = first.json()["id"]
    for resource, count in (
        ("parties", 1),
        ("party-roles", 1),
        ("party-addresses", 1),
        ("party-contacts", 1),
        ("party-address-uses", 2),
        ("party-contact-uses", 1),
    ):
        rows = (await client.get(BASE + "/" + resource, headers=headers())).json()["items"]
        assert len(rows) == count
        assert all(row["status"] == "ACTIVE" for row in rows)
        if "uses" in resource:
            for row in rows:
                detail = await client.get(BASE + f"/{resource}/{row['id']}", headers=headers())
                assert detail.json()["is_default"] is True
                assert detail.json()["party_id"] == pid
    # The role's account is created and active with it, and the replay added no second one.
    [ledger] = await party_accounts(client, pid)
    assert (ledger["kind"], ledger["party_role"], ledger["status"]) == (
        "PARTY",
        "SUPPLIER",
        "ACTIVE",
    )
    assert ledger["code"] == "WIZARD" and ledger["name"] == "Wizard supplier"
    revoked = headers(
        key=h["Idempotency-Key"], permissions=PERMISSIONS - {"accounting.party.manage"}
    )
    assert (
        await client.post(BASE + "/parties/create-with-details", json=draft(), headers=revoked)
    ).status_code == 403


@pytest.mark.parametrize("failure", ["tax", "permission", "ledger_permission", "field", "owner"])
async def test_failed_initial_setup_leaves_no_partial_party(
    client: httpx.AsyncClient, failure: str
) -> None:
    await prepare(client)
    body = draft()
    h = headers()
    if failure == "ledger_permission":
        # The party's account is part of every creation, so its permission is too.
        h = headers(permissions=PERMISSIONS - {"accounting.account.manage"})
    elif failure == "tax":
        body["tax_registration"] = {
            "scheme": "GST_IN",
            "country_code": "IN",
            "state_code": "IN-MH",
            "registration_number": "INVALID",
            "valid_from": "2026-01-01",
        }
    elif failure == "permission":
        body["tax_registration"] = {
            "scheme": "VAT",
            "country_code": "IN",
            "registration_number": "VAT-1",
            "valid_from": "2026-01-01",
        }
        h = headers(permissions=PERMISSIONS - {"accounting.tax.manage"})
    elif failure == "field":
        h = headers(
            policies=[
                {
                    "entity_type": "accounting.party_contact",
                    "field_key": "email",
                    "access": "write",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(COMPANY),
                    "condition": None,
                }
            ]
        )
    else:
        body["address"]["party_id"] = str(COMPANY)
    result = await client.post(BASE + "/parties/create-with-details", json=body, headers=h)
    assert result.status_code == (
        403 if failure in {"permission", "ledger_permission", "field"} else 422
    ), result.text
    if failure == "tax":
        assert "tax_registration.section" in result.json()["error"]["fields"]
    for resource in (
        "parties",
        "party-roles",
        "party-addresses",
        "party-contacts",
        "party-address-uses",
    ):
        assert (await client.get(BASE + "/" + resource, headers=headers())).json()["items"] == []
    # nor an account left behind: the chart holds only its business accounts, no party account
    party_ledgers = await client.get(
        BASE + "/accounts", headers=headers(), params={"kind": "PARTY"}
    )
    assert party_ledgers.status_code == 200, party_ledgers.text
    assert party_ledgers.json()["items"] == []


async def test_a_party_cannot_be_created_without_a_role(client: httpx.AsyncClient) -> None:
    await prepare(client)
    body = {key: value for key, value in draft().items() if key != "role"}
    result = await client.post(BASE + "/parties/create-with-details", json=body, headers=headers())
    assert result.status_code == 422, result.text
    assert (await client.get(BASE + "/parties", headers=headers())).json()["items"] == []
    unknown = await client.post(
        BASE + "/parties/create-with-details", json=body | {"role": "VENDOR"}, headers=headers()
    )
    assert unknown.status_code == 422, unknown.text


async def test_the_plain_party_create_route_is_gone(client: httpx.AsyncClient) -> None:
    await prepare(client)
    identity = {key: draft()[key] for key in ("code", "name", "legal_name", "country_code")}
    result = await client.post(BASE + "/parties", json=identity, headers=headers())
    # The path survives for reading, so a create is a method the resource no longer allows.
    assert result.status_code in {404, 405}, result.text
    assert (await client.get(BASE + "/parties", headers=headers())).json()["items"] == []


async def test_identity_only_and_changed_request_key_conflict(client: httpx.AsyncClient) -> None:
    await prepare(client)
    body = {key: value for key, value in draft().items() if key not in {"address", "contact"}}
    h = headers()
    created = await client.post(BASE + "/parties/create-with-details", json=body, headers=h)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "ACTIVE"
    conflict = await client.post(
        BASE + "/parties/create-with-details", json=body | {"name": "Changed"}, headers=h
    )
    # Shared idempotency contract rejects reuse with changed content as invalid input.
    assert conflict.status_code == 422
    rows = (await client.get(BASE + "/parties", headers=headers())).json()["items"]
    assert len(rows) == 1
    assert rows[0]["name"] == body["name"]
