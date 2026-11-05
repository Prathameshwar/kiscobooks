import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.commercial import ProductType, ProductTypeRevision
from catalog.schemas.commercial import TypeRevisionInput
from tests.profile_binding_factories import CASES, GOODS, ProfileCase


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.field)
async def test_profile_binding_foreign_keys_enforce_company_and_tenant(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    case: ProfileCase,
) -> None:
    company = uuid7()
    _, own = await case.seed(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            parent = ProductType(
                tenant_id=tenant_a, company_id=company, code="TYPE", name="Type", kind="GOODS"
            )
            db.add(parent)
            await db.flush()
            parent_id = parent.id
        common = {
            "tenant_id": tenant_a,
            "company_id": company,
            "product_type_id": parent_id,
            "kind": "GOODS",
            **TypeRevisionInput.model_validate(GOODS).model_dump(mode="json"),
        }
        async with factory.begin() as db:
            db.add(ProductTypeRevision(**{**common, case.field: own}, revision=1))
            await db.flush()
    for foreign_tenant, foreign_company in ((tenant_a, uuid7()), (tenant_b, company)):
        _, foreign = await case.seed(factory, foreign_tenant, foreign_company)
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(ProductTypeRevision(**{**common, case.field: foreign}, revision=2))
                await db.flush()
