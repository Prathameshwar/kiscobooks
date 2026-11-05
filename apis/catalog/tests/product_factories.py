"""Native product fixtures with real owner references and signed Identity context."""

import uuid
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ProductType, ProductTypeRevision, UnitOfMeasure
from tests.test_api import headers
from tests.test_classification_api import setup_source


async def setup_product(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    *,
    kind: str = "GOODS",
    advanced: bool = True,
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str], dict[str, Any]]:
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant, company, user)
    with tenant_scope(tenant):
        async with factory.begin() as db:
            common = {"tenant_id": tenant, "company_id": company}
            # Existing suites describe pre-rollout companies; new simple-mode tests
            # explicitly request advanced=False to exercise the production fallback.
            if advanced:
                from catalog.models.product_authoring import CompanyProductAuthoringConfiguration

                db.add(
                    CompanyProductAuthoringConfiguration(
                        id=uuid7(),
                        **common,
                        product_family_sku_enabled=True,
                        row_version=1,
                        change_reason="Legacy-company fixture",
                    )
                )
            owner = ProductType(id=uuid7(), code="GENERAL", name="General", kind=kind, **common)
            unit = UnitOfMeasure(
                id=uuid7(),
                code="PCS" if kind == "GOODS" else "HR",
                symbol="pc" if kind == "GOODS" else "h",
                name="Pieces" if kind == "GOODS" else "Hours",
                dimension="COUNT" if kind == "GOODS" else "TIME",
                decimal_places=0 if kind == "GOODS" else 2,
                quantity_increment=1 if kind == "GOODS" else "0.25",
                **common,
            )
            db.add_all([owner, unit])
            await db.flush()
            revision = ProductTypeRevision(
                id=uuid7(),
                product_type_id=owner.id,
                revision=1,
                kind=kind,
                inventory_modes=["STOCK"] if kind == "GOODS" else ["NON_STOCK"],
                tracking_modes=["NONE"],
                unit_dimensions=[unit.dimension],
                allow_variants=True,
                require_brand=False,
                require_manufacturer=False,
                require_expiry=False,
                published_at=utcnow(),
                **common,
            )
            db.add(revision)
            await db.flush()
            body = {
                "code": "PRODUCT",
                "name": "Product",
                "kind": kind,
                "product_type_revision_id": str(revision.id),
                "default_item": {
                    "sku": "SKU1",
                    "name": "Product SKU",
                    "base_unit_id": str(unit.id),
                    "min_sale_quantity": "1",
                },
            }
    auth = headers(
        company,
        tenant=tenant,
        user=user,
        permission=[
            "item.create",
            "item.read",
            "item.update",
            "unit.read",
            "product_type.read",
            "brand.read",
            "brand_series.read",
            "product_configuration.read",
            "product_definition.read",
        ],
    )
    return company, user, auth, body
