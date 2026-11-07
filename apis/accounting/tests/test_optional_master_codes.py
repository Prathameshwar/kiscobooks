import re

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import headers
from tests.test_field_policy import layout, policy
from tests.test_masters import BASE, party_accounts, post, prepare
from tests.test_party_ledger_mandatory import counts, outbox_total


@pytest.mark.parametrize("code", [None, "", "   ", "omitted"])
async def test_generated_account_and_party_codes(
    client: httpx.AsyncClient, code: str | None
) -> None:
    groups = await prepare(client)
    identity = {} if code == "omitted" else {"code": code}
    account_body = {"name": "Office expense", "group_id": groups["INDIRECT_EXPENSES"], **identity}
    authority = headers()
    account = await post(client, "/accounts/create-active", account_body, h=authority)
    assert re.fullmatch(r"[A-Z0-9]{8}", account["code"])
    replay = await post(client, "/accounts/create-active", account_body, h=authority)
    assert replay == account
    party_authority = headers()
    party_body = {
        "name": "Supplier",
        "legal_name": "Supplier",
        "country_code": "IN",
        "role": "SUPPLIER",
        **identity,
    }
    party = await post(
        client,
        "/parties/create-with-details",
        party_body,
        h=party_authority,
    )
    assert re.fullmatch(r"[A-Z0-9]{8}", party["code"])
    assert (await party_accounts(client, party["id"]))[0]["code"] == party["code"]
    assert (
        await post(client, "/parties/create-with-details", party_body, h=party_authority) == party
    )


@pytest.mark.parametrize("code", ["x" * 41, "bad\u0000code"])
@pytest.mark.parametrize("resource", ["account", "party"])
async def test_invalid_code_has_field_error(
    client: httpx.AsyncClient,
    code: str,
    resource: str,
) -> None:
    groups = await prepare(client)
    body = {"code": code, "name": "Office expense", "group_id": groups["INDIRECT_EXPENSES"]}
    if resource == "party":
        body = {
            "code": code,
            "name": "Supplier",
            "legal_name": "Supplier",
            "country_code": "IN",
            "role": "SUPPLIER",
        }
    response = await client.post(
        BASE
        + ("/accounts/create-active" if resource == "account" else "/parties/create-with-details"),
        headers=headers(),
        json=body,
    )
    assert response.status_code == 422, response.text
    assert ("code" if resource == "account" else "party.code") in response.json()["error"]["fields"]


async def test_generated_party_avoids_default_ledger_collision(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups = await prepare(client)
    await post(
        client,
        "/accounts/create-active",
        {
            "code": "AABBCCDD",
            "name": "Existing",
            "group_id": groups["INDIRECT_EXPENSES"],
        },
    )
    candidates = iter(["AABBCCDD", "EEFF0011"])
    monkeypatch.setattr("accounting.tasks.master_codes.candidate_code", lambda: next(candidates))
    party = await post(
        client,
        "/parties/create-with-details",
        {
            "name": "Supplier",
            "legal_name": "Supplier",
            "country_code": "IN",
            "role": "SUPPLIER",
        },
    )
    assert party["code"] == "EEFF0011"
    assert (await party_accounts(client, party["id"]))[0]["code"] == "EEFF0011"


async def test_manual_code_preserved_and_duplicate_has_specific_error(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    body = {"code": " 00-Office & rent ", "name": "Rent", "group_id": groups["INDIRECT_EXPENSES"]}
    account = await post(client, "/accounts", body)
    assert account["code"] == "00-Office & rent"
    duplicate = await client.post(BASE + "/accounts", json=body, headers=headers())
    assert duplicate.status_code == 409, duplicate.text
    assert "code" in duplicate.json()["error"]["fields"]
    party_body = {
        "code": "SUPPLIER001",
        "name": "Supplier",
        "legal_name": "Supplier",
        "country_code": "IN",
        "role": "SUPPLIER",
    }
    await post(client, "/parties/create-with-details", party_body)
    duplicate_party = await client.post(
        BASE + "/parties/create-with-details",
        json=party_body | {"ledger": {"code": "NEWLEDGER"}},
        headers=headers(),
    )
    assert duplicate_party.status_code == 409, duplicate_party.text
    assert "party.code" in duplicate_party.json()["error"]["fields"]


async def test_optional_metadata_and_generated_code_authority(client: httpx.AsyncClient) -> None:
    groups = await prepare(client)
    for resource, entity in [("accounts", "accounting.account"), ("parties", "accounting.party")]:
        current = headers(layouts=[layout("code", entity_type=entity, is_required=True)])
        response = await client.get(BASE + f"/configuration/{resource}/field-set", headers=current)
        assert response.status_code == 200, response.text
        code = next(field for field in response.json()["fields"] if field["key"] == "code")
        assert code["required"] is False
        assert code["control"]["nullable"] is True
    body = {"name": "Private expense", "group_id": groups["INDIRECT_EXPENSES"]}
    denied = await client.post(
        BASE + "/accounts/create-active",
        json=body,
        headers=headers(
            policies=[policy("code", access="write", entity="accounting.account")],
        ),
    )
    assert denied.status_code == 403, denied.text
    allowed = await post(
        client,
        "/accounts/create-active",
        body,
        h=headers(
            layouts=[layout("code", entity_type="accounting.account", is_required=True)],
        ),
    )
    assert re.fullmatch(r"[A-Z0-9]{8}", allowed["code"])


async def test_retired_code_collision_is_bounded_and_retry_is_atomic(
    client: httpx.AsyncClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups = await prepare(client)
    body = {"name": "Expense", "group_id": groups["INDIRECT_EXPENSES"]}
    existing = await post(client, "/accounts/create-active", body | {"code": "AABBCCDD"})
    await post(
        client,
        f"/accounts/{existing['id']}/deactivate",
        {"expected_version": existing["row_version"]},
        status=200,
    )
    before, audit_before = await counts(app), await outbox_total(app)
    calls = 0

    def taken() -> str:
        nonlocal calls
        calls += 1
        return "AABBCCDD"

    monkeypatch.setattr("accounting.tasks.master_codes.candidate_code", taken)
    authority = headers()
    refused = await client.post(BASE + "/accounts/create-active", json=body, headers=authority)
    assert refused.status_code == 409, refused.text
    assert calls == 20
    assert await counts(app) == before
    assert await outbox_total(app) == audit_before
    monkeypatch.setattr("accounting.tasks.master_codes.candidate_code", lambda: "EEFF0011")
    created = await post(client, "/accounts/create-active", body, h=authority)
    assert created["code"] == "EEFF0011"
    assert await post(client, "/accounts/create-active", body, h=authority) == created


async def test_generated_party_avoids_party_identity_with_custom_ledger(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await prepare(client)
    body = {"name": "Supplier", "legal_name": "Supplier", "country_code": "IN", "role": "SUPPLIER"}
    await post(
        client,
        "/parties/create-with-details",
        body
        | {
            "code": "AABBCCDD",
            "ledger": {"code": "CUSTOMLEDGER"},
        },
    )
    candidates = iter(["AABBCCDD", "EEFF0011"])
    monkeypatch.setattr("accounting.tasks.master_codes.candidate_code", lambda: next(candidates))
    created = await post(client, "/parties/create-with-details", body | {"ledger": {"code": "   "}})
    assert created["code"] == "EEFF0011"
    assert (await party_accounts(client, created["id"]))[0]["code"] == "EEFF0011"


async def test_auto_party_code_does_not_bypass_field_policy_or_leave_audit(
    client: httpx.AsyncClient,
    app: FastAPI,
) -> None:
    await prepare(client)
    before, audit_before = await counts(app), await outbox_total(app)
    body = {"name": "Supplier", "legal_name": "Supplier", "country_code": "IN", "role": "SUPPLIER"}
    for entity in ("accounting.party", "accounting.account"):
        refused = await client.post(
            BASE + "/parties/create-with-details",
            json=body,
            headers=headers(
                policies=[policy("code", access="write", entity=entity)],
            ),
        )
        assert refused.status_code == 403, refused.text
        assert await counts(app) == before
        assert await outbox_total(app) == audit_before


async def test_manual_code_limit_counts_unicode_characters(client: httpx.AsyncClient) -> None:
    groups = await prepare(client)
    account = await post(
        client,
        "/accounts/create-active",
        {
            "name": "Expense",
            "group_id": groups["INDIRECT_EXPENSES"],
            "code": "😀" * 40,
        },
    )
    assert account["code"] == "😀" * 40
    party = await post(
        client,
        "/parties/create-with-details",
        {
            "name": "Supplier",
            "legal_name": "Supplier",
            "country_code": "IN",
            "role": "SUPPLIER",
            "code": "🙂" * 40,
        },
    )
    assert party["code"] == "🙂" * 40
    assert (await party_accounts(client, party["id"]))[0]["code"] == party["code"]
