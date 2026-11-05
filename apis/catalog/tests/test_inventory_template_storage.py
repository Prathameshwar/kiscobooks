import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.inventory_templates import (
    InventoryProfileTemplate,
    InventoryProfileTemplateRevision,
)
from catalog.schemas.inventory_templates import InventoryRevisionInput
from tests.inventory_factories import seed_template
from tests.profile_factories import seed_identifier_profile


async def test_inventory_template_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    scopes = ((tenant_a, uuid7()), (tenant_b, uuid7()))
    for tenant, company in scopes:
        await seed_template(factory, tenant, company)
    for tenant, company in scopes:
        with tenant_scope(tenant):
            async with factory() as db:
                for model in (InventoryProfileTemplate, InventoryProfileTemplateRevision):
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == 1
                    assert isinstance(
                        rows[0], InventoryProfileTemplate | InventoryProfileTemplateRevision
                    )
                    assert rows[0].company_id == company and rows[0].tenant_id == tenant


async def test_inventory_database_enforces_scope_and_tracking_coherence(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, other = uuid7(), uuid7()
    own, _ = await seed_template(factory, tenant_a, company)
    foreign, _ = await seed_template(factory, tenant_a, other)
    identifier = await seed_identifier_profile(factory, tenant_a, company)
    foreign_identifier = await seed_identifier_profile(factory, tenant_a, other)
    valid = {
        "tenant_id": tenant_a,
        "company_id": company,
        "template_id": own,
        "revision": 2,
        "row_version": 1,
        **InventoryRevisionInput().model_dump(),
    }
    for changes in (
        {"template_id": foreign},
        {"revision": 1},
        {"revision": 0},
        {"row_version": 0},
        {"identifier_profile_id": foreign_identifier, "serial_tracking": True},
        {"identifier_profile_id": identifier},
        {"expiry_required": True},
        {"manufacture_date_required": True},
        {"shelf_life_days": 1},
        {"lot_tracking": True, "shelf_life_days": 0},
        {"lot_tracking": True, "shelf_life_days": 36501},
        {"lot_tracking": True, "expiry_required": True, "minimum_remaining_life_days": -1},
        {"lot_tracking": True, "expiry_required": True, "minimum_remaining_life_days": 36501},
        {"lot_tracking": True, "minimum_remaining_life_days": 0},
        {"issue_strategy": "FEFO"},
        {"issue_strategy": "ANY"},
        {"valuation_method": "ANY"},
        {"valuation_method": "SPECIFIC"},
        {
            "lot_tracking": True,
            "expiry_required": True,
            "shelf_life_days": 2,
            "minimum_remaining_life_days": 3,
        },
    ):
        with tenant_scope(tenant_a), pytest.raises(IntegrityError):
            async with factory.begin() as db:
                db.add(InventoryProfileTemplateRevision(**{**valid, **changes}))
                await db.flush()
