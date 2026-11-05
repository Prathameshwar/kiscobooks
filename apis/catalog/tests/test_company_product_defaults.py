"""Company enrollment owns permanent starter masters, independent of browser creation."""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from billing_platform.db import tenant_scope
from billing_platform.service_auth import CompanyServiceScope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.classification import ItemGroup
from catalog.models.commercial import ProductType, ProductTypeRevision
from catalog.models.pricing import PriceLevel, PricePlan
from catalog.tasks import source_worker
from tests.source_factories import company_record, snapshot
from tests.test_source_enrollment import worker_settings
from tests.test_unit_defaults import provision


@pytest.mark.parametrize("inventory", [False, True])
async def test_company_refresh_creates_default_type_and_group_without_wizard(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    inventory: bool,
) -> None:
    from billing_platform.ids import uuid7
    from billing_platform.snapshots import SnapshotRecord

    company = uuid7()
    records = [company_record(company, default_tax_system="none")]
    if inventory:
        records.append(
            SnapshotRecord(
                kind="feature",
                id=company,
                data={
                    "company_id": str(company),
                    "feature_key": "inventory",
                    "is_enabled": True,
                    "locked_at": None,
                },
            )
        )
    verified = snapshot(tenant_a, company, tuple(records))

    async def fetch(*args: Any, **kwargs: Any):
        return verified

    monkeypatch.setattr(source_worker, "fetch_identity_snapshot", fetch)
    settings = worker_settings(
        source_subscriptions=(
            CompanyServiceScope(
                tenant_id=tenant_a,
                company_id=company,
            ),
        )
    )
    await source_worker.refresh_once(factory, settings, strict=True)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            types = list(await db.scalars(select(ProductType)))
            groups = list(await db.scalars(select(ItemGroup)))
            assert len(types) == len(groups) == 1
            assert types[0].name == groups[0].name == "Default"
            assert types[0].code == groups[0].code == "DEFAULT"
            assert types[0].kind == groups[0].allowed_kind == "BOTH"
            assert types[0].is_active and groups[0].is_active
            revision = (await db.scalars(select(ProductTypeRevision))).one()
            assert revision.product_type_id == types[0].id and revision.published_at is not None
            assert ("STOCK" in revision.inventory_modes) is inventory
            assert revision.tracking_modes == ["NONE"]
            plans = list(await db.scalars(select(PricePlan)))
            assert {plan.code: plan.name for plan in plans} == {
                "DEFAULT_SALES": "Default sales",
                "DEFAULT_PURCHASE": "Default purchase",
            }
            sale = next(plan for plan in plans if plan.purpose == "SALE")
            purchase = next(plan for plan in plans if plan.purpose == "PURCHASE")
            assert sale.currency == purchase.currency == "INR"
            assert sale.tax_basis == purchase.tax_basis == "EXCLUSIVE"
            level = (await db.scalars(select(PriceLevel))).one()
            assert sale.price_level_id == level.id and level.ordinal == 1
            assert purchase.price_level_id is None
            from catalog.models.configuration import (
                ProductConfigurationRevision,
                ProductPricingPolicy,
            )

            configuration = (await db.scalars(select(ProductConfigurationRevision))).one()
            prices = (
                await db.scalars(
                    select(ProductPricingPolicy).where(
                        ProductPricingPolicy.revision_id == configuration.id
                    )
                )
            ).one()
            assert configuration.revision == 1
            assert prices.quantity_tiers_mode == prices.multiple_price_levels_mode == "DISABLED"
    await source_worker.refresh_once(factory, settings, strict=True)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert len(list(await db.scalars(select(ProductType)))) == 1
            assert len(list(await db.scalars(select(ItemGroup)))) == 1
            assert len(list(await db.scalars(select(ProductTypeRevision)))) == 1
            assert len(list(await db.scalars(select(PricePlan)))) == 2


async def test_existing_general_and_custom_records_are_preserved(factory, tenant_a):
    from billing_platform.ids import uuid7

    from catalog.tasks.company_product_defaults import ensure_product_defaults

    company, general_id, custom_id = uuid7(), uuid7(), uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                ItemGroup(
                    id=general_id,
                    tenant_id=tenant_a,
                    company_id=company,
                    code="GENERAL",
                    name="Our General",
                    allowed_kind="GOODS",
                )
            )
            db.add(
                ProductType(
                    id=custom_id,
                    tenant_id=tenant_a,
                    company_id=company,
                    code="CUSTOM",
                    name="Custom services",
                    kind="SERVICE",
                )
            )
        async with factory.begin() as db:
            assert (await ensure_product_defaults(db, company)).created_records == 4
        async with factory.begin() as db:
            groups = {row.code: row for row in await db.scalars(select(ItemGroup))}
            types = {row.code: row for row in await db.scalars(select(ProductType))}
            assert set(groups) == {"GENERAL", "DEFAULT"} and set(types) == {"CUSTOM", "DEFAULT"}
            assert groups["GENERAL"].id == general_id and groups["GENERAL"].name == "Our General"
            assert types["CUSTOM"].id == custom_id and types["CUSTOM"].kind == "SERVICE"


async def test_renamed_defaults_and_published_configuration_are_not_overwritten(factory, tenant_a):
    from billing_platform.ids import uuid7

    from catalog.models import Outbox
    from catalog.models.classification import CatalogPolicyState
    from catalog.tasks.company_product_defaults import ensure_product_defaults

    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_product_defaults(db, company)
        async with factory.begin() as db:
            group = (await db.scalars(select(ItemGroup))).one()
            product_type = (await db.scalars(select(ProductType))).one()
            revision = (await db.scalars(select(ProductTypeRevision))).one()
            group.name, product_type.name = "Office group", "Office type"
            revision.allow_variants = False
            revision.require_brand = True
            generation = (await db.scalars(select(CatalogPolicyState))).one().generation
            events = len(list(await db.scalars(select(Outbox))))
        async with factory.begin() as db:
            assert (await ensure_product_defaults(db, company)).created_records == 0
            assert (await db.scalars(select(ItemGroup))).one().name == "Office group"
            assert (await db.scalars(select(ProductType))).one().name == "Office type"
            revision = (await db.scalars(select(ProductTypeRevision))).one()
            assert not revision.allow_variants and revision.require_brand
            assert (await db.scalars(select(CatalogPolicyState))).one().generation == generation
            assert len(list(await db.scalars(select(Outbox)))) == events
            assert all(
                row.payload["actor_type"] == "system" for row in await db.scalars(select(Outbox))
            )


async def test_named_defaults_reused_with_alternative_codes(factory, tenant_a):
    from billing_platform.ids import uuid7

    from catalog.tasks.company_product_defaults import ensure_product_defaults

    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_product_defaults(db, company)
            (await db.scalars(select(ProductType))).one().code = "MY_DEFAULT"
            (await db.scalars(select(ItemGroup))).one().code = "MY_GROUP"
        async with factory.begin() as db:
            assert (await ensure_product_defaults(db, company)).created_records == 0
            assert len(list(await db.scalars(select(ProductType)))) == 1
            assert len(list(await db.scalars(select(ItemGroup)))) == 1


async def test_tenant_company_isolation_and_inactive_company(factory, tenant_a, tenant_b):
    from billing_platform.errors import PlatformError
    from billing_platform.ids import uuid7

    from catalog.tasks.company_product_defaults import ensure_product_defaults

    first, second, suspended = uuid7(), uuid7(), uuid7()
    await provision(factory, tenant_a, first)
    await provision(factory, tenant_b, second)
    await provision(factory, tenant_a, suspended, status="suspended")
    for tenant, company in [(tenant_a, first), (tenant_b, second)]:
        with tenant_scope(tenant):
            async with factory.begin() as db:
                await ensure_product_defaults(db, company)
                groups = list(await db.scalars(select(ItemGroup)))
                assert len(groups) == 1 and groups[0].company_id == company
    with tenant_scope(tenant_b):
        async with factory.begin() as db:
            with pytest.raises(PlatformError):
                await ensure_product_defaults(db, first)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert (await ensure_product_defaults(db, suspended)).status == "NOT_APPLICABLE"
            assert (
                await db.scalar(select(ItemGroup.id).where(ItemGroup.company_id == suspended))
                is None
            )


async def test_inactive_default_is_not_reactivated(factory, tenant_a):
    from billing_platform.ids import uuid7

    from catalog.tasks.company_product_defaults import ensure_product_defaults

    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_product_defaults(db, company)
            (await db.scalars(select(ProductType))).one().is_active = False
        async with factory.begin() as db:
            assert (await ensure_product_defaults(db, company)).status == "NEEDS_REVIEW"
            assert not (await db.scalars(select(ProductType))).one().is_active
            assert len(list(await db.scalars(select(ProductType)))) == 1


async def test_existing_unpublished_default_requires_review_without_publishing(factory, tenant_a):
    from billing_platform.ids import uuid7

    from catalog.models import Outbox
    from catalog.tasks.company_product_defaults import ensure_product_defaults

    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                ProductType(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    code="DEFAULT",
                    name="Default",
                    kind="BOTH",
                )
            )
        async with factory.begin() as db:
            assert (await ensure_product_defaults(db, company)).status == "NEEDS_REVIEW"
            assert list(await db.scalars(select(ProductTypeRevision))) == []
            assert list(await db.scalars(select(ItemGroup))) == []
            assert list(await db.scalars(select(Outbox))) == []


async def test_failure_rolls_back_defaults_and_audit_then_retry_recovers(
    factory, tenant_a, monkeypatch
):
    from billing_platform.ids import uuid7

    from catalog.models import Outbox
    from catalog.tasks import company_product_defaults as defaults

    company = uuid7()
    await provision(factory, tenant_a, company)
    real_emit, calls = defaults.emit, 0

    def failing_emit(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Injected audit failure")
        return real_emit(*args, **kwargs)

    monkeypatch.setattr(defaults, "emit", failing_emit)
    with tenant_scope(tenant_a):
        with pytest.raises(RuntimeError, match="Injected"):
            async with factory.begin() as db:
                await defaults.ensure_product_defaults(db, company)
        async with factory.begin() as db:
            assert list(await db.scalars(select(ProductType))) == []
            assert list(await db.scalars(select(ItemGroup))) == []
            assert list(await db.scalars(select(Outbox))) == []
        monkeypatch.setattr(defaults, "emit", real_emit)
        async with factory.begin() as db:
            assert (await defaults.ensure_product_defaults(db, company)).created_records == 4


async def test_refresh_recovers_existing_company_after_defaults_failure(
    factory, tenant_a, monkeypatch
):
    from billing_platform.ids import uuid7

    from catalog.models.projections import ProjectionCheckpoint
    from catalog.tasks import company_product_defaults as defaults

    company = uuid7()
    verified = snapshot(tenant_a, company, (company_record(company, default_tax_system="none"),))

    async def fetch(*args, **kwargs):
        return verified

    real_ensure = defaults.ensure_product_defaults

    async def fail(db, company_id):
        await real_ensure(db, company_id)
        raise RuntimeError("Defaults failed")

    monkeypatch.setattr(source_worker, "fetch_identity_snapshot", fetch)
    monkeypatch.setattr(defaults, "ensure_product_defaults", fail)
    settings = worker_settings(
        source_subscriptions=(CompanyServiceScope(tenant_id=tenant_a, company_id=company),)
    )
    await source_worker.refresh_once(factory, settings)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(ProjectionCheckpoint.id)) is not None
            assert list(await db.scalars(select(ProductType))) == []
    monkeypatch.setattr(defaults, "ensure_product_defaults", real_ensure)
    await source_worker.refresh_once(factory, settings, strict=True)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert len(list(await db.scalars(select(ProductType)))) == 1
            assert len(list(await db.scalars(select(ItemGroup)))) == 1


@pytest.mark.parametrize("failed", [False, True])
async def test_once_uses_authenticated_refresh_and_disposes_engine(
    factory,
    monkeypatch,
    failed,
):
    settings = worker_settings(source_discovery=True)
    disposed, calls = [], []

    async def dispose():
        disposed.append(True)

    engine = SimpleNamespace(dispose=dispose)

    async def refresh(connection, config, registry, **options):
        calls.append(options)
        assert connection is factory and config is settings
        if failed:
            raise RuntimeError("Source unavailable")
        registry.scopes = (CompanyServiceScope(tenant_id=uuid.uuid4(), company_id=uuid.uuid4()),)

    monkeypatch.setattr(source_worker, "create_engine", lambda url: engine)
    monkeypatch.setattr(source_worker, "create_session_factory", lambda value, **kwargs: factory)
    monkeypatch.setattr(source_worker, "refresh_once", refresh)
    if failed:
        with pytest.raises(RuntimeError):
            await source_worker.run_once(settings, product_defaults_only=True)
    else:
        assert await source_worker.run_once(settings, product_defaults_only=True) == 1
    assert calls == [{"strict": True, "product_defaults_only": True}]
    assert disposed == [True]
