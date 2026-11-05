import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ProductFamily, UnitOfMeasure
from catalog.models.bulk import BulkJob
from catalog.tasks import bulk_execution
from catalog.tasks.bulk_execution import step
from catalog.tasks.identity_source import IdentitySourceUnavailableError
from tests.bulk_factories import post, proofs, run, setup, unit_row
from tests.conftest import ACTOR_SECRET
from tests.pricing_factories import foundation, publish_price, setup_pricing
from tests.product_factories import setup_product
from tests.test_api import headers
from tests.test_bulk_products_prices import reviewed_commit
from tests.test_unit_api import policy, seed_context

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("mode,action", [("CREATE_ONLY", "UPDATE"), ("UPDATE_ONLY", "CREATE")])
async def test_explicit_commands_cannot_bypass_import_mode(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    mode: str,
    action: str,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}"
    old = await post(client, root, auth, "/units", unit_row("old")["data"], status=201)
    row = unit_row("new")
    row["action"] = action
    if action == "UPDATE":
        row["target"], row["data"] = {"id": old["id"]}, {"name": "Unauthorized mode"}
    job = await post(
        client,
        root + "/bulk-jobs",
        auth,
        "",
        {
            "format": "JSON",
            "mode": mode,
            "records": [row],
        },
    )
    await post(
        client,
        root + "/bulk-jobs",
        auth,
        f"/{job['id']}/validate",
        {
            "expected_version": job["row_version"],
        },
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "FAILED"
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert list(await db.scalars(select(UnitOfMeasure.name))) == ["old"]


async def test_auto_update_does_not_require_create_permission(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    await post(client, root, auth, "/product-families", body, status=201)
    with tenant_scope(tenant_a):
        async with factory() as db:
            family = (await db.scalars(select(ProductFamily.id))).one()
    job = await post(
        client,
        root + "/bulk-jobs",
        auth,
        "",
        {
            "format": "JSON",
            "mode": "UPDATE_ONLY",
            "records": [
                {
                    "key": "rename",
                    "change_set": "rename",
                    "resource": "product_family",
                    "target": {"id": str(family)},
                    "data": {"name": "Updated without create"},
                }
            ],
        },
    )
    await post(
        client,
        root + "/bulk-jobs",
        auth,
        f"/{job['id']}/validate",
        {
            "expected_version": job["row_version"],
        },
    )
    await step(
        factory,
        proofs(tenant_a, company, user, denied=frozenset({"item.create"})),
        tenant_a,
        company,
        user,
        uuid.UUID(job["id"]),
        ACTOR_SECRET.encode(),
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(select(BulkJob.state).where(BulkJob.id == uuid.UUID(job["id"])))
                == "READY"
            )


async def test_preview_and_download_respect_record_metadata_denies(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(client, root, auth, "", {"format": "JSON", "records": [unit_row("ea")]})
    rows = (await client.get(root + "/" + job["id"] + "/records", headers=auth)).json()["items"]
    ticket = (await client.get(root + "/" + job["id"] + "/report-ticket", headers=auth)).json()
    await seed_context(
        factory,
        tenant_a,
        company,
        user,
        (policy(user, "source_sheet", "read", entity="catalog.bulk_job_record"),),
        version=3,
    )
    assert (
        await client.get(root + "/" + job["id"] + "/records/" + rows[0]["id"], headers=auth)
    ).status_code == 403
    assert (await client.get(ticket["download_path"], headers=auth)).status_code == 403


async def test_expired_proof_during_preview_rolls_back_without_marking_invalid(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(client, root, auth, "", {"format": "JSON", "records": [unit_row("ea")]})
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    original = bulk_execution.current_actor
    calls = 0

    async def expiring(*args: Any, **kwargs: Any) -> Actor:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise IdentitySourceUnavailableError("expired proof")
        return await original(*args, **kwargs)

    monkeypatch.setattr(bulk_execution, "current_actor", expiring)
    with pytest.raises(IdentitySourceUnavailableError):
        await step(
            factory,
            proofs(tenant_a, company, user),
            tenant_a,
            company,
            user,
            uuid.UUID(job["id"]),
            ACTOR_SECRET.encode(),
        )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(select(BulkJob.state).where(BulkJob.id == uuid.UUID(job["id"])))
                == "VALIDATING"
            )
            assert list(await db.scalars(select(UnitOfMeasure.id))) == []


async def test_distinct_child_identifiers_can_share_one_product_aggregate(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, _, body = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    await reviewed_commit(
        client,
        factory,
        tenant_a,
        company,
        user,
        auth,
        {
            "format": "JSON",
            "records": [
                {
                    "key": "family",
                    "change_set": "product",
                    "resource": "product_family",
                    "data": body,
                },
                *[
                    {
                        "key": key,
                        "change_set": "product",
                        "resource": "item",
                        "action": "CREATE_BARCODE",
                        "target": {"record": "family", "field": "default_item.id"},
                        "data": {"value": key, "symbology": "CODE128"},
                    }
                    for key in ("first", "second")
                ],
            ],
        },
    )


async def test_purchase_filter_cannot_reveal_targets_without_purchase_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    configured = await foundation(client, root, auth, ids, purpose="PURCHASE")
    await publish_price(client, root, auth, configured)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    restricted = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=sorted(CATALOG_PERMISSIONS - {"purchase_price.read", "purchase_price.manage"}),
    )
    response = await client.post(
        root + "/bulk-jobs",
        headers={**restricted, "Idempotency-Key": str(uuid7())},
        json={
            "format": "FILTER",
            "resource": "item_price",
            "action": "ADJUST",
            "all_rows": True,
            "data": {"method": "SET", "value": "1"},
        },
    )
    assert response.status_code == 403, response.text


async def test_review_evidence_cannot_retain_an_unbounded_dependency_payload() -> None:
    from billing_platform.errors import ConflictError

    from catalog.tasks.bulk_access import Evidence

    row = ProductFamily(
        id=uuid7(),
        code="P",
        name="P",
        kind="GOODS",
        row_version=1,
        custom_fields={"cf_note": "x" * (256 * 1024)},
    )
    async with AsyncSession() as db:
        with pytest.raises(ConflictError, match="bound"):
            Evidence(db).capture(db.sync_session, row)
