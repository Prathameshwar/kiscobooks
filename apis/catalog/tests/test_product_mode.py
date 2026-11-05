"""Live mode does not depend on product type, dated defaults or product adoption."""

import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select

from catalog.models.product_authoring import CompanyProductAuthoringConfiguration as Mode
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def mode_context(factory, tenant):
    company, user, _, body = await setup_product(factory, tenant, advanced=False)
    auth = headers(
        company,
        tenant=tenant,
        user=user,
        permission=["product_configuration.read", "product_configuration.manage", "item.read"],
    )
    return company, auth, body


async def set_mode(client, company, auth, enabled):
    route = f"/v1/companies/{company}/product-configuration/authoring"
    current = await client.get(route, headers=auth)
    assert current.status_code == 200, current.text
    data = current.json()
    request = {
        "expected_version": data["row_version"],
        "expected_generation": data["policy_generation"],
        "product_family_sku_enabled": enabled,
        "change_reason": "Test mode change",
    }
    preview = await client.post(route + "/preview", headers=auth, json=request)
    assert preview.status_code == 200, preview.text
    command = {**request, "preview_token": preview.json()["preview_token"]}
    receipt = command_headers(auth)
    return await client.patch(route, headers=receipt, json=command), command, receipt


async def test_mode_default_read_does_not_insert_and_transition_replays(client, factory, tenant_a):
    company, auth, _ = await mode_context(factory, tenant_a)
    route = f"/v1/companies/{company}/product-configuration/authoring"
    response = await client.get(route, headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()["product_family_sku_enabled"] is False
    assert response.json()["row_version"] == 0
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Mode.id))) == 0
    changed, request, receipt = await set_mode(client, company, auth, True)
    assert changed.status_code == 200, changed.text
    assert changed.json()["product_family_sku_enabled"] is True
    replay = await client.patch(route, headers=receipt, json=request)
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["row_version"] == 1
    disabled, _, _ = await set_mode(client, company, auth, False)
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["row_version"] == 2


async def test_mode_strict_bool_stale_preview_and_scope(client, factory, tenant_a):
    company, auth, _ = await mode_context(factory, tenant_a)
    changed, body, _ = await set_mode(client, company, auth, True)
    assert changed.status_code == 200, changed.text
    route = f"/v1/companies/{company}/product-configuration/authoring"
    stale = await client.patch(route, headers=command_headers(auth), json=body)
    assert stale.status_code == 409, stale.text
    body["product_family_sku_enabled"] = "false"
    assert (await client.patch(route, headers=command_headers(auth), json=body)).status_code == 422
    other, _, _, _ = await setup_product(factory, tenant_a)
    assert (
        await client.get(f"/v1/companies/{other}/product-configuration/authoring", headers=auth)
    ).status_code == 403


async def test_mode_replay_rechecks_current_native_field_permissions(client, factory, tenant_a):
    from tests.test_master_reference_policy import policy

    company, user, _, _ = await setup_product(factory, tenant_a, advanced=False)
    auth = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=["product_configuration.read", "product_configuration.manage", "item.read"],
    )
    changed, body, receipt = await set_mode(client, company, auth, True)
    assert changed.status_code == 200, changed.text
    entity = "catalog.company_product_authoring_configuration"
    await policy(factory, tenant_a, company, user, entity, "product_family_sku_enabled", "write")
    route = f"/v1/companies/{company}/product-configuration/authoring"
    replay = await client.patch(route, headers=receipt, json=body)
    assert replay.status_code == 403, replay.text
    await policy(
        factory, tenant_a, company, user, entity, "product_family_sku_enabled", "read", version=4
    )
    denied = await client.get(route, headers=auth)
    assert denied.status_code == 403, denied.text
