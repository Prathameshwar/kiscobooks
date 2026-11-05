"""Default suggestions must be usable by the actual native authoring commands."""

import uuid

import httpx
import pytest
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.commercial_factories import reference_data
from tests.configuration_factories import publish_configuration
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_authoring_defaults_are_exact_and_acceptance_is_version_checked(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    await reference_data(factory)
    company, user, _, product = await setup_product(factory, tenant_a, kind="SERVICE")
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    scope, _ = await publish_configuration(
        client,
        root,
        auth,
        profiles={
            "service_type_revision_mode": "VALUE",
            "service_type_revision_id": product["product_type_revision_id"],
        },
        numeric_defaults=[
            {
                "dimension": "TIME",
                "quantity_decimal_places": 2,
                "quantity_increment": "0.20",
                "price_decimal_places": 3,
                "price_increment": "0.005",
                "currency": "INR",
                "price_basis_quantity": "100",
            }
        ],
    )
    params = {
        "kind": "SERVICE",
        "as_of": "2090-01-01",
        "unit_id": product["default_item"]["base_unit_id"],
        "currency": "INR",
    }
    response = await client.get(
        root + "/product-configuration/authoring-defaults", headers=auth, params=params
    )
    assert response.status_code == 200, response.text
    defaults = response.json()
    assert defaults["product_type_revision_id"] == product["product_type_revision_id"]
    assert defaults["quantity"]["quantity_increment"] == "1.0000"
    assert defaults["price"]["price_decimal_places"] == 3
    assert defaults["price"]["price_basis_quantity"] == "100.0000"
    acceptance = defaults["acceptance"]
    created = await client.post(
        root + "/product-families",
        headers=command_headers(auth),
        json={**product, "accept_defaults": acceptance},
    )
    assert created.status_code == 201, created.text
    sku = created.json()["default_item"]["id"]
    response = await client.get(
        root + "/product-configuration/authoring-defaults",
        headers=auth,
        params={**params, "item_id": sku},
    )
    defaults = response.json()
    assert response.status_code == 200, response.text
    for override, message in (
        ({"quantity_increment": "0.25"}, "differ from accepted defaults"),
        ({"valid_from": "2091-01-01"}, "acceptance date differs"),
    ):
        invalid = await client.post(
            root + f"/items/{sku}/unit-bindings",
            headers=command_headers(auth),
            json={
                "expected_version": 1,
                "code": "BASE",
                "role": "BASE",
                "numerator": 1,
                "denominator": 1,
                "valid_from": "2090-01-01",
                **defaults["quantity"],
                "accept_defaults": defaults["acceptance"],
                **override,
            },
        )
        assert invalid.status_code == 409 and message in invalid.text, invalid.text
    binding = await client.post(
        root + f"/items/{sku}/unit-bindings",
        headers=command_headers(auth),
        json={
            "expected_version": 1,
            "code": "BASE",
            "role": "BASE",
            "numerator": 1,
            "denominator": 1,
            "valid_from": "2090-01-01",
            **defaults["quantity"],
            "accept_defaults": defaults["acceptance"],
        },
    )
    assert binding.status_code == 200, binding.text

    bindings = await client.get(root + f"/items/{sku}/unit-bindings", headers=auth)
    binding_id = bindings.json()["items"][0]["id"]
    revisions = await client.get(root + f"/item-unit-bindings/{binding_id}/revisions", headers=auth)
    revision_id = revisions.json()["items"][0]["id"]
    response = await client.get(
        root + "/product-configuration/authoring-defaults",
        headers=auth,
        params={**params, "item_id": sku, "unit_revision_id": revision_id},
    )
    assert response.status_code == 200, response.text
    price_defaults = response.json()
    from catalog.models import ItemUnitRevision
    from tests.product_review_factories import changed

    async with changed(
        factory, tenant_a, ItemUnitRevision, uuid.UUID(revision_id), fractional_entry=False
    ):
        whole_only = await client.get(
            root + "/product-configuration/authoring-defaults",
            headers=auth,
            params={**params, "item_id": sku, "unit_revision_id": revision_id},
        )
        assert whole_only.status_code == 200, whole_only.text
        assert whole_only.json()["quantity"]["fractional_entry"] is False
    numeric = await client.post(
        root + "/price-numeric-revisions",
        headers=command_headers(auth),
        json={
            "item_id": sku,
            "unit_revision_id": revision_id,
            "currency": "INR",
            "price_decimal_places": price_defaults["price"]["price_decimal_places"],
            "price_increment": price_defaults["price"]["price_increment"],
            "valid_from": "2090-01-01",
            "accept_defaults": price_defaults["acceptance"],
            "expected_generation": price_defaults["acceptance"]["expected_generation"],
            "expected_source_version": price_defaults["acceptance"]["expected_source_version"],
        },
    )
    assert numeric.status_code == 201, numeric.text
    stale = await client.post(
        root + "/product-families",
        headers=command_headers(auth),
        json={
            **product,
            "code": "OTHER",
            "default_item": {**product["default_item"], "sku": "OTHER"},
            "accept_defaults": acceptance,
        },
    )
    assert stale.status_code == 409, stale.text
    denied = await client.get(
        root + "/product-configuration/authoring-defaults",
        headers=headers(
            company, tenant=tenant_a, user=user, permission=["product_configuration.read"]
        ),
        params=params,
    )
    assert denied.status_code == 403, denied.text


def test_nested_profile_patches_preserve_references_and_reject_contradictions() -> None:
    from billing_platform.errors import ValidationFailedError

    from catalog.schemas.configuration import DraftInput, DraftPatch
    from catalog.tasks.configuration_editing import merge_draft

    reference = str(uuid.uuid4())
    original = DraftInput.model_validate(
        {
            "scope_id": str(uuid.uuid4()),
            "effective_from": "2090-01-01",
            "change_reason": "Defaults",
            "profiles": {
                "warranty_revision_mode": "VALUE",
                "warranty_revision_id": reference,
                "return_policy_revision_mode": "CLEAR",
            },
            "options": {"brand_mode": "OPTIONAL", "brand_default": True},
        }
    )
    changed = merge_draft(
        original,
        DraftPatch.model_validate(
            {"expected_version": 1, "profiles": {"warranty_revision_mode": "INHERIT"}}
        ),
    )
    assert changed.profiles.warranty_revision_id is None
    assert changed.profiles.return_policy_revision_mode == "CLEAR"
    assert changed.options.brand_default is True
    replacement = uuid.uuid4()
    changed = merge_draft(
        original,
        DraftPatch.model_validate(
            {"expected_version": 1, "profiles": {"warranty_revision_id": str(replacement)}}
        ),
    )
    assert changed.profiles.warranty_revision_id == replacement
    assert changed.profiles.warranty_revision_mode == "VALUE"
    for changes in (
        {"profiles": {"warranty_revision_mode": "CLEAR", "warranty_revision_id": reference}},
        {"options": {"brand_mode": "REQUIRED", "brand_default": True}},
    ):
        with pytest.raises(ValidationFailedError):
            merge_draft(original, DraftPatch.model_validate({"expected_version": 1, **changes}))


async def test_authoring_candidates_require_compatible_types_units_and_price_defaults(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from billing_platform.db import tenant_scope

    from catalog.models import Currency, ProductTypeRevision, UnitOfMeasure
    from tests.test_master_reference_policy import policy

    await reference_data(factory)
    company, user, _, product = await setup_product(factory, tenant_a, kind="SERVICE")
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    path = root + "/product-configuration/authoring-defaults"
    params = {
        "as_of": "2090-01-01",
        "kind": "SERVICE",
        "unit_id": product["default_item"]["base_unit_id"],
    }
    response = await client.get(path, headers=auth, params=params)
    assert response.status_code == 200, response.text
    assert response.json()["missing"] == ["product_type_revision"]
    assert response.json()["quantity"]["quantity_increment"] == "0.2500"
    assert response.json()["price"]["price_decimal_places"] == 4
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(
                ProductTypeRevision, uuid.UUID(product["product_type_revision_id"])
            )
            assert revision is not None
            type_id = revision.product_type_id
            wrong_unit = UnitOfMeasure(
                tenant_id=tenant_a,
                company_id=company,
                code="PCS",
                symbol="pc",
                name="Pieces",
                dimension="COUNT",
                decimal_places=0,
                quantity_increment=1,
            )
            db.add(wrong_unit)
            await db.flush()
            wrong_unit_id = wrong_unit.id
            db.add(
                Currency(
                    code="USD",
                    numeric_code="840",
                    name="US Dollar",
                    symbol="USD",
                    minor_unit=2,
                    major_unit_name="Dollars",
                )
            )
    for selection in (
        {"product_type_id": str(type_id)},
        {"product_type_revision_id": product["product_type_revision_id"]},
    ):
        response = await client.get(path, headers=auth, params={**params, **selection})
        assert response.status_code == 200, response.text
        assert response.json()["product_type_revision_id"] == product["product_type_revision_id"]
    invalid = await client.get(
        path,
        headers=auth,
        params={**params, "product_type_id": str(type_id), "unit_id": str(wrong_unit_id)},
    )
    assert invalid.status_code == 409 and "dimension" in invalid.text, invalid.text
    ownerless = await client.get(
        path, headers=auth, params={**params, "unit_revision_id": str(uuid.uuid4())}
    )
    assert ownerless.status_code == 409, ownerless.text
    created = await client.post(
        root + "/product-families", headers=command_headers(auth), json=product
    )
    assert created.status_code == 201, created.text
    response = await client.get(
        path, headers=auth, params={**params, "family_id": created.json()["family"]["id"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["product_type_revision_id"] == product["product_type_revision_id"]
    scope, _ = await publish_configuration(
        client,
        root,
        auth,
        numeric_defaults=[
            {
                "dimension": "TIME",
                "price_decimal_places": 2,
                "currency": "INR",
                "price_basis_quantity": "0.30",
            }
        ],
    )
    invalid = await client.get(path, headers=auth, params=params)
    assert invalid.status_code == 422, invalid.text
    quantity_only = await client.get(
        path, headers=auth, params={**params, "include_price": "false"}
    )
    assert quantity_only.status_code == 200, quantity_only.text
    assert quantity_only.json()["price"] is None
    await publish_configuration(
        client,
        root,
        auth,
        scope_id=scope,
        effective_from="2091-01-01",
        numeric_defaults=[
            {
                "dimension": "TIME",
                "price_decimal_places": 2,
                "currency": "USD",
            }
        ],
    )
    mismatch = await client.get(
        path, headers=auth, params={**params, "as_of": "2091-01-01", "currency": "INR"}
    )
    assert mismatch.status_code == 409 and "different currency" in mismatch.text, mismatch.text
    await policy(
        factory, tenant_a, company, user, "catalog.unit_of_measure", "decimal_places", "read"
    )
    denied = await client.get(path, headers=auth, params={**params, "include_price": "false"})
    assert denied.status_code == 403, denied.text


@pytest.mark.parametrize(
    "section,values",
    [
        ("options", {"manufacturer_mode": "REQUIRED"}),
        ("options", {"measured_units_mode": "OPTIONAL", "measured_units_default": True}),
        (
            "profiles",
            {
                "inventory_template_revision_mode": "VALUE",
                "inventory_template_revision_id": str(uuid.uuid4()),
            },
        ),
        (
            "profiles",
            {"handling_revision_mode": "VALUE", "handling_revision_id": str(uuid.uuid4())},
        ),
        (
            "profiles",
            {"identifier_profile_mode": "VALUE", "identifier_profile_id": str(uuid.uuid4())},
        ),
        ("pricing", {"mrp_mode": "REQUIRED"}),
    ],
)
def test_goods_only_settings_are_masked_in_shared_scopes_and_rejected_in_service_scopes(
    section: str, values: dict[str, object]
) -> None:
    from billing_platform.errors import ConflictError

    from catalog.schemas.configuration import DraftInput
    from catalog.tasks.configuration_values import applicable_layer

    body = DraftInput.model_validate(
        {
            "scope_id": str(uuid.uuid4()),
            "effective_from": "2090-01-01",
            "change_reason": "Kind-specific defaults",
            section: values,
        }
    )
    assert applicable_layer(body, service=False, shared=False) == body
    shared = applicable_layer(body, service=True, shared=True)
    assert shared.options.manufacturer_mode == "INHERIT"
    assert shared.options.measured_units_mode == "INHERIT"
    assert shared.profiles.inventory_template_revision_id is None
    assert shared.profiles.handling_revision_id is None
    assert shared.profiles.identifier_profile_id is None
    assert shared.pricing.mrp_mode == "INHERIT"
    with pytest.raises(ConflictError):
        applicable_layer(body, service=True, shared=False)


async def test_default_acceptance_cannot_preempt_product_field_denies(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from tests.test_master_reference_policy import policy

    company, user, _, product = await setup_product(factory, tenant_a, kind="SERVICE")
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    await publish_configuration(
        client,
        root,
        auth,
        profiles={
            "service_type_revision_mode": "VALUE",
            "service_type_revision_id": product["product_type_revision_id"],
        },
    )
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.product_family",
        "product_type_revision_id",
        "write",
    )
    defaults = await client.get(
        root + "/product-configuration/authoring-defaults",
        headers=auth,
        params={"kind": "SERVICE", "as_of": "2090-01-01"},
    )
    assert defaults.status_code == 200, defaults.text
    response = await client.post(
        root + "/product-families",
        headers=command_headers(auth),
        json={
            **product,
            "product_type_revision_id": str(uuid.uuid4()),
            "accept_defaults": defaults.json()["acceptance"],
        },
    )
    assert response.status_code == 403, response.text
