"""Dense Advanced imports use bounded native work with durable continuation."""

import base64
import copy
import json
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.import_contracts import CONTROLS
from billing_platform.import_files import document
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select

from catalog.models import Item, ProductFamily
from catalog.models.product_definitions import ItemUnitBinding
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_master_imports import command
from tests.test_product_initial_setup import initial

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("atomicity", ["CHANGE_SET", "ATOMIC"])
async def test_advanced_import_continues_without_duplicate_products(
    client, factory, tenant_a, atomicity
):
    company, user, _, original = await setup_product(factory, tenant_a, advanced=True)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    template = await command(
        client,
        root,
        auth,
        "/import-templates",
        {"definition": "products", "parameters": {"resource": "product_family", "kind": "GOODS"}},
        201,
    )
    rows = []
    for index in range(2):
        data = copy.deepcopy(original)
        data["code"] = f"CONT-{index}"
        data["default_item"]["sku"] = f"CONT-{index}-SKU"
        data["initial_setup"] = initial(data)
        data["initial_setup"]["units"][0].pop("expected_version")
        key = f"row{index}"
        rows.append(
            [key, key, "product_family", "CREATE", "", "", "", "", "", "", json.dumps(data)]
        )
    raw = document("CSV", [("Records", [*CONTROLS, "_payload"], rows)])
    job = await command(
        client,
        root,
        auth,
        "/import-jobs",
        {
            "template_id": template["id"],
            "atomicity": atomicity,
            "files": [
                {
                    "filename": "advanced.csv",
                    "format": "CSV",
                    "content_base64": base64.b64encode(raw).decode(),
                }
            ],
        },
        201,
    )
    path = root + "/import-jobs/" + job["id"]
    validation_body = {"expected_version": job["row_version"]}
    validation_headers = auth | {"Idempotency-Key": str(uuid.uuid4())}
    first = await client.post(path + "/validate", json=validation_body, headers=validation_headers)
    assert first.status_code == 200, first.text
    assert first.json()["state"] == ("VALIDATING" if atomicity == "CHANGE_SET" else "READY")
    if atomicity == "CHANGE_SET":
        assert first.json()["review_digest"] is None
    replay = await client.post(path + "/validate", json=validation_body, headers=validation_headers)
    assert replay.json() == first.json()
    ready = (
        await command(
            client,
            root,
            auth,
            "/import-jobs/" + job["id"] + "/validate",
            {"expected_version": first.json()["row_version"]},
        )
        if atomicity == "CHANGE_SET"
        else first.json()
    )
    assert ready["state"] == "READY"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 0
            assert await db.scalar(select(func.count(ItemUnitBinding.id))) == 0
    commit_body = {
        "expected_version": ready["row_version"],
        "review_digest": ready["review_digest"],
    }
    commit_headers = auth | {"Idempotency-Key": str(uuid.uuid4())}
    first_commit = await client.post(path + "/commit", json=commit_body, headers=commit_headers)
    assert first_commit.status_code == 200, first_commit.text
    assert first_commit.json()["state"] == (
        "IMPORTING" if atomicity == "CHANGE_SET" else "SUCCEEDED"
    )
    assert first_commit.json()["completed_count"] == (1 if atomicity == "CHANGE_SET" else 2)
    replay = await client.post(path + "/commit", json=commit_body, headers=commit_headers)
    assert replay.json() == first_commit.json()
    finished = (
        await command(
            client,
            root,
            auth,
            "/import-jobs/" + job["id"] + "/commit",
            {
                "expected_version": first_commit.json()["row_version"],
                "review_digest": first_commit.json()["review_digest"],
            },
        )
        if atomicity == "CHANGE_SET"
        else first_commit.json()
    )
    assert finished["state"] == "SUCCEEDED" and finished["completed_count"] == 2
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == 2
            assert await db.scalar(select(func.count(Item.id))) == 2
            assert await db.scalar(select(func.count(ItemUnitBinding.id))) == 2
