import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    FamilyGroupAssignment,
    ItemUnitRevision,
    ProductConfigurationAdoption,
    ProductConfigurationRevision,
    ProductFamily,
    ProductTypeRevision,
)
from tests.product_definition_factories import seed_definitions
from tests.product_review_factories import changed
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_adoption_tokens_history_and_pinned_structure_cannot_be_rewritten(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    path = f"/v1/companies/{company}/items/{ids['item']}"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            assert family is not None
            revision = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert revision is not None
            revision.inventory_modes = ["NON_STOCK"]
            replacement = ProductTypeRevision(
                tenant_id=tenant_a,
                company_id=company,
                product_type_id=revision.product_type_id,
                revision=2,
                kind=revision.kind,
                inventory_modes=revision.inventory_modes,
                tracking_modes=revision.tracking_modes,
                unit_dimensions=revision.unit_dimensions,
                allow_variants=revision.allow_variants,
                require_brand=False,
                require_manufacturer=False,
                require_expiry=False,
                published_at=revision.published_at,
            )
            db.add(replacement)
            await db.flush()
            replacement_id = replacement.id

    async def preview(date: str = "2090-01-01") -> dict[str, Any]:
        response = await client.get(
            path + "/configuration-adoption/preview", headers=auth, params={"as_of": date}
        )
        assert response.status_code == 200, response.text
        assert response.json()["eligible"] is True, response.text
        return {
            "expected_version": 1,
            "as_of": date,
            "preview_token": response.json()["preview_token"],
        }

    body = await preview()
    invalid = await client.post(
        path + "/configuration-adoption",
        headers=command_headers(auth),
        json={**body, "preview_token": body["preview_token"] + "invalid"},
    )
    assert invalid.status_code == 422, invalid.text
    for prior_values in ({"revision": 2147483647}, {"effective_on": dt.date(2091, 1, 1)}):
        async with changed(
            factory,
            tenant_a,
            ProductConfigurationAdoption,
            ids["product_configuration_adoption"],
            **prior_values,
        ):
            response = await client.post(
                path + "/configuration-adoption",
                headers=command_headers(auth),
                json=await preview(),
            )
            assert (
                response.status_code == 409 and "prior effective history" in response.text
            ), response.text
    for model, key, values, message in (
        (
            ProductConfigurationAdoption,
            ids["product_configuration_adoption"],
            {"product_type_revision_id": replacement_id},
            "pinned type",
        ),
        (
            ProductConfigurationAdoption,
            ids["product_configuration_adoption"],
            {"group_assignment_id": None},
            "group reassignment",
        ),
        (
            ProductConfigurationRevision,
            ids["product_configuration_revision"],
            {"effective_from": dt.date(2091, 1, 1)},
            "pinned configuration",
        ),
    ):
        async with changed(factory, tenant_a, model, key, **values):
            response = await client.get(
                path + "/configuration", headers=auth, params={"as_of": "2090-01-01"}
            )
            assert response.status_code == 409 and message in response.text, response.text
    adopted = await client.post(
        path + "/configuration-adoption", headers=command_headers(auth), json=await preview()
    )
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["item_version"] == 2


async def test_ambiguous_effective_product_histories_fail_closed(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    path = f"/v1/companies/{company}/items/{ids['item']}/requirements"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            group = FamilyGroupAssignment(
                tenant_id=tenant_a,
                company_id=company,
                family_id=ids["product_family"],
                group_id=ids["item_group"],
                valid_from=dt.date(2089, 1, 1),
            )
            db.add(group)
            await db.flush()
            group_id = group.id
    response = await client.get(path, headers=auth, params={"as_of": "2090-01-01"})
    assert response.status_code == 409 and "ambiguous primary group" in response.text, response.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            previous_group = await db.get(FamilyGroupAssignment, group_id)
            assert previous_group is not None
            previous_group.valid_to = dt.date(2089, 12, 31)
            db.add(
                ItemUnitRevision(
                    tenant_id=tenant_a,
                    company_id=company,
                    binding_id=ids["item_unit_binding"],
                    revision=2,
                    conversion_mode="FIXED",
                    numerator=1,
                    denominator=1,
                    quantity_decimal_places=0,
                    quantity_increment="1",
                    fractional_entry=False,
                    valid_from=dt.date(2089, 1, 1),
                )
            )
    response = await client.get(path, headers=auth, params={"as_of": "2090-01-01"})
    assert (
        response.status_code == 409 and "ambiguous effective revisions" in response.text
    ), response.text
