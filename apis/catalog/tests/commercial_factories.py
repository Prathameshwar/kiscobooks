"""Small commercial fixtures; sources remain signed company-owned projections."""

import datetime as dt
import uuid

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Country, Currency, State
from catalog.models.commercial import (
    Brand,
    BrandManufacturer,
    BrandSeries,
    Manufacturer,
    ManufacturerSite,
    ProductType,
    ProductTypeRevision,
)
from tests.test_api import headers
from tests.test_classification_api import setup_source


async def auth(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    *,
    version: int = 2,
    facts: tuple[SnapshotRecord, ...] | None = None,
) -> dict[str, str]:
    await setup_source(factory, tenant, company, user, version=version, facts=facts)
    return headers(
        company,
        tenant=tenant,
        user=user,
        permission=[
            *(
                entity + suffix
                for entity in (
                    "brand",
                    "brand_series",
                    "manufacturer",
                    "manufacturer_site",
                    "brand_manufacturer",
                    "product_type",
                )
                for suffix in (".read", ".manage")
            ),
            "brand.move",
            "product_type.publish",
        ],
    )


async def reference_data(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory.begin() as db:
        db.add(
            Currency(
                code="INR",
                numeric_code="356",
                name="Rupee",
                symbol="INR",
                minor_unit=2,
                major_unit_name="Rupees",
            )
        )
        await db.flush()
        for code, iso3, numeric in (("IN", "IND", "356"), ("US", "USA", "840")):
            db.add(
                Country(
                    code=code,
                    iso3=iso3,
                    numeric_code=numeric,
                    name=iso3,
                    official_name=iso3,
                    default_currency_code="INR",
                    phone_prefix="1",
                    subdivision_label="State",
                )
            )
        await db.flush()
        db.add_all(
            [
                State(
                    code="IN-MH", country_code="IN", name="Maharashtra", subdivision_type="State"
                ),
                State(code="US-CA", country_code="US", name="California", subdivision_type="State"),
            ]
        )


async def seed_commercial(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, company: uuid.UUID
) -> dict[str, uuid.UUID]:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            common = {"tenant_id": tenant, "company_id": company}
            brand = Brand(id=uuid7(), **common, code="BRAND", name="Brand")
            manufacturer = Manufacturer(id=uuid7(), **common, code="MAKER", name="Maker")
            product_type = ProductType(
                id=uuid7(), **common, code="GOODS", name="Goods", kind="GOODS"
            )
            db.add_all([brand, manufacturer, product_type])
            await db.flush()
            rows: list[
                Brand
                | Manufacturer
                | ProductType
                | BrandSeries
                | ManufacturerSite
                | BrandManufacturer
                | ProductTypeRevision
            ] = [
                brand,
                manufacturer,
                product_type,
                BrandSeries(**common, brand_id=brand.id, code="SERIES", name="Series"),
                ManufacturerSite(
                    **common,
                    manufacturer_id=manufacturer.id,
                    code="SITE",
                    name="Site",
                    country_code="IN",
                    state_code="IN-MH",
                ),
                BrandManufacturer(
                    **common,
                    brand_id=brand.id,
                    manufacturer_id=manufacturer.id,
                    production_role="OEM",
                    valid_from=dt.date(2020, 1, 1),
                ),
                ProductTypeRevision(
                    **common,
                    product_type_id=product_type.id,
                    revision=1,
                    kind="GOODS",
                    inventory_modes=["STOCK"],
                    tracking_modes=["NONE"],
                    unit_dimensions=["COUNT"],
                    allow_variants=True,
                    require_brand=False,
                    require_manufacturer=False,
                    require_expiry=False,
                    inventory_template_revision_id=None,
                    warranty_revision_id=None,
                    return_policy_revision_id=None,
                    handling_revision_id=None,
                ),
            ]
            db.add_all(rows)
            await db.flush()
            return {row.__tablename__: row.id for row in rows}
