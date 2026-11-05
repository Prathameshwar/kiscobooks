"""Frozen lots and signed reference cursors retain the exact report scope."""

from conftest import COMPANY, headers
from test_inventory_api import create


async def test_frozen_lots_are_unique_and_item_scoped(app, client):
    _, run, ids = await create(app, client, "ITEM_LEDGER", native=True)
    path = f"/v2/companies/{COMPANY}/report-generations/{run['generation_id']}/inventory"
    response = await client.get(path, headers=headers(), params={"kind": "LOT"})
    assert response.status_code == 200, response.text
    lots = response.json()["items"]
    assert lots and len({row["id"] for row in lots}) == len(lots)
    selected = await client.get(
        path, headers=headers(), params={"kind": "LOT", "object_id": lots[0]["id"]}
    )
    assert selected.json()["items"] == [lots[0]]
    assert (
        await client.get(
            path,
            headers=headers(),
            params={"kind": "LOT", "item_id": "00000000-0000-0000-0000-000000000000"},
        )
    ).json()["items"] == []


async def test_reference_cursor_is_signed_and_bound_to_kind_and_search(app, client):
    _, run, _ = await create(app, client, "ITEM_LEDGER", native=True)
    path = f"/v2/companies/{COMPANY}/report-generations/{run['generation_id']}/inventory"
    response = await client.get(path, headers=headers(), params={"limit": 1})
    cursor = response.json()["next_cursor"]
    assert cursor and len(cursor) > 36
    second = await client.get(path, headers=headers(), params={"limit": 1, "cursor": cursor})
    assert second.status_code == 200
    assert second.json()["items"][0]["id"] != response.json()["items"][0]["id"]
    assert (
        await client.get(
            path, headers=headers(), params={"limit": 1, "cursor": cursor, "q": "changed"}
        )
    ).status_code == 422
