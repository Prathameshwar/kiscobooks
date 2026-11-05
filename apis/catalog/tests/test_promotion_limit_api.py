"""Promotion limit definitions preserve exact caps and never claim applied quotas."""

from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers


async def setup_limit_actor(factory, tenant, *, enabled=True):
    company, user = uuid7(), uuid7()
    facts = tuple(
        SnapshotRecord(kind=row.kind, id=row.id, data={**row.data, "entity_type": "catalog.item"})
        if row.kind == "field_policy"
        else row
        for row in all_facts(company, user)
    )
    if enabled:
        facts += (
            SnapshotRecord(
                kind="feature",
                id=uuid7(),
                data={
                    "company_id": str(company),
                    "feature_key": "sales_promotions",
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
        permission=[
            "promotion_limit.read",
            "promotion_limit.manage",
            "promotion_limit.publish",
            "unit.read",
            "unit.manage",
        ],
    )
    return company, user, facts, current


def count_identity():
    return {
        "code": "USES",
        "name": "Program total uses",
        "scope_kind": "PROGRAM",
        "metric": "TOTAL_USES",
        "period_basis": "LIFETIME",
        "timezone": "Asia/Kolkata",
    }


async def test_limit_exact_counts_publication_replay_and_stable_identity(client, factory, tenant_a):
    company, _, _, current = await setup_limit_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/promotion-limits"
    created = await client.post(root, headers=command_headers(current), json=count_identity())
    assert created.status_code == 201, created.text
    parent = root + "/" + created.json()["id"]
    body = {"maximum_count": str(2**63 - 1), "change_reason": "Initial reviewed cap"}
    command = command_headers(current)
    draft = await client.post(parent + "/revisions", headers=command, json=body)
    assert draft.status_code == 201, draft.text
    assert draft.json()["maximum_count"] == str(2**63 - 1)
    assert draft.json()["complete"] and draft.json()["operational_ready"] is False
    replay = await client.post(parent + "/revisions", headers=command, json=body)
    assert (
        replay.status_code == 201 and replay.headers["Idempotency-Replayed"] == "true"
    ), replay.text
    path = parent + "/revisions/" + draft.json()["id"]
    changed = await client.patch(
        path,
        headers=command_headers(current),
        json={
            "maximum_count": "100",
            "change_reason": "Reviewed proposed cap",
            "expected_version": 1,
        },
    )
    assert changed.status_code == 200 and changed.json()["row_version"] == 2, changed.text
    published = await client.post(
        path + "/publish", headers=command_headers(current), json={"expected_version": 2}
    )
    assert (
        published.status_code == 200 and published.json()["published_at"] is not None
    ), published.text
    assert published.json()["maximum_count"] == "100" and not published.json()["operational_ready"]
    assert (
        published.json()["published_source_version"] >= 1
        and published.json()["publication_generation"] >= 1
    )
    blocked = await client.patch(
        path,
        headers=command_headers(current),
        json={
            "maximum_count": "50",
            "change_reason": "Cannot rewrite published history",
            "expected_version": 3,
        },
    )
    assert blocked.status_code == 409, blocked.text
    next_revision = await client.post(
        parent + "/revisions",
        headers=command_headers(current),
        json={"maximum_count": "50", "change_reason": "Propose a replacement cap"},
    )
    assert (
        next_revision.status_code == 201 and next_revision.json()["revision"] == 2
    ), next_revision.text
    assert next_revision.json()["definition_id"] == created.json()["id"]
    frozen_identity = await client.patch(
        parent,
        headers=command_headers(current),
        json={"expected_version": 1, "scope_kind": "CAMPAIGN"},
    )
    assert frozen_identity.status_code == 409, frozen_identity.text
    for order in ("-id", "revision,id", "-revision,id"):
        history = await client.get(
            parent + "/revisions",
            headers=current,
            params={"sort": order, "published": "true", "limit": 1},
        )
        assert history.status_code == 200 and len(history.json()["items"]) == 1, history.text
    assert (await client.get(path)).status_code == 401


async def test_limit_caps_are_typed_and_feature_off_preserves_history(client, factory, tenant_a):
    company, user, facts, current = await setup_limit_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/promotion-limits"
    created = await client.post(root, headers=command_headers(current), json=count_identity())
    assert created.status_code == 201, created.text
    parent = root + "/" + created.json()["id"]
    for value in (1.5, 1, "0", str(2**63), "1.0000"):
        rejected = await client.post(
            parent + "/revisions",
            headers=command_headers(current),
            json={"maximum_count": value, "change_reason": "Invalid count"},
        )
        assert rejected.status_code == 422, rejected.text
    mismatch = await client.post(
        parent + "/revisions",
        headers=command_headers(current),
        json={"maximum_amount": "100.0000", "change_reason": "Wrong metric"},
    )
    assert mismatch.status_code == 422, mismatch.text
    disabled = tuple(
        row
        for row in facts
        if not (row.kind == "feature" and row.data["feature_key"] == "sales_promotions")
    )
    await setup_source(factory, tenant_a, company, user, version=3, facts=disabled)
    assert (await client.get(parent, headers=current)).status_code == 200
    assert (await client.get(parent + "/revisions", headers=current)).status_code == 200
    denied = await client.post(
        parent + "/revisions",
        headers=command_headers(current),
        json={"maximum_count": "1", "change_reason": "Feature disabled"},
    )
    assert denied.status_code == 409, denied.text


async def test_limit_scope_field_denial_and_atomic_rollback(client, factory, tenant_a, tenant_b):
    company, user, facts, current = await setup_limit_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/promotion-limits"
    created = await client.post(root, headers=command_headers(current), json=count_identity())
    assert created.status_code == 201, created.text
    parent = root + "/" + created.json()["id"]
    denied = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **next(row for row in facts if row.kind == "field_policy").data,
            "entity_type": "catalog.promotion_limit_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "maximum_count",
            "access": "write",
            "effect": "deny",
            "condition": None,
        },
    )
    await setup_source(factory, tenant_a, company, user, version=3, facts=(*facts, denied))
    rejected = await client.post(
        parent + "/revisions",
        headers=command_headers(current),
        json={"maximum_count": "10", "change_reason": "Denied cap"},
    )
    assert rejected.status_code == 403, rejected.text
    history = await client.get(parent + "/revisions", headers=current)
    assert history.status_code == 200 and not history.json()["items"]
    other, _, _, other_headers = await setup_limit_actor(factory, tenant_b)
    assert (
        await client.get(parent.replace(str(company), str(other)), headers=other_headers)
    ).status_code == 404
    assert (
        await client.get(parent.replace(str(company), str(uuid7())), headers=current)
    ).status_code == 403
    unpermitted = headers(company, tenant=tenant_a, user=user, permission="promotion_limit.read")
    assert (
        await client.post(
            root, headers=command_headers(unpermitted), json={**count_identity(), "code": "NO"}
        )
    ).status_code == 403


async def test_limit_budget_and_reward_caps_follow_their_native_measure(client, factory, tenant_a):
    company, _, _, current = await setup_limit_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/promotion-limits"
    budget = await client.post(
        root,
        headers=command_headers(current),
        json={
            **count_identity(),
            "code": "BUDGET",
            "scope_kind": "CAMPAIGN",
            "metric": "BUDGET",
            "currency": "INR",
        },
    )
    assert budget.status_code == 201, budget.text
    cap = await client.post(
        root + "/" + budget.json()["id"] + "/revisions",
        headers=command_headers(current),
        json={"maximum_amount": "1000.2500", "change_reason": "Exact net benefit budget"},
    )
    assert cap.status_code == 201 and cap.json()["maximum_amount"] == "1000.2500", cap.text
    unit = await client.post(
        f"/v1/companies/{company}/units",
        headers=command_headers(current),
        json={
            "code": "CAP-EA",
            "name": "Physical pieces",
            "symbol": "ea",
            "dimension": "COUNT",
            "decimal_places": 0,
            "quantity_increment": "1",
        },
    )
    assert unit.status_code == 201, unit.text
    reward = await client.post(
        root,
        headers=command_headers(current),
        json={
            **count_identity(),
            "code": "REWARD",
            "scope_kind": "PROMOTION",
            "metric": "REWARD_UNITS",
            "unit_id": unit.json()["id"],
        },
    )
    assert reward.status_code == 201, reward.text
    path = root + "/" + reward.json()["id"] + "/revisions"
    good = await client.post(
        path,
        headers=command_headers(current),
        json={"maximum_quantity": "25.0000", "change_reason": "Exact physical reward cap"},
    )
    assert good.status_code == 201 and good.json()["maximum_quantity"] == "25.0000", good.text
    invalid = await client.post(
        path,
        headers=command_headers(current),
        json={"maximum_quantity": "1.5000", "change_reason": "Off the physical unit grid"},
    )
    assert invalid.status_code == 422, invalid.text


async def test_limit_publication_rechecks_all_reviewed_cap_fields(client, factory, tenant_a):
    company, user, facts, current = await setup_limit_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/promotion-limits"
    parent = await client.post(root, headers=command_headers(current), json=count_identity())
    assert parent.status_code == 201, parent.text
    path = root + "/" + parent.json()["id"] + "/revisions"
    draft = await client.post(
        path,
        headers=command_headers(current),
        json={"maximum_count": "10", "change_reason": "Reviewed cap"},
    )
    assert draft.status_code == 201, draft.text
    denied = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **next(row for row in facts if row.kind == "field_policy").data,
            "entity_type": "catalog.promotion_limit_revision",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "maximum_count",
            "access": "write",
            "effect": "deny",
            "condition": None,
        },
    )
    await setup_source(factory, tenant_a, company, user, version=3, facts=(*facts, denied))
    published = await client.post(
        path + "/" + draft.json()["id"] + "/publish",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert published.status_code == 403, published.text


async def test_limit_native_field_metadata_matches_count_strings_and_publication(
    client, factory, tenant_a
):
    import json
    from pathlib import Path

    company, _, _, current = await setup_limit_actor(factory, tenant_a)
    captured = {}
    for entity in ("promotion_limit_definition", "promotion_limit_revision"):
        for operation in (
            "read",
            "create",
            "update",
            *(("publish",) if entity.endswith("revision") else ()),
        ):
            response = await client.get(
                f"/v1/companies/{company}/entities/catalog.{entity}/field-set",
                headers=current,
                params={} if operation == "read" else {"operation": operation},
            )
            assert response.status_code == 200, response.text
            captured[entity + ":" + operation] = response.json()["fields"]
    fields = {field["key"]: field for field in captured["promotion_limit_revision:publish"]}
    assert all(field["writable"] for field in fields.values())
    assert fields["maximum_count"]["control"]["kind"] == "text"
    normal = {field["key"]: field for field in captured["promotion_limit_revision:update"]}
    assert not normal["published_at"]["writable"] and normal["maximum_count"]["writable"]
    target = Path(__file__).resolve().parents[3] / ".tools/extension-masters/limit-fields.json"
    target.write_text(json.dumps(captured, indent=2), encoding="utf-8")


async def test_renaming_a_limit_does_not_require_dependency_authoring_access(client, factory, tenant_a):
    company, user, _, current = await setup_limit_actor(factory, tenant_a)
    unit = await client.post(f"/v1/companies/{company}/units", headers=command_headers(current), json={"code": "NAME-EA", "name": "Pieces", "symbol": "ea", "dimension": "COUNT", "decimal_places": 0, "quantity_increment": "1"})
    assert unit.status_code == 201, unit.text
    root = f"/v1/companies/{company}/promotion-limits"
    created = await client.post(root, headers=command_headers(current), json={**count_identity(), "metric": "REWARD_UNITS", "unit_id": unit.json()["id"]})
    assert created.status_code == 201, created.text
    restricted = headers(company, tenant=tenant_a, user=user, permission=["promotion_limit.read", "promotion_limit.manage"])
    renamed = await client.patch(root + "/" + created.json()["id"], headers=command_headers(restricted), json={"expected_version": 1, "name": "Renamed reward limit"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Renamed reward limit", renamed.text
