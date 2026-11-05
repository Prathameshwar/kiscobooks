from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.projections import (
    PROJECTION_MODELS,
    CompanyProjection,
    ProjectionCheckpoint,
    SourceEventBuffer,
)
from catalog.tasks.identity_source import IdentitySourceUnavailableError
from catalog.tasks.projections import (
    activate_snapshot,
    buffer_change,
    require_identity_context,
)
from tests.source_factories import all_facts, change, company_record, snapshot


async def test_all_projection_tables_isolate_tenants_and_same_tenant_companies(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    companies = {tenant_a: [uuid7(), uuid7()], tenant_b: [uuid7()]}
    for tenant, ids in companies.items():
        with tenant_scope(tenant):
            for company in ids:
                async with factory.begin() as db:
                    await activate_snapshot(
                        db, snapshot(tenant, company, all_facts(company, uuid7()))
                    )
            async with factory.begin() as db:
                await buffer_change(db, message_id=uuid7(), change=change(tenant, 3))
    for tenant, ids in companies.items():
        with tenant_scope(tenant), pytest.raises(ValidationFailedError):
            async with factory.begin() as db:
                await buffer_change(db, message_id=uuid7(), change=change(uuid7(), 4))
        with tenant_scope(tenant):
            async with factory.begin() as db:
                for model in PROJECTION_MODELS.values():
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == len(ids)
                    assert {row.company_id for row in rows} == set(ids)
                    assert all(row.tenant_id == tenant for row in rows)
                checkpoints = list(await db.scalars(select(ProjectionCheckpoint)))
                assert len(checkpoints) == len(ids)
                assert all(row.tenant_id == tenant for row in checkpoints)
                assert all(
                    row.tenant_id == tenant for row in await db.scalars(select(SourceEventBuffer))
                )


async def test_gap_closes_without_losing_changes_and_duplicates_are_safe(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    source = snapshot(tenant_a, company)
    third_id, fourth_id = uuid7(), uuid7()
    third = change(tenant_a, 3, (company_record(company, display_name="Changed"),))
    fourth = change(
        tenant_a, 4, (SnapshotRecord(kind="user", id=uuid7(), data={"status": "active"}),)
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, source)
            await buffer_change(db, message_id=fourth_id, change=fourth)
        async with factory.begin() as db:
            with pytest.raises(IdentitySourceUnavailableError):
                await require_identity_context(db, company)
            await buffer_change(db, message_id=third_id, change=third)
            assert (await require_identity_context(db, company)).source_version == 4
            assert (await db.scalars(select(CompanyProjection))).one().display_name == "Changed"
        async with factory.begin() as db:
            await buffer_change(db, message_id=fourth_id, change=fourth)
            assert len(list(await db.scalars(select(SourceEventBuffer)))) == 2
        with pytest.raises(ConflictError):
            async with factory.begin() as db:
                await buffer_change(db, message_id=uuid7(), change=fourth)
        async with factory.begin() as db:
            replayed = await activate_snapshot(db, source)
            assert replayed.source_version == 4
            assert replayed.expires_at == source.manifest.expires_at
        async with factory.begin() as db:
            fresh = snapshot(tenant_a, company, version=5)
            await activate_snapshot(db, fresh)
            await activate_snapshot(db, fresh)
            assert not list(await db.scalars(select(PROJECTION_MODELS["user"])))
            checkpoint = await require_identity_context(db, company)
            checkpoint.expires_at = utcnow() - dt.timedelta(seconds=1)
        async with factory.begin() as db:
            with pytest.raises(IdentitySourceUnavailableError):
                await require_identity_context(db, company)


async def test_snapshot_and_pending_event_contents_cannot_mutate_after_verification(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company = uuid7()
    source = snapshot(tenant_a, company)
    source.records[0].data["display_name"] = "Corrupt"
    with tenant_scope(tenant_a):
        with pytest.raises(ValidationFailedError):
            async with factory.begin() as db:
                await activate_snapshot(db, source)
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company))
            await buffer_change(db, message_id=uuid7(), change=change(tenant_a, 4))
        async with factory.begin() as db:
            event = (await db.scalars(select(SourceEventBuffer))).one()
            event.payload_sha256 = "0" * 64
            with pytest.raises(ConflictError, match="integrity"):
                await buffer_change(db, message_id=uuid7(), change=change(tenant_a, 3))


@pytest.mark.parametrize("snapshot_version", [3, 4])
async def test_snapshot_catches_up_when_events_arrive_before_activation(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, snapshot_version: int
) -> None:
    company, user = uuid7(), uuid7()
    initial = snapshot(tenant_a, company)
    company_change = company_record(company, display_name="Changed")
    user_change = SnapshotRecord(kind="user", id=user, data={"status": "active"})
    rows = (company_change,) if snapshot_version == 3 else (company_change, user_change)
    incoming = snapshot(tenant_a, company, rows, version=snapshot_version)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, initial)
            await buffer_change(
                db, message_id=uuid7(), change=change(tenant_a, 3, (company_change,))
            )
            await buffer_change(db, message_id=uuid7(), change=change(tenant_a, 4, (user_change,)))
        async with factory.begin() as db:
            checkpoint = await activate_snapshot(db, incoming)
            assert checkpoint.source_version == 4
            assert checkpoint.snapshot_id == incoming.manifest.snapshot_id
            assert checkpoint.expires_at == incoming.manifest.expires_at
            assert (await db.scalars(select(PROJECTION_MODELS["user"]))).one().source_id == user


async def test_source_tombstones_scope_moves_and_unrecoverable_replacement_are_atomic(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from billing_platform.constants import SCOPE_ALL

    from catalog.tasks.projections import lock_checkpoint

    company = uuid7()
    facts = all_facts(company, uuid7())
    source = snapshot(tenant_a, company, facts)
    user = next(row for row in facts if row.kind == "user")
    feature = next(row for row in facts if row.kind == "feature")
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            with pytest.raises(ValidationFailedError):
                await lock_checkpoint(db, SCOPE_ALL)
            await lock_checkpoint(db, uuid7())
            await activate_snapshot(db, source)
            await buffer_change(
                db,
                message_id=uuid7(),
                change=change(
                    tenant_a,
                    3,
                    (
                        SnapshotRecord(kind="user", id=user.id, deleted=True, data={}),
                        SnapshotRecord(
                            kind="feature",
                            id=feature.id,
                            data={**feature.data, "company_id": str(uuid7())},
                        ),
                        SnapshotRecord(kind="company", id=uuid7(), deleted=True, data={}),
                    ),
                ),
            )
            assert not list(await db.scalars(select(PROJECTION_MODELS["user"])))
            assert not list(await db.scalars(select(PROJECTION_MODELS["feature"])))
        incoming = snapshot(tenant_a, company, version=4)
        async with factory.begin() as db:
            await activate_snapshot(db, incoming)
            await buffer_change(db, message_id=uuid7(), change=change(tenant_a, 5))
            await buffer_change(db, message_id=uuid7(), change=change(tenant_a, 6))
            latest = (
                await db.scalars(
                    select(SourceEventBuffer).where(SourceEventBuffer.source_version == 6)
                )
            ).one()
            await db.delete(latest)
        with pytest.raises(ConflictError, match="recover"):
            async with factory.begin() as db:
                await activate_snapshot(db, snapshot(tenant_a, company, version=5))
        with pytest.raises(ConflictError):
            async with factory.begin() as db:
                await activate_snapshot(db, source)
        with pytest.raises(ConflictError):
            async with factory.begin() as db:
                await activate_snapshot(
                    db,
                    snapshot(
                        tenant_a,
                        company,
                        (company_record(company, display_name="Different"),),
                        version=4,
                    ),
                )


@pytest.mark.parametrize("excess", ["rows", "checkpoints", "buffer"])
async def test_projection_operational_bounds_fail_closed(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, excess: str
) -> None:
    from catalog.models.projections import UserProjection
    from catalog.schemas.identity_source import CONTRACT
    from catalog.tasks.projections import prune_buffer

    company = uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company))
            if excess == "rows":
                db.add_all(
                    UserProjection(
                        tenant_id=tenant_a,
                        company_id=company,
                        source_id=uuid7(),
                        source_version=2,
                        status="active",
                    )
                    for _ in range(10001)
                )
            elif excess == "checkpoints":
                db.add_all(
                    ProjectionCheckpoint(
                        tenant_id=tenant_a,
                        company_id=uuid7(),
                        source_key=CONTRACT,
                        source_version=0,
                        status="unavailable",
                    )
                    for _ in range(1000)
                )
            else:
                db.add_all(
                    SourceEventBuffer(
                        tenant_id=tenant_a,
                        source_key=CONTRACT,
                        source_version=i + 2,
                        previous_version=i + 1,
                        message_id=uuid7(),
                        payload_sha256="0" * 64,
                        payload={},
                        generated_at=utcnow(),
                    )
                    for i in range(10001)
                )
        with pytest.raises(IdentitySourceUnavailableError):
            async with factory.begin() as db:
                if excess == "rows":
                    await activate_snapshot(db, snapshot(tenant_a, company, version=3))
                elif excess == "checkpoints":
                    await buffer_change(db, message_id=uuid7(), change=change(tenant_a, 3))
                else:
                    await prune_buffer(db, [])
