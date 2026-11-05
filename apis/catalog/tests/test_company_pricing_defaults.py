"""Starter plans are permanent definitions, isolated, audited and safe to retry."""

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select

from catalog.models import Outbox
from catalog.models.classification import CatalogPolicyState
from catalog.models.pricing import PriceLevel, PricePlan
from catalog.tasks import company_pricing_defaults as defaults
from catalog.tasks.identity_source import IdentitySourceUnavailableError
from tests.source_factories import company_record, snapshot
from tests.test_unit_defaults import provision


async def test_defaults_follow_currency_and_preserve_renames_and_audit(factory, tenant_a):
    from catalog.tasks.projections import activate_snapshot

    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(
                db, snapshot(tenant_a, company, (company_record(company, base_currency="USD"),))
            )
        async with factory.begin() as db:
            assert (await defaults.ensure_pricing_defaults(db, company)).created_records == 3
        async with factory.begin() as db:
            plan = (await db.scalars(select(PricePlan).where(PricePlan.purpose == "SALE"))).one()
            identity = plan.id
            assert plan.currency == "USD" and plan.name == "Default sales"
            plan.name = "Our prices"
            generation = (await db.scalars(select(CatalogPolicyState))).one().generation
            events = list(await db.scalars(select(Outbox)))
            assert len(events) == 3
            assert all(event.payload["actor_type"] == "system" for event in events)
        async with factory.begin() as db:
            assert (await defaults.ensure_pricing_defaults(db, company)).created_records == 0
            plan = (await db.scalars(select(PricePlan).where(PricePlan.purpose == "SALE"))).one()
            assert plan.id == identity and plan.name == "Our prices"
            assert (await db.scalars(select(CatalogPolicyState))).one().generation == generation
            assert len(list(await db.scalars(select(Outbox)))) == 3


@pytest.mark.parametrize("conflict", ["inactive", "plan_code", "level_code", "existing_plan"])
async def test_preserves_existing_terms_and_conflicting_definitions(factory, tenant_a, conflict):
    company, level_id = uuid7(), uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                PriceLevel(
                    id=level_id,
                    tenant_id=tenant_a,
                    company_id=company,
                    code="PRICE1",
                    name="Retail",
                    ordinal=4 if conflict == "level_code" else 1,
                    is_active=conflict != "inactive",
                    row_version=1,
                )
            )
            await db.flush()
            if conflict in {"plan_code", "existing_plan"}:
                db.add(
                    PricePlan(
                        id=uuid7(),
                        tenant_id=tenant_a,
                        company_id=company,
                        code="DEFAULT_SALES" if conflict == "plan_code" else "RETAIL",
                        name="Authored",
                        purpose="PURCHASE" if conflict == "plan_code" else "SALE",
                        price_level_id=None if conflict == "plan_code" else level_id,
                        currency="INR",
                        tax_basis="INCLUSIVE",
                        custom_fields={},
                        row_version=1,
                    )
                )
        async with factory.begin() as db:
            result = await defaults.ensure_pricing_defaults(db, company)
            assert result.created_records == (1 if conflict == "existing_plan" else 0)
            assert result.status == ("READY" if conflict == "existing_plan" else "NEEDS_REVIEW")
            assert len(list(await db.scalars(select(Outbox)))) == (
                1 if conflict == "existing_plan" else 0
            )
            assert (await db.scalars(select(PriceLevel))).one().name == "Retail"
            if conflict == "existing_plan":
                assert (
                    await db.scalars(select(PricePlan).where(PricePlan.purpose == "SALE"))
                ).one().tax_basis == "INCLUSIVE"


async def test_audit_failure_rolls_back_and_retry_completes(factory, tenant_a, monkeypatch):
    company = uuid7()
    await provision(factory, tenant_a, company)
    real_emit = defaults.emit

    def fail(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(defaults, "emit", fail)
    with tenant_scope(tenant_a):
        with pytest.raises(RuntimeError, match="audit failed"):
            async with factory.begin() as db:
                await defaults.ensure_pricing_defaults(db, company)
        monkeypatch.setattr(defaults, "emit", real_emit)
        async with factory.begin() as db:
            assert list(await db.scalars(select(PriceLevel))) == []
            assert list(await db.scalars(select(Outbox))) == []
            assert (await defaults.ensure_pricing_defaults(db, company)).created_records == 3


async def test_verified_scope_required_and_company_defaults_are_isolated(
    factory, tenant_a, tenant_b
):
    first, second, inactive = uuid7(), uuid7(), uuid7()
    await provision(factory, tenant_a, first)
    await provision(factory, tenant_a, second)
    await provision(factory, tenant_a, inactive, status="suspended")
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await defaults.ensure_pricing_defaults(db, first)
            await defaults.ensure_pricing_defaults(db, second)
            assert (await defaults.ensure_pricing_defaults(db, inactive)).status == "NOT_APPLICABLE"
            assert {row.company_id for row in await db.scalars(select(PricePlan))} == {
                first,
                second,
            }
    with tenant_scope(tenant_b):
        async with factory.begin() as db:
            assert list(await db.scalars(select(PricePlan))) == []
            with pytest.raises(IdentitySourceUnavailableError):
                await defaults.ensure_pricing_defaults(db, first)
