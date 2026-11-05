import datetime as dt
import uuid
from typing import Any

import httpx
from billing_platform.actor_authorization import ActorAuthorizationProof
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.bulk import (
    BulkChangeSet,
    BulkChangeSetEffect,
    BulkImportArtifact,
    BulkJob,
    BulkJobDependency,
    BulkJobRecord,
)
from catalog.tasks.bulk_execution import PERMISSION_CHUNKS, step
from catalog.tasks.bulk_jobs import new
from tests.conftest import ACTOR_SECRET
from tests.test_api import headers
from tests.test_unit_api import seed_context


async def setup(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    company, user = uuid7(), uuid7()
    await seed_context(factory, tenant, company, user)
    return (
        company,
        user,
        headers(company, tenant=tenant, user=user, permission=sorted(CATALOG_PERMISSIONS)),
    )


def proofs(
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    *,
    version: int = 2,
    denied: frozenset[str] = frozenset(),
) -> tuple[ActorAuthorizationProof, ...]:
    now = utcnow()
    return tuple(
        ActorAuthorizationProof(
            request_id=uuid7(),
            tenant_id=tenant,
            company_id=company,
            user_id=user,
            source_version=version,
            generated_at=now,
            expires_at=now + dt.timedelta(seconds=30),
            permissions=chunk - denied,
        )
        for chunk in PERMISSION_CHUNKS
    )


async def run(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    job: str,
    *,
    count: int = 20,
    version: int | None = None,
    denied: frozenset[str] = frozenset(),
) -> str:
    """``version`` is the company's live Identity checkpoint; a stale proof is refused.

    ``denied`` withholds a key from every step, which is how a test reaches the authority
    the worker resolves *when the file runs* rather than when it was staged.

    Both are forwarded only when the caller states them, so a test that patches ``proofs``
    wholesale still decides its own defaults instead of being overridden from here.
    """
    issued: dict[str, Any] = {}
    if version is not None:
        issued["version"] = version
    if denied:
        issued["denied"] = denied
    for _ in range(count):
        with tenant_scope(tenant):
            async with factory() as db:
                state = await db.scalar(
                    select(BulkJob.state).where(
                        BulkJob.company_id == company, BulkJob.id == uuid.UUID(job)
                    )
                )
        if state not in {"VALIDATING", "QUEUED", "RUNNING"}:
            assert isinstance(state, str)
            return state
        await step(
            factory,
            proofs(tenant, company, user, **issued),
            tenant,
            company,
            user,
            uuid.UUID(job),
            ACTOR_SECRET.encode(),
        )
    raise AssertionError("bulk worker did not finish within its test bound")


async def post(
    client: httpx.AsyncClient,
    root: str,
    auth: dict[str, str],
    suffix: str,
    body: dict[str, Any],
    *,
    status: int = 202,
) -> dict[str, Any]:
    response = await client.post(
        root + suffix, headers={**auth, "Idempotency-Key": str(uuid7())}, json=body
    )
    assert response.status_code == status, response.text
    return dict(response.json())


def unit_row(key: str, *, group: str | None = None) -> dict[str, Any]:
    return {
        "key": key,
        "change_set": group or key,
        "resource": "unit_of_measure",
        "data": {
            "code": key.upper(),
            "name": key,
            "symbol": key,
            "dimension": "COUNT",
            "decimal_places": 0,
            "quantity_increment": "1",
        },
    }


async def seed_storage(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    *,
    company: uuid.UUID | None = None,
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    company = company or uuid7()
    actor = Actor(tenant_id=tenant, user_id=uuid7())
    ids: dict[str, uuid.UUID] = {}
    with tenant_scope(tenant):
        async with factory.begin() as db:
            job = new(
                BulkJob,
                actor,
                company,
                actor_user_id=actor.user_id,
                kind="IMPORT",
                mode="CREATE_ONLY",
                atomicity="CHANGE_SET",
                on_error="STOP",
                state="STAGED",
                revision=1,
                schema_version=1,
                input_hash="a" * 64,
                record_count=2,
                completed_count=0,
                invalid_count=0,
                expires_at=utcnow() + dt.timedelta(days=7),
            )
            db.add(job)
            await db.flush()
            ids["bulk_job"] = job.id
            group = new(
                BulkChangeSet,
                actor,
                company,
                job_id=job.id,
                logical_key="group",
                ordinal=1,
                record_count=2,
                action_hash="b" * 64,
                state="STAGED",
            )
            db.add(group)
            await db.flush()
            ids["bulk_change_set"] = group.id
            records = []
            for index, key in enumerate(("parent", "child"), 1):
                row = new(
                    BulkJobRecord,
                    actor,
                    company,
                    job_id=job.id,
                    change_set_id=group.id,
                    logical_key=key,
                    ordinal=index,
                    resource="unit_of_measure",
                    action="CREATE",
                    source_sheet="JSON",
                    source_row=index,
                    state="STAGED",
                    normalized_input=unit_row(key),
                )
                db.add(row)
                records.append(row)
            await db.flush()
            ids["bulk_job_record"] = records[0].id
            for model, values in (
                (
                    BulkJobDependency,
                    {"parent_record_id": records[0].id, "child_record_id": records[1].id},
                ),
                (
                    BulkChangeSetEffect,
                    {
                        "change_set_id": group.id,
                        "logical_key": "group",
                        "accepted_revision": 1,
                        "action_hash": "b" * 64,
                        "results": {},
                        "source_pins": [],
                    },
                ),
                (
                    BulkImportArtifact,
                    {
                        "content_type": "text/csv",
                        "content_sha256": "c" * 64,
                        "byte_count": 3,
                        "expires_at": job.expires_at,
                        "content": b"abc",
                    },
                ),
            ):
                value = new(model, actor, company, job_id=job.id, **values)
                db.add(value)
                await db.flush()
                ids[model.__tablename__] = value.id
    return company, ids
