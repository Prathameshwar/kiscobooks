"""Consistent synthetic sources for unit integration regressions."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db import tenant_scope
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import InventoryProfileTemplateRevision, ProductFamily, ProductTypeRevision
from catalog.models.units import UnitOfMeasure
from tests.pricing_factories import setup_pricing
from tests.product_integrity_factories import features
from tests.profile_factories import seed_identifier_profile
from tests.source_factories import all_facts
from tests.tax_factories import seed_tax
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers


async def setup_units(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
) -> tuple[str, dict[str, str], dict[str, uuid.UUID]]:
    root, auth, ids = await setup_pricing(factory, tenant)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    await setup_source(
        factory,
        tenant,
        company,
        ids["actor_user"],
        version=3,
        facts=tuple(
            row for row in all_facts(company, ids["actor_user"]) if row.kind != "field_policy"
        ),
    )
    return root, auth, ids


async def serial_units(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
) -> tuple[str, dict[str, str], dict[str, uuid.UUID]]:
    root, auth, ids = await seed_tax(factory, tenant)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    identifier = await seed_identifier_profile(factory, tenant, company)
    with tenant_scope(tenant):
        async with factory.begin() as db:
            base = await db.get(UnitOfMeasure, ids["unit_of_measure"])
            family = await db.get(ProductFamily, ids["product_family"])
            assert base is not None and family is not None
            base.decimal_places, base.quantity_increment = 4, Decimal("0.0001")
            product_type = await db.get(ProductTypeRevision, family.product_type_revision_id)
            template = await db.get(
                InventoryProfileTemplateRevision, ids["inventory_profile_template_revision"]
            )
            assert product_type is not None and template is not None
            product_type.tracking_modes = ["BATCH_SERIAL"]
            template.lot_tracking = template.serial_tracking = template.expiry_required = True
            template.identifier_profile_id = identifier
    await features(
        factory,
        tenant,
        company,
        ids["actor_user"],
        {"batch_tracking", "serial_tracking", "expiry_tracking"},
    )
    return root, auth, ids


async def new_unit(
    client: AsyncClient, root: str, auth: dict[str, str], code: str, *, decimals: int = 0
) -> str:
    result = await client.post(
        root + "/units",
        headers=command_headers(auth),
        json={
            "code": code,
            "symbol": code,
            "name": code,
            "dimension": "COUNT",
            "decimal_places": decimals,
            "quantity_increment": "0.0001" if decimals else "1",
        },
    )
    assert result.status_code == 201, result.text
    return str(result.json()["id"])


async def latest_revision(
    client: AsyncClient, root: str, auth: dict[str, str], item: uuid.UUID, code: str
) -> dict[str, Any]:
    result = await client.get(root + f"/items/{item}/unit-bindings", headers=auth)
    assert result.status_code == 200, result.text
    binding = next(row for row in result.json()["items"] if row["code"] == code)
    result = await client.get(root + f"/item-unit-bindings/{binding['id']}/revisions", headers=auth)
    assert result.status_code == 200, result.text
    return dict(max(result.json()["items"], key=lambda row: row["revision"]))


def binding_body(unit: str, **changes: Any) -> dict[str, Any]:
    return {
        "expected_version": 1,
        "code": "ALT",
        "unit_id": unit,
        "role": "SALE",
        "numerator": 12,
        "denominator": 1,
        "quantity_decimal_places": 0,
        "quantity_increment": "1",
        "valid_from": "2090-01-01",
        **changes,
    }
