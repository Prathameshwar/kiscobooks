"""Simple categories/manufacturer use protected native records before activation."""

import pytest
from billing_platform.company_context import verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select

from catalog.models.classification import CategoryScheme, ItemCategory
from catalog.models.commercial import Manufacturer, ManufacturerSite
from catalog.models.configuration import ProductEntryOptionPolicy
from catalog.models.product_definitions import FamilyCategory, FamilyManufacturer
from catalog.models.products import Item
from tests.commercial_factories import reference_data
from tests.conftest import ACTOR_SECRET
from tests.test_simple_product_creation import finish, starter
from tests.test_simple_product_import import fresh_company_context
from tests.test_unit_defaults import provision

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.fixture(autouse=True)
def fresh_context(client):
    client.event_hooks["request"].append(fresh_company_context)


async def setup_details(factory, tenant, mode="REQUIRED"):
    root, auth, unit = await starter(factory, tenant)
    await reference_data(factory)
    facts = verify_company_context(
        auth["x-company-context"], auth["x-company-signature"], ACTOR_SECRET.encode()
    )
    scheme, category, manufacturer, site = (uuid7() for _ in range(4))
    common = {"tenant_id": tenant, "company_id": facts.company_id, "is_active": True}
    with tenant_scope(tenant):
        async with factory.begin() as db:
            policy = await db.scalar(
                select(ProductEntryOptionPolicy).where(
                    ProductEntryOptionPolicy.revision_id.is_not(None)
                )
            )
            policy.category_mode = policy.manufacturer_mode = mode
            policy.category_default = policy.manufacturer_default = (
                False if mode == "OPTIONAL" else None
            )
            db.add(
                CategoryScheme(
                    id=scheme,
                    code="RANGE",
                    name="Product range",
                    membership_mode="SINGLE",
                    is_required=mode == "REQUIRED",
                    **common,
                )
            )
            db.add(Manufacturer(id=manufacturer, code="MAKER", name="Maker", **common))
            await db.flush()
            db.add(ItemCategory(id=category, scheme_id=scheme, code="TEA", name="Tea", **common))
            db.add(
                ManufacturerSite(
                    id=site,
                    manufacturer_id=manufacturer,
                    code="PLANT",
                    name="Main plant",
                    country_code="IN",
                    **common,
                )
            )
    return root, auth, unit, facts, scheme, category, manufacturer, site


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
async def test_configured_details_create_active_product_once(client, factory, tenant_a, kind):
    root, auth, unit, _, scheme, category, manufacturer, site = await setup_details(
        factory, tenant_a
    )
    options = await client.get(
        root + "/simple-product-creations/options", headers=auth, params={"kind": kind}
    )
    assert options.status_code == 200, options.text
    assert options.json()["required_category_schemes"] == [
        {"id": str(scheme), "name": "Product range", "membership_mode": "SINGLE"}
    ]
    fields = {field["key"] for field in options.json()["fields"]}
    assert {"category_scheme_id", "category_id", "category_is_primary"} <= fields
    assert ("manufacturer_id" in fields) == (kind == "GOODS")
    body = {
        "name": "Classified product",
        "kind": kind,
        "base_unit_id": unit,
        "sale_price": "10.25",
        "categories": [
            {"scheme_id": str(scheme), "category_id": str(category), "is_primary": True}
        ],
    }
    if kind == "GOODS":
        body |= {"manufacturer_id": str(manufacturer), "manufacturer_site_id": str(site)}
    signed = auth | {"Idempotency-Key": str(uuid7())}
    started = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert started.status_code == 201, started.text
    done = await finish(client, root, auth, started.json()["id"])
    replay = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert replay.status_code == 201 and replay.json()["id"] == done["id"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            item = (await db.scalars(select(Item))).one()
            assert item.status == "ACTIVE"
            membership = (await db.scalars(select(FamilyCategory))).one()
            assert membership.category_id == category and membership.is_primary
            assert membership.family_id == item.family_id
            manufacturers = list(await db.scalars(select(FamilyManufacturer)))
            assert len(manufacturers) == int(kind == "GOODS")
            if manufacturers:
                assert (
                    manufacturers[0].manufacturer_id == manufacturer
                    and manufacturers[0].site_id == site
                )
                assert manufacturers[0].production_role == "MANUFACTURER"


async def test_disabled_required_and_invalid_relationships_reject_before_creation(
    client, factory, tenant_a
):
    root, auth, unit, facts, scheme, category, manufacturer, site = await setup_details(
        factory, tenant_a, "OPTIONAL"
    )
    base = {"name": "Review details", "base_unit_id": unit}

    async def send(extra):
        return await client.post(
            root + "/simple-product-creations",
            headers=auth | {"Idempotency-Key": str(uuid7())},
            json=base | extra,
        )

    other_manufacturer, other_scheme, other_category = uuid7(), uuid7(), uuid7()
    second_category, foreign_manufacturer, foreign_scheme, foreign_category = (
        uuid7() for _ in range(4)
    )
    foreign_company = uuid7()
    await provision(factory, tenant_a, foreign_company, user=uuid7(), inventory=False)
    common = {"tenant_id": tenant_a, "company_id": facts.company_id, "is_active": True}
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(Manufacturer(id=other_manufacturer, code="OTHER", name="Other", **common))
            foreign = common | {"company_id": foreign_company}
            db.add(Manufacturer(id=foreign_manufacturer, code="FOREIGN", name="Foreign", **foreign))
            db.add(
                CategoryScheme(
                    id=foreign_scheme,
                    code="FOREIGN",
                    name="Foreign",
                    membership_mode="SINGLE",
                    **foreign,
                )
            )
            db.add(
                CategoryScheme(
                    id=other_scheme,
                    code="OTHER",
                    name="Other",
                    membership_mode="MULTIPLE",
                    **common,
                )
            )
            await db.flush()
            db.add(
                ItemCategory(
                    id=other_category, scheme_id=other_scheme, code="OTHER", name="Other", **common
                )
            )
            db.add(
                ItemCategory(
                    id=second_category, scheme_id=scheme, code="SECOND", name="Second", **common
                )
            )
            db.add(
                ItemCategory(
                    id=foreign_category,
                    scheme_id=foreign_scheme,
                    code="FOREIGN",
                    name="Foreign",
                    **foreign,
                )
            )
    foreign = await send({"manufacturer_id": str(foreign_manufacturer)})
    assert foreign.status_code == 403, foreign.text
    foreign = await send(
        {"categories": [{"scheme_id": str(foreign_scheme), "category_id": str(foreign_category)}]}
    )
    assert foreign.status_code == 403, foreign.text
    cardinality = await send(
        {
            "categories": [
                {"scheme_id": str(scheme), "category_id": str(entry)}
                for entry in (category, second_category)
            ]
        }
    )
    assert cardinality.status_code == 422 and "categories" in cardinality.json()["error"]["fields"]
    mismatch = await send(
        {"manufacturer_id": str(other_manufacturer), "manufacturer_site_id": str(site)}
    )
    assert mismatch.status_code == 403, mismatch.text
    mismatch = await send(
        {"categories": [{"scheme_id": str(other_scheme), "category_id": str(category)}]}
    )
    assert mismatch.status_code == 403, mismatch.text
    service = await send({"kind": "SERVICE", "manufacturer_id": str(manufacturer)})
    assert service.status_code == 422, service.text
    orphan = await send({"manufacturer_site_id": str(site)})
    assert orphan.status_code == 422, orphan.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            policy = await db.scalar(
                select(ProductEntryOptionPolicy).where(
                    ProductEntryOptionPolicy.revision_id.is_not(None)
                )
            )
            policy.category_mode = policy.manufacturer_mode = "DISABLED"
            policy.category_default = policy.manufacturer_default = None
    disabled = await send(
        {"categories": [{"scheme_id": str(scheme), "category_id": str(category)}]}
    )
    assert disabled.status_code == 422, disabled.text
    disabled = await send({"manufacturer_id": str(manufacturer)})
    assert disabled.status_code == 422, disabled.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            policy = await db.scalar(
                select(ProductEntryOptionPolicy).where(
                    ProductEntryOptionPolicy.revision_id.is_not(None)
                )
            )
            policy.category_mode = policy.manufacturer_mode = "REQUIRED"
    missing = await send({"manufacturer_id": str(manufacturer)})
    assert missing.status_code == 422 and "categories" in missing.json()["error"]["fields"]
    missing = await send({"categories": [{"scheme_id": str(scheme), "category_id": str(category)}]})
    assert missing.status_code == 422 and "manufacturer_id" in missing.json()["error"]["fields"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 0


@pytest.mark.parametrize(
    "entity,field", [("family_category", "category_id"), ("family_manufacturer", "manufacturer_id")]
)
async def test_field_write_denial_rolls_back_initial_assignments(
    client, factory, tenant_a, entity, field
):
    root, auth, unit, facts, scheme, category, manufacturer, site = await setup_details(
        factory, tenant_a
    )
    await provision(
        factory,
        tenant_a,
        facts.company_id,
        user=facts.user_id,
        inventory=False,
        version=3,
        policies=(
            SnapshotRecord(
                kind="field_policy",
                id=uuid7(),
                data={
                    "subject_type": "user",
                    "subject_id": str(facts.user_id),
                    "entity_type": "catalog." + entity,
                    "field_key": field,
                    "access": "write",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(facts.company_id),
                    "condition": None,
                    "is_active": True,
                },
            ),
        ),
    )
    options = await client.get(root + "/simple-product-creations/options", headers=auth)
    assert options.status_code == 200, options.text
    assert not next(value for value in options.json()["fields"] if value["key"] == field)[
        "writable"
    ]
    started = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={
            "name": "Protected details",
            "base_unit_id": unit,
            "manufacturer_id": str(manufacturer),
            "manufacturer_site_id": str(site),
            "categories": [{"scheme_id": str(scheme), "category_id": str(category)}],
        },
    )
    assert started.status_code == 201, started.text
    rejected = await client.post(
        root + "/simple-product-creations/" + started.json()["id"] + "/advance", headers=auth
    )
    assert rejected.status_code == 403, rejected.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 0
            assert await db.scalar(select(func.count(FamilyCategory.id))) == 0
            assert await db.scalar(select(func.count(FamilyManufacturer.id))) == 0


def test_legacy_creation_request_omits_empty_new_details():
    from catalog.schemas.simple_product_creation import SimpleCreationInput
    from catalog.tasks.simple_product_creation import creation_request

    assert (
        not {"categories", "manufacturer_id", "manufacturer_site_id"}
        & creation_request(SimpleCreationInput(name="Legacy", base_unit_id=uuid7())).keys()
    )


async def test_required_schemes_and_import_guidance_keep_reference_fields_protected(
    client, factory, tenant_a
):
    root, auth, unit, facts, _, _, manufacturer, _ = await setup_details(factory, tenant_a)
    missing = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={
            "name": "Missing required category",
            "base_unit_id": unit,
            "manufacturer_id": str(manufacturer),
        },
    )
    assert missing.status_code == 422, missing.text
    assert "Product range" in missing.json()["error"]["fields"]["categories"]
    template = await client.post(
        root + "/import-templates",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={
            "definition": "simple_products",
            "parameters": {"resource": "simple_product_create", "kind": "GOODS"},
        },
    )
    assert template.status_code == 409, template.text
    assert "required category, manufacturer" in template.json()["error"]["message"]
    await provision(
        factory,
        tenant_a,
        facts.company_id,
        user=facts.user_id,
        inventory=False,
        version=3,
        policies=(
            SnapshotRecord(
                kind="field_policy",
                id=uuid7(),
                data={
                    "subject_type": "user",
                    "subject_id": str(facts.user_id),
                    "entity_type": "catalog.category_scheme",
                    "field_key": "name",
                    "access": "read",
                    "effect": "deny",
                    "scope_type": "company",
                    "scope_id": str(facts.company_id),
                    "condition": None,
                    "is_active": True,
                },
            ),
        ),
    )
    denied = await client.get(root + "/simple-product-creations/options", headers=auth)
    assert denied.status_code == 403, denied.text
    assert "Product range" not in denied.text
