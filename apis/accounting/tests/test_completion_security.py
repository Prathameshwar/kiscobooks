"""Isolation and indirect-edit regressions for the completed master surfaces."""

import uuid
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import select

from accounting.models import masters as m
from tests.conftest import TENANT, headers
from tests.test_field_policy import policy
from tests.test_group_completion import installed_groups
from tests.test_masters import BASE, activate, new_party, post, prepare


async def test_alias_table_isolates_tenants_and_foreign_company_references(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await prepare(client)
    alias = await post(
        client, "/account-group-aliases", {"group_id": groups["SALES"], "alias": "Scoped alias"}
    )
    other_tenant, other_company = uuid7(), uuid7()
    base = f"/v1/companies/{other_company}"
    for path, body in [
        ("/accounting-setup/initialize", {}),
        ("/accounting-setup/install", {"business_accounts": False}),
    ]:
        result = await client.post(
            base + path, json=body, headers=headers(tenant=other_tenant, company=other_company)
        )
        assert result.status_code == 200, result.text
    other_groups = (
        await client.get(
            base + "/account-groups", headers=headers(tenant=other_tenant, company=other_company)
        )
    ).json()["items"]
    other = await client.post(
        base + "/account-group-aliases",
        json={"group_id": other_groups[0]["id"], "alias": "Scoped alias"},
        headers=headers(tenant=other_tenant, company=other_company),
    )
    assert other.status_code == 201, other.text
    for tenant, expected in [(TENANT, alias["id"]), (other_tenant, other.json()["id"])]:
        with tenant_scope(tenant):
            async with app.state.session_factory() as db:
                assert [str(row.id) for row in await db.scalars(select(m.AccountGroupAlias))] == [
                    expected
                ]
    invisible = await client.get(
        BASE + "/account-group-aliases/" + alias["id"], headers=headers(tenant=other_tenant)
    )
    assert invisible.status_code == 404
    foreign_company = await client.get(
        base + "/account-group-aliases/" + alias["id"], headers=headers(company=other_company)
    )
    assert foreign_company.status_code == 403
    denied = await client.post(
        BASE + "/account-group-aliases",
        json={"group_id": groups["SALES"], "alias": "Denied"},
        headers=headers(permissions={"accounting.group.read"}),
    )
    assert denied.status_code == 403
    denied = await client.post(
        BASE + "/account-group-aliases",
        json={"group_id": other_groups[0]["id"], "alias": "Cross tenant"},
        headers=headers(),
    )
    assert denied.status_code == 404


async def test_group_behavior_cannot_reinterpret_a_used_subtree(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    groups = await installed_groups(client)
    expense = next(row for row in groups if row["code"] == "INDIRECT_EXPENSES")
    group = await post(
        client,
        "/account-groups",
        {"code": "CUSTOM_USED", "name": "Used group", "head_id": expense["head_id"]},
    )
    group = await activate(client, "/account-groups", group)
    ledger = await post(
        client, "/accounts", {"code": "USED", "name": "Used ledger", "group_id": group["id"]}
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            row = await db.get(m.Account, uuid.UUID(ledger["id"]))
            assert row is not None
            row.used_at = utcnow()
    for field, value in [
        ("allocation_method", "BY_VALUE"),
        ("used_for_calculation", True),
        ("nett_balances", True),
        ("sub_ledger_behaviour", True),
    ]:
        result = await client.patch(
            BASE + "/account-groups/" + group["id"],
            json={"expected_version": group["row_version"], field: value},
            headers=headers(),
        )
        assert result.status_code == 409, result.text


async def test_alias_filter_and_group_sort_cannot_expose_denied_values(
    client: httpx.AsyncClient,
) -> None:
    groups = await prepare(client)
    await post(client, "/account-group-aliases", {"group_id": groups["SALES"], "alias": "Hidden"})
    cases: list[tuple[str, dict[str, str], dict[str, Any]]] = [
        (
            "account-group-aliases",
            {"alias": "Hidden"},
            policy("alias", entity="accounting.account_group_alias"),
        ),
        (
            "account-groups",
            {"sort": "sort_order"},
            policy("sort_order", entity="accounting.account_group"),
        ),
    ]
    for path, query, rule in cases:
        result = await client.get(BASE + "/" + path, params=query, headers=headers(policies=[rule]))
        assert result.status_code == 403, result.text


async def test_gst_state_code_must_match_the_registration_number(client: httpx.AsyncClient) -> None:
    await prepare(client)
    party = await new_party(client, code="STATE", name="State", legal_name="State")
    result = await client.post(
        BASE + "/party-tax-registrations",
        json={
            "party_id": party["id"],
            "scheme": "GST_IN",
            "registration_number": "27ABCDE1234F1Z0",
            "country_code": "IN",
            "state_code": "IN-KA",
            "valid_from": "2026-01-01",
        },
        headers=headers(),
    )
    assert result.status_code == 422, result.text
