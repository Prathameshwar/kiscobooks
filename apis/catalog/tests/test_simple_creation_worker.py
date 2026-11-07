"""Saved product jobs resume without a browser and retain visible retry state."""

from types import SimpleNamespace

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import select

from catalog.models.simple_product_creation import SimpleProductCreation
from catalog.tasks import simple_creation_worker as worker
from tests.conftest import ACTOR_SECRET


async def test_worker_resumes_saved_creation_and_persists_retry(
    factory, app, monkeypatch, tenant_a
):
    company, user, identity, unit = (uuid7() for _ in range(4))
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(SimpleProductCreation(
                id=identity, tenant_id=tenant_a, company_id=company,
                command_key="saved-product", request_hash="a" * 64, code="ITEM001",
                request={"name": "Grams product", "base_unit_id": str(unit)},
                progress={}, created_by=user, updated_by=user,
            ))
    calls = []

    async def fresh_context(*args):
        calls.append("authority")
        return object(), SimpleNamespace(company_id=company), {}

    async def drive(*args):
        calls.append("drive")

    monkeypatch.setattr(worker, "fetch_context", fresh_context)
    monkeypatch.setattr(worker.simple_product_creation, "drive", drive)
    settings = SimpleNamespace(
        identity_source=object(), actor_signing_secret=SecretStr(ACTOR_SECRET),
        simple_creation_origins={}, voucher_source_delivery=None,
    )
    scope = SimpleNamespace(tenant_id=tenant_a, company_id=company)
    assert await worker.work_scope(app, settings, scope) == 1
    assert calls == ["authority", "drive"]

    await worker.defer(factory, scope, "simple", identity, None, RuntimeError("private detail"))
    with tenant_scope(tenant_a):
        async with factory() as db:
            row = await db.scalar(select(SimpleProductCreation).where(
                SimpleProductCreation.id == identity
            ))
            assert row is not None
            assert "private detail" not in row.progress["last_error"]
            assert row.progress["worker_attempt"] == 1
    assert await worker.work_scope(app, settings, scope) == 0


async def test_failed_jobs_do_not_hide_later_jobs_beyond_the_worker_page(
    factory, app, monkeypatch, tenant_a
):
    company, user, unit = (uuid7() for _ in range(3))
    ids = [uuid7() for _ in range(21)]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add_all(SimpleProductCreation(
                id=identity, tenant_id=tenant_a, company_id=company,
                command_key=f"saved-{index}", request_hash="a" * 64,
                code=f"ITEM{index:03}",
                request={"name": "Grams product", "base_unit_id": str(unit)},
                progress={}, created_by=user, updated_by=user,
            ) for index, identity in enumerate(ids))

    seen = []

    async def fresh_context(*args):
        return object(), SimpleNamespace(company_id=company), {}

    async def fail(factory, actor, context, identity, owners):
        seen.append(identity)
        raise RuntimeError("temporary owner failure")

    monkeypatch.setattr(worker, "fetch_context", fresh_context)
    monkeypatch.setattr(worker.simple_product_creation, "drive", fail)
    settings = SimpleNamespace(
        identity_source=object(), actor_signing_secret=SecretStr(ACTOR_SECRET),
        simple_creation_origins={}, voucher_source_delivery=None,
    )
    scope = SimpleNamespace(tenant_id=tenant_a, company_id=company)
    for _ in ids:
        assert await worker.work_scope(app, settings, scope) == 0
    assert set(seen) == set(ids)
