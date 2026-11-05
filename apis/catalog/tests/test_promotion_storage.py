"""Dormant promotion storage still obeys native tenant and company boundaries."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.promotions import (
    PROMOTION_MODELS,
    Promotion,
    PromotionBenefit,
    PromotionPriceLevelTarget,
    PromotionRevision,
    PromotionSkuTarget,
    PromotionStackGroup,
    PromotionStackPermission,
    PromotionStackPolicy,
)
from catalog.tasks.promotion_facts import read_stored_same_item_deal
from tests.pricing_storage_factories import seed_pricing
from tests.return_factories import seed_policy


async def seed_promotion(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    company, sources = await seed_pricing(factory, tenant)
    _, return_revision = await seed_policy(factory, tenant, company)
    now = dt.datetime(2090, 1, 1, tzinfo=dt.UTC)
    with tenant_scope(tenant):
        async with factory.begin() as db:
            common = {"tenant_id": tenant, "company_id": company}
            promotion = Promotion(**common, code="BUY10GET1", name="Buy ten get one")
            db.add(promotion)
            await db.flush()
            stack = PromotionStackPolicy(
                **common,
                code="SALE_STACK",
                version=1,
                maximum_applied=2,
                published_at=now,
                source_sha256="b" * 64,
            )
            db.add(stack)
            await db.flush()
            product_group = PromotionStackGroup(
                **common,
                policy_revision_id=stack.id,
                position=0,
                stage="PRODUCT_SCHEME",
                selection="PRIORITY",
                changes_basket=True,
            )
            manual_group = PromotionStackGroup(
                **common,
                policy_revision_id=stack.id,
                position=1,
                stage="MANUAL",
                selection="PRIORITY",
                changes_basket=False,
            )
            db.add_all((product_group, manual_group))
            await db.flush()
            stack_permission = PromotionStackPermission(
                **common,
                policy_revision_id=stack.id,
                earlier_group_id=product_group.id,
                later_group_id=manual_group.id,
                include_reward_units=False,
            )
            db.add(stack_permission)
            await db.flush()
            revision = PromotionRevision(
                **common,
                promotion_id=promotion.id,
                version=1,
                trigger_mode="AUTOMATIC",
                selection_mode="SNAPSHOT_ON_PUBLISH",
                currency="INR",
                starts_at=now,
                ends_at=dt.datetime(2091, 1, 1, tzinfo=dt.UTC),
                timezone="Asia/Kolkata",
                stack_policy_revision_id=stack.id,
                stack_group_id=product_group.id,
                return_policy_revision_id=return_revision,
                priority=1,
                policy_generation=1,
                source_version=1,
                published_at=now,
                source_sha256="a" * 64,
            )
            db.add(revision)
            await db.flush()
            benefit = PromotionBenefit(
                **common,
                revision_id=revision.id,
                kind="BUY_GET",
                pool="SAME_ITEM",
                unit_revision_id=sources["item_unit_revision"],
                qualifying_quantity=Decimal(10),
                reward_quantity=Decimal(1),
                reward_percent=Decimal(100),
                maximum_repeats=10,
            )
            sku = PromotionSkuTarget(**common, revision_id=revision.id, item_id=sources["item"])
            level = PromotionPriceLevelTarget(
                **common, revision_id=revision.id, price_level_id=sources["price_level"]
            )
            db.add_all((benefit, sku, level))
            await db.flush()
            return company, {
                "promotion": promotion.id,
                "promotion_revision": revision.id,
                "promotion_benefit": benefit.id,
                "promotion_sku_target": sku.id,
                "promotion_price_level_target": level.id,
                "item": sources["item"],
                "promotion_stack_policy": stack.id,
                "promotion_stack_group": product_group.id,
                "promotion_stack_permission": stack_permission.id,
            }


async def test_promotion_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    _, own = await seed_promotion(factory, tenant_a)
    _, foreign = await seed_promotion(factory, tenant_b)
    for tenant, visible, hidden in ((tenant_a, own, foreign), (tenant_b, foreign, own)):
        with tenant_scope(tenant):
            async with factory() as db:
                for model in PROMOTION_MODELS:
                    ids = set(await db.scalars(select(model.id)))
                    assert visible[model.__tablename__] in ids
                    assert hidden[model.__tablename__] not in ids


async def test_promotion_target_rejects_foreign_tenant_item(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, own = await seed_promotion(factory, tenant_a)
    _, foreign = await seed_promotion(factory, tenant_b)
    with tenant_scope(tenant_a):
        with pytest.raises(IntegrityError):
            async with factory.begin() as db:
                await db.execute(
                    insert(PromotionSkuTarget).values(
                        tenant_id=tenant_a,
                        company_id=company,
                        revision_id=own["promotion_revision"],
                        item_id=foreign["item"],
                    )
                )


async def test_stack_permission_rejects_foreign_group(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, own = await seed_promotion(factory, tenant_a)
    _, foreign = await seed_promotion(factory, tenant_b)
    with tenant_scope(tenant_a):
        with pytest.raises(IntegrityError):
            async with factory.begin() as db:
                await db.execute(
                    insert(PromotionStackPermission).values(
                        tenant_id=tenant_a,
                        company_id=company,
                        policy_revision_id=own["promotion_stack_policy"],
                        earlier_group_id=own["promotion_stack_group"],
                        later_group_id=foreign["promotion_stack_group"],
                        include_reward_units=False,
                    )
                )


async def test_promotion_revision_rejects_foreign_stack_group(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    _, own = await seed_promotion(factory, tenant_a)
    _, foreign = await seed_promotion(factory, tenant_b)
    with tenant_scope(tenant_a):
        with pytest.raises(IntegrityError):
            async with factory.begin() as db:
                await db.execute(
                    update(PromotionRevision)
                    .where(PromotionRevision.id == own["promotion_revision"])
                    .values(stack_group_id=foreign["promotion_stack_group"])
                )


async def test_published_promotion_rows_cannot_be_edited(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    _, own = await seed_promotion(factory, tenant_a)
    with tenant_scope(tenant_a):
        with pytest.raises(ConflictError, match="immutable"):
            async with factory.begin() as db:
                revision = await db.get(PromotionRevision, own["promotion_revision"])
                assert revision is not None
                revision.priority = 2
                await db.flush()
        with pytest.raises(ConflictError, match="immutable"):
            async with factory.begin() as db:
                benefit = await db.get(PromotionBenefit, own["promotion_benefit"])
                assert benefit is not None
                await db.delete(benefit)
                await db.flush()


async def test_published_promotion_cannot_gain_targets_after_publication(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, own = await seed_promotion(factory, tenant_a)
    with tenant_scope(tenant_a):
        with pytest.raises(ConflictError, match="immutable"):
            async with factory.begin() as db:
                db.add(
                    PromotionSkuTarget(
                        tenant_id=tenant_a,
                        company_id=company,
                        revision_id=own["promotion_revision"],
                        item_id=own["item"],
                    )
                )
                await db.flush()


async def test_published_stack_policy_cannot_change_or_gain_children(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, own = await seed_promotion(factory, tenant_a)
    with tenant_scope(tenant_a):
        with pytest.raises(ConflictError, match="immutable"):
            async with factory.begin() as db:
                policy = await db.get(PromotionStackPolicy, own["promotion_stack_policy"])
                assert policy is not None
                policy.maximum_applied = 3
                await db.flush()
        with pytest.raises(ConflictError, match="immutable"):
            async with factory.begin() as db:
                db.add(
                    PromotionStackGroup(
                        tenant_id=tenant_a,
                        company_id=company,
                        policy_revision_id=own["promotion_stack_policy"],
                        position=2,
                        stage="MANUAL",
                        selection="PRIORITY",
                        changes_basket=False,
                    )
                )
                await db.flush()


async def test_stored_same_item_facts_reconstruct_bounded_deal(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_promotion(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory() as db:
            deal = await read_stored_same_item_deal(db, company, ids["promotion_revision"])
    assert deal.revision_id == ids["promotion_revision"]
    assert deal.terms.item_ids == frozenset({ids["item"]})
    assert deal.terms.qualifying == Decimal(10)
    assert deal.terms.reward == Decimal(1)
    assert deal.terms.manual_stacking


async def test_stored_same_item_facts_reject_missing_benefit(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_promotion(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await db.execute(
                delete(PromotionBenefit).where(PromotionBenefit.id == ids["promotion_benefit"])
            )
        with pytest.raises(ValidationFailedError, match="incomplete"):
            async with factory() as db:
                await read_stored_same_item_deal(db, company, ids["promotion_revision"])


async def test_stored_same_item_facts_reject_inconsistent_stack(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_promotion(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await db.execute(
                update(PromotionStackGroup)
                .where(PromotionStackGroup.id == ids["promotion_stack_group"])
                .values(stage="MANUAL")
            )
        with pytest.raises(ValidationFailedError, match="product stack group"):
            async with factory() as db:
                await read_stored_same_item_deal(db, company, ids["promotion_revision"])


async def test_stored_same_item_facts_normalize_invalid_policy_error(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, ids = await seed_promotion(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await db.execute(
                update(PromotionStackGroup)
                .where(PromotionStackGroup.id == ids["promotion_stack_group"])
                .values(selection="BEST_SINGLE")
            )
        with pytest.raises(ValidationFailedError, match="inconsistent"):
            async with factory() as db:
                await read_stored_same_item_deal(db, company, ids["promotion_revision"])


async def test_stored_same_item_facts_reject_foreign_company(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    _, own = await seed_promotion(factory, tenant_a)
    foreign_company, _ = await seed_promotion(factory, tenant_b)
    with tenant_scope(tenant_a):
        with pytest.raises(ValidationFailedError, match="unavailable"):
            async with factory() as db:
                await read_stored_same_item_deal(db, foreign_company, own["promotion_revision"])
