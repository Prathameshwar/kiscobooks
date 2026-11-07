"""The Simple picker excludes units the selected published type cannot admit."""

import uuid

from billing_platform.db import tenant_scope
from sqlalchemy import select

from catalog.models.commercial import ProductTypeRevision
from catalog.models.units import UnitOfMeasure
from tests.test_simple_product_creation import starter


async def test_grams_is_offered_only_for_a_mass_compatible_type(client, factory, tenant_a):
    root, auth, _ = await starter(factory, tenant_a, inventory=True)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.scalar(
                select(ProductTypeRevision).where(ProductTypeRevision.company_id == company)
            )
            grams = await db.scalar(
                select(UnitOfMeasure).where(
                    UnitOfMeasure.company_id == company, UnitOfMeasure.name == "Grams"
                )
            )
            assert revision is not None and grams is not None
            revision.unit_dimensions = ["COUNT"]
            revision_id, grams_id = revision.id, grams.id
    path = f"/v1/companies/{company}/option-sources/catalog.units"
    response = await client.get(
        path, params={"q": "Grams", "product_type_revision_id": str(revision_id)},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    assert all(row["value"] != str(grams_id) for row in response.json()["items"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(ProductTypeRevision, revision_id)
            assert revision is not None
            revision.unit_dimensions = ["COUNT", "MASS"]
    response = await client.get(
        path, params={"q": "Grams", "product_type_revision_id": str(revision_id)},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    assert any(row["value"] == str(grams_id) for row in response.json()["items"])
