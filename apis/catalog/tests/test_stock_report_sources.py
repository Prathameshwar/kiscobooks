"""A complete Catalog cut is scoped, immutable, paged and held until publication."""

import secrets

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from billing_platform.owner_snapshot import SnapshotCredential
from billing_platform.service_auth import CompanyServiceScope
from pydantic import SecretStr
from reporting_contract.catalog_stock import CatalogStockOwner, acquire, exchange

from catalog.models.classification import ItemGroup
from tests.test_stock_source_fences import prepared


async def test_native_replenishment_definitions_use_the_products_exact_ordering_unit(
    app, client, factory, tenant_a
):
    from catalog.tasks.stock_report_sources import masters
    from tests.test_commercial_api import command_headers
    from tests.test_warehouse_policies import band, band_route, guard, provision, read

    fixture = await provision(client, factory, tenant_a)
    company, item = fixture["company"], fixture["item"]
    path = band_route(company, item)
    current = fixture["current"]
    view = await read(client, path, current)
    response = await client.put(
        path,
        headers=command_headers(current),
        json={"scopes": [band(fixture["binding"])], **guard(view)},
    )
    assert response.status_code == 200, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            import datetime as dt

            source = await masters(db, company, dt.date(2090, 1, 1))
    selected = next(row for row in source if row["kind"] == "ITEM" and row["item_id"] == item)
    policy = selected["replenishment"][0]
    assert policy["location_id"] is None
    assert policy["target_level"] == "20.0000"
    assert policy["order_multiple"] == "10.0000"


async def test_complete_master_pages_freeze_group_labels_and_reject_other_scope(
    app, client, tenant_a
):
    company, _, fence_id = await prepared(app.state.session_factory, tenant_a)
    from billing_platform.db.types import utcnow

    from catalog.models.stock_source import StockSourceFence

    with tenant_scope(tenant_a):
        async with app.state.session_factory.begin() as db:
            (await db.get(StockSourceFence, fence_id)).closed_at = utcnow()
        async with app.state.session_factory.begin() as db:
            for index in range(205):
                db.add(
                    ItemGroup(
                        tenant_id=tenant_a,
                        company_id=company,
                        code=f"G{index:03}",
                        name=f"Group {index}",
                        allowed_kind="GOODS",
                        is_active=True,
                    )
                )
    secret = SecretStr(secrets.token_hex(32))
    scopes = (CompanyServiceScope(tenant_id=tenant_a, company_id=company),)
    app.state.settings.stock_report_credentials["stock.qa"] = SnapshotCredential(
        secret=secret, scopes=scopes
    )
    owner = CatalogStockOwner(
        origin="http://127.0.0.1", key_id="stock.qa", secret=secret, scopes=scopes
    )
    identity = uuid7()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=owner.origin
    ) as transport:
        lease, records = await acquire(
            transport,
            owner,
            tenant=tenant_a,
            company=company,
            identity=identity,
            as_of=utcnow().date(),
        )
        assert len(records) == lease.record_count == 205
        with tenant_scope(tenant_a):
            with pytest.raises(ConflictError, match="stock posting"):
                async with app.state.session_factory.begin() as db:
                    from sqlalchemy import select

                    row = await db.scalar(
                        select(ItemGroup).where(ItemGroup.company_id == company).limit(1)
                    )
                    row.name = "Changed during report copy"
        _, replay = await acquire(
            transport,
            owner,
            tenant=tenant_a,
            company=company,
            identity=identity,
            as_of=utcnow().date(),
        )
        assert replay == records
        with pytest.raises(httpx.HTTPStatusError) as denied:
            await acquire(
                transport,
                owner,
                tenant=tenant_a,
                company=uuid7(),
                identity=uuid7(),
                as_of=utcnow().date(),
            )
        assert denied.value.response.status_code == 401
        body = {
            "tenant_id": str(tenant_a),
            "company_id": str(company),
            "source_id": str(identity),
            "as_of": utcnow().date().isoformat(),
            "offset": 0,
            "release": True,
        }
        await exchange(transport, owner, "/internal/v1/stock-report-sources", body)
        with tenant_scope(tenant_a):
            async with app.state.session_factory.begin() as db:
                import uuid

                row = await db.get(ItemGroup, uuid.UUID(next(r["group_id"] for r in records)))
                row.name = "Changed after publication"


async def test_private_source_requires_authentication(client):
    assert (await client.post("/internal/v1/stock-report-sources", json={})).status_code == 401
