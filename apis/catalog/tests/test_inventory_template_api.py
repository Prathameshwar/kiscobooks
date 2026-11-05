from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.db import tenant_scope
from billing_platform.errors import ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdempotencyKey, Outbox
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.profiles import IdentifierProfileRequirement
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.commercial_history import INVENTORY_REVISION, command
from tests.inventory_factories import auth
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_commercial_api import command_headers


async def setup_template(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str], str]:
    company, user = uuid7(), uuid7()
    current = await auth(factory, tenant, company, user)
    route = f"/v1/companies/{company}/inventory-templates"
    result = await client.post(
        route, headers=command_headers(current), json={"code": "STOCK", "name": "Stock"}
    )
    assert result.status_code == 201, result.text
    return company, user, current, route + "/" + result.json()["id"]


async def test_inventory_master_and_revision_workflow_lists_and_scopes(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, user, current, master = await setup_template(client, factory, tenant_a)
    route = master.rsplit("/", 1)[0]
    assert (await client.get(master)).status_code == 401
    reader = headers(
        company, tenant=tenant_a, user=user, permission="inventory_profile_template.read"
    )
    body = {"code": "STOCK", "name": "Stock"}
    assert (await client.post(route, headers=command_headers(reader), json=body)).status_code == 403
    assert (
        await client.post(route, headers=command_headers(current), json=body)
    ).status_code == 409
    assert (await client.get(master, headers=current)).status_code == 200
    changed = await client.patch(
        master,
        headers=command_headers(current),
        json={"expected_version": 1, "name": "Stock requirements"},
    )
    assert changed.status_code == 200 and changed.json()["row_version"] == 2
    for action, version in (("deactivate", 2), ("activate", 3)):
        result = await client.post(
            master + "/" + action,
            headers=command_headers(current),
            json={"expected_version": version},
        )
        assert result.status_code == 200, result.text
    second = await client.post(
        route, headers=command_headers(current), json={"code": "OTHER", "name": "Other"}
    )
    assert second.status_code == 201
    renamed = await client.patch(
        route + "/" + second.json()["id"],
        headers=command_headers(current),
        json={"expected_version": 1, "code": "MATERIAL"},
    )
    assert renamed.status_code == 200 and renamed.json()["code"] == "MATERIAL"
    listing = await client.get(route, headers=current, params={"limit": 1, "sort": "code"})
    assert listing.status_code == 200 and listing.json()["page"]["has_more"]
    assert (
        await client.get(route, headers=current, params={"q": "Stock", "is_active": True})
    ).json()["items"][0]["id"] == master.rsplit("/", 1)[-1]
    revisions = master + "/revisions"
    receipt = command_headers(current)
    first = await client.post(revisions, headers=receipt, json={})
    assert first.status_code == 201, first.text
    assert first.json()["revision"] == 1 and first.json()["lot_tracking"] is False
    assert (await client.post(revisions, headers=receipt, json={})).headers[
        "Idempotency-Replayed"
    ] == "true"
    detail = revisions + "/" + first.json()["id"]
    assert (await client.get(detail, headers=current)).status_code == 200
    assert (
        await client.patch(
            master,
            headers=command_headers(current),
            json={"expected_version": 4, "code": "RENAMED"},
        )
    ).status_code == 409
    invalid_inputs = [
        {"lot_tracking": "false"},
        {"expiry_required": True},
        {"valuation_method": "SPECIFIC"},
        {"issue_strategy": "FEFO"},
        {"quantity": "10"},
        {"shelf_life_days": True},
    ]
    for invalid in invalid_inputs:
        assert (
            await client.post(revisions, headers=command_headers(current), json=invalid)
        ).status_code == 422
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 1, "lot_tracking": None},
        )
    ).status_code == 422
    update: dict[str, Any] = {
        "expected_version": 1,
        "lot_tracking": True,
        "expiry_required": True,
        "issue_strategy": "FEFO",
        "shelf_life_days": 30,
        "minimum_remaining_life_days": 0,
    }
    updated = await client.patch(detail, headers=command_headers(current), json=update)
    assert updated.status_code == 200 and updated.json()["row_version"] == 2, updated.text
    assert (
        await client.patch(detail, headers=command_headers(current), json=update)
    ).status_code == 409
    noop = await client.patch(
        detail, headers=command_headers(current), json={"expected_version": 2, "lot_tracking": True}
    )
    assert noop.status_code == 200 and noop.json()["row_version"] == 2
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(reader), json={"expected_version": 2}
        )
    ).status_code == 403
    publication = command_headers(current)
    published = await client.post(
        detail + "/publish", headers=publication, json={"expected_version": 2}
    )
    assert published.status_code == 200 and published.json()["published_at"], published.text
    assert (
        await client.post(detail + "/publish", headers=publication, json={"expected_version": 2})
    ).headers["Idempotency-Replayed"] == "true"
    for action in ("patch", "publish"):
        response = await (
            client.patch(detail, headers=command_headers(current), json={"expected_version": 3})
            if action == "patch"
            else client.post(
                detail + "/publish", headers=command_headers(current), json={"expected_version": 3}
            )
        )
        assert response.status_code == 409
    second_revision = await client.post(revisions, headers=command_headers(current), json={})
    assert second_revision.status_code == 201 and second_revision.json()["revision"] == 2
    page = await client.get(revisions, headers=current, params={"limit": 1, "sort": "-revision"})
    next_page = await client.get(
        revisions,
        headers=current,
        params={"limit": 1, "sort": "-revision", "cursor": page.json()["page"]["next_cursor"]},
    )
    assert next_page.json()["items"][0]["id"] == first.json()["id"]
    filter_cases: tuple[dict[str, str | bool], ...] = (
        {"published": True},
        {"expiry_required": True},
        {"issue_strategy": "FEFO"},
        {"lot_tracking": True, "serial_tracking": False, "valuation_method": "FIFO"},
    )
    for filters in filter_cases:
        result = await client.get(revisions, headers=current, params=filters)
        assert result.status_code == 200 and len(result.json()["items"]) == 1, result.text
        assert "identifier_profile_id" not in result.json()["items"][0]
    assert (await client.get(revisions, headers=current, params={"q": "stock"})).status_code == 422
    assert (
        await client.get(revisions, headers=current, params={"sort": "shelf_life_days"})
    ).status_code == 422
    assert (await client.get(revisions, headers=current, params={"published": False})).json()[
        "items"
    ][0]["id"] == second_revision.json()["id"]
    options = await client.get(
        f"/v1/companies/{company}/option-sources/catalog.inventory_templates", headers=current
    )
    assert options.status_code == 200 and len(options.json()["items"]) == 2
    wrong_parent = detail.replace(master.rsplit("/", 1)[-1], second.json()["id"])
    assert (await client.get(wrong_parent, headers=current)).status_code == 403
    other_company = uuid7()
    other = await auth(factory, tenant_a, other_company, user)
    assert (
        await client.get(detail.replace(str(company), str(other_company)), headers=other)
    ).status_code == 403
    assert (
        await client.get(revisions.replace(str(company), str(other_company)), headers=other)
    ).status_code == 403
    alien = await auth(factory, tenant_b, company, user)
    assert (await client.get(detail, headers=alien)).status_code == 404


async def test_inventory_identifier_dependencies_preserve_published_requirements(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, current, master = await setup_template(client, factory, tenant_a)
    identifiers = f"/v1/companies/{company}/identifier-profiles"
    identifier_input = {
        "code": "DEVICE",
        "name": "Device",
        "requirements": [
            {
                "identifier_type": "SERIAL",
                "namespace_rule": "COMPANY",
                "min_count": 1,
                "max_count": 1,
            }
        ],
    }
    identifier = await client.post(
        identifiers, headers=command_headers(current), json=identifier_input
    )
    assert identifier.status_code == 201
    identifier_path = identifiers + "/" + identifier.json()["id"]
    revisions = master + "/revisions"
    body = {
        "identifier_profile_id": identifier.json()["id"],
        "serial_tracking": True,
        "valuation_method": "SPECIFIC",
    }
    draft = await client.post(revisions, headers=command_headers(current), json=body)
    assert draft.status_code == 201, draft.text
    detail = revisions + "/" + draft.json()["id"]
    assert (
        await client.get(
            revisions,
            headers=current,
            params={"identifier_profile_id": body["identifier_profile_id"]},
        )
    ).json()["items"][0]["id"] == draft.json()["id"]
    off = await client.post(
        identifier_path + "/deactivate",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert off.status_code == 200
    assert (
        await client.post(revisions, headers=command_headers(current), json=body)
    ).status_code == 409
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 409
    assert (
        await client.post(
            identifier_path + "/activate",
            headers=command_headers(current),
            json={"expected_version": 2},
        )
    ).status_code == 200
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    assert (
        await client.post(
            identifier_path + "/deactivate",
            headers=command_headers(current),
            json={"expected_version": 3},
        )
    ).status_code == 409
    assert (
        await client.post(
            master + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    assert (
        await client.post(revisions, headers=command_headers(current), json={})
    ).status_code == 409
    assert (
        await client.post(
            identifier_path + "/deactivate",
            headers=command_headers(current),
            json={"expected_version": 3},
        )
    ).status_code == 200
    assert (
        await client.post(
            master + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 409
    assert (
        await client.post(
            identifier_path + "/activate",
            headers=command_headers(current),
            json={"expected_version": 4},
        )
    ).status_code == 200
    assert (
        await client.post(
            master + "/activate", headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 200
    other_company = uuid7()
    other = await auth(factory, tenant_a, other_company, user)
    foreign = await client.post(
        identifiers.replace(str(company), str(other_company)),
        headers=command_headers(other),
        json=identifier_input,
    )
    assert foreign.status_code == 201
    assert (
        await client.post(
            revisions,
            headers=command_headers(current),
            json={**body, "identifier_profile_id": foreign.json()["id"]},
        )
    ).status_code == 403
    second = await client.post(revisions, headers=command_headers(current), json=body)
    assert second.status_code == 201
    second_path = revisions + "/" + second.json()["id"]
    cleared = await client.patch(
        second_path,
        headers=command_headers(current),
        json={
            "expected_version": 1,
            "identifier_profile_id": None,
            "valuation_method": "FIFO",
            "serial_tracking": False,
        },
    )
    assert cleared.status_code == 200 and cleared.json()["identifier_profile_id"] is None
    assert (
        await client.post(
            master + "/deactivate", headers=command_headers(current), json={"expected_version": 3}
        )
    ).status_code == 200
    assert (
        await client.patch(
            second_path, headers=command_headers(current), json={"expected_version": 2}
        )
    ).status_code == 409


async def test_inventory_current_field_policy_atomicity_and_lean_read_guards(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, _, master = await setup_template(client, factory, tenant_a)
    facts = all_facts(company, user)
    source = next(row for row in facts if row.kind == "field_policy")
    policy = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": "catalog.inventory_profile_template_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "shelf_life_days",
            "access": "write",
            "condition": {"field": "shelf_life_days", "cmp": "gt", "value": "30"},
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, policy))
    revisions = master + "/revisions"
    payload = {"lot_tracking": True, "expiry_required": True, "shelf_life_days": 60}
    receipt = command_headers(current)
    assert (await client.post(revisions, headers=receipt, json=payload)).status_code == 403
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(InventoryProfileTemplateRevision.id))) == 0
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == 1
            assert await db.scalar(select(func.count(Outbox.id))) == 1
    payload["shelf_life_days"] = 30
    allowed = await client.post(revisions, headers=receipt, json=payload)
    assert allowed.status_code == 201, allowed.text
    assert (await client.post(revisions, headers=receipt, json=payload)).status_code == 201
    detail = revisions + "/" + allowed.json()["id"]
    deny = SnapshotRecord(
        kind="field_policy", id=policy.id, data={**policy.data, "condition": None}
    )
    current = await auth(factory, tenant_a, company, user, version=4, facts=(*facts, deny))
    assert (
        await client.post(revisions, headers={**receipt, **current}, json=payload)
    ).status_code == 403
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 403
    hidden = tuple(
        SnapshotRecord(
            kind="field_policy",
            id=uuid7(),
            data={
                **deny.data,
                "field_key": key,
                "access": "read",
            },
        )
        for key in ("identifier_profile_id", "revision", "published_at")
    )
    current = await auth(factory, tenant_a, company, user, version=5, facts=(*facts, *hidden))
    page = await client.get(revisions, headers=current)
    assert page.status_code == 200
    assert (
        "revision" not in page.json()["items"][0] and "published_at" not in page.json()["items"][0]
    )
    for query in (
        {"identifier_profile_id": str(uuid7())},
        {"sort": "revision"},
        {"published": "true"},
    ):
        assert (await client.get(revisions, headers=current, params=query)).status_code == 403
    metadata = await client.get(
        f"/v1/companies/{company}/entities/catalog.inventory_profile_template_revision/field-set",
        headers=current,
    )
    assert metadata.status_code == 200
    fields = {entry["key"]: entry for entry in metadata.json()["fields"]}
    assert fields["template_id"]["writable"] is False and "revision" not in fields
    membership = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={**deny.data, "field_key": "template_id", "access": "read"},
    )
    current = await auth(factory, tenant_a, company, user, version=6, facts=(*facts, membership))
    for path in (revisions, detail):
        assert (await client.get(path, headers=current)).status_code == 403


async def test_inventory_reactivation_rejects_missing_identifier_requirements(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, current, master = await setup_template(client, factory, tenant_a)
    identifier = await client.post(
        f"/v1/companies/{company}/identifier-profiles",
        headers=command_headers(current),
        json={
            "code": "DEVICE",
            "name": "Device",
            "requirements": [
                {
                    "identifier_type": "SERIAL",
                    "namespace_rule": "COMPANY",
                    "min_count": 1,
                    "max_count": 1,
                }
            ],
        },
    )
    assert identifier.status_code == 201
    draft = await client.post(
        master + "/revisions",
        headers=command_headers(current),
        json={
            "serial_tracking": True,
            "identifier_profile_id": identifier.json()["id"],
        },
    )
    assert draft.status_code == 201
    assert (
        await client.post(
            master + "/revisions/" + draft.json()["id"] + "/publish",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    assert (
        await client.post(
            master + "/deactivate", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 200
    # Restore corruption can leave a valid header/FK but no immutable requirements.
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            for row in await db.scalars(select(IdentifierProfileRequirement)):
                await db.delete(row)
    rejected = await client.post(
        master + "/activate", headers=command_headers(current), json={"expected_version": 2}
    )
    assert rejected.status_code == 409, rejected.text
    assert (await client.get(master, headers=current)).json()["is_active"] is False


async def test_inventory_label_rejects_invalid_unicode_before_storage(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, current, _ = await setup_template(client, factory, tenant_a)
    response = await client.post(
        f"/v1/companies/{company}/inventory-templates",
        headers={**command_headers(current), "Content-Type": "application/json"},
        content='{"code":"BAD","name":"\\ud800"}',
    )
    assert response.status_code == 422, response.text


async def test_inventory_command_rejects_unsupported_close_without_effects(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, current, master = await setup_template(client, factory, tenant_a)
    response = await client.post(master + "/revisions", headers=command_headers(current), json={})
    assert response.status_code == 201
    actor = Actor(
        tenant_a,
        user,
        grants=(
            Grant(
                frozenset({"inventory_profile_template.manage"}),
                Scope("company", company),
                dt.date(2000, 1, 1),
            ),
        ),
    )
    # The common handler also serves dated relationships; an internal adapter must
    # not accidentally close or publish an inventory revision through that action.
    with pytest.raises(ValidationFailedError, match="unsupported inventory"):
        await command(
            factory,
            actor,
            company,
            INVENTORY_REVISION,
            key=str(uuid7()),
            body=ExpectedVersion(expected_version=1),
            action="close",
            object_id=uuid.UUID(response.json()["id"]),
            parent_id=uuid.UUID(master.rsplit("/", 1)[-1]),
        )
    with tenant_scope(tenant_a):
        async with factory() as db:
            row = await db.get(InventoryProfileTemplateRevision, uuid.UUID(response.json()["id"]))
            assert row is not None and row.row_version == 1 and row.published_at is None
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == 2
            assert await db.scalar(select(func.count(Outbox.id))) == 2


async def test_inventory_negative_stock_policy(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, current, master = await setup_template(client, factory, tenant_a)
    # 1. Default is BLOCK
    created = await client.post(master + "/revisions", headers=command_headers(current), json={})
    assert created.status_code == 201, created.text
    assert created.json()["negative_stock_policy"] == "BLOCK"
    rev_id = created.json()["id"]

    # 2. Update to WARN
    updated = await client.patch(
        f"{master}/revisions/{rev_id}",
        headers=command_headers(current),
        json={"expected_version": 1, "negative_stock_policy": "WARN"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["negative_stock_policy"] == "WARN"

    # 3. Create with ALLOW
    created_allow = await client.post(
        master + "/revisions",
        headers=command_headers(current),
        json={"negative_stock_policy": "ALLOW"},
    )
    assert created_allow.status_code == 201, created_allow.text
    assert created_allow.json()["negative_stock_policy"] == "ALLOW"

    # 4. Invalid policy fails with 422
    invalid = await client.post(
        master + "/revisions",
        headers=command_headers(current),
        json={"negative_stock_policy": "INVALID"},
    )
    assert invalid.status_code == 422
