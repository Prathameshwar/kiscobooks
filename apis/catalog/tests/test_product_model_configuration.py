"""Model and brand gates cover native writes, publication, metadata and readiness."""

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.permissions import CATALOG_PERMISSIONS
from pydantic import ValidationError
from sqlalchemy import select

from catalog.models import ProductConfigurationRevision, ProductEntryOptionPolicy, ProductFamily
from catalog.schemas.configuration import EntryOptions
from tests.configuration_factories import publish_configuration
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_commercial_api import command_headers
from tests.test_simple_products import simple_input

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def test_model_requires_an_explicit_optional_default():
    assert EntryOptions().model_mode == "INHERIT"
    with pytest.raises(ValidationFailedError):
        EntryOptions(model_mode="OPTIONAL")
    with pytest.raises(ValidationFailedError):
        EntryOptions(model_mode="DISABLED", model_default=True)
    with pytest.raises(ValidationError):
        EntryOptions(model_mode="ENABLED")
    assert EntryOptions(model_mode="OPTIONAL", model_default=False).model_default is False


@pytest.mark.parametrize("advanced", [False, True])
async def test_native_model_create_update_clear_and_requirements(
    client, factory, tenant_a, advanced
):
    company, user, _, legacy = await setup_product(factory, tenant_a, advanced=advanced)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    _, revision = await publish_configuration(
        client, root, auth, options={"model_mode": "DISABLED"}
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            stored = await db.get(ProductConfigurationRevision, uuid.UUID(revision["id"]))
            stored.effective_from = dt.date(2000, 1, 1)
    path = root + ("/product-families" if advanced else "/products")
    body = legacy if advanced else simple_input(legacy)
    denied = await client.post(
        path, headers=command_headers(auth), json={**body, "model_code": "M1"}
    )
    assert denied.status_code == 422 and "disables this native choice" in denied.text, denied.text
    created = await client.post(path, headers=command_headers(auth), json=body)
    assert created.status_code == 201, created.text
    row = created.json()
    item = row["default_item"]["id"] if advanced else row["id"]
    if advanced:
        row = row["family"]
    version = (
        {"expected_version": row["row_version"]}
        if advanced
        else {"revision": row["revision"], "authoring_version": 0}
    )
    denied = await client.patch(
        path + "/" + row["id"], headers=command_headers(auth), json={**version, "model_code": "M2"}
    )
    assert denied.status_code == 422, denied.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            options = (
                await db.scalars(
                    select(ProductEntryOptionPolicy).where(
                        ProductEntryOptionPolicy.revision_id == uuid.UUID(revision["id"])
                    )
                )
            ).one()
            options.model_mode = "REQUIRED"
    ready = await client.get(
        root + "/items/" + item + "/requirements", headers=auth, params={"as_of": "2090-01-01"}
    )
    assert ready.status_code == 200 and "model" in ready.json()["missing"], ready.text
    saved = await client.patch(
        path + "/" + row["id"], headers=command_headers(auth), json={**version, "model_code": "M2"}
    )
    assert saved.status_code == 200, saved.text
    ready = await client.get(
        root + "/items/" + item + "/requirements", headers=auth, params={"as_of": "2090-01-01"}
    )
    assert "model" not in ready.json()["missing"]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            options = (
                await db.scalars(
                    select(ProductEntryOptionPolicy).where(
                        ProductEntryOptionPolicy.revision_id == uuid.UUID(revision["id"])
                    )
                )
            ).one()
            options.model_mode = "DISABLED"
    ready = await client.get(
        root + "/items/" + item + "/requirements", headers=auth, params={"as_of": "2090-01-01"}
    )
    assert "forbidden_model" in ready.json()["missing"]
    row = saved.json()
    version = (
        {"expected_version": row["row_version"]}
        if advanced
        else {"revision": row["revision"], "authoring_version": 0}
    )
    cleared = await client.patch(
        path + "/" + row["id"], headers=command_headers(auth), json={**version, "model_code": None}
    )
    assert cleared.status_code == 200, cleared.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (await db.scalars(select(ProductFamily))).one().model_code is None


async def test_entry_metadata_explains_brand_model_and_conversion(client, factory, tenant_a):
    company, user, _, _ = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    response = await client.get(
        f"/v1/companies/{company}/entities/catalog.product_entry_option_policy/field-set?operation=create",
        headers=auth,
    )
    assert response.status_code == 200, response.text
    fields = {row["key"]: row for row in response.json()["fields"]}
    assert fields["model_mode"]["control"]["label"] == "Model"
    assert fields["model_default"]["control"]["depends_on"] == "model_mode"
    assert "brand series" in fields["brand_mode"]["help_text"]
    for option in ("alternate_units", "compound_units", "measured_units"):
        assert fields[option + "_mode"]["display_group"] == "unit_conversion"
        assert fields[option + "_default"]["display_group"] == "unit_conversion"
        assert fields[option + "_mode"]["help_text"]
