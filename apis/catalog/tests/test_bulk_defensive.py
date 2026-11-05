import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.bulk import BulkRecord
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.ids import uuid7
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import UnitOfMeasure
from catalog.models.bulk import BulkJob
from catalog.schemas.bulk import JobAction
from catalog.tasks import bulk_identity
from catalog.tasks.bulk_access import Evidence, wire
from catalog.tasks.bulk_execution import RowFailureError, current_actor
from catalog.tasks.bulk_jobs import command, touch
from catalog.tasks.bulk_registry import OPERATIONS, register
from tests.bulk_factories import post, run, setup, unit_row
from tests.test_bulk_matching import actor

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def test_safe_row_errors_and_immutable_registry_bounds() -> None:
    assert wire(b"\x00\xff") == "00ff"
    assert wire(dt.date(2026, 1, 1)) == "2026-01-01"
    with pytest.raises(ValidationError) as caught:
        BulkRecord.model_validate(
            {
                "key": "a",
                "change_set": "a",
                "resource": "unit_of_measure",
                "data": {"private key!": 1.2},
            }
        )
    assert RowFailureError(uuid7(), caught.value).fields() == ["data"]
    bad = ValidationError.from_exception_data(
        "bad", [{"type": "missing", "loc": ("private key!",), "input": {}}]
    )
    assert RowFailureError(uuid7(), bad).fields() == []
    op = OPERATIONS["unit_of_measure", "CREATE"]
    with pytest.raises(RuntimeError, match="duplicate"):
        register(op.model, op.action, op.schema, op.call)
    with pytest.raises(ConflictError, match="version exhausted"):
        touch(BulkJob(row_version=2**31 - 1), actor(uuid7(), uuid7(), uuid7()))


async def test_evidence_count_and_cumulative_size_are_bounded() -> None:
    async with AsyncSession() as db:
        evidence = Evidence(db)
        evidence.rows = {("unit_of_measure", uuid7()): None for _ in range(10000)}
        unit = UnitOfMeasure(
            id=uuid7(), code="EA", name="each", symbol="ea", dimension="COUNT", row_version=1
        )
        with pytest.raises(ConflictError, match="dependency set"):
            evidence.capture(db.sync_session, unit)
        evidence.rows = {}
        evidence.byte_count = 256 * 1024
        with pytest.raises(ConflictError, match="byte bound"):
            evidence.capture(db.sync_session, unit)
        with pytest.raises(PermissionDeniedError, match="complete current"):
            await current_actor(db, (), uuid7(), uuid7(), uuid7())


async def test_identity_snapshot_limit_is_enforced(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    company, _, _ = await setup(factory, tenant_a)
    monkeypatch.setattr(bulk_identity, "MAX_RECORDS", 0)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            with pytest.raises(ValidationFailedError, match="review bound"):
                await bulk_identity.identity_digest(db, company)


async def test_invalid_job_transitions_never_change_a_reviewed_job(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    body = {"format": "JSON", "records": [unit_row("ea")]}
    job = await post(client, root, auth, "", body)

    async def reject(suffix: str, data: dict[str, Any], status: int) -> None:
        response = await client.post(
            root + "/" + job["id"] + suffix,
            headers={**auth, "Idempotency-Key": str(uuid7())},
            json=data,
        )
        assert response.status_code == status, response.text

    await reject("/cancel", {"expected_version": 99}, 409)
    await reject("/commit", {"expected_version": 1, "selection_digest": "a" * 64}, 409)
    await reject("/validate", {"expected_version": 1, "selected_keys": ["ea", "ea"]}, 422)
    await reject("/validate", {"expected_version": 1, "selected_keys": ["missing"]}, 422)
    await reject(
        "/revise",
        {"expected_version": 1, "batch": {"mode": "UPSERT", "records": body["records"]}},
        409,
    )
    with pytest.raises(ValidationFailedError, match="unsupported bulk"):
        await command(
            factory,
            actor(tenant_a, company, user),
            company,
            JobAction(expected_version=1),
            str(uuid7()),
            action="unsupported",
            job_id=uuid.UUID(job["id"]),
        )
    validating = await post(
        client, root, auth, "/" + job["id"] + "/validate", {"expected_version": 1}
    )
    await reject("/validate", {"expected_version": validating["row_version"]}, 409)
    await reject(
        "/revise",
        {"expected_version": validating["row_version"], "batch": {"records": body["records"]}},
        409,
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "READY"
    state = (await client.get(root + "/" + job["id"], headers=auth)).json()
    await post(
        client,
        root,
        auth,
        "/" + job["id"] + "/commit",
        {"expected_version": state["row_version"], "selection_digest": state["selection_digest"]},
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "SUCCEEDED"
    state = (await client.get(root + "/" + job["id"], headers=auth)).json()
    await reject("/cancel", {"expected_version": state["row_version"]}, 409)
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(BulkJob.state)) == "SUCCEEDED"


@pytest.mark.parametrize("atomic", [False, True])
async def test_native_command_weights_enforce_set_and_atomic_bounds(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    atomic: bool,
) -> None:
    company, _, auth = await setup(factory, tenant_a)
    records = [
        {
            "key": f"r{i}",
            "change_set": f"g{i//10}" if atomic else "one",
            "resource": "item_price",
            "action": "ADJUST",
            "target": {"id": str(uuid7())},
            "data": {},
        }
        for i in range(501 if atomic else 51)
    ]
    response = await client.post(
        f"/v1/companies/{company}/bulk-jobs",
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={
            "format": "JSON",
            "mode": "UPDATE_ONLY",
            "atomicity": "ATOMIC" if atomic else "CHANGE_SET",
            "records": records,
        },
    )
    assert response.status_code == 422, response.text
    assert "native commands" in response.text


@pytest.mark.parametrize("relation", [False, True])
async def test_exhausted_policy_generation_rolls_back_new_unit_semantics(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    relation: bool,
) -> None:
    from catalog.models import UnitConversion
    from catalog.models.classification import CatalogPolicyState

    company, _, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}"
    unit = await post(client, root, auth, "/units", unit_row("ea")["data"], status=201)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            state = (await db.scalars(select(CatalogPolicyState))).one()
            state.generation = 2**63 - 1
    if relation:
        response = await client.post(
            root + "/unit-conversions",
            headers={**auth, "Idempotency-Key": str(uuid7())},
            json={
                "from_unit_id": unit["id"],
                "canonical_unit_id": unit["id"],
                "numerator": 1,
                "denominator": 1,
            },
        )
    else:
        response = await client.patch(
            root + "/units/" + unit["id"],
            headers={**auth, "Idempotency-Key": str(uuid7())},
            json={"expected_version": 1, "name": "Changed"},
        )
    assert response.status_code == 409, response.text
    unchanged = await client.patch(
        root + "/units/" + unit["id"],
        headers={**auth, "Idempotency-Key": str(uuid7())},
        json={"expected_version": 1, "name": "ea"},
    )
    assert unchanged.status_code == 200, unchanged.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert list(await db.scalars(select(UnitConversion.id))) == []
            assert await db.scalar(select(UnitOfMeasure.name)) == "ea"
            assert await db.scalar(select(CatalogPolicyState.generation)) == 2**63 - 1


async def test_dependency_fanout_and_restored_atomic_jobs_cannot_exceed_worker_bounds(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    from catalog.models.bulk import BulkChangeSet
    from catalog.models.classification import CatalogPolicyState
    from catalog.tasks.bulk_execution import ancestors, step
    from tests.bulk_factories import proofs
    from tests.conftest import ACTOR_SECRET

    company, user, auth = await setup(factory, tenant_a)
    rows = []
    for index in range(1100):
        record = unit_row(f"u{index}", group=f"g{index//100}")
        if index and index % 100 == 0:
            record["depends_on"] = [f"u{index-100}"]
        rows.append(record)
    response = await post(
        client, f"/v1/companies/{company}/bulk-jobs", auth, "", {"format": "JSON", "records": rows}
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            job = await db.get(BulkJob, uuid.UUID(response["id"]))
            assert job is not None
            groups = list(await db.scalars(select(BulkChangeSet).order_by(BulkChangeSet.ordinal)))
            with pytest.raises(ValidationFailedError, match="dependent preview"):
                await ancestors(db, job, groups[-1])
            # Simulate an inconsistent restored checkpoint; the execution fence must still hold.
            job.state, job.atomicity = "QUEUED", "ATOMIC"
            job.source_version = 2
            job.policy_generation = await db.scalar(select(CatalogPolicyState.generation))
            for group in groups:
                group.state = "VALID"
    with pytest.raises(ValidationFailedError, match="worker chunk exceeds"):
        await step(
            factory,
            proofs(tenant_a, company, user),
            tenant_a,
            company,
            user,
            uuid.UUID(response["id"]),
            ACTOR_SECRET.encode(),
        )
