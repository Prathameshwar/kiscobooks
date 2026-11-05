import secrets
import time
import uuid

import httpx
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import (
    CompanyServiceScope,
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from fastapi import FastAPI
from pydantic import SecretStr


async def test_scoped_catalog_snapshot_has_a_bound_signature(
    client: httpx.AsyncClient, app: FastAPI, tenant_a: uuid.UUID
) -> None:
    from decimal import Decimal

    from catalog.models.units import UnitOfMeasure

    tenant, company, unit = tenant_a, uuid7(), uuid7()
    owner, entity = "catalog", "unit"
    with tenant_scope(tenant):
        async with app.state.session_factory() as db, db.begin():
            db.add(
                UnitOfMeasure(
                    id=unit,
                    tenant_id=tenant,
                    company_id=company,
                    code="EA",
                    symbol="ea",
                    name="Unit",
                    dimension="COUNT",
                    decimal_places=0,
                    quantity_increment=Decimal("1"),
                    row_version=1,
                    is_active=True,
                )
            )
    secret = secrets.token_hex(32)
    key_id = "vouchers.snapshot.test"
    app.state.settings.voucher_snapshot_credentials[key_id] = SnapshotCredential(
        secret=SecretStr(secret),
        scopes=(CompanyServiceScope(tenant_id=tenant, company_id=company),),
    )
    path = f"/internal/v1/voucher-sources/{tenant}/{company}/{entity}"
    assert (await client.get(path)).status_code == 401
    framed = service_request_bytes(method="GET", path=path, query="limit=1", body=b"")
    stamp = int(time.time())
    key = ServiceKey("vouchers", owner, frozenset({"vouchers.snapshot.read"}), secret.encode())
    signature = sign_service_body(
        key, key_id=key_id, operation="vouchers.snapshot.read", timestamp=stamp, body=framed
    )
    request_headers = {
        "X-Source-Key-Id": key_id,
        "X-Source-Issued-At": str(stamp),
        "X-Source-Signature": signature,
    }
    response = await client.get(path + "?limit=1", headers=request_headers)
    assert response.status_code == 200, response.text
    verify_service_body(
        {
            key_id: ServiceKey(
                owner, "vouchers", frozenset({"vouchers.snapshot.response"}), secret.encode()
            )
        },
        key_id=key_id,
        issuer=owner,
        audience="vouchers",
        operation="vouchers.snapshot.response",
        timestamp=response.headers["x-source-issued-at"],
        signature=response.headers["x-source-signature"],
        body=service_response_bytes(request_bytes=framed, response_body=response.content),
        now=stamp,
    )
    assert (await client.get(path + "?limit=2", headers=request_headers)).status_code == 401
    assert (
        await client.get(
            path.replace(str(company), str(uuid.uuid4())) + "?limit=1", headers=request_headers
        )
    ).status_code == 401
    assert response.json()["bundle"]["masters"][0]["source_id"] == str(unit)


async def test_item_transaction_snapshot_carries_direction_and_stock_mode(
    factory, tenant_a: uuid.UUID
) -> None:
    from catalog.api.voucher_sources import facts
    from catalog.models.commercial import ProductTypeRevision
    from catalog.models.products import Item, ProductFamily
    from catalog.models.tax import ItemInventoryProfile
    from catalog.schemas.inventory_templates import InventoryRevisionInput
    from tests.inventory_factories import seed_template
    from tests.product_definition_factories import seed_definitions

    company, ids = await seed_definitions(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, ids["item"])
            family = await db.get(ProductFamily, ids["product_family"])
            assert item is not None and family is not None
            revision = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert revision is not None
            revision.inventory_modes = ["NON_STOCK"]
            item.sellable = False
            item.purchasable = True
        async with factory() as db:
            bundle, _ = await facts(
                db, tenant_a, company, "item_transaction_policy", None, 128
            )
    policy = next(
        row for row in bundle["masters"] if row["source_id"] == str(ids["item"])
    )
    assert policy["facts"] == {
        "kind": "GOODS",
        "item_version": item.row_version,
        "inventory_mode": "NON_STOCK",
        "sellable": False,
        "purchasable": True,
    }
    _, template_id = await seed_template(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, ids["item"])
            family = await db.get(ProductFamily, ids["product_family"])
            assert item is not None and family is not None
            revision = await db.get(ProductTypeRevision, family.product_type_revision_id)
            assert revision is not None
            revision.inventory_modes = ["STOCK"]
            item.row_version += 1
            db.add(ItemInventoryProfile(
                tenant_id=tenant_a, company_id=company, item_id=item.id,
                base_unit_id=item.base_unit_id, template_revision_id=template_id,
                **InventoryRevisionInput().model_dump(),
            ))
        async with factory() as db:
            stock_bundle, _ = await facts(
                db, tenant_a, company, "item_transaction_policy", None, 128
            )
    stock_policy = next(
        row for row in stock_bundle["masters"] if row["source_id"] == str(ids["item"])
    )
    assert stock_policy["facts"]["inventory_mode"] == "STOCK"
    assert stock_policy["source_version"] > policy["source_version"]


async def test_automatic_voucher_source_requires_current_native_company_projection(client, app, tenant_a):
    import datetime as dt
    from billing_platform.db.types import utcnow
    from billing_platform.owner_snapshot import request_headers
    from catalog.models.projections import ProjectionCheckpoint
    from catalog.tasks.projections import activate_snapshot
    from tests.source_factories import snapshot, all_facts
    from sqlalchemy import select
    company = uuid7()
    secret, key_id = secrets.token_hex(32), "vouchers.enrollment.test"
    app.state.settings.voucher_snapshot_credentials[key_id] = SnapshotCredential(secret=SecretStr(secret), allow_enrolled_companies=True)
    path = f"/internal/v1/voucher-sources/{tenant_a}/{company}/unit"
    def signed():
        frame = service_request_bytes(method="GET", path=path, query="", body=b"")
        return request_headers(requester="vouchers", owner="catalog", key_id=key_id, secret=secret.encode(), framed=frame)
    assert (await client.get(path, headers=signed())).status_code == 503
    with tenant_scope(tenant_a):
        async with app.state.session_factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, all_facts(company, uuid7())))
    available = await client.get(path, headers=signed())
    assert available.status_code == 200, available.text
    assert available.json()["bundle"]["company_id"] == str(company)
    with tenant_scope(tenant_a):
        async with app.state.session_factory.begin() as db:
            checkpoint = await db.scalar(select(ProjectionCheckpoint).where(ProjectionCheckpoint.company_id == company))
            checkpoint.expires_at = utcnow() - dt.timedelta(seconds=1)
    assert (await client.get(path, headers=signed())).status_code == 503
