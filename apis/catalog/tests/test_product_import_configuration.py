"""The downloaded file and actual native execution use current product settings."""

import base64
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.import_contracts import CONTROLS
from billing_platform.import_files import document
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select

from catalog.models import Item, ItemUnitBinding
from catalog.tasks import product_import_configuration as configuration
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_master_imports import command, source
from tests.test_product_initial_setup import initial
from tests.test_product_mode import set_mode
from tests.test_simple_products import simple_input

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize(
    "advanced,kind,file_format",
    [
        (False, "GOODS", "CSV"),
        (False, "SERVICE", "TSV"),
        (False, "GOODS", "XLSX"),
        (True, "GOODS", "CSV"),
        (True, "SERVICE", "TSV"),
        (True, "GOODS", "XLSX"),
    ],
)
async def test_configured_template_create_and_unit_setup_without_internal_versions(
    client, factory, tenant_a, advanced, kind, file_format
):
    company, user, _, legacy = await setup_product(factory, tenant_a, kind=kind, advanced=advanced)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    resource = "product_family" if advanced else "simple_product"
    template = await command(
        client,
        root,
        auth,
        "/import-templates",
        {
            "definition": "products",
            "parameters": {
                "resource": resource,
                "kind": kind,
                "as_of": "2026-01-01",
                "product_type_revision_id": legacy["product_type_revision_id"],
            },
        },
        201,
    )
    snapshot = template["snapshot"]
    schema = snapshot["schemas"][resource + ":CREATE"]
    assert schema["properties"]["kind"]["enum"] == [kind]
    assert not configuration.DERIVED.intersection(schema["properties"])
    assert "expected_version" not in schema["$defs"]["UnitBindingInput"]["properties"]
    assert snapshot["product_configuration"]["kind"] == kind
    downloaded = await client.get(
        root + "/import-templates/" + template["id"],
        headers=auth,
        params={"resource": resource, "format": file_format},
    )
    assert downloaded.status_code == 200, downloaded.text
    data = dict(legacy) if advanced else simple_input(legacy)
    data.pop("authoring_version", None)
    data["initial_setup"] = initial(legacy)
    data["initial_setup"]["units"][0].pop("expected_version")
    job = await command(
        client,
        root,
        auth,
        "/import-jobs",
        {"template_id": template["id"], "files": [source(resource, data, file_format)]},
        201,
    )
    path = "/import-jobs/" + job["id"]
    review = await command(client, root, auth, path + "/validate", {"expected_version": 1})
    assert review["state"] == "READY", review
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 0
    body = {"expected_version": review["row_version"], "review_digest": review["review_digest"]}
    key = {**auth, "Idempotency-Key": str(uuid.uuid4())}
    applied = await client.post(root + path + "/commit", headers=key, json=body)
    assert applied.status_code == 200 and applied.json()["state"] == "SUCCEEDED", applied.text
    replay = await client.post(root + path + "/commit", headers=key, json=body)
    assert replay.status_code == 200, replay.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 1
            assert await db.scalar(select(func.count(ItemUnitBinding.id))) == 1
    # An unrelated product write/Identity refresh must not expire an equivalent template.
    assert (
        await client.get(
            root + "/import-templates/" + template["id"],
            headers=auth,
            params={"resource": resource, "format": file_format},
        )
    ).status_code == 200


@pytest.mark.parametrize(
    "advanced,wrong", [(False, "product_family"), (False, "item"), (True, "simple_product")]
)
async def test_explicit_template_resources_follow_company_mode(
    client, factory, tenant_a, advanced, wrong
):
    company, user, _, _ = await setup_product(factory, tenant_a, advanced=advanced)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    response = await client.post(
        f"/v1/companies/{company}/import-templates",
        headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
        json={"definition": "products", "parameters": {"resource": wrong}},
    )
    assert response.status_code == 409, response.text


async def test_kind_mismatch_and_mode_change_preserve_historical_job(client, factory, tenant_a):
    company, user, _, legacy = await setup_product(factory, tenant_a, advanced=False)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    template = await command(
        client,
        root,
        auth,
        "/import-templates",
        {"definition": "products", "parameters": {"resource": "simple_product", "kind": "GOODS"}},
        201,
    )
    data = simple_input(legacy)
    data.pop("authoring_version")
    wrong = {**data, "kind": "SERVICE"}
    await command(
        client,
        root,
        auth,
        "/import-jobs",
        {"template_id": template["id"], "files": [source("simple_product", wrong)]},
        422,
    )
    job = await command(
        client,
        root,
        auth,
        "/import-jobs",
        {"template_id": template["id"], "files": [source("simple_product", data)]},
        201,
    )
    enabled, _, _ = await set_mode(client, company, auth, True)
    assert enabled.status_code == 200, enabled.text
    old = await client.get(
        root + "/import-templates/" + template["id"],
        headers=auth,
        params={"resource": "simple_product", "format": "CSV"},
    )
    assert old.status_code == 409, old.text
    history = await client.get(root + "/import-jobs/" + job["id"], headers=auth)
    assert history.status_code == 200, history.text


async def test_changed_effective_values_require_current_template(
    client, factory, tenant_a, monkeypatch
):
    company, user, _, _ = await setup_product(factory, tenant_a, advanced=False)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    template = await command(
        client, root, auth, "/import-templates", {"definition": "products"}, 201
    )
    original = configuration.resolve

    async def changed(*args, **kwargs):
        current = await original(*args, **kwargs)
        return current.model_copy(
            update={
                "options": current.options.model_copy(
                    update={"barcode_default": not current.options.barcode_default}
                )
            }
        )

    monkeypatch.setattr(configuration, "resolve", changed)
    old = await client.get(
        root + "/import-templates/" + template["id"],
        headers=auth,
        params={"resource": "simple_product", "format": "CSV"},
    )
    assert old.status_code == 409, old.text


@pytest.mark.parametrize("advanced", [False, True])
async def test_file_update_uses_the_same_native_product_identity(
    client, factory, tenant_a, advanced
):
    company, user, _, legacy = await setup_product(factory, tenant_a, advanced=advanced)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    created = await command(
        client,
        root,
        auth,
        "/product-families" if advanced else "/products",
        legacy if advanced else simple_input(legacy),
        201,
    )
    item = created["default_item"] if advanced else created
    resource = "item" if advanced else "simple_product"
    template = await command(
        client,
        root,
        auth,
        "/import-templates",
        {"definition": "products", "parameters": {"resource": resource}},
        201,
    )
    assert (
        "expected_version"
        not in template["snapshot"]["schemas"][resource + ":UPDATE"]["properties"]
    )
    raw = document(
        "CSV",
        [
            (
                "Records",
                [*CONTROLS, "name"],
                [
                    [
                        "one",
                        "one",
                        resource,
                        "UPDATE",
                        item["id"],
                        "",
                        "",
                        "",
                        "",
                        "",
                        "Updated through configured import",
                    ]
                ],
            )
        ],
    )
    job = await command(
        client,
        root,
        auth,
        "/import-jobs",
        {
            "template_id": template["id"],
            "mode": "UPDATE_ONLY",
            "files": [
                {
                    "filename": "updates.csv",
                    "format": "CSV",
                    "content_base64": base64.b64encode(raw).decode(),
                }
            ],
        },
        201,
    )
    path = "/import-jobs/" + job["id"]
    reviewed = await command(client, root, auth, path + "/validate", {"expected_version": 1})
    assert reviewed["state"] == "READY", reviewed
    applied = await command(
        client,
        root,
        auth,
        path + "/commit",
        {"expected_version": reviewed["row_version"], "review_digest": reviewed["review_digest"]},
    )
    assert applied["state"] == "SUCCEEDED", applied
    row = await client.get(root + "/items/" + item["id"], headers=auth)
    assert (
        row.json()["name"] == "Updated through configured import" and row.json()["id"] == item["id"]
    )


async def test_import_template_cannot_infer_protected_authoring_mode(client, factory, tenant_a):
    company, user, _, _ = await setup_product(factory, tenant_a)
    auth = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=sorted(CATALOG_PERMISSIONS - {"product_configuration.read"}),
    )
    response = await client.post(
        f"/v1/companies/{company}/import-templates",
        headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
        json={"definition": "products", "parameters": {"resource": "item"}},
    )
    assert response.status_code == 403, response.text
