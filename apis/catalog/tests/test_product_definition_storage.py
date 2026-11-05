import uuid
from typing import Any

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    CONFIGURATION_MODELS,
    PRODUCT_DEFINITION_MODELS,
    FamilyCategory,
    ItemBarcode,
)
from tests.product_definition_factories import seed_definitions

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_all_nineteen_definition_tables_isolate_tenants_and_foreign_references(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    models: tuple[type[Any], ...] = (*CONFIGURATION_MODELS, *PRODUCT_DEFINITION_MODELS)
    own_company, own = await seed_definitions(factory, tenant_a)
    foreign_company, foreign = await seed_definitions(factory, tenant_b)
    for tenant, company in ((tenant_a, own_company), (tenant_b, foreign_company)):
        with tenant_scope(tenant):
            async with factory() as db:
                for model in models:
                    rows = list(await db.scalars(select(model)))
                    assert rows and all(
                        row.tenant_id == tenant and row.company_id == company for row in rows
                    )
                    assert (
                        all(row.id != foreign.get(model.__tablename__) for row in rows)
                        if tenant == tenant_a
                        else True
                    )
    # Every new native table has scoped ownership: changing company while retaining
    # its owner references must fail under the actual database FK/check constraints.
    with tenant_scope(tenant_a):
        async with factory() as db:
            originals = [(model, await db.get(model, own[model.__tablename__])) for model in models]
        for model, row in originals:
            assert row is not None
            values = {column.name: getattr(row, column.name) for column in model.__table__.columns}
            values.update(id=uuid7(), company_id=foreign_company)
            with pytest.raises((IntegrityError, OperationalError)) as rejected:
                async with factory.begin() as db:
                    db.add(model(**values))
                    await db.flush()
            if isinstance(rejected.value, OperationalError):
                assert rejected.value.orig is not None
                assert rejected.value.orig.args[0] == 3819
        for row in (
            FamilyCategory(
                tenant_id=tenant_a,
                company_id=own_company,
                family_id=own["product_family"],
                scheme_id=own["category_scheme"],
                category_id=own["item_category"],
                is_primary=True,
                primary_slot=None,
            ),
            ItemBarcode(
                tenant_id=tenant_a,
                company_id=own_company,
                item_id=own["item"],
                binding_id=foreign["item_unit_binding"],
                value="foreign",
                symbology="CODE128",
                is_active=True,
            ),
        ):
            with pytest.raises((IntegrityError, OperationalError)) as rejected:
                async with factory.begin() as db:
                    db.add(row)
                    await db.flush()
            if isinstance(rejected.value, OperationalError):
                assert rejected.value.orig is not None
                assert rejected.value.orig.args[0] == 3819
