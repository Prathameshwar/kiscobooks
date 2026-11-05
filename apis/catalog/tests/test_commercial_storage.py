import datetime as dt
import uuid
from typing import Any

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.commercial import (
    Brand,
    BrandManufacturer,
    BrandSeries,
    Manufacturer,
    ManufacturerSite,
    ProductType,
    ProductTypeRevision,
)
from tests.commercial_factories import reference_data, seed_commercial


async def test_all_seven_commercial_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await reference_data(factory)
    companies = (uuid7(), uuid7())
    for tenant, company in zip((tenant_a, tenant_b), companies, strict=True):
        await seed_commercial(factory, tenant, company)
    for tenant, company in zip((tenant_a, tenant_b), companies, strict=True):
        with tenant_scope(tenant):
            async with factory() as db:
                for model in (
                    Brand,
                    BrandSeries,
                    Manufacturer,
                    ManufacturerSite,
                    BrandManufacturer,
                    ProductType,
                    ProductTypeRevision,
                ):
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == 1
                    assert isinstance(
                        rows[0],
                        Brand
                        | BrandSeries
                        | Manufacturer
                        | ManufacturerSite
                        | BrandManufacturer
                        | ProductType
                        | ProductTypeRevision,
                    )
                    assert rows[0].tenant_id == tenant and rows[0].company_id == company


async def test_commercial_database_references_and_checks(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    await reference_data(factory)
    company, other = uuid7(), uuid7()
    own = await seed_commercial(factory, tenant_a, company)
    foreign = await seed_commercial(factory, tenant_a, other)
    common: dict[str, Any] = {"tenant_id": tenant_a, "company_id": company}
    master = {**common, "code": "INVALID", "name": "Invalid"}
    revision = {
        **common,
        "revision": 2,
        "kind": "GOODS",
        "inventory_modes": ["STOCK"],
        "tracking_modes": ["NONE"],
        "unit_dimensions": ["COUNT"],
        "allow_variants": True,
        "require_brand": False,
        "require_manufacturer": False,
        "require_expiry": False,
    }
    for row in (
        Brand(**master, parent_brand_id=foreign["brand"]),
        Brand(**master, id=uuid7(), row_version=0),
        BrandSeries(**master, brand_id=foreign["brand"]),
        Manufacturer(**master, row_version=0),
        ManufacturerSite(**master, manufacturer_id=foreign["manufacturer"], country_code="IN"),
        ManufacturerSite(
            **master, manufacturer_id=own["manufacturer"], country_code="IN", state_code="US-CA"
        ),
        BrandManufacturer(
            **common,
            brand_id=foreign["brand"],
            manufacturer_id=own["manufacturer"],
            production_role="OEM",
            valid_from=dt.date(2025, 1, 1),
        ),
        BrandManufacturer(
            **common,
            brand_id=own["brand"],
            manufacturer_id=foreign["manufacturer"],
            production_role="OEM",
            valid_from=dt.date(2025, 1, 1),
        ),
        BrandManufacturer(
            **common,
            brand_id=own["brand"],
            manufacturer_id=own["manufacturer"],
            production_role="OEM",
            valid_from=dt.date(2025, 1, 1),
            valid_to=dt.date(2024, 1, 1),
        ),
        ProductType(**master, kind="INVALID"),
        ProductTypeRevision(**revision, product_type_id=foreign["product_type"]),
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(row)
                await db.flush()
