"""Exercise native creation, pricing and activation behind the single Save flow."""

import datetime as dt
import time
import uuid

import pytest
from billing_platform.company_context import CompanyContext, FinancialContext, sign_company_context
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.permissions import PERMISSIONS
from pydantic import ValidationError
from sqlalchemy import func, select

from catalog.models import Item, UnitOfMeasure
from catalog.models.pricing import ItemPrice
from catalog.models.simple_product_creation import SimpleProductCreation
from catalog.tasks.company_configuration_defaults import ensure_configuration_defaults
from catalog.tasks.company_pricing_defaults import ensure_pricing_defaults
from catalog.tasks.company_product_defaults import ensure_product_defaults
from catalog.tasks.simple_creation_transport import CreationOwners, OwnerRejectedError
from catalog.tasks.unit_defaults import ensure_unit_defaults
from tests.conftest import ACTOR_SECRET
from tests.test_api import headers
from tests.test_unit_defaults import provision

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def test_zero_purchase_price_is_rejected_before_native_product_creation():
    from catalog.schemas.simple_product_creation import SimpleBatchInput, SimpleCreationInput

    with pytest.raises(ValidationError, match="greater than 0"):
        SimpleCreationInput.model_validate(
            {"name": "Opening stock", "base_unit_id": str(uuid7()),
             "opening_quantity": "100", "purchase_price": "0"}
        )
    with pytest.raises(ValidationError, match="greater than 0"):
        SimpleBatchInput.model_validate(
            {"code": "B1", "opening_quantity": "100", "purchase_price": "0"}
        )


async def test_creation_receipts_are_tenant_isolated(factory, tenant_a, tenant_b):
    company, user = uuid7(), uuid7()
    for tenant, code in ((tenant_a, "TENANTA001"), (tenant_b, "TENANTB001")):
        with tenant_scope(tenant):
            async with factory.begin() as db:
                db.add(
                    SimpleProductCreation(
                        id=uuid7(),
                        tenant_id=tenant,
                        company_id=company,
                        command_key="same-key-per-tenant",
                        request_hash="a" * 64,
                        code=code,
                        request={"name": code},
                        created_by=user,
                        updated_by=user,
                    )
                )
    for tenant, code in ((tenant_a, "TENANTA001"), (tenant_b, "TENANTB001")):
        with tenant_scope(tenant):
            async with factory() as db:
                rows = list(await db.scalars(select(SimpleProductCreation)))
                assert [(row.tenant_id, row.code) for row in rows] == [(tenant, code)]


async def starter(factory, tenant, *, inventory=False, gst=False):
    company, user = uuid7(), uuid7()
    await provision(factory, tenant, company, user=user, inventory=inventory)
    if gst:
        from billing_platform.snapshots import SnapshotRecord

        from catalog.tasks.projections import activate_snapshot
        from tests.source_factories import company_record, snapshot

        with tenant_scope(tenant):
            async with factory.begin() as db:
                await activate_snapshot(
                    db,
                    snapshot(
                        tenant,
                        company,
                        (
                            company_record(company, default_tax_system="gst_in"),
                            SnapshotRecord(kind="user", id=user, data={"status": "active"}),
                            *(
                                (
                                    SnapshotRecord(
                                        kind="feature",
                                        id=company,
                                        data={
                                            "company_id": str(company),
                                            "feature_key": "inventory",
                                            "is_enabled": True,
                                            "locked_at": None,
                                        },
                                    ),
                                )
                                if inventory
                                else ()
                            ),
                        ),
                        version=3,
                    ),
                )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await ensure_unit_defaults(db, company)
            await ensure_product_defaults(db, company)
            await ensure_pricing_defaults(db, company)
            assert (await ensure_configuration_defaults(db, company)).status == "READY"
            if inventory:
                from catalog.tasks.warehouse_defaults import ensure_warehouse_defaults

                await ensure_warehouse_defaults(db, company)
            if gst:
                from catalog.tasks.tax_defaults import ensure_tax_defaults

                await ensure_tax_defaults(db, company)
            unit = await db.scalar(
                select(UnitOfMeasure).where(
                    UnitOfMeasure.company_id == company,
                    UnitOfMeasure.code == ("NOS" if inventory else "HOUR"),
                )
            )
            if unit is None:
                unit = await db.scalar(
                    select(UnitOfMeasure).where(UnitOfMeasure.company_id == company).limit(1)
                )
            unit_id = str(unit.id)
    auth = headers(company, tenant=tenant, user=user, permission=list(PERMISSIONS))
    context = CompanyContext(
        issued_at=int(time.time()),
        tenant_id=tenant,
        company_id=company,
        user_id=user,
        base_currency="INR",
        features=frozenset({"inventory"}) if inventory else frozenset(),
        finance=FinancialContext(
            configuration_hash="a" * 64,
            company_active=True,
            books_begin_date=dt.date(2026, 4, 1),
            fiscal_year_start_month=4,
            fiscal_year_start_day=1,
            amount_precision=2,
            rounding_mode="half_up",
            default_payment_terms_days=0,
            timezone="Asia/Kolkata",
        ),
    )
    token, signature = sign_company_context(context, ACTOR_SECRET.encode())
    auth |= {"x-company-context": token, "x-company-signature": signature}
    return f"/v1/companies/{company}", auth, unit_id


async def finish(client, root, auth, identity):
    for _ in range(16):
        response = await client.post(
            root + f"/simple-product-creations/{identity}/advance", headers=auth
        )
        assert response.status_code == 200, response.text
        if response.json()["status"] == "COMPLETE":
            return response.json()
    pytest.fail("creation did not finish")


async def test_stock_fence_retry_reuses_the_saved_product_command(
    client, factory, tenant_a, monkeypatch
):
    root, auth, unit = await starter(factory, tenant_a)
    created = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={"name": "Fence retry product", "kind": "GOODS", "base_unit_id": unit},
    )
    assert created.status_code == 201, created.text
    identity = created.json()["id"]
    original_call = CreationOwners.call
    attempts = []

    async def one_busy(self, service, method, path, body=None, key=None):
        if service == "catalog" and method == "POST" and path.endswith("/products"):
            attempts.append((body, key))
            if len(attempts) == 1:
                raise OwnerRejectedError(
                    409,
                    {
                        "message": "stock posting is using these definitions; "
                        "retry after it completes"
                    },
                )
        return await original_call(self, service, method, path, body, key)

    monkeypatch.setattr(CreationOwners, "call", one_busy)
    first = await client.post(root + f"/simple-product-creations/{identity}/advance", headers=auth)
    assert first.status_code == 409
    with tenant_scope(tenant_a):
        async with factory() as db:
            row = await db.get(SimpleProductCreation, uuid.UUID(identity))
            assert row is not None and row.step == "CREATE"
            assert row.progress["pending"]["key"] == attempts[0][1]
    second = await client.post(root + f"/simple-product-creations/{identity}/advance", headers=auth)
    assert second.status_code == 200, second.text
    assert attempts[0] == attempts[1]
    assert (await finish(client, root, auth, identity))["status"] == "COMPLETE"


async def test_price_source_conflict_repreviews_and_publishes_once(
    client, factory, tenant_a, monkeypatch
):
    root, auth, unit = await starter(factory, tenant_a)
    created = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={"name": "Price refresh product", "base_unit_id": unit,
              "purchase_price": "12.50", "sale_price": "20.00"},
    )
    assert created.status_code == 201, created.text
    identity = created.json()["id"]
    original_call = CreationOwners.call
    create_keys = []
    publish_keys = []

    async def once_changed(self, service, method, path, body=None, key=None):
        if service == "catalog" and method == "POST" and path.endswith("/products"):
            create_keys.append(key)
            if len(create_keys) == 1:
                raise OwnerRejectedError(
                    409, {"message": "pricing policy or Identity source changed; preview again"}
                )
        if (
            service == "catalog"
            and method == "POST"
            and "/price-drafts/" in path
            and path.endswith("/publish")
        ):
            publish_keys.append(key)
            if len(publish_keys) == 1:
                raise OwnerRejectedError(
                    409, {"message": "pricing policy or Identity source changed; preview again"}
                )
        return await original_call(self, service, method, path, body, key)

    monkeypatch.setattr(CreationOwners, "call", once_changed)
    route = root + f"/simple-product-creations/{identity}/advance"
    rejected_create = await client.post(route, headers=auth)
    assert rejected_create.status_code == 409, rejected_create.text
    assert (await client.post(route, headers=auth)).status_code == 200
    assert len(create_keys) == 2 and create_keys[0] != create_keys[1]
    rejected = await client.post(route, headers=auth)
    assert rejected.status_code == 409, rejected.text
    status = (await client.get(root + f"/simple-product-creations/{identity}", headers=auth)).json()
    assert status["step"] == "PUBLISH" and not status["can_edit"]
    resumed = await client.post(route, headers=auth)
    assert resumed.status_code == 200, resumed.text
    assert len(publish_keys) == 2 and publish_keys[0] != publish_keys[1]
    result = await finish(client, root, auth, identity)
    assert result["status"] == "COMPLETE"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 1
            assert await db.scalar(select(func.count(ItemPrice.id))) == 2


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
@pytest.mark.parametrize("inventory", [False, True])
async def test_save_creates_active_product_and_live_prices(
    client, factory, tenant_a, kind, inventory
):
    root, auth, unit = await starter(factory, tenant_a, inventory=inventory)
    body = {
        "name": "Ready product",
        "kind": kind,
        "base_unit_id": unit,
        "purchase_price": "12.50",
        "sale_price": "20.00",
    }
    signed = auth | {"Idempotency-Key": str(uuid7())}
    response = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert len(saved["code"]) == 10
    result = await finish(client, root, auth, saved["id"])
    replay = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert replay.status_code == 201 and replay.json()["id"] == saved["id"]
    assert result["opening_posted"] is False
    product = await client.get(root + "/products/" + result["item_id"], headers=auth)
    assert product.status_code == 200 and product.json()["status"] == "ACTIVE", product.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 1
            assert await db.scalar(select(func.count(ItemPrice.id))) == 2
            assert await db.scalar(select(func.count(SimpleProductCreation.id))) == 1


async def test_services_reject_stock_and_reused_save_key_rejects_different_input(
    client, factory, tenant_a
):
    root, auth, unit = await starter(factory, tenant_a)
    body = {"name": "Consulting", "kind": "SERVICE", "base_unit_id": unit}
    assert (await client.post(root + "/simple-product-creations", json=body)).status_code == 401
    signed = auth | {"Idempotency-Key": str(uuid7())}
    invalid = await client.post(
        root + "/simple-product-creations",
        headers=signed,
        json=body | {"opening_quantity": "1", "purchase_price": "10"},
    )
    assert invalid.status_code == 422
    response = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert response.status_code == 201, response.text
    changed = await client.post(
        root + "/simple-product-creations", headers=signed, json=body | {"name": "Different"}
    )
    assert changed.status_code == 409
    wrong = await client.get(
        f"/v1/companies/{uuid7()}/simple-product-creations/{response.json()['id']}", headers=auth
    )
    assert wrong.status_code in {403, 404}
    import uuid

    company = uuid.UUID(root.rsplit("/", 1)[1])
    foreign = headers(company, tenant=uuid7(), permission=list(PERMISSIONS))
    assert (
        await client.get(
            root + "/simple-product-creations/" + response.json()["id"], headers=foreign
        )
    ).status_code == 404
    other_user = headers(company, tenant=tenant_a, permission=list(PERMISSIONS))
    assert (
        await client.get(
            root + "/simple-product-creations/" + response.json()["id"], headers=other_user
        )
    ).status_code == 403


async def test_options_use_native_fields_and_services_hide_stock(client, factory, tenant_a):
    root, auth, _ = await starter(factory, tenant_a)
    response = await client.get(
        root + "/simple-product-creations/options?kind=SERVICE", headers=auth
    )
    assert response.status_code == 200, response.text
    fields = {field["key"] for field in response.json()["fields"]}
    assert {
        "name",
        "code",
        "kind",
        "base_unit_id",
        "sale_price",
        "purchase_price",
        "group_id",
    } <= fields
    assert "opening_quantity" not in fields and "mrp" not in fields
    assert response.headers["Cache-Control"] == "no-store"
    assert (
        await client.get(root + "/simple-product-creations/options?unknown=true", headers=auth)
    ).status_code == 422


@pytest.mark.parametrize("with_prices", [False, True])
async def test_configured_mrp_with_or_without_prices_is_published(
    client, factory, tenant_a, with_prices
):
    from decimal import Decimal

    from catalog.models.configuration import ProductPricingPolicy
    from catalog.models.pricing import ItemMrp

    root, auth, unit = await starter(factory, tenant_a)
    body = {"name": "MRP product", "base_unit_id": unit, "mrp": "50.00"}
    denied = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert denied.status_code == 422
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            pricing = await db.scalar(
                select(ProductPricingPolicy).where(ProductPricingPolicy.revision_id.is_not(None))
            )
            pricing.mrp_mode = "OPTIONAL"
    if with_prices:
        body.update(purchase_price="12.50", sale_price="20.00")
    created = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert created.status_code == 201, created.text
    await finish(client, root, auth, created.json()["id"])
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (await db.scalar(select(ItemMrp))).amount == Decimal("50")
            assert await db.scalar(select(func.count(ItemPrice.id))) == (2 if with_prices else 0)


@pytest.mark.parametrize("kind", ["GOODS", "SERVICE"])
async def test_gst_hsn_or_sac_applies_to_both_directions(client, factory, tenant_a, kind):
    from catalog.models.tax import TaxClassification, TaxRule

    root, auth, unit = await starter(factory, tenant_a, inventory=True, gst=True)
    with tenant_scope(tenant_a):
        async with factory() as db:
            classification = await db.scalar(
                select(TaxClassification).where(TaxClassification.item_kind == kind).limit(1)
            )
            rule = await db.scalar(
                select(TaxRule)
                .where(
                    TaxRule.item_kind == kind,
                    TaxRule.classification_scope == "ANY",
                    TaxRule.treatment == "TAXABLE",
                )
                .limit(1)
            )
            tax = {
                "classification_id": str(classification.id),
                "rule_id": str(rule.id),
                "directions": ["SALE", "PURCHASE"],
            }
    body = {"name": "GST ready", "kind": kind, "base_unit_id": unit, "tax": tax}
    created = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert created.status_code == 201, created.text
    result = await finish(client, root, auth, created.json()["id"])
    for direction in ["SALE", "PURCHASE"]:
        resolved = await client.post(
            root + "/tax-configurations/resolve",
            headers=auth,
            json={
                "item_id": result["item_id"],
                "as_of": dt.datetime.now(dt.UTC).date().isoformat(),
                "direction": direction,
            },
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "COMPLETE"
        assert resolved.json()["classification_id"] == tax["classification_id"]


async def test_opening_workflow_uses_exact_native_manifest_and_resumes_uncertain_create(
    client, factory, tenant_a, monkeypatch, *, terminal_rejection=False
):
    from decimal import Decimal

    from voucher_execution.opening import OpeningCapture
    from voucher_execution.stock import StockInput

    from catalog.tasks.simple_creation_transport import CreationOwners, ServiceUnavailableError

    root, auth, unit = await starter(factory, tenant_a, inventory=True)
    original = CreationOwners.call
    calls = []
    state = {"lost": False}

    async def owner(self, service, method, path, body=None, key=None):
        if service == "catalog":
            result = await original(self, service, method, path, body, key)
            if path.endswith("/products") and method == "POST" and not state["lost"]:
                state["lost"] = True
                raise ServiceUnavailableError("Simulated lost response after native product commit")
            return result
        calls.append((service, method, path, body, key))
        if path.endswith("/stock/openings/readiness"):
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
            import uuid

            from billing_platform.db.types import utcnow
            from billing_platform.errors import ConflictError
            from billing_platform.gateway import decode_actor_context
            from voucher_execution.contracts import DelegatedAuthority
            from voucher_execution.stock_facts import StockFenceRequest

            from catalog.tasks.stock_sources import build

            actor = decode_actor_context(
                auth["x-actor-context"], auth["x-actor-signature"], ACTOR_SECRET.encode()
            )
            source = StockFenceRequest(
                purpose="PREVIEW",
                tenant_id=tenant_a,
                company_id=uuid.UUID(root.rsplit("/", 1)[1]),
                execution_id=uuid7(),
                actor_user_id=actor.user_id,
                authority=DelegatedAuthority(
                    actor_context=auth["x-actor-context"],
                    actor_signature=auth["x-actor-signature"],
                    company_context=auth["x-company-context"],
                    company_signature=auth["x-company-signature"],
                ),
                authority_expires_at=utcnow() + dt.timedelta(seconds=45),
                stock_date=body["stock_date"],
                content_hash="a" * 64,
                item_ids=(body["item_id"],),
                warehouse_ids=(body["warehouse_id"],),
                opening_unit_revision_ids=(body["opening"]["unit_revision_id"],),
            )
            with tenant_scope(tenant_a):
                async with factory() as db:
                    facts = await build(db, actor, source, 1)
                    assert facts.items[0].opening_units[0].revision_id == uuid.UUID(
                        body["opening"]["unit_revision_id"]
                    )
                    await build(db, actor, source.model_copy(update={"purpose": "EXECUTION"}), 1)
                    with pytest.raises(ConflictError, match="Finish product creation"):
                        await build(
                            db,
                            actor,
                            source.model_copy(
                                update={"purpose": "EXECUTION", "opening_unit_revision_ids": ()}
                            ),
                            1,
                        )
            capture = OpeningCapture.model_validate(body["opening"])
            assert capture.unit_cost == Decimal("12.50")
            return {
                "base_quantity": str(capture.entered_quantity),
                "received_value": str(capture.entered_quantity * capture.unit_cost),
            }
        if "/stock/openings/products/" in path:
            state["manifest"] = body
            return {"id": str(uuid7())}
        if path.endswith("/vouchers"):
            stock = StockInput.model_validate(body["stock"])
            assert stock.lines[0].received_value == Decimal("37.50")
            assert stock.lines[0].quantity == Decimal("3")
            state["voucher"] = body
            return {"id": str(uuid7())}
        if path.endswith("/submit"):
            state["submitted"] = True
            return {"status": "APPROVED"}
        if path.endswith("/post"):
            state["post_attempts"] = state.get("post_attempts", 0) + 1
            state["posted"] = not terminal_rejection or state["post_attempts"] > 1
            return {"operation_id": str(uuid7())}
        if "/voucher-operations/" in path:
            state["operation_reads"] = state.get("operation_reads", 0) + 1
            return {
                "status": "PENDING" if state["operation_reads"] == 1 else "REJECTED",
                "rejection_code": "AUTHORITY_EXPIRED",
            }
        if path.endswith("/issue"):
            state["issued"] = True
            return {"status": "ISSUED"}
        if path.endswith("/reconciliation"):
            return {"blockers": [], "expected_version": 1, "manifest_hash": "a" * 64}
        if path.endswith("/finalize"):
            return {"status": "FINALIZED"}
        if "/vouchers/" in path:
            return {
                "row_version": 1,
                "status": "POSTED"
                if state.get("posted")
                else "ISSUED"
                if state.get("issued")
                else "APPROVED"
                if state.get("submitted")
                else "DRAFT",
            }
        raise AssertionError((service, path))

    monkeypatch.setattr(CreationOwners, "call", owner)
    body = {
        "name": "Opening product",
        "kind": "GOODS",
        "base_unit_id": unit,
        "purchase_price": "12.50",
        "opening_quantity": "3",
        "opening_date": "2026-04-01",
    }
    response = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert response.status_code == 201, response.text
    identity = response.json()["id"]
    failed = await client.post(root + f"/simple-product-creations/{identity}/advance", headers=auth)
    assert failed.status_code == 503
    if terminal_rejection:
        for _ in range(16):
            response = await client.post(
                root + f"/simple-product-creations/{identity}/advance", headers=auth
            )
            if response.status_code == 409:
                break
            assert response.status_code == 200, response.text
        assert response.status_code == 409 and "AUTHORITY_EXPIRED" in response.text
        saved = await client.get(root + f"/simple-product-creations/{identity}", headers=auth)
        assert saved.json()["step"] == "POST"
        assert state["post_attempts"] == 1 and state["operation_reads"] == 2
    result = await finish(client, root, auth, identity)
    assert result["opening_posted"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(Item.id))) == 1
    assert (
        sum(path.endswith("/vouchers") and method == "POST" for _, method, path, _, _ in calls) == 1
    )
    if terminal_rejection:
        posts = [(body, key) for _, _, path, body, key in calls if path.endswith("/post")]
        assert len(posts) == 2 and posts[0][0] == posts[1][0] and posts[0][1] != posts[1][1]


async def test_rejected_post_can_retry_same_voucher_but_pending_post_cannot_duplicate(
    client, factory, tenant_a, monkeypatch
):
    await test_opening_workflow_uses_exact_native_manifest_and_resumes_uncertain_create(
        client, factory, tenant_a, monkeypatch, terminal_rejection=True
    )


async def test_rejected_input_can_be_corrected_but_committed_or_uncertain_create_cannot(
    client, factory, tenant_a, monkeypatch
):
    from catalog.tasks.simple_creation_transport import CreationOwners, ServiceUnavailableError

    root, auth, unit = await starter(factory, tenant_a)
    body = {"name": "Correctable product", "base_unit_id": unit, "model_code": "DISABLED"}
    from catalog.models.configuration import ProductEntryOptionPolicy

    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            policy = await db.scalar(
                select(ProductEntryOptionPolicy).where(
                    ProductEntryOptionPolicy.revision_id.is_not(None)
                )
            )
            policy.model_mode, policy.model_default = "OPTIONAL", False
    response = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=body,
    )
    assert response.status_code == 201, response.text
    route = root + "/simple-product-creations/" + response.json()["id"]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            policy = await db.scalar(
                select(ProductEntryOptionPolicy).where(
                    ProductEntryOptionPolicy.revision_id.is_not(None)
                )
            )
            policy.model_mode, policy.model_default = "DISABLED", None
    rejected = await client.post(route + "/advance", headers=auth)
    assert rejected.status_code == 422, rejected.text
    status = (await client.get(route, headers=auth)).json()
    assert status["can_edit"]
    correction = {
        "expected_version": status["row_version"],
        "product": {"name": "Corrected product", "base_unit_id": unit},
    }
    key = auth | {"Idempotency-Key": str(uuid7())}
    revised = await client.patch(route, headers=key, json=correction)
    assert revised.status_code == 200, revised.text
    assert (await client.patch(route, headers=key, json=correction)).json() == revised.json()
    original = CreationOwners.call

    async def uncertain(self, service, method, path, body=None, key=None):
        result = await original(self, service, method, path, body, key)
        if path.endswith("/products"):
            raise ServiceUnavailableError("Lost native response")
        return result

    monkeypatch.setattr(CreationOwners, "call", uncertain)
    assert (await client.post(route + "/advance", headers=auth)).status_code == 503
    status = (await client.get(route, headers=auth)).json()
    assert not status["can_edit"]
    denied = await client.patch(
        route,
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json=correction | {"expected_version": status["row_version"]},
    )
    assert denied.status_code == 409
    monkeypatch.setattr(CreationOwners, "call", original)
    result = await finish(client, root, auth, response.json()["id"])
    assert not result["can_edit"]
    assert (
        await client.patch(
            route,
            headers=auth | {"Idempotency-Key": str(uuid7())},
            json=correction | {"expected_version": result["row_version"]},
        )
    ).status_code == 409
