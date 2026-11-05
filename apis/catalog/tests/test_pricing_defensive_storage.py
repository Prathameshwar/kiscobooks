import datetime as dt
import uuid
from decimal import Decimal

import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    Item,
    ItemGroup,
    ItemGroupParent,
    ItemUnitBinding,
    ItemUnitRevision,
    Outbox,
    ProductFamily,
)
from catalog.models import pricing as m
from catalog.schemas.pricing import DatedInput
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import PricingWork, purpose_access
from catalog.tasks.pricing_guards import discounts, restrictions
from catalog.tasks.product_commands import ProductWork
from tests.pricing_factories import pack_unit
from tests.pricing_storage_factories import seed_pricing

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def actor(tenant: uuid.UUID, company: uuid.UUID, user: uuid.UUID) -> Actor:
    return Actor(
        tenant,
        user,
        grants=(Grant(CATALOG_PERMISSIONS, Scope("company", company), dt.date(2000, 1, 1)),),
    )


async def test_price_children_inherit_purchase_read_and_write_authority(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    current = actor(tenant_a, company, ids["actor_user"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            plan = await db.get(m.PricePlan, ids["price_plan"])
            tier = await db.get(m.ItemPriceTier, ids["item_price_tier"])
            assert plan is not None and tier is not None
            plan.purpose, plan.price_level_id = "PURCHASE", None
            await db.flush()
            children = (tier, m.ItemPriceTier(draft_id=ids["item_price_draft"], price_id=None))
            for child in children:
                await purpose_access(ConfigurationAccess(db, current, company), child, write=True)
                for denied, write in (
                    ("purchase_price.read", False),
                    ("purchase_price.manage", True),
                ):
                    restricted = Actor(
                        tenant_a,
                        ids["actor_user"],
                        grants=(
                            Grant(
                                CATALOG_PERMISSIONS - {denied},
                                Scope("company", company),
                                dt.date(2000, 1, 1),
                            ),
                        ),
                    )
                    with pytest.raises(PermissionDeniedError):
                        await purpose_access(
                            ConfigurationAccess(db, restricted, company), child, write=write
                        )


async def test_history_owner_and_no_change_audit_contract(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    current = actor(tenant_a, company, ids["actor_user"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            access = ConfigurationAccess(db, current, company)
            state = await policy_state(db, current, company, lock=True)
            assert state is not None
            work = PricingWork(access, state)
            plan = await db.get(m.PricePlan, ids["price_plan"])
            assert plan is not None
            before = await access.values(plan)
            audit_count = await db.scalar(select(func.count(Outbox.id)))
            await work.record(plan, before, "update")
            assert (
                work.changed == {} and await db.scalar(select(func.count(Outbox.id))) == audit_count
            )
            with pytest.raises(PermissionDeniedError, match="different price history"):
                await work.history(
                    m.ItemPriceNumericRevision,
                    DatedInput.model_validate(
                        {
                            "expected_generation": state.generation,
                            "expected_source_version": 2,
                            "valid_from": "2091-01-01",
                            "supersedes_id": str(ids["item_price_numeric_revision"]),
                            "expected_previous_version": 1,
                        }
                    ),
                    {"currency": "USD"},
                )


async def test_guard_evaluator_rejects_ambiguous_unbounded_and_cyclic_storage(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_pricing(factory, tenant_a)
    current = actor(tenant_a, company, ids["actor_user"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            access = ConfigurationAccess(db, current, company)
            item = await db.get(Item, ids["item"])
            family = await db.get(ProductFamily, ids["product_family"])
            assert item is not None and family is not None
            work = ProductWork(db, current, company, family, item, access)
            result = await restrictions(
                access,
                work,
                ids["item_unit_revision"],
                "INR",
                dt.date(2090, 1, 1),
                "EXCLUSIVE",
                None,
            )
            assert result.minimum == 50 and not result.needs_tax
            master = await pack_unit(db, tenant_a, company)
            pack = ItemUnitBinding(
                tenant_id=tenant_a,
                company_id=company,
                item_id=item.id,
                unit_id=master.id,
                code="CASE",
                usage_role="PACK",
            )
            db.add(pack)
            await db.flush()
            revision = ItemUnitRevision(
                tenant_id=tenant_a,
                company_id=company,
                binding_id=pack.id,
                revision=1,
                conversion_mode="FIXED",
                numerator=12,
                denominator=1,
                quantity_decimal_places=0,
                quantity_increment="1",
                fractional_entry=False,
                valid_from=dt.date(2090, 1, 1),
            )
            db.add(revision)
            await db.flush()
            converted = await restrictions(
                access, work, revision.id, "INR", dt.date(2090, 1, 1), "EXCLUSIVE", None
            )
            assert converted.minimum == 600
            revision.conversion_mode = "MEASURED"
            revision.numerator = revision.denominator = None
            revision.nominal_ratio = Decimal("12")
            revision.secondary_unit_id = item.base_unit_id
            await db.flush()
            with pytest.raises(ConflictError, match="measured allocation"):
                await restrictions(
                    access, work, revision.id, "INR", dt.date(2090, 1, 1), "EXCLUSIVE", None
                )
            deferred = await restrictions(
                access,
                work,
                revision.id,
                "INR",
                dt.date(2090, 1, 1),
                "EXCLUSIVE",
                None,
                defer_measurement=True,
            )
            assert deferred.needs_measurement and deferred.minimum is None
            assert deferred.comparable_minimum is None
            assert ids["commercial_guard_rule"] in deferred.guard_ids
            original = await db.get(m.CommercialGuardRule, ids["commercial_guard_rule"])
            assert original is not None
            common = {
                field: getattr(original, field)
                for field in (
                    "tenant_id",
                    "company_id",
                    "item_id",
                    "unit_revision_id",
                    "numeric_revision_id",
                    "currency",
                    "rule_kind",
                    "amount",
                    "percentage",
                    "price_basis_quantity",
                    "tax_basis",
                    "estimate_kind",
                    "severity",
                    "source_reference",
                )
            }
            duplicate = m.CommercialGuardRule(**common, valid_from=dt.date(2089, 1, 1))
            db.add(duplicate)
            await db.flush()
            with pytest.raises(ConflictError, match="ambiguous"):
                await restrictions(
                    access,
                    work,
                    ids["item_unit_revision"],
                    "INR",
                    dt.date(2090, 1, 1),
                    "EXCLUSIVE",
                    None,
                )
            db.add_all(
                m.CommercialGuardRule(
                    **common, valid_from=dt.date(2080, 1, 1) + dt.timedelta(days=index)
                )
                for index in range(255)
            )
            await db.flush()
            with pytest.raises(ConflictError, match="bounded"):
                await restrictions(
                    access,
                    work,
                    ids["item_unit_revision"],
                    "INR",
                    dt.date(2090, 1, 1),
                    "EXCLUSIVE",
                    None,
                )
            other = ItemGroup(
                tenant_id=tenant_a,
                company_id=company,
                code="OTHER",
                name="Other",
                allowed_kind="GOODS",
            )
            db.add(other)
            await db.flush()
            db.add(
                ItemGroupParent(
                    tenant_id=tenant_a,
                    company_id=company,
                    group_id=other.id,
                    parent_group_id=ids["item_group"],
                    valid_from=dt.date(2090, 1, 1),
                )
            )
            edge = await db.get(ItemGroupParent, ids["item_group_parent"])
            assert edge is not None
            edge.valid_from = dt.date(2091, 1, 1)
            await db.flush()
            with pytest.raises(ConflictError, match="incomplete"):
                await discounts(access, work, dt.date(2090, 1, 1))
            edge.valid_from = dt.date(2090, 1, 1)
            edge.parent_group_id = other.id
            await db.flush()
            with pytest.raises(ConflictError, match="cyclic"):
                await discounts(access, work, dt.date(2090, 1, 1))
