import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.bulk import BulkRecord, BulkTarget
from billing_platform.db import tenant_scope
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import MasterExternalKey, UnitConversion, UnitOfMeasure
from catalog.models.bulk import BulkJobRecord
from catalog.tasks.bulk_matching import exact_target, prepare
from catalog.tasks.bulk_registry import Runtime
from tests.bulk_factories import post, setup, unit_row
from tests.conftest import ACTOR_SECRET
from tests.test_unit_api import policy, seed_context

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def actor(tenant: uuid.UUID, company: uuid.UUID, user: uuid.UUID) -> Actor:
    return Actor(
        tenant_id=tenant,
        user_id=user,
        grants=(
            Grant(
                permissions=CATALOG_PERMISSIONS,
                scope=Scope("company", company),
                valid_from=dt.date(2000, 1, 1),
            ),
        ),
    )


def record(
    target: dict[str, Any],
    *,
    action: str = "AUTO",
    data: dict[str, Any] | None = None,
    resource: str = "unit_of_measure",
) -> BulkJobRecord:
    value = BulkRecord(
        key="row",
        change_set="row",
        resource=resource,
        action=action,
        target=BulkTarget.model_validate(target),
        data=data or {"name": "Reviewed"},
    )
    return BulkJobRecord(normalized_input=value.model_dump(mode="json"))


async def test_exact_matching_and_reviewed_identity_reject_ambiguous_or_blind_writes(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    created = await post(
        client, f"/v1/companies/{company}", auth, "/units", unit_row("ea")["data"], status=201
    )
    key = uuid.UUID(created["id"])
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            link = MasterExternalKey(
                company_id=company,
                tenant_id=tenant_a,
                entity_type="catalog.unit_of_measure",
                target_id=key,
                source_namespace="ERP",
                external_key="0001",
            )
            db.add(link)
        async with factory.begin() as db:
            runtime = Runtime(
                db, factory, actor(tenant_a, company, user), company, ACTOR_SECRET.encode()
            )
            for identity in (
                {"code": "EA"},
                {"id": str(key), "code": "EA"},
                {"external_system": "ERP", "external_key": "0001"},
            ):
                stored = record(identity)
                op, body, target, before = await prepare(
                    runtime, stored, "UPSERT", {}, reviewed=False
                )
                assert (
                    op.action == "UPDATE"
                    and target == key
                    and before is not None
                    and before["code"] == "EA"
                )
                assert body.expected_version == 1 and stored.expected_version == 1
                again = await prepare(runtime, stored, "UPSERT", {}, reviewed=True)
                assert again[2] == key
            cases = [
                (record({"id": str(key), "code": "MISSING"}), "UPSERT", ValidationFailedError),
                (record({"code": "EA"}), "CREATE_ONLY", ConflictError),
                (record({"code": "MISSING"}), "UPDATE_ONLY", NotFoundError),
                (record({"code": "MISSING"}, action="UPDATE"), "UPSERT", NotFoundError),
                (record({"code": "EA"}, action="CREATE"), "UPSERT", ConflictError),
                (record({"id": str(uuid7())}), "UPDATE_ONLY", NotFoundError),
                (
                    record({"external_system": "ERP", "external_key": "MISSING"}, action="CREATE"),
                    "UPSERT",
                    ValidationFailedError,
                ),
                (
                    record({"code": "NEW"}, data=unit_row("different")["data"]),
                    "CREATE_ONLY",
                    ValidationFailedError,
                ),
                (
                    record({"id": str(key)}, data={"name": "changed", "expected_version": 2}),
                    "UPDATE_ONLY",
                    ConflictError,
                ),
                (record({}, resource="bulk_job"), "UPSERT", ValidationFailedError),
            ]
            for stored, mode, error in cases:
                with pytest.raises(error):
                    await prepare(runtime, stored, mode, {}, reviewed=False)
            stored = record({"id": str(key)})
            with pytest.raises(ConflictError):
                await prepare(runtime, stored, "UPDATE_ONLY", {}, reviewed=True)
            await prepare(runtime, stored, "UPDATE_ONLY", {}, reviewed=False)
            stored.target_id = uuid7()
            with pytest.raises(ConflictError):
                await prepare(runtime, stored, "UPDATE_ONLY", {}, reviewed=True)
            data = unit_row("new")["data"]
            data.pop("code")
            op, body, target, before = await prepare(
                runtime, record({"code": "NEW"}, data=data), "CREATE_ONLY", {}, reviewed=False
            )
            assert (
                op.action == "CREATE" and body.code == "NEW" and target is None and before is None
            )
            with pytest.raises(ValidationFailedError):
                await exact_target(
                    runtime,
                    BulkRecord(
                        key="row",
                        change_set="row",
                        resource="unit_conversion",
                        target=BulkTarget(code="EA"),
                    ),
                    UnitConversion,
                    {},
                )


@pytest.mark.parametrize(
    "entity,field,target",
    [
        ("catalog.unit_of_measure", "code", {"code": "EA"}),
        ("catalog.unit_of_measure", "name", {"code": "EA"}),
        (
            "catalog.master_external_key",
            "target_id",
            {"external_system": "ERP", "external_key": "001"},
        ),
    ],
)
async def test_matching_does_not_bypass_field_denies(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    entity: str,
    field: str,
    target: dict[str, str],
) -> None:
    company, user, auth = await setup(factory, tenant_a)
    await post(
        client, f"/v1/companies/{company}", auth, "/units", unit_row("ea")["data"], status=201
    )
    await seed_context(
        factory, tenant_a, company, user, (policy(user, field, "read", entity=entity),), version=3
    )
    with tenant_scope(tenant_a):
        async with factory() as db:
            runtime = Runtime(
                db, factory, actor(tenant_a, company, user), company, ACTOR_SECRET.encode()
            )
            with pytest.raises(PermissionDeniedError):
                await exact_target(
                    runtime,
                    BulkRecord(
                        key="row",
                        change_set="row",
                        resource="unit_of_measure",
                        target=BulkTarget.model_validate(target),
                    ),
                    UnitOfMeasure,
                    {},
                )
