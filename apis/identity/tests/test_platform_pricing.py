"""Commercial correctness, lifecycle history and the actual platform authority boundary."""

import time
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select

from identity.models import PlatformPrice, PlatformPriceRevision, RoleAssignment
from identity.schemas.platform_price import PlatformPriceInput
from identity.seeds.pricing import seed_pricing
from tests.test_gap_login import bearer
from tests.test_platform_details import complete
from tests.test_platform_setup import signed

pytest_plugins = ["tests.test_platform_setup"]
BODY = {
    "code": "custom-1y",
    "name": "Custom annual",
    "category": "platform",
    "term_months": 12,
    "unit": "none",
    "monthly_fee": "449",
}


async def create(client, key, **values):
    response = await client.post(
        "/v1/platform/pricing", headers=signed(key), json={**BODY, **values}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_catalog_exact_conversion_tax_and_revision_history(client, setup_app, factory):
    key, _ = await complete(client, setup_app)
    row = await create(client, key)
    inr, usd = row["prices"]
    assert inr == {
        "currency": "INR",
        "monthly_fee": "449.00",
        "unit_price": "0.0000",
        "output_unit_price": "0.0000",
        "term_net": "5388.00",
        "term_tax": "969.84",
        "term_total": "6357.84",
    }
    assert Decimal(usd["monthly_fee"]) >= Decimal("449") / Decimal(row["fx_inr_per_usd"]) * Decimal(
        "1.20"
    )
    body = {**BODY, "monthly_fee": "389", "expected_version": 1}
    response = await client.patch(
        "/v1/platform/pricing/" + row["id"], headers=signed(key), json=body
    )
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    assert (
        await client.patch("/v1/platform/pricing/" + row["id"], headers=signed(key), json=body)
    ).status_code == 409
    versions = (
        await client.get("/v1/platform/pricing/" + row["id"] + "/revisions", headers=signed(key))
    ).json()["items"]
    assert [item["snapshot"]["monthly_fee"] for item in versions] == ["449", "389"]
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(PlatformPriceRevision)) == 2


async def test_delete_restore_and_seed_preserve_admin_decisions(client, setup_app, factory):
    key, _ = await complete(client, setup_app)
    async with factory() as db, db.begin():
        await seed_pricing(db)
    listing = (
        await client.get("/v1/platform/pricing?category=platform", headers=signed(key))
    ).json()
    assert len(listing["items"]) == 2
    row = listing["items"][0]
    path = "/v1/platform/pricing/" + row["id"]
    deleted = await client.post(
        path + "/delete", headers=signed(key), json={"expected_version": row["version"]}
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_at"] and not deleted.json()["is_active"]
    async with factory() as db, db.begin():
        await seed_pricing(db)
    assert (
        len(
            (await client.get("/v1/platform/pricing?status=deleted", headers=signed(key))).json()[
                "items"
            ]
        )
        == 1
    )
    restored = await client.post(
        path + "/restore", headers=signed(key), json={"expected_version": 2}
    )
    assert restored.status_code == 200 and not restored.json()["is_active"]
    assert restored.json()["deleted_at"] is None
    assert (
        len(
            (await client.get("/v1/platform/pricing?status=active", headers=signed(key))).json()[
                "items"
            ]
        )
        == 8
    )


async def test_create_conflicts_and_rollback_without_audit(client, setup_app, factory):
    key, _ = await complete(client, setup_app)
    await create(client, key)
    assert (
        await client.post("/v1/platform/pricing", headers=signed(key), json=BODY)
    ).status_code == 409
    with patch(
        "identity.api.platform_pricing.record", side_effect=RuntimeError("audit unavailable")
    ):
        response = await client.post(
            "/v1/platform/pricing", headers=signed(key), json={**BODY, "code": "rolled-back"}
        )
        assert response.status_code == 500
        assert "audit unavailable" not in response.text
    async with factory() as db:
        assert (
            await db.scalar(select(PlatformPrice.id).where(PlatformPrice.code == "rolled-back"))
            is None
        )


async def test_read_write_missing_revoked_and_stale_authority(client, setup_app, factory):
    key, installation = await complete(client, setup_app)
    assert (await client.get("/v1/platform/pricing")).status_code == 401
    old = bearer(
        key, email="admin@example.com", email_verified=True, auth_time=int(time.time()) - 900
    )
    assert (await client.get("/v1/platform/pricing", headers=old)).status_code == 200
    assert (await client.post("/v1/platform/pricing", headers=old, json=BODY)).status_code == 403
    with tenant_scope(uuid.UUID(installation["tenant_id"])):
        async with factory() as db, db.begin():
            (await db.scalar(select(RoleAssignment))).is_active = False
    assert (await client.get("/v1/platform/pricing", headers=signed(key))).status_code == 403
    assert (
        await client.post("/v1/platform/pricing", headers=signed(key), json=BODY)
    ).status_code == 403


async def test_seed_values_idempotence_and_admin_edits(factory):
    async with factory() as db, db.begin():
        await seed_pricing(db)
        row = await db.scalar(select(PlatformPrice).where(PlatformPrice.code == "platform-3y"))
        assert row.monthly_fee == Decimal("389") and row.term_months == 36
        row.monthly_fee, row.is_active = Decimal("400"), False
        await seed_pricing(db)
        assert row.monthly_fee == Decimal("400") and not row.is_active
        assert await db.scalar(select(func.count()).select_from(PlatformPrice)) == 9
        assert await db.scalar(select(func.count()).select_from(PlatformPriceRevision)) == 9


@pytest.mark.parametrize(
    "values",
    [
        {"monthly_fee": "-1"},
        {"monthly_fee": "NaN"},
        {"monthly_fee": "1.00001"},
        {"tax_percent": "101"},
        {"fx_inr_per_usd": "0"},
        {"term_months": 2},
        {"unit": "messages"},
        {"code": "bad code"},
        {"name": "   "},
        {"name": "bad\x00"},
        {"category": "sms", "term_months": 1, "unit": "segments", "unit_price": "0"},
        {"category": "llm", "term_months": 1, "unit": "tokens", "unit_price": "1"},
        {"currency_code": "USD"},
        {"usd_monthly_fee": "0.01"},
    ],
)
def test_invalid_price_definitions(values):
    with pytest.raises(ValueError):
        PlatformPriceInput.model_validate({**BODY, **values})


async def test_bounded_lists_and_bound_cursors(client, setup_app):
    key, _ = await complete(client, setup_app)
    for code in ["custom-aa", "custom-bb", "custom-cc"]:
        await create(client, key, code=code)
    first = (await client.get("/v1/platform/pricing?limit=2", headers=signed(key))).json()
    assert len(first["items"]) == 2 and first["page"]["has_more"]
    cursor = first["page"]["next_cursor"]
    following = (
        await client.get(
            "/v1/platform/pricing", params={"limit": 2, "cursor": cursor}, headers=signed(key)
        )
    ).json()
    assert len(following["items"]) == 1
    assert (
        await client.get(
            "/v1/platform/pricing",
            params={"category": "sms", "cursor": cursor},
            headers=signed(key),
        )
    ).status_code == 422
    assert (
        await client.get("/v1/platform/pricing?limit=201", headers=signed(key))
    ).status_code == 422


async def test_valid_grants_without_configured_operator_cannot_manage_catalog(
    client, setup_app, factory
):
    key, _ = await complete(client, setup_app)
    from identity.models import PlatformInstallation

    async with factory() as db, db.begin():
        installation = await db.scalar(select(PlatformInstallation))
        installation.administrator_subject = "different-subject"
    assert (await client.get("/v1/platform/pricing", headers=signed(key))).status_code == 403
    assert (
        await client.post("/v1/platform/pricing", headers=signed(key), json=BODY)
    ).status_code == 403
