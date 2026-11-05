from __future__ import annotations

import pytest
from billing_platform.db.reference_management import ReferenceRevision
from sqlalchemy import select

from identity.models import Country, Currency
from tests.test_platform_setup import BODY, signed

pytest_plugins = ["tests.test_platform_setup"]


@pytest.mark.parametrize("kind", ["countries", "states", "languages", "currencies"])
async def test_reference_directory_requires_authentication(client, kind):
    assert (await client.get(f"/v1/platform/references/{kind}")).status_code == 401


async def test_country_directory_lean_and_create_duplicate_validation(setup_app, client, factory):
    _, key, access = setup_app
    assert (
        await client.post("/v1/setup/complete", json=BODY, headers={**access, **signed(key)})
    ).status_code == 200
    async with factory() as db, db.begin():
        for model in [Country, Currency]:
            for row in await db.scalars(select(model)):
                db.add(
                    ReferenceRevision(
                        kind=model.__tablename__,
                        code=row.code,
                        name=row.name,
                        parent_code=getattr(row, "default_currency_code", None),
                        is_active=row.is_active,
                        source="seed",
                        version=0,
                        payload={
                            column.name: getattr(row, column.name)
                            for column in model.__table__.columns
                        },
                    )
                )
    response = await client.get("/v1/platform/references/countries?sort=name", headers=signed(key))
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["code"] == "IN" and "official_name" not in item
    duplicate = await client.post(
        "/v1/platform/references/countries",
        headers=signed(key),
        json={
            "kind": "country",
            "code": "IN",
            "iso3": "IND",
            "numeric_code": "356",
            "name": "India",
            "official_name": "Republic of India",
            "default_currency_code": "INR",
            "phone_prefix": "+91",
            "subdivision_label": "State",
        },
    )
    assert duplicate.status_code == 409, duplicate.text
