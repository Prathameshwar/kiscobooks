from __future__ import annotations

from billing_platform.db.reference_management import ReferenceRevision

from identity.models import Language
from tests.test_platform_setup import signed
from tests.test_reference_crud import ready

pytest_plugins = ["tests.test_platform_setup"]


async def test_code_and_name_paging_query_bound_and_cross_kind_rejected(setup_app, client, factory):
    key, _ = await ready(setup_app, client, factory)
    async with factory() as db, db.begin():
        for code in ["xx", "yy", "zz"]:
            db.add(Language(code=code, iso3=code + "x", name="Same name", is_active=True))
            db.add(
                ReferenceRevision(
                    kind="language",
                    code=code,
                    name="Same name",
                    is_active=True,
                    source="seed",
                    version=0,
                    payload={
                        "code": code,
                        "iso3": code + "x",
                        "name": "Same name",
                        "native_name": None,
                        "is_active": True,
                    },
                )
            )
    path = "/v1/platform/references/languages"
    first = await client.get(path + "?q=Same&sort=name&limit=1", headers=signed(key))
    assert first.status_code == 200
    cursor = first.json()["page"]["next_cursor"]
    assert cursor
    second = await client.get(
        path + "?q=Same&sort=name&limit=1&cursor=" + cursor, headers=signed(key)
    )
    assert second.status_code == 200
    assert first.json()["items"][0]["code"] != second.json()["items"][0]["code"]
    assert (
        await client.get(path + "?q=Other&sort=name&cursor=" + cursor, headers=signed(key))
    ).status_code == 422
    assert (
        await client.get(
            "/v1/platform/references/countries?q=Same&sort=name&cursor=" + cursor,
            headers=signed(key),
        )
    ).status_code == 422
    response = await client.get(path + "?sort=code&limit=1", headers=signed(key))
    assert response.status_code == 200
    assert (
        await client.get(
            path + "?sort=code&limit=1&cursor=" + response.json()["page"]["next_cursor"],
            headers=signed(key),
        )
    ).status_code == 200
