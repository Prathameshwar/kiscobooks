import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import UnitOfMeasure
from catalog.models.tax import TaxRateComponent
from tests.tax_factories import seed_tax
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_fixed_cess_freezes_its_independent_unit_semantics(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            unit = UnitOfMeasure(
                tenant_id=tenant_a,
                company_id=company,
                code="CESS_UNIT",
                symbol="cu",
                name="Independent cess unit",
                dimension="COUNT",
                decimal_places=0,
                quantity_increment=Decimal(1),
            )
            db.add(unit)
            await db.flush()
            unit_id = unit.id
            db.add(
                TaxRateComponent(
                    tenant_id=tenant_a,
                    company_id=company,
                    rate_id=ids["rate_INTER_STATE"],
                    component_key="CESS",
                    component="CESS",
                    kind="FIXED_PER_UNIT",
                    amount=Decimal(1),
                    currency="INR",
                    unit_id=unit_id,
                    basis_quantity=Decimal(1),
                    rounding_mode="HALF_UP",
                    position=1,
                    row_version=1,
                )
            )
    response = await client.patch(
        root + "/units/" + str(unit_id),
        headers=command_headers(auth),
        json={"expected_version": 1, "decimal_places": 1},
    )
    assert response.status_code == 409, response.text
