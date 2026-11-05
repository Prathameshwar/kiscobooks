import pytest

from billing_platform.db.history import previous_scalar
from billing_platform.db.session import create_session_factory
from billing_platform.db.tenant_context import TenantContextError, tenant_scope
from billing_platform.ids import uuid7
from tests.models import CompanyThing, TenantThing


async def test_previous_scalar_preserves_values_across_edits_expiry_and_rollback(engine):
    factory = create_session_factory(engine, guarded=True)
    tenant = uuid7()
    with tenant_scope(tenant):
        async with factory() as db:
            row = TenantThing(tenant_id=tenant, name="retained")
            db.add(row)
            with pytest.raises(ValueError):
                await db.run_sync(lambda sync: previous_scalar(sync, row, "name"))
            await db.commit()
            assert await db.run_sync(lambda sync: previous_scalar(sync, row, "name")) == "retained"
            row.name = "pending"
            assert await db.run_sync(lambda sync: previous_scalar(sync, row, "name")) == "retained"
            db.expire(row, ["name"])
            row.name = "replacement"
            assert await db.run_sync(lambda sync: previous_scalar(sync, row, "name")) == "retained"
            await db.rollback()
            await db.refresh(row)
            assert row.name == "retained"
            db.expire(row, ["currency"])
            row.currency = "INR"
            assert await db.run_sync(lambda sync: previous_scalar(sync, row, "currency")) is None
            with pytest.raises(ValueError):
                await db.run_sync(lambda sync: previous_scalar(sync, row, "unknown_attribute"))
            with tenant_scope(uuid7()), pytest.raises(TenantContextError):
                await db.run_sync(lambda sync: previous_scalar(sync, row, "name"))


async def test_previous_scalar_keeps_company_scope_on_fallback(engine):
    factory = create_session_factory(engine, guarded=True)
    tenant, company = uuid7(), uuid7()
    with tenant_scope(tenant):
        async with factory() as db:
            row = CompanyThing(tenant_id=tenant, company_id=company)
            db.add(row)
            await db.commit()
            db.expire(row, ["company_id"])
            row.company_id = company
            assert (
                await db.run_sync(lambda sync: previous_scalar(sync, row, "company_id")) == company
            )
