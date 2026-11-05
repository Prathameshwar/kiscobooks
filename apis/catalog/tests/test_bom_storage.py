"""BOM native storage isolates every table and enforces immutable-copy parent scope."""

import datetime as dt
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from catalog.models.boms import BOM_MODELS, BomAssignment, BomComponent, BomOutput
from tests.bom_factories import seed_bom


async def test_all_bom_tables_are_tenant_isolated(factory, tenant_a, tenant_b):
    _, own = await seed_bom(factory, tenant_a)
    _, foreign = await seed_bom(factory, tenant_b)
    for tenant, visible, hidden in ((tenant_a, own, foreign), (tenant_b, foreign, own)):
        with tenant_scope(tenant):
            async with factory() as db:
                for model in BOM_MODELS:
                    ids = set(await db.scalars(select(model.id)))
                    assert visible[model.__tablename__] in ids
                    assert hidden[model.__tablename__] not in ids


async def test_bom_children_reject_foreign_scope_and_invalid_parent(factory, tenant_a, tenant_b):
    company, own = await seed_bom(factory, tenant_a)
    _, foreign = await seed_bom(factory, tenant_b)
    common = {
        "tenant_id": tenant_a,
        "company_id": company,
        "line_key": uuid7(),
        "sequence": 2,
        "item_id": own["item"],
        "unit_revision_id": own["unit_revision"],
    }
    with tenant_scope(tenant_a):
        for parent in (
            {"draft_id": foreign["next_draft"], "revision_id": None},
            {"draft_id": own["next_draft"], "revision_id": own["bom_revision"]},
            {"draft_id": None, "revision_id": None},
        ):
            with pytest.raises(IntegrityError):
                async with factory.begin() as db:
                    await db.execute(
                        insert(BomComponent).values(
                            **common,
                            **parent,
                            quantity=Decimal("1"),
                            basis="GROSS_INPUT",
                            loss_fraction=Decimal("0"),
                            timing="PER_BASIS",
                        )
                    )
        with pytest.raises(IntegrityError):
            async with factory.begin() as db:
                await db.execute(
                    insert(BomOutput).values(
                        **{**common, "sequence": 1},
                        draft_id=None,
                        revision_id=foreign["bom_revision"],
                        nominal_quantity=Decimal("1"),
                        yield_fraction=Decimal("1"),
                        role="PRIMARY",
                    )
                )


async def test_assignment_enforces_primary_output_and_keeps_inactive_history(factory, tenant_a):
    company, own = await seed_bom(factory, tenant_a)
    common = {
        "tenant_id": tenant_a,
        "company_id": company,
        "bom_revision_id": own["bom_revision"],
        "item_id": own["item"],
        "valid_from": dt.date(2090, 1, 1),
        "change_reason": "Retained applicability",
    }
    with tenant_scope(tenant_a):
        for extra in ({}, {"output_role": "SCRAP"}):
            with pytest.raises(IntegrityError):
                async with factory.begin() as db:
                    await db.execute(insert(BomAssignment).values(**common, **extra))
        async with factory.begin() as db:
            db.add_all([BomAssignment(**common, is_active=False) for _ in range(2)])
            await db.flush()
            rows = list(await db.scalars(select(BomAssignment)))
            assert len(rows) == 3
            assert all(row.scope_key == "*" for row in rows)
