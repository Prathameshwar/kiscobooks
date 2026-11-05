from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.reference_management import ReferenceRevision
from billing_platform.reference.seed import seed_reference
from sqlalchemy import select

from identity.models import Country, Currency, Language, Outbox, ReferenceChange, State
from tests.test_gap_login import bearer
from tests.test_platform_setup import BODY, signed

pytest_plugins = ["tests.test_platform_setup"]
DATA = {
    "countries": {
        "kind": "country",
        "code": "ZZ",
        "iso3": "ZZZ",
        "numeric_code": "999",
        "name": "Test territory",
        "official_name": "Test territory",
        "default_currency_code": "INR",
        "phone_prefix": "+999",
        "subdivision_label": "Province",
    },
    "states": {
        "kind": "state",
        "code": "IN-LA",
        "country_code": "IN",
        "name": "Test subdivision",
        "subdivision_type": "Province",
        "tax_jurisdiction_code": "38",
    },
    "languages": {
        "kind": "language",
        "code": "zz",
        "iso3": "zzz",
        "name": "Test language",
        "native_name": None,
    },
    "currencies": {
        "kind": "currency",
        "code": "ZZZ",
        "numeric_code": "999",
        "name": "Test currency",
        "symbol": "Z",
        "minor_unit": 2,
        "major_unit_name": "Test units",
        "minor_unit_name": "Cent",
        "minor_unit_name_plural": "Cents",
    },
}


async def ready(setup_app, client, factory):
    _, key, access = setup_app
    response = await client.post("/v1/setup/complete", json=BODY, headers={**access, **signed(key)})
    assert response.status_code == 200, response.text
    async with factory() as db, db.begin():
        for model in [Country, Currency]:
            for row in await db.scalars(select(model)):
                if (
                    await db.scalar(
                        select(ReferenceRevision).where(
                            ReferenceRevision.kind == model.__tablename__,
                            ReferenceRevision.code == row.code,
                        )
                    )
                    is None
                ):
                    db.add(
                        ReferenceRevision(
                            kind=model.__tablename__,
                            code=row.code,
                            name=row.name,
                            parent_code=getattr(row, "default_currency_code", None),
                            is_active=row.is_active,
                            source="seed",
                            version=0,
                            payload={c.name: getattr(row, c.name) for c in model.__table__.columns},
                        )
                    )
    return key, response.json()


@pytest.mark.parametrize("kind", list(DATA))
async def test_crud_preserves_codes_history_seed_and_emits_audit(kind, setup_app, client, factory):
    key, result = await ready(setup_app, client, factory)
    data = DATA[kind]
    path = "/v1/platform/references/" + kind
    created = await client.post(path, json=data, headers=signed(key))
    assert created.status_code == 201, created.text
    value = created.json()
    assert value["version"] == 1 and not value["sync_ready"]
    edited = await client.patch(
        path + "/" + data["code"],
        json={"version": 1, "data": {**value["data"], "name": "Reviewed reference"}},
        headers=signed(key),
    )
    assert edited.status_code == 200, edited.text
    stale = await client.patch(
        path + "/" + data["code"],
        json={"version": 1, "data": edited.json()["data"]},
        headers=signed(key),
    )
    assert stale.status_code == 409
    deleted = await client.post(
        path + "/" + data["code"] + "/archive",
        json={"version": 2, "reason": "Test archive"},
        headers=signed(key),
    )
    assert deleted.status_code == 200, deleted.text
    assert not deleted.json()["is_active"]
    model = {"countries": Country, "states": State, "currencies": Currency, "languages": Language}[
        kind
    ]
    async with factory() as db, db.begin():
        await seed_reference(db, datasets=("currency", "country", "state", "language"))
        row = await db.get(model, data["code"])
        assert row is not None and not row.is_active and row.name == "Reviewed reference"
    restored = await client.post(
        path + "/" + data["code"] + "/restore",
        json={"version": 3, "reason": "Test restore"},
        headers=signed(key),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["is_active"]
    async with factory() as db:
        assert len(list(await db.scalars(select(ReferenceChange)))) == 4
        with tenant_scope(uuid.UUID(result["tenant_id"])):
            assert (
                len(
                    list(
                        await db.scalars(
                            select(Outbox).where(Outbox.event_type.like("platform.reference_%"))
                        )
                    )
                )
                == 4
            )


async def test_dependency_protection_input_validation_and_fresh_auth(setup_app, client, factory):
    key, _ = await ready(setup_app, client, factory)
    path = "/v1/platform/references/countries/IN"
    blocked = await client.post(
        path + "/archive", json={"version": 0, "reason": "Cannot archive"}, headers=signed(key)
    )
    assert blocked.status_code == 409
    detail = (await client.get(path, headers=signed(key))).json()
    invalid = await client.patch(
        path, json={"version": 0, "data": {**detail["data"], "iso3": "ZZZ"}}, headers=signed(key)
    )
    assert invalid.status_code == 422
    staleauth = await client.post(
        "/v1/platform/references/languages",
        json=DATA["languages"],
        headers=bearer(
            key, email="admin@example.com", email_verified=True, auth_time=int(time.time()) - 600
        ),
    )
    assert staleauth.status_code == 403
    badpair = await client.post(
        "/v1/platform/references/states",
        json={**DATA["states"], "country_code": "US"},
        headers=signed(key),
    )
    assert badpair.status_code == 422
    unknown = await client.get(
        "/v1/platform/references/countries?email=private", headers=signed(key)
    )
    assert unknown.status_code == 422
    async with factory() as db:
        assert not list(await db.scalars(select(ReferenceChange)))


async def test_audit_failure_rolls_back_native_record_and_change_journal(
    setup_app, client, factory
):
    key, _ = await ready(setup_app, client, factory)
    with patch(
        "identity.services.reference_management.record",
        side_effect=RuntimeError("audit unavailable"),
    ):
        response = await client.post(
            "/v1/platform/references/languages", json=DATA["languages"], headers=signed(key)
        )
        assert response.status_code == 500
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["error"]["code"] == "internal_error"
        assert "audit unavailable" not in response.text
    async with factory() as db:
        assert await db.get(Language, "zz") is None
        assert not list(await db.scalars(select(ReferenceChange)))


async def test_duplicate_json_and_invalid_archive_reasons_are_rejected(setup_app, client, factory):
    key, _ = await ready(setup_app, client, factory)
    path = "/v1/platform/references/languages"
    duplicate = await client.post(
        path,
        content='{"kind":"language","code":"zz","code":"yy","iso3":"zzz","name":"Test"}',
        headers={**signed(key), "Content-Type": "application/json"},
    )
    assert duplicate.status_code == 422
    for reason in ["   ", "a\nb", "\x00bad"]:
        result = await client.post(
            path + "/en/archive", json={"version": 0, "reason": reason}, headers=signed(key)
        )
        assert result.status_code == 422
    oversized = await client.post(
        path,
        content='{"name":"' + ("a" * 17000) + '"}',
        headers={**signed(key), "Content-Type": "application/json"},
    )
    assert oversized.status_code == 422
    async with factory() as db:
        assert not list(await db.scalars(select(ReferenceChange)))


async def test_live_authority_and_operator_restriction(setup_app, client, factory):
    from identity.models import PlatformInstallation, RolePermission

    key, result = await ready(setup_app, client, factory)
    path = "/v1/platform/references/languages"
    assert (await client.get(path, headers=signed(key))).status_code == 200
    unverified = bearer(
        key, email="admin@example.com", email_verified=False, auth_time=int(time.time())
    )
    assert (await client.post(path, json=DATA["languages"], headers=unverified)).status_code == 403
    async with factory() as db, db.begin():
        with tenant_scope(uuid.UUID(result["tenant_id"])):
            permissions = list(
                await db.scalars(
                    select(RolePermission).where(
                        RolePermission.permission_key == "platform.config.manage"
                    )
                )
            )
            for permission in permissions:
                await db.delete(permission)
    # Warm cached grants cannot override the live write authorization check.
    assert (await client.post(path, json=DATA["languages"], headers=signed(key))).status_code == 403
    async with factory() as db, db.begin():
        installation = await db.scalar(select(PlatformInstallation))
        installation.administrator_subject = "different-operator"
    assert (await client.get(path, headers=signed(key))).status_code == 403


async def test_active_addresses_and_currency_allowances_prevent_archival(
    setup_app, client, factory
):
    from identity.models import CompanyCurrencyAllowance
    from tests.factories import build_company, build_company_address, build_state

    key, result = await ready(setup_app, client, factory)
    state = (
        await client.post(
            "/v1/platform/references/states", json=DATA["states"], headers=signed(key)
        )
    ).json()
    currency = (
        await client.post(
            "/v1/platform/references/currencies", json=DATA["currencies"], headers=signed(key)
        )
    ).json()
    tenant_id = uuid.UUID(result["tenant_id"])
    async with factory() as db, db.begin():
        with tenant_scope(tenant_id):
            db.add(build_state(code="IN-MH"))
            await db.flush()
            company = build_company(tenant_id=tenant_id, state_code="IN-LA")
            db.add(company)
            await db.flush()
            address = build_company_address(
                tenant_id=tenant_id, company_id=company.id, state_code="IN-LA"
            )
            allowance = CompanyCurrencyAllowance(
                tenant_id=tenant_id, company_id=company.id, currency_code="ZZZ"
            )
            db.add_all([address, allowance])
            await db.flush()
            # Keep the address dependent while removing the company's direct state use.
            company.state_code = "IN-MH"
    for kind, value in [("states", state), ("currencies", currency)]:
        blocked = await client.post(
            f"/v1/platform/references/{kind}/{value['code']}/archive",
            json={"version": 1, "reason": "Protected dependency"},
            headers=signed(key),
        )
        assert blocked.status_code == 409, blocked.text
    async with factory() as db, db.begin():
        with tenant_scope(tenant_id):
            address = await db.get(type(address), address.id)
            address.is_active = False
            allowance = await db.get(CompanyCurrencyAllowance, allowance.id)
            allowance.is_active = False
    for kind, value in [("states", state), ("currencies", currency)]:
        archived = await client.post(
            f"/v1/platform/references/{kind}/{value['code']}/archive",
            json={"version": 1, "reason": "Unused dependency"},
            headers=signed(key),
        )
        assert archived.status_code == 200, archived.text
