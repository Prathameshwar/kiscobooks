from __future__ import annotations

import pytest
from billing_platform.errors import ValidationFailedError
from sqlalchemy import func, select

from identity.models import Language, Timezone
from identity.seeds.regional import seed_regional_defaults
from identity.services.tenant_choices import choices
from identity.services.tenant_provisioning import validate_defaults
from tests.test_platform_setup import BODY, signed

pytest_plugins = ["tests.test_platform_setup"]


async def test_all_four_catalogues_are_materialized_and_active(setup_app, factory):
    async with factory() as db:
        result = (await choices(db)).model_dump()
        assert {"countries", "currencies", "timezones", "languages"} <= result.keys()
        assert "UTC" in {item["code"] for item in result["timezones"]}
        assert "Asia/Kolkata" in {item["code"] for item in result["timezones"]}
        assert "en" in {item["code"] for item in result["languages"]}


async def test_unknown_language_is_rejected_before_writes(setup_app, factory):
    async with factory() as db:
        with pytest.raises(ValidationFailedError):
            await validate_defaults(db, "IN", "INR", "UTC", "zz")


@pytest.mark.parametrize("model,code", [(Language, "en"), (Timezone, "UTC")])
async def test_inactive_references_are_hidden_and_cannot_be_saved(setup_app, factory, model, code):
    async with factory() as db, db.begin():
        row = await db.get(model, code)
        row.is_active = False
    async with factory() as db:
        catalogue = await choices(db)
        values = catalogue.languages if model is Language else catalogue.timezones
        assert code not in {item.code for item in values}
        with pytest.raises(ValidationFailedError):
            await validate_defaults(db, "IN", "INR", "UTC", "en")


async def test_seed_repeats_without_duplicate_rows_and_deactivates_withdrawn_codes(
    setup_app, factory
):
    async with factory() as db, db.begin():
        before = await db.scalar(select(func.count()).select_from(Timezone))
        db.add(Timezone(code="Withdrawn/Timezone", name="Withdrawn", is_active=True))
        await db.flush()
        await seed_regional_defaults(db)
        assert await db.scalar(select(func.count()).select_from(Timezone)) == before + 1
        assert not (await db.get(Timezone, "Withdrawn/Timezone")).is_active
        await seed_regional_defaults(db)
        assert await db.scalar(select(func.count()).select_from(Timezone)) == before + 1


async def test_setup_choice_endpoint_returns_four_lists_with_key_gate(setup_app, client):
    _, _, access = setup_app
    assert (await client.get("/v1/setup/checks")).status_code == 403
    response = await client.get("/v1/setup/checks", headers=access)
    assert response.status_code == 200
    data = response.json()
    assert all(data[key] for key in ["countries", "currencies", "languages", "timezones"])
    assert len(data["timezones"]) <= 1000


async def test_setup_persists_selected_language_and_timezone(setup_app, client, factory):
    _, key, access = setup_app
    response = await client.post(
        "/v1/setup/complete",
        headers={**access, **signed(key)},
        json={**BODY, "locale": "hi", "timezone": "UTC"},
    )
    assert response.status_code == 200
    from billing_platform.db import unfiltered

    from identity.models import Tenant, User

    async with factory() as db:
        with unfiltered():
            tenant, user = await db.scalar(select(Tenant)), await db.scalar(select(User))
            assert tenant.default_locale == user.locale == "hi"
            assert tenant.default_timezone == user.timezone == "UTC"
