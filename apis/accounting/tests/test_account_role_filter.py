"""The account list's `role` filter and `party_role` field.

A party that is both customer and supplier holds two accounts (one per role). A voucher takes the
customer's receivable or the supplier's payable by role, never "the first party account", which for
a party that is both would be the wrong ledger (docs/party-ledger-mandatory-plan.md, PL-D07).
"""

from typing import Any

import httpx
from billing_platform.ids import uuid7

from tests.conftest import headers
from tests.test_field_policy import policy
from tests.test_masters import BASE, new_party, party, prepare


async def listed(client: httpx.AsyncClient, h: dict[str, str] | None = None, **params: str) -> Any:
    result = await client.get(
        BASE + "/accounts",
        params={"kind": "PARTY", "status": "ACTIVE", **params},
        headers=h or headers(),
    )
    assert result.status_code == 200, result.text
    return result.json()["items"]


async def test_the_list_carries_each_accounts_party_role(client: httpx.AsyncClient) -> None:
    await prepare(client)
    abc = await party(client)
    rows = await listed(client, party_id=abc["id"])
    assert {(row["code"], row["party_role"]) for row in rows} == {
        ("ABC", "CUSTOMER"),
        ("ABC-SUPP", "SUPPLIER"),
    }


async def test_role_filter_returns_only_that_roles_account(client: httpx.AsyncClient) -> None:
    await prepare(client)
    abc = await party(client)
    customer = await listed(client, party_id=abc["id"], role="CUSTOMER")
    supplier = await listed(client, party_id=abc["id"], role="SUPPLIER")
    assert [(row["code"], row["party_role"]) for row in customer] == [("ABC", "CUSTOMER")]
    assert [(row["code"], row["party_role"]) for row in supplier] == [("ABC-SUPP", "SUPPLIER")]
    assert await listed(client, party_id=abc["id"], role="OTHER") == []


async def test_a_brokers_account_is_found_under_both_broker_and_other(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    broker = await new_party(client, code="BRK", role="BROKER")
    for role in ("BROKER", "OTHER"):
        rows = await listed(client, party_id=broker["id"], role=role)
        assert [(row["code"], row["party_role"]) for row in rows] == [("BRK", "OTHER")]
    assert await listed(client, party_id=broker["id"], role="CUSTOMER") == []


async def test_an_unknown_role_is_a_validation_error(client: httpx.AsyncClient) -> None:
    await prepare(client)
    result = await client.get(BASE + "/accounts", params={"role": "WIZARD"}, headers=headers())
    assert result.status_code == 422


async def test_role_filter_is_refused_where_the_party_role_is_not_readable(
    client: httpx.AsyncClient,
) -> None:
    await prepare(client)
    abc = await party(client)
    denied = headers(policies=[policy("party_role", entity="accounting.account")])
    # Without the filter the list still works and simply omits the denied field.
    rows = await listed(client, denied, party_id=abc["id"])
    assert rows and all("party_role" not in row for row in rows)
    # A denied field is also forbidden in filters.
    refused = await client.get(
        BASE + "/accounts",
        params={"party_id": abc["id"], "role": "SUPPLIER"},
        headers=denied,
    )
    assert refused.status_code == 403, refused.text


async def test_another_tenant_never_sees_the_accounts_by_role(client: httpx.AsyncClient) -> None:
    await prepare(client)
    await party(client)
    assert await listed(client, role="SUPPLIER")
    outsider = await client.get(
        BASE + "/accounts",
        params={"kind": "PARTY", "role": "SUPPLIER"},
        headers=headers(tenant=uuid7()),
    )
    assert outsider.status_code in {403, 404} or outsider.json().get("items") == []
