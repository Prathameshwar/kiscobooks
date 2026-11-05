"""Sequential route contracts pin operation revisions and preserve exact time text."""

import json
from pathlib import Path

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select

from catalog.models import (
    IdempotencyKey,
    ManufacturingRouteRevision,
    ManufacturingRouteStep,
    Outbox,
)
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers


async def setup_route_actor(factory, tenant):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant, company, user)
    return company, headers(
        company,
        tenant=tenant,
        user=user,
        permission=[
            prefix + suffix
            for prefix in ("manufacturing_route", "manufacturing_operation")
            for suffix in (".read", ".manage", ".publish")
        ],
    )


async def published_operation(client, company, current):
    root = f"/v1/companies/{company}/manufacturing-operations"
    created = await client.post(
        root, headers=command_headers(current), json={"code": "CUT", "name": "Cutting"}
    )
    assert created.status_code == 201, created.text
    master = root + "/" + created.json()["id"]
    draft = await client.post(
        master + "/revisions",
        headers=command_headers(current),
        json={"specification": "Approved cutting specification", "change_reason": "Initial"},
    )
    assert draft.status_code == 201, draft.text
    revision = master + "/revisions/" + draft.json()["id"]
    result = await client.post(
        revision + "/publish", headers=command_headers(current), json={"expected_version": 1}
    )
    assert result.status_code == 200, result.text
    return result.json()["id"], revision


async def test_route_native_field_metadata(client, factory, tenant_a):
    company, current = await setup_route_actor(factory, tenant_a)
    captured = {}
    for entity in (
        "manufacturing_route",
        "manufacturing_route_revision",
        "manufacturing_route_step",
    ):
        for operation in (
            "read",
            "create",
            "update",
            *(() if entity == "manufacturing_route" else ("publish",)),
        ):
            response = await client.get(
                f"/v1/companies/{company}/entities/catalog.{entity}/field-set",
                headers=current,
                params={} if operation == "read" else {"operation": operation},
            )
            assert response.status_code == 200, response.text
            captured[entity + ":" + operation] = response.json()["fields"]
    step = {field["key"]: field for field in captured["manufacturing_route_step:create"]}
    assert step["run_minutes"]["control"]["kind"] == "decimal"
    assert (
        step["operation_revision_id"]["control"]["reference_source"]
        == "manufacturing-operation-revisions"
    )
    assert step["revision_id"]["writable"]
    revision = {field["key"]: field for field in captured["manufacturing_route_revision:create"]}
    assert not revision["status"]["writable"] and not revision["step_count"]["writable"]
    target = Path(__file__).resolve().parents[3] / ".tools/extension-masters/route-fields.json"
    target.write_text(json.dumps(captured, indent=2), encoding="utf-8")


async def test_complete_route_reorders_stable_steps_publishes_and_preserves_retired_references(
    client, factory, tenant_a
):
    company, current = await setup_route_actor(factory, tenant_a)
    operation, operation_path = await published_operation(client, company, current)
    root = f"/v1/companies/{company}/manufacturing-routes"
    choices = await client.get(root + "/operation-options", headers=current)
    assert choices.status_code == 200, choices.text
    assert choices.json()["items"][0]["id"] == operation
    master = await client.post(
        root, headers=command_headers(current), json={"code": "CUT-PACK", "name": "Cut and pack"}
    )
    revisions = root + "/" + master.json()["id"] + "/revisions"
    payload = {
        "specification": "Cut then pack",
        "change_reason": "Initial route",
        "steps": [
            {
                "sequence": 1,
                "operation_revision_id": operation,
                "setup_minutes": "2.0000",
                "run_minutes": "0.1250",
            },
            {
                "sequence": 2,
                "operation_revision_id": operation,
                "run_minutes": "3.2500",
                "time_basis": "PER_BATCH",
                "quantity_basis": "10.0000",
            },
        ],
    }
    receipt = command_headers(current)
    draft = await client.post(revisions, headers=receipt, json=payload)
    assert draft.status_code == 201, draft.text
    assert draft.json()["step_count"] == 2
    assert (await client.post(revisions, headers=receipt, json=payload)).json() == draft.json()
    detail = revisions + "/" + draft.json()["id"]
    rows = await client.get(detail + "/steps?sort=sequence", headers=current)
    assert rows.status_code == 200, rows.text
    steps = rows.json()["items"]
    assert [step["sequence"] for step in steps] == [1, 2]
    assert steps[0]["run_minutes"] == "0.1250"
    changes = []
    for sequence, step in enumerate(reversed(steps), 1):
        changes.append(
            {
                key: value
                for key, value in {**step, "sequence": sequence}.items()
                if key != "revision_id"
            }
        )
    changed = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 1, "steps": changes, "change_reason": "Reviewed ordering"},
    )
    assert changed.status_code == 200, changed.text
    reordered = (await client.get(detail + "/steps?sort=sequence", headers=current)).json()["items"]
    assert [step["id"] for step in reordered] == [step["id"] for step in reversed(steps)]
    published = await client.post(
        detail + "/publish", headers=command_headers(current), json={"expected_version": 2}
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "PUBLISHED"
    assert (
        await client.patch(
            detail, headers=command_headers(current), json={"expected_version": 3, "steps": []}
        )
    ).status_code == 409
    retired_operation = await client.post(
        operation_path + "/retire", headers=command_headers(current), json={"expected_version": 2}
    )
    assert retired_operation.status_code == 200, retired_operation.text
    assert (await client.get(root + "/operation-options", headers=current)).json()["items"] == []
    historical = await client.get(root + "/operation-references/" + operation, headers=current)
    assert historical.status_code == 200 and historical.json()["status"] == "RETIRED"
    assert (
        await client.post(revisions, headers=command_headers(current), json=payload)
    ).status_code == 422
    retired = await client.post(
        detail + "/retire", headers=command_headers(current), json={"expected_version": 3}
    )
    assert retired.status_code == 200 and retired.json()["status"] == "RETIRED"
    assert (await client.get(detail + "/steps?sort=sequence", headers=current)).json()[
        "items"
    ] == reordered


async def test_route_step_input_validation_and_reference_authority(client, factory, tenant_a):
    company, current = await setup_route_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/manufacturing-routes"
    master = await client.post(
        root, headers=command_headers(current), json={"code": "ROUTE", "name": "Route"}
    )
    revisions = root + "/" + master.json()["id"] + "/revisions"
    base = {"specification": "Sequential definition", "change_reason": "Initial"}
    for field, value in (
        ("run_minutes", 0.1),
        ("run_minutes", "-1"),
        ("setup_minutes", "0.00001"),
        ("quantity_basis", "0"),
        ("time_basis", "PARALLEL"),
        ("sequence", 2),
    ):
        body = {
            **base,
            "steps": [{"sequence": 1, "operation_revision_id": str(uuid7()), field: value}],
        }
        assert (
            await client.post(revisions, headers=command_headers(current), json=body)
        ).status_code == 422
    missing = {**base, "steps": [{"sequence": 1, "operation_revision_id": str(uuid7())}]}
    assert (
        await client.post(revisions, headers=command_headers(current), json=missing)
    ).status_code == 404
    reader = headers(
        company, tenant=tenant_a, user=uuid7(), permission=["manufacturing_route.read"]
    )
    assert (await client.get(root + "/operation-options", headers=reader)).status_code == 403
    assert (
        await client.post(revisions, headers=command_headers(reader), json=base)
    ).status_code == 403


async def test_route_directory_and_empty_draft_cannot_publish(client, factory, tenant_a):
    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "manufacturing_route.read",
            "manufacturing_route.manage",
            "manufacturing_route.publish",
        ],
    )
    root = f"/v1/companies/{company}/manufacturing-routes"
    assert (await client.get(root, headers=current)).status_code == 200
    created = await client.post(
        root, headers=command_headers(current), json={"code": "CUT-PACK", "name": "Cut and pack"}
    )
    assert created.status_code == 201, created.text
    revisions = root + "/" + created.json()["id"] + "/revisions"
    draft = await client.post(
        revisions,
        headers=command_headers(current),
        json={
            "specification": "Sequential cut and pack route",
            "change_reason": "Initial route",
            "steps": [],
        },
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["step_count"] == 0
    result = await client.post(
        revisions + "/" + draft.json()["id"] + "/publish",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert result.status_code == 422, result.text


async def test_route_field_denial_precedes_reference_lookup_and_is_atomic(
    client, factory, tenant_a
):
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    await setup_source(factory, tenant_a, company, user, facts=facts)
    current = headers(
        company,
        tenant=tenant_a,
        user=user,
        permission=[
            "manufacturing_route.read",
            "manufacturing_route.manage",
            "manufacturing_operation.read",
        ],
    )
    root = f"/v1/companies/{company}/manufacturing-routes"
    parent = await client.post(
        root, headers=command_headers(current), json={"code": "SECURE", "name": "Secure route"}
    )
    assert parent.status_code == 201, parent.text
    source = next(row for row in facts if row.kind == "field_policy")
    deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": "catalog.manufacturing_route_step",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "operation_revision_id",
            "access": "write",
            "condition": None,
        },
    )
    await setup_source(factory, tenant_a, company, user, version=3, facts=(*facts, deny))
    revisions = root + "/" + parent.json()["id"] + "/revisions"
    result = await client.post(
        revisions,
        headers=command_headers(current),
        json={
            "specification": "Secure route",
            "change_reason": "Initial",
            "steps": [{"sequence": 1, "operation_revision_id": str(uuid7())}],
        },
    )
    assert result.status_code == 403, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ManufacturingRouteRevision.id))) == 0
            assert await db.scalar(select(func.count(ManufacturingRouteStep.id))) == 0
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == 1
            assert await db.scalar(select(func.count(Outbox.id))) == 1


async def test_route_cannot_pin_another_tenants_operation_or_browse_its_steps(
    client, factory, tenant_a, tenant_b
):
    company, current = await setup_route_actor(factory, tenant_a)
    foreign_company, foreign_actor = await setup_route_actor(factory, tenant_b)
    operation, _ = await published_operation(client, foreign_company, foreign_actor)
    root = f"/v1/companies/{company}/manufacturing-routes"
    parent = await client.post(
        root, headers=command_headers(current), json={"code": "LOCAL", "name": "Local route"}
    )
    revisions = root + "/" + parent.json()["id"] + "/revisions"
    result = await client.post(
        revisions,
        headers=command_headers(current),
        json={
            "specification": "Local route",
            "change_reason": "Initial",
            "steps": [{"sequence": 1, "operation_revision_id": operation}],
        },
    )
    assert result.status_code == 404, result.text
    foreign = f"/v1/companies/{foreign_company}/manufacturing-routes"
    assert (await client.get(foreign + "/operation-options", headers=current)).status_code == 403
    assert (
        await client.get(root + "/operation-references/" + operation, headers=current)
    ).status_code == 404
