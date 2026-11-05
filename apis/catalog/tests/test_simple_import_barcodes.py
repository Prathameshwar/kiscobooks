"""Barcode import parity, duplicate preflight and protected retained results."""

import uuid

import pytest
from billing_platform.company_context import verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.import_models import ImportJobRevision
from sqlalchemy import func, select

from catalog.models.product_definitions import ItemBarcode
from catalog.models.products import Item
from tests.conftest import ACTOR_SECRET
from tests.test_master_imports import command
from tests.test_master_reference_policy import policy
from tests.test_simple_creation_details import barcode_policy
from tests.test_simple_product_creation import starter
from tests.test_simple_product_import import (
    commit,
    report,
    simple_source,
    stage_rows,
    template,
    validate,
)

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_optional_barcode_template_accepts_blank_or_default_format(client, factory, tenant_a):
    root, auth, _ = await starter(factory, tenant_a)
    disabled = await template(client, root, auth)
    columns = disabled["snapshot"]["schemas"]["simple_product_create:CREATE"]["properties"]
    assert "barcode_value" not in columns and "barcode_symbology" not in columns
    await barcode_policy(factory, tenant_a, "OPTIONAL")
    configured = await template(client, root, auth)
    schema = configured["snapshot"]["schemas"]["simple_product_create:CREATE"]
    assert "barcode_value" not in schema["required"]
    staged = await stage_rows(
        client,
        root,
        auth,
        configured,
        [
            {"name": "No barcode", "base_unit": "HOUR"},
            {"name": "Plain barcode", "base_unit": "HOUR", "barcode_value": "0000123"},
            {"name": "Format only", "base_unit": "HOUR", "barcode_symbology": "QR"},
        ],
    )
    assert (await validate(client, root, auth, staged))["state"] == "INVALID"
    response = await client.get(
        root + "/simple-product-imports/" + staged["id"] + "/rows", headers=auth
    )
    rows = {row["name"]: row for row in response.json()["items"]}
    assert rows["No barcode"]["state"] == rows["Plain barcode"]["state"] == "VALID"
    assert rows["Format only"]["state"] == "INVALID"
    assert rows["Format only"]["messages"][0]["field"] == "barcode_value"


@pytest.mark.parametrize("kind,file_format", [("GOODS", "CSV"), ("SERVICE", "XLSX")])
async def test_barcode_import_reaches_active_and_preserves_history_and_read_denies(
    client, factory, tenant_a, kind, file_format
):
    root, auth, _ = await starter(factory, tenant_a)
    context = verify_company_context(
        auth["x-company-context"], auth["x-company-signature"], ACTOR_SECRET.encode()
    )
    await barcode_policy(factory, tenant_a, "REQUIRED")
    configured = await template(client, root, auth, kind)
    staged = await command(
        client,
        root,
        auth,
        "/import-jobs",
        {
            "template_id": configured["id"],
            "files": [
                simple_source(
                    [
                        {
                            "name": "Barcoded import",
                            "base_unit": "HOUR",
                            "barcode_value": "0012345678905",
                            "barcode_symbology": "GTIN",
                        }
                    ],
                    file_format,
                )
            ],
        },
        201,
    )
    ready = await validate(client, root, auth, staged)
    assert ready["state"] == "READY", await report(client, root, auth, staged["id"], "RESULT")
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemBarcode.id))) == 0
    pending = await commit(client, root, auth, ready)
    path = root + "/simple-product-imports/" + staged["id"]
    for _ in range(20):
        response = await client.post(path + "/advance", headers=auth, json={})
        assert response.status_code == 200, response.text
        if response.json()["job"]["state"] == "SUCCEEDED":
            break
    assert response.json()["job"]["state"] == "SUCCEEDED", response.text
    replay = await client.post(path + "/advance", headers=auth, json={})
    assert replay.status_code == 200 and replay.json()["pending_count"] == 0
    results = await client.get(path + "/rows", headers=auth)
    assert results.json()["items"][0]["state"] == "APPLIED"
    assert b"0012345678905" in await report(client, root, auth, staged["id"], "RESULT")
    history = await client.get(
        root + "/import-jobs/" + staged["id"] + "/history/attempts", headers=auth
    )
    assert history.status_code == 200 and history.json()["items"]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            barcode = (await db.scalars(select(ItemBarcode))).one()
            assert barcode.value == "0012345678905" and barcode.symbology == "GTIN"
            assert (await db.get(Item, barcode.item_id)).status == "ACTIVE"
            revision = await db.scalar(
                select(ImportJobRevision).where(
                    ImportJobRevision.job_id == uuid.UUID(pending["id"])
                )
            )
            revision.batch = None  # Retained native commands outlive source payload retention.
    await policy(
        factory,
        tenant_a,
        context.company_id,
        context.user_id,
        "catalog.item_barcode",
        "value",
        "read",
    )
    denied = await client.get(path + "/progress", headers=auth)
    assert denied.status_code == 403 and "0012345678905" not in denied.text


async def test_barcode_validation_detects_alias_duplicates_missing_and_invalid_values(
    client, factory, tenant_a
):
    root, auth, _ = await starter(factory, tenant_a)
    await barcode_policy(factory, tenant_a, "REQUIRED")
    configured = await template(client, root, auth)
    rows = [
        {
            "name": "First",
            "base_unit": "HOUR",
            "barcode_value": "0012345678905",
            "barcode_symbology": "GTIN",
        },
        {"name": "Alias", "base_unit": "HOUR", "barcode_value": "00012345678905"},
        {
            "name": "Invalid",
            "base_unit": "HOUR",
            "barcode_value": "0012345678900",
            "barcode_symbology": "GTIN",
        },
        {"name": "Missing", "base_unit": "HOUR"},
    ]
    staged = await stage_rows(client, root, auth, configured, rows)
    invalid = await validate(client, root, auth, staged)
    assert invalid["state"] == "INVALID"
    response = await client.get(
        root + "/simple-product-imports/" + staged["id"] + "/rows", headers=auth
    )
    results = {row["name"]: row for row in response.json()["items"]}
    assert results["First"]["state"] == "VALID"
    for name in ("Alias", "Invalid", "Missing"):
        assert results[name]["state"] == "INVALID", results[name]
        assert any(
            issue["field"] == "barcode_value" for issue in results[name]["messages"]
        ), results[name]
    correction = await report(client, root, auth, staged["id"], "CORRECTION")
    assert b"barcode_value" in correction and b"00012345678905" in correction
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 0
