from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.errors import PermissionDeniedError

from identity.api.auth import Actor, actor
from identity.api.reference import _authorize
from identity.models import Timezone
from tests.test_platform_setup import signed
from tests.test_reference_crud import ready

pytest_plugins = ["tests.test_platform_setup"]


async def test_timezone_directory_paging_and_no_rule_mutation(setup_app, client, factory):
    key, _ = await ready(setup_app, client, factory)
    path = "/v1/platform/references/timezones"
    first = await client.get(path + "?q=Asia&limit=1&sort=code", headers=signed(key))
    assert first.status_code == 200, first.text
    cursor = first.json()["page"]["next_cursor"]
    assert cursor
    second = await client.get(
        path + "?q=Asia&limit=1&sort=code&cursor=" + cursor, headers=signed(key)
    )
    assert second.status_code == 200
    assert first.json()["items"][0]["code"] != second.json()["items"][0]["code"]
    assert (
        await client.get(path + "?q=Europe&cursor=" + cursor, headers=signed(key))
    ).status_code == 422
    for query in ["?limit=201", "?sort=offset", "?q=A", "?limit=1&limit=2", "?private=value"]:
        assert (await client.get(path + query, headers=signed(key))).status_code == 422
    assert (await client.get(path)).status_code == 401
    assert (
        await client.post(path, json={"code": "Fake/Zone"}, headers=signed(key))
    ).status_code == 422
    assert (await client.patch(path + "/UTC", json={}, headers=signed(key))).status_code == 422


async def test_active_timezone_choices_are_bounded_and_archived_visible_to_admin(
    setup_app, client, factory
):
    key, _ = await ready(setup_app, client, factory)
    async with factory() as db, db.begin():
        row = await db.get(Timezone, "UTC")
        assert row
        row.is_active = False
    assert (await client.get("/v1/reference/timezones")).status_code == 401
    assert (await client.get("/v1/reference/timezones", headers=signed(key))).status_code == 403
    setup_app[0].dependency_overrides[actor] = lambda: Actor(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        grants=(
            Grant(
                permissions=frozenset({"warehouse.read"}),
                scope=Scope("company", uuid.uuid4()),
                valid_from=dt.date(2020, 1, 1),
            ),
        ),
    )
    response = await client.get("/v1/reference/timezones", headers=signed(key))
    assert response.status_code == 200, response.text
    assert 0 < len(response.json()) <= 1000
    assert "UTC" not in {row["code"] for row in response.json()}
    setup_app[0].dependency_overrides.pop(actor)
    rows = await client.get(
        "/v1/platform/references/timezones?status=archived", headers=signed(key)
    )
    assert rows.status_code == 200
    assert "UTC" in {row["code"] for row in rows.json()["items"]}


@pytest.mark.parametrize("permission", ["warehouse.read", "warehouse.manage"])
def test_warehouse_scoped_grants_can_read_regional_choices(permission):
    current = Actor(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        group_ids=frozenset(),
        grants=(
            Grant(
                permissions=frozenset({permission}),
                scope=Scope("company", uuid.uuid4()),
                valid_from=dt.date(2020, 1, 1),
            ),
        ),
    )
    _authorize(current)


def test_expired_or_unrelated_grants_cannot_read_choices():
    for permission, end in [("warehouse.read", dt.date(2020, 1, 2)), ("role.read", None)]:
        current = Actor(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            group_ids=frozenset(),
            grants=(
                Grant(
                    permissions=frozenset({permission}),
                    scope=Scope("company", uuid.uuid4()),
                    valid_from=dt.date(2020, 1, 1),
                    valid_to=end,
                ),
            ),
        )
        with pytest.raises(PermissionDeniedError):
            _authorize(current)
