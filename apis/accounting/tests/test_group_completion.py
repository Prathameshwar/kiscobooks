"""The complete chart and aliases work through the public master API."""

from typing import Any, cast

import httpx

from tests.conftest import headers
from tests.test_masters import BASE, activate, post


async def installed_groups(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    await post(client, "/accounting-setup/initialize", {}, status=200)
    response = await client.get(BASE + "/account-groups", headers=headers())
    assert response.status_code == 200, response.text
    return cast(list[dict[str, Any]], response.json()["items"])


async def test_complete_base_chart_and_derived_classification(client: httpx.AsyncClient) -> None:
    groups = await installed_groups(client)
    assert len(groups) == 28
    assert sum(row["is_primary"] for row in groups) == 15
    assert all(row["is_reserved"] for row in groups)
    by_code = {row["code"]: row for row in groups}
    assert by_code["RESERVES"]["parent_id"] == by_code["CAPITAL"]["id"]
    detail = await client.get(
        BASE + f'/account-groups/{by_code["PURCHASES"]["id"]}', headers=headers()
    )
    assert detail.json()["affects_gross_profit"] is True
    assert detail.json()["is_revenue"] is True
    assert detail.json()["is_deemed_positive"] is True


async def test_group_alias_round_trip_conflict_and_retirement(client: httpx.AsyncClient) -> None:
    group = (await installed_groups(client))[0]
    body: dict[str, Any] = {"group_id": group["id"], "alias": "  Alternate chart label  "}
    alias = await post(client, "/account-group-aliases", body)
    assert alias["alias"] == "Alternate chart label"
    assert alias["group_id"] == group["id"]
    duplicate = await client.post(BASE + "/account-group-aliases", json=body, headers=headers())
    assert duplicate.status_code == 409, duplicate.text
    alias = await activate(client, "/account-group-aliases", alias)
    retired = await client.post(
        BASE + f'/account-group-aliases/{alias["id"]}/deactivate',
        json={"expected_version": alias["row_version"]},
        headers=headers(),
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["status"] == "INACTIVE"


async def test_child_classification_inherits_and_cannot_conflict(client: httpx.AsyncClient) -> None:
    parent = next(row for row in await installed_groups(client) if row["code"] == "PURCHASES")
    child = await post(
        client,
        "/account-groups",
        {
            "code": "LOCAL_PURCHASE",
            "name": "Local purchase",
            "head_id": parent["head_id"],
            "parent_id": parent["id"],
            "sort_order": 12,
        },
    )
    assert child["is_primary"] is False and child["is_reserved"] is False
    assert child["affects_gross_profit"] is True
    denied = await client.patch(
        BASE + f'/account-groups/{child["id"]}',
        json={
            "expected_version": child["row_version"],
            "affects_gross_profit": False,
        },
        headers=headers(),
    )
    assert denied.status_code in (409, 422), denied.text


async def test_primary_reparent_and_parent_classification_changes_preserve_descendants(
    client: httpx.AsyncClient,
) -> None:
    system = next(row for row in await installed_groups(client) if row["code"] == "SALES")
    root = await post(
        client,
        "/account-groups",
        {
            "code": "CUSTOM_ROOT",
            "name": "Root",
            "head_id": system["head_id"],
        },
    )
    root = await activate(client, "/account-groups", root)
    result = await client.patch(
        BASE + "/account-groups/" + root["id"],
        json={
            "expected_version": root["row_version"],
            "parent_id": system["id"],
            "affects_gross_profit": True,
        },
        headers=headers(),
    )
    assert result.status_code == 409, result.text
    child = await post(
        client,
        "/account-groups",
        {
            "code": "CUSTOM_CHILD",
            "name": "Child",
            "head_id": root["head_id"],
            "parent_id": root["id"],
        },
    )
    result = await client.patch(
        BASE + "/account-groups/" + root["id"],
        json={
            "expected_version": root["row_version"],
            "affects_gross_profit": True,
        },
        headers=headers(),
    )
    assert result.status_code == 409, result.text
    unchanged = await client.get(BASE + "/account-groups/" + child["id"], headers=headers())
    assert unchanged.json()["affects_gross_profit"] is False
