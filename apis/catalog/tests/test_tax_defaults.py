"""Automatic defaults use real scoped storage and never rewrite company tax history."""

import uuid
from decimal import Decimal

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Outbox
from catalog.models.classification import CatalogPolicyState
from catalog.models.projections import CompanyProjection
from catalog.models.tax import TaxCategory, TaxClassification, TaxRate, TaxRateComponent, TaxRule
from catalog.tasks.projections import activate_snapshot
from catalog.tasks.tax_defaults import ensure_tax_defaults, starter_pack
from tests.source_factories import company_record, snapshot


async def provision(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    **settings: str,
) -> None:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(
                db,
                snapshot(
                    tenant,
                    company,
                    (
                        company_record(
                            company,
                            default_tax_system=settings.pop("default_tax_system", "gst_in"),
                            **settings,
                        ),
                    ),
                ),
            )


async def test_defaults_complete_exact_audited_and_repeatable(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            result = await ensure_tax_defaults(db, company)
            assert result.status == "READY"
            assert (
                result.categories_created,
                result.classifications_created,
                result.rules_created,
                result.rates_created,
            ) == (5, 13, 20, 48)
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(TaxClassification.id))) == 13
            components = list(await db.scalars(select(TaxRateComponent)))
            assert len(components) == 80
            for row in await db.scalars(select(TaxRule)):
                assert row.classification_scope == "ANY"
            assert all(isinstance(row.percentage, Decimal) for row in components)
            assert {row.percentage for row in components} == {
                Decimal(value)
                for value in (
                    "0",
                    "0.05",
                    "0.1",
                    "0.125",
                    "0.25",
                    "0.75",
                    "1.5",
                    "2.5",
                    "3",
                    "3.75",
                    "5",
                    "6",
                    "7.5",
                    "9",
                    "12",
                    "18",
                    "20",
                    "40",
                )
            }
            audit_count = await db.scalar(select(func.count(Outbox.id)))
            generation = await db.scalar(select(CatalogPolicyState.generation))
            repeated = await ensure_tax_defaults(db, company)
            assert repeated.status == "READY" and repeated.rules_created == 0
            assert repeated.preserved_records == 38
            assert await db.scalar(select(func.count(Outbox.id))) == audit_count
            assert await db.scalar(select(CatalogPolicyState.generation)) == generation


@pytest.mark.parametrize(
    "settings",
    [
        {"country_code": "GB", "state_code": "GB-ENG", "default_tax_system": "vat_uk"},
        {"default_tax_system": "none"},
        {"status": "suspended"},
    ],
)
async def test_non_applicable_companies_have_no_indian_tax_rows(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    settings: dict[str, str],
) -> None:
    company = uuid7()
    await provision(factory, tenant_a, company, **settings)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            result = await ensure_tax_defaults(db, company)
            assert result.status == "NOT_APPLICABLE"
            assert await db.scalar(select(func.count(TaxCategory.id))) == 0


async def test_existing_edits_and_rule_history_are_preserved(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_tax_defaults(db, company)
            row = await db.scalar(select(TaxRule).where(TaxRule.code == "GST_G_18"))
            assert row is not None
            row.name, row.is_active, row.row_version = "My computers", False, 2
        async with factory.begin() as db:
            await ensure_tax_defaults(db, company)
            row = await db.scalar(select(TaxRule).where(TaxRule.code == "GST_G_18"))
            assert row is not None and row.name == "My computers" and not row.is_active
            assert row.row_version == 2
            assert await db.scalar(select(func.count(TaxRate.id))) == 48


async def test_rollback_and_same_tenant_company_isolation(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    first, second = uuid7(), uuid7()
    await provision(factory, tenant_a, first)
    await provision(factory, tenant_a, second)
    with tenant_scope(tenant_a):
        with pytest.raises(RuntimeError):
            async with factory.begin() as db:
                await ensure_tax_defaults(db, first)
                raise RuntimeError("Abort the complete setup")
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(TaxRule.id))) == 0
            await ensure_tax_defaults(db, second)
        async with factory.begin() as db:
            assert (
                await db.scalar(select(func.count(TaxRule.id)).where(TaxRule.company_id == first))
                == 0
            )
            assert (
                await db.scalar(select(func.count(TaxRule.id)).where(TaxRule.company_id == second))
                == 20
            )


def test_pack_official_sources_and_native_codes() -> None:
    pack = starter_pack()
    assert len({row.code for row in pack.rules}) == len(pack.rules)
    assert all(
        source.evidence()["source_url"].startswith("https://") for source in pack.sources.values()
    )
    assert next(row for row in pack.rules if row.code == "GST_G_5").percentage == Decimal("5")
    assert next(row for row in pack.rules if row.code == "GST_G_40").percentage == Decimal("40")


async def test_bootstrap_api_requires_publication_authority_and_replays(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from tests.tax_factories import seed_tax
    from tests.test_api import headers

    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            profile = await db.scalar(
                select(CompanyProjection).where(CompanyProjection.company_id == company)
            )
            assert profile is not None
            profile.default_tax_system = "gst_in"
    path = root + "/tax-defaults/bootstrap"
    auth["Idempotency-Key"] = str(uuid7())
    denied = headers(
        company,
        tenant=tenant_a,
        user=ids["actor_user"],
        permission=["tax_rule.read", "tax_rule.manage"],
    )
    denied["Idempotency-Key"] = str(uuid7())
    assert (await client.post(path, json={}, headers=denied)).status_code == 403
    assert (await client.post(path, json={"percentage": "99"}, headers=auth)).status_code == 422
    first = await client.post(path, json={}, headers=auth)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "READY"
    assert first.json()["rules_created"] == 20
    replay = await client.post(path, json={}, headers=auth)
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert replay.headers["Idempotency-Replayed"] == "true"
    revoked = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=["tax_rule.read"]
    )
    revoked["Idempotency-Key"] = auth["Idempotency-Key"]
    assert (await client.post(path, json={}, headers=revoked)).status_code == 403


async def test_enrollment_refresh_automatically_provisions_without_a_browser(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import Any

    from billing_platform.service_auth import CompanyServiceScope

    from catalog.tasks import source_worker
    from tests.test_source_enrollment import worker_settings

    company = uuid7()
    scope = CompanyServiceScope(tenant_id=tenant_a, company_id=company)
    verified = snapshot(tenant_a, company, (company_record(company, default_tax_system="none"),))

    async def fetch(*args: Any, **kwargs: Any):
        return verified

    monkeypatch.setattr(source_worker, "fetch_identity_snapshot", fetch)
    config = worker_settings(source_subscriptions=(scope,))
    await source_worker.refresh_once(factory, config, strict=True)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(TaxRule.id))) == 0
    verified = snapshot(
        tenant_a, company, (company_record(company, default_tax_system="gst_in"),), version=3
    )
    await source_worker.refresh_once(factory, config, strict=True)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(TaxRule.id))) == 20
    await source_worker.refresh_once(factory, config, strict=True)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(TaxRule.id))) == 20
