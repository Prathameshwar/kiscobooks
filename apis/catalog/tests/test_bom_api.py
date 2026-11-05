"""Native BOM draft routes enforce capabilities, field authority, scope and replay."""

import json
from pathlib import Path

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select

from catalog.models import BomDraft, IdempotencyKey, Outbox
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def setup_bom_actor(factory, tenant, *, enabled=True):
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    if enabled:
        facts += (
            SnapshotRecord(
                kind="feature",
                id=uuid7(),
                data={
                    "company_id": str(company),
                    "feature_key": "bom_definitions",
                    "is_enabled": True,
                    "locked_at": None,
                },
            ),
        )
    await setup_source(factory, tenant, company, user, facts=facts)
    current = headers(
        company,
        tenant=tenant,
        user=user,
        permission=["bom.read", "bom.manage", "bom.publish", "bom.assign", "item.read"],
    )
    return company, user, facts, current


async def test_bom_native_metadata_covers_header_lines_and_publication_authority(
    client, factory, tenant_a
):
    company, _, _, current = await setup_bom_actor(factory, tenant_a)
    captured = {}
    for entity in (
        "bom",
        "bom_draft",
        "bom_revision",
        "bom_component",
        "bom_output",
        "bom_assignment",
    ):
        for operation in (
            "read",
            "create",
            "update",
            *(("publish",) if entity not in {"bom", "bom_assignment"} else ()),
        ):
            response = await client.get(
                f"/v1/companies/{company}/entities/catalog.{entity}/field-set",
                headers=current,
                params={} if operation == "read" else {"operation": operation},
            )
            assert response.status_code == 200, response.text
            captured[entity + ":" + operation] = response.json()["fields"]
    revision = {field["key"]: field for field in captured["bom_revision:publish"]}
    assert revision["dependency_manifest"]["writable"] and revision["source_version"]["writable"]
    assert revision["row_version"]["writable"]
    draft = {field["key"]: field for field in captured["bom_draft:create"]}
    assert not draft["status"]["writable"] and draft["bom_id"]["writable"]
    component = {field["key"]: field for field in captured["bom_component:create"]}
    assert component["quantity"]["control"]["kind"] == "decimal"
    assert component["unit_revision_id"]["control"]["reference_source"] == "bom-unit-revisions"
    target = Path(__file__).resolve().parents[3] / ".tools/extension-masters/bom-fields.json"
    target.write_text(json.dumps(captured, indent=2), encoding="utf-8")


async def test_bom_capability_defaults_off_and_metadata_follows_it(client, factory, tenant_a):
    company, _, _, current = await setup_bom_actor(factory, tenant_a, enabled=False)
    root = f"/v1/companies/{company}/boms"
    context = await client.get(root + "/authoring-context", headers=current)
    assert context.status_code == 200, context.text
    assert context.json()["enabled"] is False
    assert context.json()["operational_ready"] is False
    metadata = await client.get(
        f"/v1/companies/{company}/entities/catalog.bom/field-set",
        headers=current,
        params={"operation": "create"},
    )
    assert metadata.status_code == 200, metadata.text
    assert not any(field["writable"] for field in metadata.json()["fields"])
    denied = await client.post(
        root, headers=command_headers(current), json={"code": "BOM", "name": "Recipe"}
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["feature"] == "bom_definitions"
    read = await client.get(root, headers=current)
    assert read.status_code == 200 and read.json()["items"] == []


async def test_bom_empty_draft_lifecycle_replay_and_scope(client, factory, tenant_a, tenant_b):
    company, _, _, current = await setup_bom_actor(factory, tenant_a)
    other_company, _, _, foreign = await setup_bom_actor(factory, tenant_b)
    same_tenant_company, _, _, same_tenant_actor = await setup_bom_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/boms"
    parent = await client.post(
        root, headers=command_headers(current), json={"code": "BOM", "name": "Recipe"}
    )
    assert parent.status_code == 201, parent.text
    path = root + "/" + parent.json()["id"]
    body = {
        "specification": "Test recipe",
        "change_reason": "Initial draft",
        "definition_date": "2090-01-01",
        "components": [],
        "outputs": [],
    }
    key = command_headers(current)
    draft = await client.post(path + "/drafts", headers=key, json=body)
    assert draft.status_code == 201, draft.text
    assert draft.json()["status"] == "DRAFT"
    code_change = await client.patch(
        path, headers=command_headers(current), json={"expected_version": 1, "code": "RENAMED"}
    )
    assert code_change.status_code == 409, code_change.text
    replay = await client.post(path + "/drafts", headers=key, json=body)
    assert replay.status_code == 201 and replay.json()["id"] == draft.json()["id"], replay.text
    revision = path + "/drafts/" + draft.json()["id"]
    denied = await client.post(
        revision + "/publish", headers=command_headers(current), json={"expected_version": 1}
    )
    assert denied.status_code == 409, denied.text
    updated = await client.patch(
        revision,
        headers=command_headers(current),
        json={**body, "specification": "Updated recipe", "expected_version": 1},
    )
    assert updated.status_code == 200 and updated.json()["row_version"] == 2, updated.text
    stale = await client.patch(
        revision, headers=command_headers(current), json={**body, "expected_version": 1}
    )
    assert stale.status_code == 409, stale.text
    history = await client.get(path + "/drafts", headers=current, params={"limit": 1})
    assert history.status_code == 200 and len(history.json()["items"]) == 1, history.text
    assert "specification" not in history.json()["items"][0]
    for child in ("components", "outputs"):
        response = await client.get(revision + "/" + child, headers=current)
        assert response.status_code == 200 and response.json()["items"] == [], response.text
    wrong_company = revision.replace(str(company), str(other_company))
    assert (await client.get(wrong_company, headers=foreign)).status_code == 404
    assert (
        await client.get(
            revision.replace(str(company), str(same_tenant_company)), headers=same_tenant_actor
        )
    ).status_code == 403
    assert (await client.get(revision)).status_code == 401
    unpermitted = headers(company, tenant=tenant_a, permission=["company.read"])
    assert (await client.get(revision, headers=unpermitted)).status_code == 403
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(BomDraft.id))) == 1


async def test_bom_component_field_denial_precedes_reference_lookup_and_rolls_back(
    client, factory, tenant_a
):
    company, user, facts, current = await setup_bom_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/boms"
    parent = await client.post(
        root, headers=command_headers(current), json={"code": "SECURE", "name": "Recipe"}
    )
    assert parent.status_code == 201, parent.text
    source = next(row for row in facts if row.kind == "field_policy")
    denial = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": "catalog.bom_component",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "item_id",
            "access": "write",
            "condition": None,
        },
    )
    await setup_source(factory, tenant_a, company, user, version=3, facts=(*facts, denial))
    response = await client.post(
        root + "/" + parent.json()["id"] + "/drafts",
        headers=command_headers(current),
        json={
            "specification": "Protected recipe",
            "change_reason": "Initial draft",
            "definition_date": "2090-01-01",
            "components": [
                {"line_key": str(uuid7()), "sequence": 1, "item_id": str(uuid7()), "quantity": "1"}
            ],
            "outputs": [],
        },
    )
    assert response.status_code == 403, response.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(BomDraft.id))) == 0
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == 1
            assert await db.scalar(select(func.count(Outbox.id))) == 1


async def test_bom_publishes_exact_physical_copy_previews_and_assigns_dates(
    client, factory, tenant_a
):
    from billing_platform.permissions import CATALOG_PERMISSIONS

    from tests.bom_factories import physical_bom_sources

    company, ids = await physical_bom_sources(factory, tenant_a)
    current = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}/boms"
    parent = await client.post(
        root, headers=command_headers(current), json={"code": "MAKE", "name": "Make finished goods"}
    )
    assert parent.status_code == 201, parent.text
    path = root + "/" + parent.json()["id"]
    body = {
        "specification": "Single-level physical recipe",
        "change_reason": "Reviewed basis",
        "definition_date": "2090-01-01",
        "components": [
            {
                "line_key": str(uuid7()),
                "sequence": 1,
                "item_id": str(ids["item"]),
                "unit_revision_id": str(ids["item_unit_revision"]),
                "quantity": "20",
                "basis": "GROSS_INPUT",
                "loss_fraction": "0",
                "timing": "PER_BASIS",
            }
        ],
        "outputs": [
            {
                "line_key": str(uuid7()),
                "sequence": 1,
                "item_id": str(ids["output_item"]),
                "unit_revision_id": str(ids["output_unit_revision"]),
                "nominal_quantity": "10",
                "yield_fraction": "1",
                "role": "PRIMARY",
            }
        ],
    }
    created = await client.post(path + "/drafts", headers=command_headers(current), json=body)
    assert created.status_code == 201, created.text
    draft = path + "/drafts/" + created.json()["id"]
    preview = await client.post(
        draft + "/preview", headers=current, json={"requested_good_quantity": "30"}
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["requirements"][0]["required_quantity"] == "60.0000"
    assert preview.json()["operational_ready"] is False
    published = await client.post(
        draft + "/publish", headers=command_headers(current), json={"expected_version": 1}
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "PUBLISHED"
    revision_id = published.json()["published_revision_id"]
    revision = path + "/revisions/" + revision_id
    detail = await client.get(revision, headers=current)
    assert detail.status_code == 200 and len(detail.json()["content_sha256"]) == 64, detail.text
    copied = await client.get(revision + "/components", headers=current)
    assert (
        copied.status_code == 200
        and copied.json()["items"][0]["line_key"] == body["components"][0]["line_key"]
    ), copied.text
    blocked = await client.patch(
        draft, headers=command_headers(current), json={**body, "expected_version": 2}
    )
    assert blocked.status_code == 409, blocked.text
    assignments = f"/v1/companies/{company}/bom-assignments"
    interval = {
        "bom_revision_id": revision_id,
        "item_id": str(ids["output_item"]),
        "valid_from": "2090-01-01",
        "valid_to": "2090-01-31",
        "change_reason": "Default recipe",
    }
    assigned = await client.post(assignments, headers=command_headers(current), json=interval)
    assert assigned.status_code == 201, assigned.text
    overlap = await client.post(
        assignments, headers=command_headers(current), json={**interval, "valid_from": "2090-01-31"}
    )
    assert overlap.status_code == 409, overlap.text
    resolved = await client.get(
        assignments + "/resolve",
        headers=current,
        params={"item_id": str(ids["output_item"]), "as_of": "2090-01-31"},
    )
    assert (
        resolved.status_code == 200 and resolved.json()["bom_revision_id"] == revision_id
    ), resolved.text
    assert resolved.json()["operational_ready"] is False
    retired = await client.post(
        revision + "/retire", headers=command_headers(current), json={"expected_version": 1}
    )
    assert retired.status_code == 200 and retired.json()["status"] == "RETIRED", retired.text
    historical = await client.get(revision + "/components", headers=current)
    assert historical.status_code == 200, historical.text
    blocked_selection = await client.get(
        assignments + "/resolve",
        headers=current,
        params={"item_id": str(ids["output_item"]), "as_of": "2090-01-31"},
    )
    assert blocked_selection.status_code == 409, blocked_selection.text


async def test_bom_lists_accept_the_console_descending_keyset_order(client, factory, tenant_a):
    company, _, _, current = await setup_bom_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/boms"
    parent = await client.post(
        root, headers=command_headers(current), json={"code": "SORT", "name": "Sorted recipe"}
    )
    assert parent.status_code == 201, parent.text
    path = root + "/" + parent.json()["id"]
    draft = await client.post(
        path + "/drafts",
        headers=command_headers(current),
        json={
            "specification": "Initial recipe",
            "change_reason": "Initial review",
            "definition_date": "2090-01-01",
        },
    )
    assert draft.status_code == 201, draft.text
    for target, order in (
        (path + "/drafts", "-id"),
        (path + "/revisions", "-id"),
        (f"/v1/companies/{company}/bom-assignments", "-id"),
        (path + "/drafts/" + draft.json()["id"] + "/components", "-sequence,id"),
        (path + "/drafts/" + draft.json()["id"] + "/outputs", "-id"),
    ):
        response = await client.get(target, headers=current, params={"sort": order, "limit": 25})
        assert response.status_code == 200, response.text
