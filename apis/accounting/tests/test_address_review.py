"""Address association and default workflows reviewed from a caller's perspective."""

import asyncio
import json
import os
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models.workflows import MasterRevision
from tests.conftest import TENANT, headers
from tests.test_field_policy import policy
from tests.test_integrity_regressions import address_and_registration, day
from tests.test_masters import BASE, activate, new_party, post, prepare
from tests.test_party_completion import address as another_address


async def setup_addresses(
    client: httpx.AsyncClient,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    await prepare(client)
    return await address_and_registration(client, day(-10), None)


async def test_registration_address_pages_identify_both_ends_and_protect_them(
    client: httpx.AsyncClient,
) -> None:
    party, address, first = await setup_addresses(client)
    second = await post(
        client,
        "/party-tax-registrations",
        {
            "party_id": party["id"],
            "scheme": "GST_IN",
            # A second GSTIN in the same state: an SEZ unit beside the regular registration
            # (two overlapping regular registrations for one party and state are refused).
            "registration_type": "SEZ_UNIT",
            "registration_number": "27FGHIJ5678K1Z1",
            "country_code": "IN",
            "state_code": "IN-MH",
            "valid_from": day(-10),
        },
    )
    expected = {}
    for registration in (first, second):
        link = await post(
            client,
            "/party-registration-addresses",
            {
                "party_id": party["id"],
                "registration_id": registration["id"],
                "address_id": address["id"],
                "valid_from": day(1),
            },
        )
        expected[link["id"]] = registration["id"]
    params = {"party_id": party["id"], "as_of": day(1), "limit": "1"}
    seen = {}
    for _ in range(2):
        response = await client.get(
            BASE + "/party-registration-addresses", params=params, headers=headers()
        )
        assert response.status_code == 200, response.text
        page = response.json()
        assert len(page["items"]) == 1
        item = page["items"][0]
        assert item["address_id"] == address["id"]
        assert item.get("registration_id") == expected[item["id"]]
        seen[item["id"]] = item["registration_id"]
        if page["page"]["has_more"]:
            params["cursor"] = page["page"]["next_cursor"]
    assert seen == expected
    rule = policy("registration_id", entity="accounting.party_registration_address")
    restricted = headers(policies=[rule])
    for path in ("/party-registration-addresses", "/exports/party-registration-addresses"):
        result = await client.get(BASE + path, headers=restricted)
        assert result.status_code == 200, result.text
        assert all("registration_id" not in item for item in result.json()["items"])
        filtered = await client.get(
            BASE + path, params={"registration_id": first["id"]}, headers=restricted
        )
        assert filtered.status_code == 403, filtered.text


async def address_use(
    client: httpx.AsyncClient, party: str, address: str, *, default: bool = False
) -> dict[str, Any]:
    return await post(
        client,
        "/party-address-uses",
        {"party_id": party, "address_id": address, "purpose": "BILLING", "is_default": default},
    )


async def versions_and_revisions(
    client: httpx.AsyncClient, app: FastAPI, identifiers: list[str]
) -> tuple[list[dict[str, Any]], int]:
    rows = [
        (await client.get(BASE + "/party-address-uses/" + item, headers=headers())).json()
        for item in identifiers
    ]
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            revisions = list(
                await db.scalars(
                    select(MasterRevision.id).where(
                        MasterRevision.object_id.in_([uuid.UUID(item) for item in identifiers])
                    )
                )
            )
    return rows, len(revisions)


async def test_default_switch_rejects_conflicts_and_applies_atomically_without_private_audit(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    party, office, _ = await setup_addresses(client)
    delivery = await another_address(client, party["id"], "IN-KA")
    old = await activate(
        client,
        "/party-address-uses",
        await address_use(client, party["id"], office["id"], default=True),
    )
    new = await activate(
        client, "/party-address-uses", await address_use(client, party["id"], delivery["id"])
    )
    ids = [old["id"], new["id"]]
    before = await versions_and_revisions(client, app, ids)
    conflict = await client.patch(
        BASE + "/party-address-uses/" + new["id"],
        json={"expected_version": new["row_version"], "is_default": True},
        headers=headers(),
    )
    assert conflict.status_code == 409, conflict.text
    rule = policy(
        "is_default",
        entity="accounting.party_address_use",
        access="write",
        condition={"field": "purpose", "cmp": "eq", "value": "BILLING"},
    )
    forbidden = await client.patch(
        BASE + "/party-address-uses/" + old["id"],
        json={"expected_version": old["row_version"], "is_default": False},
        headers=headers(policies=[rule]),
    )
    assert forbidden.status_code == 403, forbidden.text
    items = [
        {
            "key": key,
            "resource": "party-address-uses",
            "action": "update",
            "object_id": row["id"],
            "values": {"expected_version": row["row_version"], "is_default": default},
        }
        for key, row, default in [("old", old, False), ("new", new, True)]
    ]
    bad = await post(client, "/imports/preview", {"items": list(reversed(items))}, status=200)
    assert bad["valid"] is False and bad["preview_token"] is None
    assert await versions_and_revisions(client, app, ids) == before
    preview = await post(client, "/imports/preview", {"items": items}, status=200)
    assert preview["valid"] is True
    assert await versions_and_revisions(client, app, ids) == before
    payload = {"items": items, "preview_token": preview["preview_token"]}
    h = headers()
    applied = await post(client, "/imports/apply", payload, h=h, status=200)
    assert await post(client, "/imports/apply", payload, h=h, status=200) == applied
    rows, revisions = await versions_and_revisions(client, app, ids)
    assert [row["is_default"] for row in rows] == [False, True]
    assert [row["row_version"] for row in rows] == [old["row_version"] + 1, new["row_version"] + 1]
    assert revisions == before[1] + 2
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            payloads = list(await db.scalars(select(Outbox.payload)))
    serialized = json.dumps(payloads, default=str)
    assert office["line1"] not in serialized and delivery["line1"] not in serialized


async def test_active_address_use_preserves_ownership_eligibility_and_default_scope(
    client: httpx.AsyncClient,
) -> None:
    party, office, registration = await setup_addresses(client)
    general = await activate(
        client,
        "/party-address-uses",
        await address_use(client, party["id"], office["id"], default=True),
    )
    scoped = await post(
        client,
        "/party-address-uses",
        {
            "party_id": party["id"],
            "address_id": office["id"],
            "registration_id": registration["id"],
            "purpose": "BILLING",
            "is_default": True,
        },
    )
    scoped = await activate(client, "/party-address-uses", scoped)
    result = await client.patch(
        BASE + "/party-address-uses/" + scoped["id"],
        json={"expected_version": scoped["row_version"], "registration_id": None},
        headers=headers(),
    )
    assert result.status_code == 409, result.text
    other_party = await new_party(client, code="OTHER", name="Other", legal_name="Other")
    foreign = await another_address(client, other_party["id"], "IN-KA")
    result = await client.patch(
        BASE + "/party-address-uses/" + general["id"],
        json={"expected_version": general["row_version"], "address_id": foreign["id"]},
        headers=headers(),
    )
    assert result.status_code == 422, result.text
    owned = await another_address(client, party["id"], "IN-KA")
    await post(
        client,
        "/party-addresses/" + owned["id"] + "/deactivate",
        {"expected_version": owned["row_version"]},
        status=200,
    )
    result = await client.patch(
        BASE + "/party-address-uses/" + general["id"],
        json={"expected_version": general["row_version"], "address_id": owned["id"]},
        headers=headers(),
    )
    assert result.status_code == 409, result.text
    saved = await client.get(BASE + "/party-address-uses/" + general["id"], headers=headers())
    assert saved.json() == general
    denied = await client.post(
        BASE + "/party-addresses/" + office["id"] + "/deactivate",
        json={"expected_version": office["row_version"]},
        headers=headers(),
    )
    assert denied.status_code == 409, denied.text


async def test_address_fields_remain_private_on_export_replay_and_condition_changes(
    client: httpx.AsyncClient,
) -> None:
    party, office, _ = await setup_addresses(client)
    path = "/party-addresses/" + office["id"]
    h = headers()
    body = {"expected_version": office["row_version"], "line1": "Private replacement address"}
    updated = await client.patch(BASE + path, json=body, headers=h)
    assert updated.status_code == 200, updated.text
    condition = {"field": "country_code", "cmp": "eq", "value": "IN"}
    read_rule = policy("line1", entity="accounting.party_address", condition=condition)
    restricted = headers(policies=[read_rule], key=h["Idempotency-Key"])
    replay = await client.patch(BASE + path, json=body, headers=restricted)
    assert replay.status_code == 200 and "line1" not in replay.json()
    for suffix in (path, "/exports/party-addresses"):
        result = await client.get(BASE + suffix, headers=restricted)
        assert result.status_code == 200, result.text
        rows = result.json().get("items", [result.json()])
        assert rows and all("line1" not in row for row in rows)
    write_rule = policy(
        "line1", access="write", entity="accounting.party_address", condition=condition
    )
    escaped = await client.patch(
        BASE + path,
        json={
            "expected_version": updated.json()["row_version"],
            "country_code": "US",
            "state_code": None,
            "line1": "Attempted bypass",
        },
        headers=headers(policies=[write_rule]),
    )
    assert escaped.status_code == 403, escaped.text
    saved = await client.get(BASE + path, headers=headers())
    assert saved.json() == updated.json() and saved.json()["party_id"] == party["id"]


async def test_address_references_reject_foreign_company_and_tenant_objects(
    client: httpx.AsyncClient,
) -> None:
    party, office, _ = await setup_addresses(client)
    company = uuid7()
    foreign_base = f"/v1/companies/{company}"

    async def foreign_post(path: str, values: dict[str, Any], expected: int) -> dict[str, Any]:
        response = await client.post(
            foreign_base + path, json=values, headers=headers(company=company)
        )
        assert response.status_code == expected, response.text
        return dict(response.json())

    await foreign_post("/accounting-setup/initialize", {}, 200)
    owner = await foreign_post(
        "/parties/create-with-details",
        {
            "code": "FOREIGN",
            "name": "Foreign",
            "legal_name": "Foreign",
            "country_code": "IN",
            "role": "SUPPLIER",
        },
        201,
    )
    foreign = await foreign_post(
        "/party-addresses",
        {
            "party_id": owner["id"],
            "label": "Office",
            "mailing_name": "Foreign",
            "line1": "Foreign private address",
            "city": "Mumbai",
            "country_code": "IN",
        },
        201,
    )
    await foreign_post(
        "/party-addresses/" + foreign["id"] + "/activate", {"expected_version": 1}, 200
    )
    response = await client.get(BASE + "/party-addresses/" + foreign["id"], headers=headers())
    assert response.status_code == 403, response.text
    response = await client.post(
        BASE + "/party-address-uses",
        json={"party_id": party["id"], "address_id": foreign["id"], "purpose": "BILLING"},
        headers=headers(),
    )
    assert response.status_code == 403, response.text
    other_tenant = headers(tenant=uuid7())
    response = await client.get(BASE + "/party-addresses/" + office["id"], headers=other_tenant)
    assert response.status_code == 404, response.text
    response = await client.get(
        BASE + "/exports/party-addresses", params={"party_id": party["id"]}, headers=other_tenant
    )
    assert response.status_code == 200 and response.json()["items"] == []


@pytest.mark.skipif(
    not os.environ.get("ACCOUNTING_TEST_DATABASE_URL", "").startswith("mysql"),
    reason="concurrent company locking requires native MySQL",
)
async def test_concurrent_default_activation_commits_one_winner(client: httpx.AsyncClient) -> None:
    party, office, _ = await setup_addresses(client)
    delivery = await another_address(client, party["id"], "IN-KA")
    drafts = [
        await address_use(client, party["id"], row["id"], default=True)
        for row in (office, delivery)
    ]
    outcomes = await asyncio.gather(
        *(
            client.post(
                BASE + "/party-address-uses/" + row["id"] + "/activate",
                json={"expected_version": row["row_version"]},
                headers=headers(),
            )
            for row in drafts
        )
    )
    assert sorted(response.status_code for response in outcomes) == [200, 409]
    page = await client.get(
        BASE + "/party-address-uses",
        params={"party_id": party["id"], "purpose": "BILLING", "status": "ACTIVE"},
        headers=headers(),
    )
    assert len(page.json()["items"]) == 1 and page.json()["items"][0]["is_default"] is True
