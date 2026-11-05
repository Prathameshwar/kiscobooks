"""Company defaults retain exact quantities, native isolation and existing history."""

import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Outbox, PackType, UnitConversion, UnitOfMeasure
from catalog.models.classification import CatalogPolicyState
from catalog.tasks.projections import activate_snapshot
from catalog.tasks.unit_defaults import ensure_unit_defaults
from tests.source_factories import company_record, snapshot
from tests.test_api import headers
from tests.test_unit_api import UNIT_BODY, policy


async def provision(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    *,
    inventory: bool = True,
    version: int = 2,
    user: uuid.UUID | None = None,
    policies: tuple[SnapshotRecord, ...] = (),
    status: str = "active",
) -> None:
    records = [company_record(company, status=status, default_tax_system="none")]
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
    if user:
        records.append(SnapshotRecord(kind="user", id=user, data={"status": "active"}))
    with tenant_scope(tenant):
        async with factory.begin() as db:
            await activate_snapshot(
                db, snapshot(tenant, company, (*records, *policies), version=version)
            )


@pytest.mark.parametrize("inventory,expected", [(False, (4, 4, 0)), (True, (17, 17, 8))])
async def test_configured_defaults_exact_audited_and_repeatable(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    inventory: bool,
    expected: tuple[int, int, int],
) -> None:
    company = uuid7()
    await provision(factory, tenant_a, company, inventory=inventory)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            result = await ensure_unit_defaults(db, company)
            assert result.status == "READY" and result.inventory_enabled is inventory
            assert (
                result.units_created,
                result.conversions_created,
                result.packs_created,
            ) == expected
            assert not result.notices
        async with factory.begin() as db:
            units = {u.code: u for u in await db.scalars(select(UnitOfMeasure))}
            relations = {r.from_unit_id: r for r in await db.scalars(select(UnitConversion))}
            assert all(isinstance(u.quantity_increment, Decimal) for u in units.values())
            day = relations[units["DAY"].id]
            assert (day.canonical_unit_id, day.numerator, day.denominator) == (
                units["HOUR"].id,
                24,
                1,
            )
            if inventory:
                assert relations[units["KG"].id].canonical_unit_id == units["G"].id
                assert relations[units["KG"].id].numerator == 1000
                assert relations[units["MG"].id].denominator == 1000
                assert relations[units["DOZEN"].id].numerator == 12
                assert relations[units["PAIR"].id].numerator == 2
                assert {p.code for p in await db.scalars(select(PackType))} >= {
                    "BOX",
                    "BAG",
                    "BOTTLE",
                }
            audits = await db.scalar(select(func.count(Outbox.id)))
            assert audits == sum(expected)
            generation = await db.scalar(select(CatalogPolicyState.generation))
            repeated = await ensure_unit_defaults(db, company)
            assert (
                repeated.units_created,
                repeated.conversions_created,
                repeated.packs_created,
            ) == (0, 0, 0)
            assert await db.scalar(select(func.count(Outbox.id))) == audits
            assert await db.scalar(select(CatalogPolicyState.generation)) == generation


async def test_existing_settings_inactive_labels_and_conversion_graph_are_preserved(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_unit_defaults(db, company)
            unit = await db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "KG"))
            pack = await db.scalar(select(PackType).where(PackType.code == "BOX"))
            assert unit is not None and pack is not None
            unit.name, unit.is_active, unit.row_version = "My kilogram", False, 2
            pack.name, pack.is_active, pack.row_version = "My box", False, 2
            relation = await db.scalar(
                select(UnitConversion).where(UnitConversion.from_unit_id == unit.id)
            )
            assert relation is not None
            relation.numerator = 1234
        async with factory.begin() as db:
            result = await ensure_unit_defaults(db, company)
            assert result.units_created == result.packs_created == result.conversions_created == 0
            unit = await db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "KG"))
            pack = await db.scalar(select(PackType).where(PackType.code == "BOX"))
            assert unit is not None and pack is not None
            assert (unit.name, unit.is_active, unit.row_version) == ("My kilogram", False, 2)
            assert (pack.name, pack.is_active, pack.row_version) == ("My box", False, 2)
            assert (
                await db.scalar(
                    select(UnitConversion.numerator).where(UnitConversion.from_unit_id == unit.id)
                )
                == 1234
            )


async def test_existing_undeclared_or_custom_root_is_never_reinterpreted(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            # Existing NOS already has a company-specific meaning. No conversion
            # may be invented for it or linked through it by the backfill.
            db.add(
                UnitOfMeasure(
                    id=uuid7(),
                    tenant_id=tenant_a,
                    company_id=company,
                    **{
                        **UNIT_BODY,
                        "code": "NOS",
                        "name": "My piece",
                        "quantity_increment": Decimal("1"),
                    },
                    is_active=True,
                    row_version=1,
                )
            )
        async with factory.begin() as db:
            result = await ensure_unit_defaults(db, company)
            assert result.units_created == 16 and result.conversions_created == 14
            units = {u.code: u for u in await db.scalars(select(UnitOfMeasure))}
            assert units["NOS"].name == "My piece"
            assert result.notices and len(result.notices) == 3
            assert not list(
                await db.scalars(
                    select(UnitConversion).where(
                        UnitConversion.from_unit_id.in_(
                            [units[c].id for c in ("NOS", "DOZEN", "PAIR")]
                        )
                    )
                )
            )


async def test_atomic_rollback_and_tenant_company_isolation(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    first, second, foreign = uuid7(), uuid7(), uuid7()
    for tenant, company in ((tenant_a, first), (tenant_a, second), (tenant_b, foreign)):
        await provision(factory, tenant, company)
    with tenant_scope(tenant_a):
        with pytest.raises(RuntimeError):
            async with factory.begin() as db:
                await ensure_unit_defaults(db, first)
                raise RuntimeError("Rollback")
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(Outbox.id))) == 0
            await ensure_unit_defaults(db, second)
    with tenant_scope(tenant_b):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 0
            await ensure_unit_defaults(db, foreign)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 17
            assert (
                await db.scalar(
                    select(func.count(UnitOfMeasure.id)).where(UnitOfMeasure.company_id == first)
                )
                == 0
            )


async def test_worker_enables_inventory_later_and_preserves_service_units(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from billing_platform.service_auth import CompanyServiceScope

    from catalog.tasks import source_worker
    from tests.test_source_enrollment import worker_settings

    company = uuid7()
    config = worker_settings(
        source_subscriptions=(CompanyServiceScope(tenant_id=tenant_a, company_id=company),)
    )
    verified = snapshot(tenant_a, company, (company_record(company, default_tax_system="none"),))

    async def fetch(*args: Any, **kwargs: Any):
        return verified

    monkeypatch.setattr(source_worker, "fetch_identity_snapshot", fetch)
    await source_worker.refresh_once(factory, config, strict=True)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            original = await db.scalar(select(UnitOfMeasure.id).where(UnitOfMeasure.code == "NOS"))
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 4
            assert await db.scalar(select(func.count(PackType.id))) == 0
    verified = snapshot(
        tenant_a,
        company,
        (
            company_record(company, default_tax_system="none"),
            SnapshotRecord(
                kind="feature",
                id=company,
                data={
                    "company_id": str(company),
                    "feature_key": "inventory",
                    "is_enabled": True,
                    "locked_at": None,
                },
            ),
        ),
        version=3,
    )
    await source_worker.refresh_once(factory, config, strict=True)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert (
                await db.scalar(select(UnitOfMeasure.id).where(UnitOfMeasure.code == "NOS"))
                == original
            )
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 17
            assert await db.scalar(select(func.count(UnitConversion.id))) == 17
            assert await db.scalar(select(func.count(PackType.id))) == 8


async def test_bootstrap_api_auth_strict_input_replay_and_current_field_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await provision(factory, tenant_a, company, user=user)
    path = f"/v1/companies/{company}/unit-defaults/bootstrap"
    keys = ["unit.read", "unit.manage", "pack_type.read", "pack_type.manage"]
    auth = {
        **headers(company, tenant=tenant_a, user=user, permission=keys),
        "Idempotency-Key": str(uuid7()),
    }
    assert (await client.post(path, json={})).status_code == 401
    read_only = {
        **headers(company, tenant=tenant_a, user=user, permission=["unit.read"]),
        "Idempotency-Key": auth["Idempotency-Key"],
    }
    assert (await client.post(path, json={}, headers=read_only)).status_code == 403
    no_packs = {
        **headers(company, tenant=tenant_a, user=user, permission=["unit.read", "unit.manage"]),
        "Idempotency-Key": auth["Idempotency-Key"],
    }
    assert (await client.post(path, json={}, headers=no_packs)).status_code == 403
    assert (await client.post(path, json={"numerator": 99}, headers=auth)).status_code == 422
    assert (await client.post(path + "?extra=1", json={}, headers=auth)).status_code == 422
    first = await client.post(path, json={}, headers=auth)
    assert first.status_code == 200, first.text
    assert first.json()["company_id"] == str(company)
    assert first.json()["units_created"] == 17 and "_writes" not in first.json()
    replay = await client.post(path, json={}, headers=auth)
    assert replay.status_code == 200 and replay.json() == first.json(), replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert (await client.post(path, json={}, headers=read_only)).status_code == 403
    await provision(
        factory,
        tenant_a,
        company,
        user=user,
        version=3,
        policies=(
            policy(user, "name", "write", condition={"field": "code", "cmp": "eq", "value": "KG"}),
        ),
    )
    assert (await client.post(path, json={}, headers=auth)).status_code == 403


async def test_field_deny_rolls_back_all_seed_writes_and_allows_retry(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await provision(
        factory,
        tenant_a,
        company,
        user=user,
        policies=(policy(user, "name", "write", entity="catalog.pack_type"),),
    )
    path = f"/v1/companies/{company}/unit-defaults/bootstrap"
    auth = {
        **headers(
            company,
            tenant=tenant_a,
            user=user,
            permission=["unit.read", "unit.manage", "pack_type.read", "pack_type.manage"],
        ),
        "Idempotency-Key": str(uuid7()),
    }
    denied = await client.post(path, json={}, headers=auth)
    assert denied.status_code == 403, denied.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 0
            assert await db.scalar(select(func.count(Outbox.id))) == 0
    await provision(factory, tenant_a, company, user=user, version=3)
    retry = await client.post(path, json={}, headers=auth)
    assert retry.status_code == 200 and retry.json()["units_created"] == 17, retry.text


async def test_inactive_company_not_provisioned(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company = uuid7()
    await provision(factory, tenant_a, company, status="suspended")
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            result = await ensure_unit_defaults(db, company)
            assert result.status == "NOT_APPLICABLE"
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 0


async def test_expected_feature_snapshot_retries_without_a_sticky_success_receipt(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await provision(factory, tenant_a, company, user=user, inventory=False)
    auth = {
        **headers(
            company,
            tenant=tenant_a,
            user=user,
            permission=[
                "unit.read",
                "unit.manage",
                "pack_type.read",
                "pack_type.manage",
            ],
        ),
        "Idempotency-Key": str(uuid7()),
    }
    path = f"/v1/companies/{company}/unit-defaults/bootstrap"
    body = {"expected_inventory": True}
    waiting = await client.post(path, json=body, headers=auth)
    assert waiting.status_code == 503 and waiting.json()["error"]["code"] == "source_unavailable"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 0
    await provision(factory, tenant_a, company, user=user, version=3)
    ready = await client.post(path, json=body, headers=auth)
    assert ready.status_code == 200 and ready.json()["units_created"] == 17, ready.text
    # The same key with a different configuration expectation is a new request.
    assert (await client.post(path, json={}, headers=auth)).status_code == 422


async def test_seeded_units_work_in_native_conversion_and_reject_unrepresentable_quantities(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user = uuid7(), uuid7()
    await provision(factory, tenant_a, company, user=user)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_unit_defaults(db, company)
            units = {u.code: str(u.id) for u in await db.scalars(select(UnitOfMeasure))}
    auth = headers(company, tenant=tenant_a, user=user, permission=["unit.read"])
    path = f"/v1/companies/{company}/units/convert"
    for source, target, quantity, expected in (
        ("KG", "G", "1.25", "1250"),
        ("MG", "G", "1", "0.001"),
        ("DOZEN", "NOS", "2", "24"),
        ("L", "ML", "0.25", "250"),
        ("DAY", "HOUR", "1.5", "36"),
        ("M", "CM", "1.25", "125"),
    ):
        response = await client.post(
            path,
            json={"from_unit_id": units[source], "to_unit_id": units[target], "quantity": quantity},
            headers=auth,
        )
        assert response.status_code == 200, response.text
        assert Decimal(response.json()["quantity"]) == Decimal(expected)
    invalid = await client.post(
        path,
        json={"from_unit_id": units["MG"], "to_unit_id": units["KG"], "quantity": "1"},
        headers=auth,
    )
    assert invalid.status_code == 422
    assert (
        await client.post(
            path,
            json={"from_unit_id": units["G"], "to_unit_id": units["ML"], "quantity": "1"},
            headers=auth,
        )
    ).status_code == 422
    other = uuid7()
    await provision(factory, tenant_a, other, user=user)
    wrong = await client.post(
        f"/v1/companies/{other}/unit-defaults/bootstrap",
        json={},
        headers={
            **headers(
                company,
                tenant=tenant_a,
                user=user,
                permission=["unit.read", "unit.manage", "pack_type.read", "pack_type.manage"],
            ),
            "Idempotency-Key": str(uuid7()),
        },
    )
    assert wrong.status_code == 403


async def test_failed_unit_defaults_do_not_block_tax_or_roll_back_verified_source(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from billing_platform.service_auth import CompanyServiceScope

    from catalog.models.projections import ProjectionCheckpoint
    from catalog.models.tax import TaxRule
    from catalog.tasks import source_worker, unit_defaults
    from tests.test_source_enrollment import worker_settings

    company = uuid7()
    verified = snapshot(tenant_a, company, (company_record(company, default_tax_system="gst_in"),))
    config = worker_settings(
        source_subscriptions=(CompanyServiceScope(tenant_id=tenant_a, company_id=company),)
    )

    async def fetch(*args: Any, **kwargs: Any):
        return verified

    async def fail_after_writes(db: AsyncSession, company_id: uuid.UUID):
        await ensure_unit_defaults(db, company_id)
        raise RuntimeError("Simulated seed failure")

    monkeypatch.setattr(source_worker, "fetch_identity_snapshot", fetch)
    monkeypatch.setattr(unit_defaults, "ensure_unit_defaults", fail_after_writes)
    await source_worker.refresh_once(factory, config)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(UnitOfMeasure.id))) == 0
            assert await db.scalar(select(func.count(TaxRule.id))) == 9
            assert await db.scalar(select(func.count(ProjectionCheckpoint.id))) == 1
