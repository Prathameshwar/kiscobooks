"""Form configuration must describe the native requirements used by Save."""

import pytest
from billing_platform.company_context import verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select

from catalog.models.commercial import ProductTypeRevision
from catalog.models.configuration import ProductEntryOptionPolicy
from catalog.models.simple_product_creation import SimpleProductCreation
from catalog.tasks.projections import activate_snapshot
from tests.conftest import ACTOR_SECRET
from tests.source_factories import company_record, snapshot
from tests.test_simple_product_creation import finish, starter

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
async def test_options_include_selected_default_type_requirements(client, factory, tenant_a, kind):
    root, auth, unit = await starter(factory, tenant_a)
    # Represent a published custom default type whose required Brand is inherited.
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = (await db.scalars(select(ProductTypeRevision))).one()
            revision.require_brand = True
            policy = await db.scalar(
                select(ProductEntryOptionPolicy).where(
                    ProductEntryOptionPolicy.revision_id.is_not(None)
                )
            )
            policy.brand_mode, policy.brand_default = "INHERIT", None
    options = await client.get(
        root + "/simple-product-creations/options", headers=auth, params={"kind": kind}
    )
    assert options.status_code == 200, options.text
    assert options.json()["configuration"]["options"]["brand_mode"] == "REQUIRED"
    rejected = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={"kind": kind, "name": "Needs a brand", "base_unit_id": unit},
    )
    assert rejected.status_code == 422, rejected.text
    assert "brand_id" in rejected.json()["error"]["fields"]


async def test_start_does_not_disclose_protected_code_or_save_unreadable_receipt(
    client, factory, tenant_a
):
    root, auth, unit = await starter(factory, tenant_a)
    context = verify_company_context(
        auth["x-company-context"], auth["x-company-signature"], ACTOR_SECRET.encode()
    )
    records = (
        company_record(context.company_id),
        SnapshotRecord(kind="user", id=context.user_id, data={"status": "active"}),
        SnapshotRecord(
            kind="field_policy",
            id=uuid7(),
            data={
                "subject_type": "user",
                "subject_id": str(context.user_id),
                "entity_type": "catalog.item",
                "field_key": "sku",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(context.company_id),
                "condition": None,
                "is_active": True,
            },
        ),
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, context.company_id, records, version=3))
    result = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={"name": "Private code", "base_unit_id": unit},
    )
    assert result.status_code == 403, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(SimpleProductCreation.id))) == 0


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
async def test_published_configuration_controls_form_and_ready_product(
    client, factory, tenant_a, kind
):
    from decimal import Decimal

    from catalog.models.configuration import ProductConfigurationScope
    from catalog.models.pricing import ItemMrp, ItemPrice
    from catalog.schemas.configuration import EntryOptions, PricingRequirements, ProfileDefaults
    from tests.configuration_factories import publish_configuration

    root, auth, unit = await starter(factory, tenant_a)
    initial = await client.get(root + "/simple-product-creations/options", headers=auth)
    assert initial.status_code == 200, initial.text
    configuration = initial.json()["configuration"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            scope_id = str((await db.scalars(select(ProductConfigurationScope))).one().id)
    values = {
        section: {key: configuration[section][key] for key in schema.model_fields}
        for section, schema in (
            ("options", EntryOptions),
            ("profiles", ProfileDefaults),
            ("pricing", PricingRequirements),
        )
    }
    # Copy the complete published profile, including the service default omitted
    # from Goods-only effective settings.
    revision_id = configuration["sources"][0]["revision_id"]
    published = await client.get(
        root + "/product-configuration-revisions/" + revision_id, headers=auth
    )
    assert published.status_code == 200, published.text
    values["profiles"] = {
        key: published.json()["profiles"][key] for key in ProfileDefaults.model_fields
    }
    values["options"]["model_mode"] = "REQUIRED"
    values["pricing"].update(sale_price_mode="DISABLED", mrp_mode="REQUIRED")
    await publish_configuration(
        client, root, auth, scope_id=scope_id, effective_from=initial.json()["today"], **values
    )
    options = await client.get(
        root + "/simple-product-creations/options", headers=auth, params={"kind": kind}
    )
    assert options.status_code == 200, options.text
    result = options.json()
    assert result["configuration"]["options"]["model_mode"] == "REQUIRED"
    fields = {field["key"] for field in result["fields"]}
    assert "sale_price" not in fields
    assert ("mrp" in fields) == (kind == "GOODS")
    body = {"kind": kind, "name": "Configured product", "base_unit_id": unit}
    rejected = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert rejected.status_code == 422 and "model_code" in rejected.json()["error"]["fields"]
    body["model_code"] = "MODEL-1"
    if kind == "GOODS":
        body["mrp"] = "50.00"
    created = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert created.status_code == 201, created.text
    completed = await finish(client, root, auth, created.json()["id"])
    product = await client.get(root + "/products/" + completed["item_id"], headers=auth)
    assert product.status_code == 200 and product.json()["status"] == "ACTIVE", product.text
    assert product.json()["model_code"] == "MODEL-1"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemPrice.id))) == 0
            mrp = await db.scalar(select(ItemMrp))
            if kind == "GOODS":
                assert mrp is not None and isinstance(mrp.amount, Decimal)
                assert mrp.amount == Decimal("50.00")
            else:
                assert mrp is None
