"""Measured entry cannot override declared physical equivalence."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import UnitConversion
from catalog.tasks import activation
from tests.test_commercial_api import command_headers
from tests.unit_integrity_factories import binding_body, latest_revision, new_unit, setup_units

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("global_first", [False, True])
async def test_measured_and_canonical_definitions_cannot_conflict(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    global_first: bool,
) -> None:
    root, auth, ids = await setup_units(factory, tenant_a)
    path = root + f"/items/{ids['item']}"
    base = (await client.get(path, headers=auth)).json()["base_unit_id"]
    alternate = await new_unit(client, root, auth, "ALT")
    relation = {
        "from_unit_id": base,
        "canonical_unit_id": base,
        "numerator": "1",
        "denominator": "1",
    }
    result = await client.post(
        root + "/unit-conversions", headers=command_headers(auth), json=relation
    )
    assert result.status_code == 201, result.text
    relation.update(from_unit_id=alternate, numerator="12")
    if global_first:
        result = await client.post(
            root + "/unit-conversions", headers=command_headers(auth), json=relation
        )
        assert result.status_code == 201, result.text
    result = await client.post(
        path + "/unit-bindings",
        headers=command_headers(auth),
        json=binding_body(
            alternate,
            role="MEASURED",
            conversion_mode="MEASURED",
            numerator=None,
            denominator=None,
            secondary_unit_id=base,
            nominal_ratio="12",
        ),
    )
    assert result.status_code == (409 if global_first else 200), result.text
    if not global_first:
        result = await client.post(
            root + "/unit-conversions", headers=command_headers(auth), json=relation
        )
        assert result.status_code == 409, result.text


async def test_legacy_measured_canonical_conflicts_fail_in_every_consumer(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await setup_units(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    path = root + f"/items/{ids['item']}"
    base = (await client.get(path, headers=auth)).json()["base_unit_id"]
    alternate = await new_unit(client, root, auth, "ALT")
    result = await client.post(
        path + "/unit-bindings",
        headers=command_headers(auth),
        json=binding_body(
            alternate,
            role="MEASURED",
            conversion_mode="MEASURED",
            numerator=None,
            denominator=None,
            secondary_unit_id=base,
            nominal_ratio="12",
        ),
    )
    assert result.status_code == 200, result.text
    revision = await latest_revision(client, root, auth, ids["item"], "ALT")
    positive = await client.post(
        path + "/quantity-preview",
        headers=auth,
        json={
            "as_of": "2090-01-01",
            "components": [
                {"unit_revision_id": revision["id"], "quantity": "1", "measured_base_quantity": "2"}
            ],
        },
    )
    assert (
        positive.status_code == 200 and positive.json()["base_quantity"] == "2.0000"
    ), positive.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            for unit, numerator in ((base, 1), (alternate, 12)):
                db.add(
                    UnitConversion(
                        tenant_id=tenant_a,
                        company_id=company,
                        from_unit_id=uuid.UUID(unit),
                        canonical_unit_id=uuid.UUID(base),
                        numerator=numerator,
                        denominator=1,
                    )
                )
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    for route, body in (
        (
            path + "/quantity-preview",
            {
                "components": [
                    {
                        "unit_revision_id": revision["id"],
                        "quantity": "1",
                        "measured_base_quantity": "2",
                    }
                ]
            },
        ),
        (
            root + "/prices/resolve",
            {
                "item_id": str(ids["item"]),
                "unit_revision_id": revision["id"],
                "quantity": "1",
                "currency": "INR",
            },
        ),
        (path + "/activation-preview", {}),
    ):
        result = await client.post(route, headers=auth, json={"as_of": "2090-01-01", **body})
        assert result.status_code == 409 and "canonical" in result.text, result.text
