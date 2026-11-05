"""Simple import files validate native readiness without retaining preview effects."""

import base64
import csv
import datetime as dt
import io
import time
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.import_files import document
from billing_platform.import_models import ImportJob
from sqlalchemy import func, select

from catalog.models import Item
from catalog.models.pricing import ItemPrice
from catalog.models.simple_product_creation import SimpleProductCreation
from tests.conftest import ACTOR_SECRET
from tests.test_master_imports import command
from tests.test_simple_product_creation import starter

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize(
    ("state", "expired", "resumable"),
    [("VALIDATING", True, False), ("VALIDATING", False, True), ("IMPORTING", True, True)],
)
def test_progress_distinguishes_expired_validation_from_accepted_commands(
    state, expired, resumable
):
    from catalog.tasks.simple_import_execution import progress

    now = utcnow()
    job = ImportJob(
        id=uuid7(),
        definition="simple_products",
        state=state,
        revision=1,
        row_version=1,
        record_count=2,
        completed_count=0,
        review_digest=None,
        expires_at=now + dt.timedelta(days=-1 if expired else 1),
        created_at=now,
    )
    assert progress(job, {}).can_resume is resumable


def simple_source(values, file_format="CSV", keys=None):
    columns = keys or list(dict.fromkeys(key for row in values for key in row))
    raw = document(
        file_format,
        [("Records", columns, [[str(row.get(key, "")) for key in columns] for row in values])],
    )
    return {
        "filename": "products." + file_format.lower(),
        "format": file_format,
        "content_base64": base64.b64encode(raw).decode(),
    }


async def fresh_company_context(request):
    # ASGI tests bypass Identity. Re-sign facts per request as the real gateway does.
    from billing_platform.company_context import CompanyContext, sign_company_context

    token = request.headers.get("x-company-context")
    if token:
        context = CompanyContext.model_validate_json(
            base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        )
        token, signature = sign_company_context(
            context.model_copy(update={"issued_at": int(time.time())}), ACTOR_SECRET.encode()
        )
        request.headers["x-company-context"] = token
        request.headers["x-company-signature"] = signature


async def template(client, root, auth, kind="GOODS"):
    if fresh_company_context not in client.event_hooks["request"]:
        client.event_hooks["request"].append(fresh_company_context)
    return await command(
        client,
        root,
        auth,
        "/import-templates",
        {
            "definition": "simple_products",
            "parameters": {"resource": "simple_product_create", "kind": kind},
        },
        201,
    )


async def stage_rows(client, root, auth, configured, values):
    return await command(
        client,
        root,
        auth,
        "/import-jobs",
        {"template_id": configured["id"], "files": [simple_source(values)]},
        201,
    )


async def validate(client, root, auth, job):
    for _ in range(201):
        job = await command(
            client,
            root,
            auth,
            "/import-jobs/" + job["id"] + "/validate",
            {"expected_version": job["row_version"]},
        )
        if job["state"] != "VALIDATING":
            return job
    pytest.fail("Validation did not finish")


async def commit(client, root, auth, job):
    return await command(
        client,
        root,
        auth,
        "/import-jobs/" + job["id"] + "/commit",
        {"expected_version": job["row_version"], "review_digest": job["review_digest"]},
    )


async def report(client, root, auth, identity, kind):
    path = root + "/import-jobs/" + identity
    options = {"kind": kind, "format": "CSV"}
    ticket = await client.post(path + "/download-ticket", headers=auth, json=options)
    assert ticket.status_code == 200, ticket.text
    response = await client.post(
        path + "/download", headers=auth, json=options | {"token": ticket.json()["token"]}
    )
    assert response.status_code == 200, response.text
    return response.content


@pytest.mark.parametrize(
    "kind,file_format", [("GOODS", "CSV"), ("SERVICE", "TSV"), ("GOODS", "XLSX")]
)
async def test_simple_template_validates_ready_product_and_retains_only_pending_commands(
    client, factory, tenant_a, kind, file_format
):
    root, auth, _ = await starter(factory, tenant_a)
    configured = await template(client, root, auth, kind)
    columns = configured["snapshot"]["schemas"]["simple_product_create:CREATE"]["properties"]
    assert {"name", "code", "base_unit", "group", "purchase_price", "sale_price"} <= columns.keys()
    assert (
        not {"product_type_revision_id", "initial_setup", "authoring_version", "mrp"}
        & columns.keys()
    )
    assert (
        "code" not in configured["snapshot"]["schemas"]["simple_product_create:CREATE"]["required"]
    )
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
                            "name": "Imported ready",
                            "base_unit": "HOUR",
                            "purchase_price": "12.50",
                            "sale_price": "20.00",
                        }
                    ],
                    file_format,
                )
            ],
        },
        201,
    )
    ready = await command(
        client,
        root,
        auth,
        "/import-jobs/" + staged["id"] + "/validate",
        {"expected_version": staged["row_version"]},
    )
    if ready["state"] != "READY":
        attempts = (
            await client.get(
                root + "/import-jobs/" + ready["id"] + "/history/attempts", headers=auth
            )
        ).json()
        messages = await client.get(
            root
            + "/import-jobs/"
            + ready["id"]
            + "/attempts/"
            + attempts["items"][-1]["id"]
            + "/issues",
            headers=auth,
        )
        pytest.fail(messages.text)
    with tenant_scope(tenant_a):
        async with factory() as db:
            for model in (Item, ItemPrice, SimpleProductCreation):
                assert await db.scalar(select(func.count(model.id))) == 0
    pending = await command(
        client,
        root,
        auth,
        "/import-jobs/" + staged["id"] + "/commit",
        {"expected_version": ready["row_version"], "review_digest": ready["review_digest"]},
    )
    assert pending["state"] == "PARTIAL" and pending["completed_count"] == 0
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 0
            receipt = (await db.scalars(select(SimpleProductCreation))).one()
            assert len(receipt.code) == 10 and receipt.request["kind"] == kind
            assert Decimal(receipt.request["purchase_price"]) == Decimal("12.50")
    path = root + "/simple-product-imports/" + staged["id"]
    for _ in range(20):
        response = await client.post(path + "/advance", headers=auth, json={})
        assert response.status_code == 200, response.text
        if response.json()["job"]["state"] == "SUCCEEDED":
            break
    assert response.json()["job"]["completed_count"] == 1, response.text
    replay = await client.post(path + "/advance", headers=auth, json={})
    assert replay.status_code == 200 and replay.json()["pending_count"] == 0
    results = await client.get(path + "/rows", headers=auth)
    assert results.status_code == 200, results.text
    assert results.json()["items"][0]["state"] == "APPLIED"
    assert results.json()["items"][0]["name"] == "Imported ready"
    assert len(results.json()["items"][0]["code"]) == 10
    with tenant_scope(tenant_a):
        async with factory() as db:
            product = (await db.scalars(select(Item))).one()
            assert product.status == "ACTIVE"
            assert await db.scalar(select(func.count(ItemPrice.id))) == 2
    result_file = await report(client, root, auth, staged["id"], "RESULT")
    assert b"Imported ready" in result_file and b"opening_posted" in result_file
    assert b"product_code" in result_file and b"product_name" in result_file


async def test_invalid_rows_correction_report_history_and_isolation(
    client, factory, tenant_a, tenant_b
):
    root, auth, _ = await starter(factory, tenant_a)
    configured = await template(client, root, auth)
    staged = await stage_rows(
        client,
        root,
        auth,
        configured,
        [
            {"name": "Valid", "base_unit": "HOUR", "code": "REPEAT"},
            {"name": "Bad unit", "base_unit": "UNKNOWN", "code": "OTHER"},
            {"name": "Duplicate", "base_unit": "HOUR", "code": "REPEAT"},
            {"name": "Bad price", "base_unit": "HOUR", "code": "PRICE", "purchase_price": "-1"},
        ],
    )
    invalid = await validate(client, root, auth, staged)
    assert invalid["state"] == "INVALID"
    path = root + "/simple-product-imports/" + staged["id"]
    results = (await client.get(path + "/rows", headers=auth)).json()["items"]
    assert results[0]["state"] == "VALID"
    assert results[1]["messages"][0]["field"] == "base_unit"
    assert results[2]["state"] == "INVALID"
    assert results[3]["messages"][0]["field"] == "purchase_price"
    correction = await report(client, root, auth, staged["id"], "CORRECTION")
    assert b"_payload" not in correction and b"_resource" not in correction
    parsed = list(csv.reader(io.StringIO(correction.decode("utf-8-sig"))))
    header_index = next(index for index, row in enumerate(parsed) if "_key" in row)
    records = list(
        csv.DictReader(io.StringIO("\n".join(",".join(row) for row in parsed[header_index:])))
    )
    records[1]["base_unit"] = "HOUR"
    records[2]["code"] = "DISTINCT"
    records[3]["purchase_price"] = "1.25"
    corrected = await command(
        client,
        root,
        auth,
        "/import-jobs/" + staged["id"] + "/revisions",
        {"expected_version": invalid["row_version"], "files": [simple_source(records)]},
    )
    ready = await validate(client, root, auth, corrected)
    assert ready["state"] == "READY", ready
    history = await client.get(
        root + "/import-jobs/" + staged["id"] + "/history/revisions", headers=auth
    )
    assert len(history.json()["items"]) == 2
    other_root, other_auth, _ = await starter(factory, tenant_b)
    for url in (
        path + "/rows",
        other_root + "/simple-product-imports/" + staged["id"] + "/progress",
    ):
        denied = await client.get(url, headers=other_auth)
        assert denied.status_code in {401, 403, 404}
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 0


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
async def test_gst_import_resolves_hsn_sac_and_rule_codes(client, factory, tenant_a, kind):
    from catalog.models.tax import TaxClassification, TaxRule

    root, auth, _ = await starter(factory, tenant_a, gst=True)
    configured = await template(client, root, auth, kind)
    schema = configured["snapshot"]["schemas"]["simple_product_create:CREATE"]
    assert {"hsn_sac", "gst_rule"} <= set(schema["required"])
    assert "opening_quantity" not in schema["properties"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            hsn = await db.scalar(
                select(TaxClassification.code).where(TaxClassification.item_kind == kind).limit(1)
            )
            rule = await db.scalar(
                select(TaxRule.code)
                .where(
                    TaxRule.item_kind == kind,
                    TaxRule.classification_scope == "ANY",
                    TaxRule.treatment == "TAXABLE",
                )
                .limit(1)
            )
    staged = await stage_rows(
        client,
        root,
        auth,
        configured,
        [{"name": "GST import", "base_unit": "HOUR", "hsn_sac": hsn, "gst_rule": rule}],
    )
    ready = await validate(client, root, auth, staged)
    assert ready["state"] == "READY", (
        await client.get(root + "/simple-product-imports/" + staged["id"] + "/rows", headers=auth)
    ).text


async def test_templates_follow_required_brand_model_and_price_configuration(
    client, factory, tenant_a, monkeypatch
):
    from catalog.models.configuration import ProductEntryOptionPolicy, ProductPricingPolicy
    from catalog.tasks.simple_creation_transport import CreationOwners

    root, auth, _ = await starter(factory, tenant_a, inventory=True)

    async def capture_fields(self, service, method, path, body=None, key=None):
        assert service == "accounting" and path.endswith("/capture-fields")
        return {
            "fields": [{"key": "quantity", "readable": True, "writable": True, "visible": True}]
        }

    monkeypatch.setattr(CreationOwners, "call", capture_fields)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            options = await db.scalar(
                select(ProductEntryOptionPolicy).where(
                    ProductEntryOptionPolicy.revision_id.is_not(None)
                )
            )
            options.brand_mode = options.model_mode = "REQUIRED"
            pricing = await db.scalar(
                select(ProductPricingPolicy).where(ProductPricingPolicy.revision_id.is_not(None))
            )
            pricing.mrp_mode = "REQUIRED"
            pricing.purchase_reference_mode = "DISABLED"
    goods = await template(client, root, auth)
    schema = goods["snapshot"]["schemas"]["simple_product_create:CREATE"]
    assert {"brand", "model_code", "mrp"} <= set(schema["required"])
    assert "purchase_price" not in schema["properties"]
    assert "opening_quantity" not in schema["properties"]
    assert "opening_date" not in schema["properties"]
    services = await template(client, root, auth, "SERVICE")
    assert (
        "mrp" not in services["snapshot"]["schemas"]["simple_product_create:CREATE"]["properties"]
    )


async def test_opening_import_keeps_exact_cost_and_resumes_lost_native_response(
    client, factory, tenant_a, monkeypatch
):
    from voucher_execution.stock import StockInput

    from catalog.tasks.simple_creation_transport import CreationOwners, ServiceUnavailableError

    root, auth, _ = await starter(factory, tenant_a, inventory=True)
    original = CreationOwners.call
    state = {"lost": False, "posted": False, "submitted": False, "issued": False}
    writes = []

    async def owner(self, service, method, path, body=None, key=None):
        if service == "catalog":
            value = await original(self, service, method, path, body, key)
            if method == "POST" and path.endswith("/products") and not state["lost"]:
                state["lost"] = True
                raise ServiceUnavailableError("Lost native response")
            return value
        if method == "POST":
            writes.append((path, body, key))
        if path.endswith("/capture-fields"):
            return {
                "fields": [{"key": "quantity", "readable": True, "writable": True, "visible": True}]
            }
        if path.endswith("/readiness"):
            return {"blockers": []}
        if path.endswith("/voucher-capabilities"):
            return {"stock_execution": True}
        if "/voucher-types?" in path:
            return {"items": [{"id": str(uuid7()), "profile": "OPENING"}]}
        if "/effective-configuration?" in path:
            return {"policy": {"approval_required": False}}
        if "/voucher-types/" in path:
            return {"revision_id": str(uuid7())}
        if path.endswith("/calculate"):
            opening = body["opening"]
            assert Decimal(opening["unit_cost"]) == Decimal("12.50")
            assert Decimal(opening["entered_quantity"]) == Decimal("3")
            return {"base_quantity": "3", "received_value": "37.50"}
        if "/stock/openings/products/" in path:
            return {"id": str(uuid7())}
        if path.endswith("/vouchers"):
            stock = StockInput.model_validate(body["stock"])
            assert stock.lines[0].received_value == Decimal("37.50")
            return {"id": str(uuid7())}
        for suffix, state_key, status in (
            ("/submit", "submitted", "APPROVED"),
            ("/issue", "issued", "ISSUED"),
            ("/post", "posted", "POSTED"),
        ):
            if path.endswith(suffix):
                state[state_key] = True
                return {"status": status, "operation_id": str(uuid7())}
        if path.endswith("/reconciliation"):
            return {"blockers": [], "expected_version": 1, "manifest_hash": "a" * 64}
        if path.endswith("/finalize"):
            return {"status": "FINALIZED"}
        if "/vouchers/" in path:
            return {
                "row_version": 1,
                "status": "POSTED"
                if state["posted"]
                else "ISSUED"
                if state["issued"]
                else "APPROVED"
                if state["submitted"]
                else "DRAFT",
            }
        raise AssertionError((service, path))

    monkeypatch.setattr(CreationOwners, "call", owner)
    configured = await template(client, root, auth)
    assert (
        "opening_quantity"
        in configured["snapshot"]["schemas"]["simple_product_create:CREATE"]["properties"]
    )
    staged = await stage_rows(
        client,
        root,
        auth,
        configured,
        [
            {
                "name": "Opening import",
                "base_unit": "NOS",
                "purchase_price": "12.50",
                "opening_quantity": "3",
                "opening_date": "2026-04-01",
            }
        ],
    )
    ready = await validate(client, root, auth, staged)
    assert ready["state"] == "READY"
    assert not writes  # Validation only reads owners; no opening is posted.
    pending = await commit(client, root, auth, ready)
    assert pending["completed_count"] == 0
    path = root + "/simple-product-imports/" + staged["id"]
    interrupted = await client.post(path + "/advance", headers=auth)
    assert interrupted.status_code == 200, interrupted.text
    assert (
        interrupted.json()["failed_count"] == 1
        and interrupted.json()["job"]["completed_count"] == 0
    )
    for _ in range(20):
        result = await client.post(path + "/advance", headers=auth)
        assert result.status_code == 200, result.text
        if not result.json()["pending_count"]:
            break
    assert result.json()["job"]["state"] == "SUCCEEDED", result.text
    rows = (await client.get(path + "/rows", headers=auth)).json()["items"]
    assert rows[0]["opening_posted"] and rows[0]["state"] == "APPLIED" and not rows[0]["messages"]
    assert len([path for path, _, _ in writes if path.endswith("/vouchers")]) == 1
    assert len([path for path, _, _ in writes if path.endswith("/post")]) == 1
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 1


@pytest.mark.parametrize("with_prices", [False, True])
async def test_mrp_validation_uses_native_numeric_revision_without_saving_prices(
    client, factory, tenant_a, with_prices
):
    from catalog.models.configuration import ProductPricingPolicy
    from catalog.models.pricing import ItemMrp

    root, auth, _ = await starter(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            pricing = await db.scalar(
                select(ProductPricingPolicy).where(ProductPricingPolicy.revision_id.is_not(None))
            )
            pricing.mrp_mode = "OPTIONAL"
    configured = await template(client, root, auth)
    values = {"name": "MRP import", "base_unit": "HOUR", "mrp": "50.00"}
    if with_prices:
        values.update(purchase_price="12.50", sale_price="20.00")
    staged = await stage_rows(client, root, auth, configured, [values])
    ready = await validate(client, root, auth, staged)
    assert ready["state"] == "READY", (
        await client.get(root + "/simple-product-imports/" + staged["id"] + "/rows", headers=auth)
    ).text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemMrp.id))) == 0
            assert await db.scalar(select(func.count(Item.id))) == 0
