"""The native signed feed carries published dated SKU bindings and master grids."""

import uuid

from billing_platform.db import tenant_scope

from catalog.api.voucher_sources import facts
from catalog.models.products import Item
from tests.unit_integrity_factories import setup_units


async def test_published_unit_history_and_master_facts_are_complete(factory, tenant_a):
    root, _, ids = await setup_units(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            item = await db.get(Item, ids["item"])
            item.status = "ACTIVE"
        async with factory() as db:
            revisions, after = await facts(db, tenant_a, company, "item_unit_revision", None, 1)
            master = revisions["masters"][0]
            assert master["entity_type"] == "item_unit_revision"
            assert master["facts"]["item_id"] == str(ids["item"])
            assert master["facts"]["numerator"] == "1"
            assert master["facts"]["denominator"] == "1"
            assert master["facts"]["usage_role"] == "BASE"
            units, _ = await facts(db, tenant_a, company, "unit", None, 128)
            unit = next(
                row for row in units["masters"] if row["source_id"] == master["facts"]["unit_id"]
            )
            assert unit["facts"]["quantity_increment"]
            assert unit["facts"]["dimension"] == "COUNT"
            items, _ = await facts(db, tenant_a, company, "item", None, 128)
            assert (
                next(row for row in items["masters"] if row["source_id"] == str(ids["item"]))[
                    "facts"
                ]["base_unit_id"]
                == master["facts"]["unit_id"]
            )
            other, _ = await facts(db, tenant_a, uuid.uuid4(), "item_unit_revision", None, 128)
            assert other["masters"] == []
