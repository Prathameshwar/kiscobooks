from decimal import Decimal

import pytest
from billing_platform.db.access import company_object
from billing_platform.db.session import create_session_factory
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.errors import NotFoundError, PermissionDeniedError
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncEngine

from catalog.models import Country, UnitOfMeasure


async def test_company_access_uses_real_tenant_and_company(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine, guarded=True)
    tenant, company, other_company = uuid7(), uuid7(), uuid7()
    async with factory() as db:
        with unfiltered():
            row = UnitOfMeasure(
                tenant_id=tenant,
                company_id=company,
                code="EA",
                symbol="ea",
                name="Each",
                dimension="COUNT",
                decimal_places=0,
                quantity_increment=Decimal(1),
            )
            db.add(row)
            await db.commit()
            row_id = row.id
        with tenant_scope(tenant):
            assert (
                await company_object(db, UnitOfMeasure, row_id, company_id=company, lock=True)
                is row
            )
            with pytest.raises(PermissionDeniedError):
                await company_object(db, UnitOfMeasure, row_id, company_id=other_company)
            with pytest.raises(NotFoundError):
                await company_object(db, UnitOfMeasure, uuid7(), company_id=company)
            with pytest.raises(TypeError):
                await company_object(db, Country, row_id, company_id=company)
            row.company_id = other_company
            with pytest.raises(TenantContextError):
                await db.flush()
    async with factory() as db:
        with tenant_scope(uuid7()), pytest.raises(NotFoundError):
            await company_object(db, UnitOfMeasure, row_id, company_id=company)
