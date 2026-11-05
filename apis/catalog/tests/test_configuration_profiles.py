import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ProductFamily, ProductTypeRevision
from catalog.models.warranties import WarrantyPolicy, WarrantyPolicyRevision
from tests.commercial_factories import reference_data
from tests.configuration_factories import publish_configuration
from tests.product_definition_factories import seed_definitions
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.warranty_factories import seed_policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_company_profile_and_price_defaults_replace_native_optional_defaults(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    await reference_data(factory)
    company, ids = await seed_definitions(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    base = f"/v1/companies/{company}"
    _, default_id = await seed_policy(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            default = await db.get(WarrantyPolicyRevision, default_id)
            assert default is not None
            default.published_at = utcnow()
            family = await db.get(ProductFamily, ids["product_family"])
            assert family is not None
            type_revision = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert type_revision is not None
            type_revision.warranty_revision_id = default_id
            second = WarrantyPolicy(
                id=uuid7(), tenant_id=tenant_a, company_id=company, code="SECOND", name="Second"
            )
            db.add(second)
            await db.flush()
            replacement = WarrantyPolicyRevision(
                tenant_id=tenant_a,
                company_id=company,
                policy_id=second.id,
                revision=1,
                duration=6,
                duration_unit="MONTHS",
                start_trigger="SALE",
                published_at=utcnow(),
            )
            db.add(replacement)
            await db.flush()
            replacement_id = str(replacement.id)
            type_revision_id = str(type_revision.id)
    await publish_configuration(
        client,
        base,
        auth,
        scope_id=str(ids["product_configuration_scope"]),
        effective_from="2091-01-01",
        profiles={"warranty_revision_mode": "VALUE", "warranty_revision_id": replacement_id},
        numeric_defaults=[
            {
                "dimension": "COUNT",
                "price_decimal_places": 2,
                "price_increment": "0.05",
                "currency": "INR",
            }
        ],
    )
    params = {"as_of": "2091-01-01", "kind": "GOODS", "item_id": str(ids["item"])}
    effective = await client.get(
        base + "/product-configuration/effective", headers=auth, params=params
    )
    assert effective.status_code == 200, effective.text
    assert effective.json()["profiles"]["warranty_revision_id"] == replacement_id
    await publish_configuration(
        client,
        base,
        auth,
        effective_from="2091-01-02",
        scope_id=str(ids["product_configuration_scope"]),
        profiles={"warranty_revision_mode": "CLEAR"},
        numeric_defaults=[{"dimension": "COUNT", "price_decimal_places": 4, "currency": "INR"}],
    )
    params["as_of"] = "2091-01-02"
    effective = await client.get(
        base + "/product-configuration/effective", headers=auth, params=params
    )
    assert effective.status_code == 200, effective.text
    assert effective.json()["profiles"]["warranty_revision_id"] is None
    assert effective.json()["numeric_defaults"][0]["price_increment"] is None
    assert effective.json()["numeric_defaults"][0]["price_decimal_places"] == 4
    await publish_configuration(
        client,
        base,
        auth,
        effective_from="2091-01-03",
        scope_id=str(ids["product_configuration_scope"]),
        profiles={"warranty_revision_mode": "VALUE", "warranty_revision_id": replacement_id},
    )
    params["as_of"] = "2091-01-03"
    effective = await client.get(
        base + "/product-configuration/effective", headers=auth, params=params
    )
    assert effective.json()["profiles"]["warranty_revision_id"] == replacement_id
    common = {
        "scope_id": str(ids["product_configuration_scope"]),
        "effective_from": "2092-01-01",
        "change_reason": "Invalid",
    }
    for values, status in (
        (
            {
                "numeric_defaults": [
                    {"dimension": "COUNT", "price_decimal_places": 2, "currency": "ZZZ"}
                ]
            },
            422,
        ),
        ({"pricing": {"sale_level_count": 2}}, 409),
        (
            {
                "profiles": {
                    "service_type_revision_mode": "VALUE",
                    "service_type_revision_id": type_revision_id,
                }
            },
            409,
        ),
    ):
        invalid = await client.post(
            base + "/product-configurations",
            headers=command_headers(auth),
            json={**common, **values},
        )
        assert invalid.status_code == status, invalid.text
