import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from billing_platform.db.access import company_object
from billing_platform.db.session import create_session_factory
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.errors import NotFoundError, PermissionDeniedError
from billing_platform.ids import uuid7
from tests.models import CompanyThing, ExemptThing


async def test_company_reference_cannot_cross_scope(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    tenant, company = uuid7(), uuid7()
    async with factory() as db:
        with unfiltered():
            row = CompanyThing(tenant_id=tenant, company_id=company)
            db.add(row)
            await db.commit()
        with tenant_scope(tenant):
            assert (
                await company_object(db, CompanyThing, row.id, company_id=company, lock=True) is row
            )
            with pytest.raises(PermissionDeniedError):
                await company_object(db, CompanyThing, row.id, company_id=uuid7())
            with pytest.raises(TypeError):
                await company_object(db, ExemptThing, row.id, company_id=company)
            with pytest.raises(NotFoundError):
                await company_object(db, CompanyThing, uuid7(), company_id=company)
    async with factory() as db:
        with tenant_scope(uuid7()), pytest.raises(NotFoundError):
            await company_object(db, CompanyThing, row.id, company_id=company)
