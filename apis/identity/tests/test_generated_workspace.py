from __future__ import annotations

import uuid

import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import select

from identity.models import State, Tenant, User
from tests.factories import build_country, build_state
from tests.test_tenant_onboarding import initialize, signed

pytest_plugins = ["tests.test_platform_setup"]
BODY = {"name": "Books", "administrator_name": "Owner", "country_code": "IN", "state_code": "IN-MH"}


async def seed_state(factory):
    async with factory() as db, db.begin():
        db.add(build_state(code="IN-MH"))


async def test_platform_generates_unique_stable_ids_and_defaults(setup_app, client, factory):
    _, key = await initialize(setup_app, client)
    await seed_state(factory)
    body = {**BODY, "administrator_email": "owner@example.invalid",
            "administrator_password": "temporary-secret-for-test", "recipient_confirmed": True}
    headers = {**signed(key), "Idempotency-Key": "generated-one"}
    first = await client.post("/v1/platform/tenants", headers=headers, json=body)
    assert first.status_code == 201, first.text
    result = first.json()
    assert result["slug"] == "workspace-" + uuid.UUID(result["id"]).hex
    assert result["default_state_code"] == "IN-MH"
    assert result["default_currency_code"] == "INR"
    assert result["default_timezone"] == "Asia/Kolkata" and result["default_locale"] == "en"
    replay = await client.post("/v1/platform/tenants", headers=headers, json=body)
    assert replay.json()["slug"] == result["slug"]
    second = await client.post(
        "/v1/platform/tenants", headers={**headers, "Idempotency-Key": "generated-two"}, json=body
    )
    assert second.status_code == 201 and second.json()["slug"] != result["slug"]
    renamed = await client.patch(
        "/v1/platform/tenants/" + result["id"], headers=headers, json={"name": "Renamed"}
    )
    assert renamed.status_code == 200 and renamed.json()["slug"] == result["slug"]
    async with factory() as db:
        with tenant_scope(uuid.UUID(result["id"])):
            assert (await db.get(Tenant, uuid.UUID(result["id"]))).default_state_code == "IN-MH"
            assert (await db.scalar(select(User))).timezone == "Asia/Kolkata"


async def test_self_service_replay_keeps_generated_id_and_state(setup_app, client, factory):
    _, key = await initialize(setup_app, client)
    await seed_state(factory)
    headers = signed(key, subject="new-owner")
    first = await client.post("/v1/onboarding/tenant", headers=headers, json=BODY)
    assert first.status_code == 201, first.text
    second = await client.post("/v1/onboarding/tenant", headers=headers, json=BODY)
    assert second.json()["slug"] == first.json()["slug"]
    changed = await client.post(
        "/v1/onboarding/tenant", headers=headers, json={**BODY, "state_code": None}
    )
    assert changed.status_code == 409


@pytest.mark.parametrize("state", ["IN-XX", "US-CA"])
async def test_invalid_state_is_rejected_before_creation(setup_app, client, factory, state):
    _, key = await initialize(setup_app, client)
    await seed_state(factory)
    response = await client.post(
        "/v1/onboarding/tenant",
        headers=signed(key, subject="new-owner"),
        json={**BODY, "state_code": state},
    )
    assert response.status_code == 422


async def test_identifier_cannot_be_supplied_by_browser(setup_app, client):
    _, key = await initialize(setup_app, client)
    response = await client.post(
        "/v1/onboarding/tenant",
        headers=signed(key, subject="new-owner"),
        json={**BODY, "slug": "chosen-id"},
    )
    assert response.status_code == 422


async def test_country_choices_filter_states_and_inactive_states_cannot_be_saved(
    setup_app, client, factory
):
    _, key = await initialize(setup_app, client)
    await seed_state(factory)
    async with factory() as db, db.begin():
        db.add(build_country(code="US", iso3="USA", numeric_code="840", name="United States"))
        await db.flush()
        db.add(build_state(code="US-CA", country_code="US", name="California"))
    options = (await client.get("/v1/platform/tenant-options", headers=signed(key))).json()
    assert {item["country_code"] for item in options["states"]} == {"IN", "US"}
    mismatched = await client.post(
        "/v1/onboarding/tenant",
        headers=signed(key, subject="new-owner"),
        json={**BODY, "state_code": "US-CA"},
    )
    assert mismatched.status_code == 422
    async with factory() as db, db.begin():
        (await db.get(State, "IN-MH")).is_active = False
    options = (await client.get("/v1/platform/tenant-options", headers=signed(key))).json()
    assert all(item["code"] != "IN-MH" for item in options["states"])
    inactive = await client.post(
        "/v1/onboarding/tenant", headers=signed(key, subject="new-owner"), json=BODY
    )
    assert inactive.status_code == 422
    other = await client.post(
        "/v1/onboarding/tenant",
        headers=signed(key, subject="other-owner"),
        json={**BODY, "country_code": "US", "state_code": "US-CA"},
    )
    assert other.status_code == 201 and other.json()["default_timezone"] == "UTC"
