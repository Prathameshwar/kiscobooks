"""Native stack policy authoring preserves scoped, immutable publication facts."""

from billing_platform.db import tenant_scope
from sqlalchemy import select

from catalog.models.promotion_authoring import PromotionStackDraft, PromotionStackDraftGroup
from tests.product_definition_factories import seed_definitions


async def test_stack_drafts_and_groups_are_tenant_isolated(factory, tenant_a, tenant_b):
    companies = {}
    for tenant in (tenant_a, tenant_b):
        company, _ = await seed_definitions(factory, tenant)
        companies[tenant] = company
        with tenant_scope(tenant):
            async with factory.begin() as db:
                draft = PromotionStackDraft(
                    tenant_id=tenant,
                    company_id=company,
                    code="STACK",
                    maximum_applied=2,
                    change_reason="Initial policy",
                    group_count=1,
                    permission_count=0,
                )
                db.add(draft)
                await db.flush()
                db.add(
                    PromotionStackDraftGroup(
                        tenant_id=tenant,
                        company_id=company,
                        draft_id=draft.id,
                        position=0,
                        stage="PRODUCT_SCHEME",
                        selection="PRIORITY",
                        changes_basket=True,
                    )
                )
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert [row.company_id for row in await db.scalars(select(PromotionStackDraft))] == [
                companies[tenant_a]
            ]
            assert [
                row.company_id for row in await db.scalars(select(PromotionStackDraftGroup))
            ] == [companies[tenant_a]]


async def stack_actor(factory, tenant, *, enabled=True):
    from billing_platform.ids import uuid7
    from billing_platform.snapshots import SnapshotRecord
    from tests.source_factories import all_facts
    from tests.test_api import headers
    from tests.test_classification_api import setup_source

    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
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
    return (
        company,
        user,
        facts,
        headers(
            company,
            tenant=tenant,
            user=user,
            permission=[
                "promotion_stack_policy.read",
                "promotion_stack_policy.manage",
                "promotion_stack_policy.publish",
            ],
        ),
    )


async def test_stack_authoring_reorder_publish_replay_and_immutable_history(
    client, factory, tenant_a
):
    from billing_platform.ids import uuid7
    from tests.test_commercial_api import command_headers

    company, _, _, current = await stack_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/promotion-stack-policies"
    first, second = str(uuid7()), str(uuid7())
    body = {
        "code": "STACK",
        "change_reason": "Explicit scheme then manual policy",
        "maximum_applied": 2,
        "groups": [
            {
                "group_id": first,
                "stage": "PRODUCT_SCHEME",
                "selection": "PRIORITY",
                "changes_basket": True,
            },
            {
                "group_id": second,
                "stage": "MANUAL",
                "selection": "PRIORITY",
                "changes_basket": False,
            },
        ],
        "permissions": [
            {"earlier_group_id": first, "later_group_id": second, "include_reward_units": False}
        ],
    }
    command = command_headers(current)
    created = await client.post(root + "/drafts", headers=command, json=body)
    assert created.status_code == 201, created.text
    replayed = await client.post(root + "/drafts", headers=command, json=body)
    assert (
        replayed.status_code == 201 and replayed.headers["Idempotency-Replayed"] == "true"
    ), replayed.text
    assert replayed.json()["id"] == created.json()["id"]
    path = root + "/drafts/" + created.json()["id"]
    assert created.json()["complete"] and not created.json()["operational_ready"]
    stored = {
        key: created.json()[key]
        for key in ("code", "change_reason", "maximum_applied", "groups", "permissions")
    }
    updated = await client.patch(
        path,
        headers=command_headers(current),
        json={**stored, "change_reason": "Reviewed complete policy", "expected_version": 1},
    )
    assert (
        updated.status_code == 200 and updated.json()["groups"] == created.json()["groups"]
    ), updated.text
    published = await client.post(
        path + "/publish", headers=command_headers(current), json={"expected_version": 2}
    )
    assert (
        published.status_code == 200 and published.json()["status"] == "PUBLISHED"
    ), published.text
    revision_id = published.json()["published_policy_id"]
    history = await client.get(root + "/revisions/" + revision_id, headers=current)
    assert history.status_code == 200 and history.json()["version"] == 1, history.text
    assert len(history.json()["source_sha256"]) == 64
    assert (
        history.json()["permissions"][0]["earlier_group_id"]
        == history.json()["groups"][0]["group_id"]
    )
    assert (
        history.json()["permissions"][0]["later_group_id"]
        == history.json()["groups"][1]["group_id"]
    )
    blocked = await client.patch(
        path, headers=command_headers(current), json={**stored, "expected_version": 3}
    )
    assert blocked.status_code == 409, blocked.text
    for collection in ("drafts", "revisions"):
        page = await client.get(
            root + "/" + collection, headers=current, params={"sort": "-id", "limit": 1}
        )
        assert page.status_code == 200 and len(page.json()["items"]) == 1, page.text
    assert (await client.get(root + "/revisions/" + revision_id)).status_code == 401


async def test_stack_feature_off_and_empty_publication_are_explicit(client, factory, tenant_a):
    from tests.test_commercial_api import command_headers

    company, _, _, current = await stack_actor(factory, tenant_a, enabled=False)
    root = f"/v1/companies/{company}/promotion-stack-policies"
    context = await client.get(root + "/authoring-context", headers=current)
    assert context.status_code == 200 and not context.json()["enabled"]
    body = {"code": "EMPTY", "change_reason": "Initial draft", "maximum_applied": 1}
    response = await client.post(root + "/drafts", headers=command_headers(current), json=body)
    assert response.status_code == 409, response.text
    company, _, _, current = await stack_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/promotion-stack-policies"
    created = await client.post(root + "/drafts", headers=command_headers(current), json=body)
    assert created.status_code == 201, created.text
    rejected = await client.post(
        root + "/drafts/" + created.json()["id"] + "/publish",
        headers=command_headers(current),
        json={"expected_version": 1},
    )
    assert rejected.status_code == 409, rejected.text


async def test_stack_native_metadata_and_protected_complete_collection(client, factory, tenant_a):
    import json
    from pathlib import Path
    from billing_platform.ids import uuid7
    from billing_platform.snapshots import SnapshotRecord
    from tests.test_classification_api import setup_source
    from tests.test_commercial_api import command_headers

    company, user, facts, current = await stack_actor(factory, tenant_a)
    captured = {}
    for entity in (
        "promotion_stack_draft",
        "promotion_stack_draft_group",
        "promotion_stack_draft_permission",
        "promotion_stack_policy",
        "promotion_stack_group",
        "promotion_stack_permission",
    ):
        for operation in ("read", "create", "update", "publish"):
            response = await client.get(
                f"/v1/companies/{company}/entities/catalog.{entity}/field-set",
                headers=current,
                params={} if operation == "read" else {"operation": operation},
            )
            assert response.status_code == 200, response.text
            captured[entity + ":" + operation] = response.json()["fields"]
    target = Path(__file__).resolve().parents[3] / ".tools/extension-masters/stack-fields.json"
    target.write_text(json.dumps(captured, indent=2), encoding="utf-8")
    root = f"/v1/companies/{company}/promotion-stack-policies"
    body = {
        "code": "PROTECTED",
        "change_reason": "Initial",
        "maximum_applied": 1,
        "groups": [
            {
                "group_id": str(uuid7()),
                "stage": "PRODUCT_SCHEME",
                "selection": "PRIORITY",
                "changes_basket": True,
            }
        ],
    }
    created = await client.post(root + "/drafts", headers=command_headers(current), json=body)
    assert created.status_code == 201, created.text
    policy = next(row for row in facts if row.kind == "field_policy")
    denied = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **policy.data,
            "entity_type": "catalog.promotion_stack_draft_group",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "stage",
            "access": "read",
            "condition": None,
        },
    )
    await setup_source(factory, tenant_a, company, user, version=3, facts=(*facts, denied))
    path = root + "/drafts/" + created.json()["id"]
    protected = await client.get(path, headers=current)
    assert protected.status_code == 200 and not protected.json()["complete"], protected.text
    assert "groups" not in protected.json() and "permissions" not in protected.json()
    rejected = await client.post(
        path + "/publish", headers=command_headers(current), json={"expected_version": 1}
    )
    assert rejected.status_code == 403, rejected.text


async def test_stack_scope_bad_input_and_version_checks(client, factory, tenant_a, tenant_b):
    from billing_platform.ids import uuid7
    from tests.test_api import headers
    from tests.test_commercial_api import command_headers

    company, user, _, current = await stack_actor(factory, tenant_a)
    root = f"/v1/companies/{company}/promotion-stack-policies"
    body = {"code": "VERSION", "change_reason": "Initial", "maximum_applied": 1}
    response = await client.post(
        root + "/drafts", headers=command_headers(current), json={**body, "maximum_applied": 1.5}
    )
    assert response.status_code == 422
    response = await client.post(
        root + "/drafts",
        headers=command_headers(
            headers(company, tenant=tenant_a, user=user, permission="promotion_stack_policy.read")
        ),
        json=body,
    )
    assert response.status_code == 403
    created = await client.post(root + "/drafts", headers=command_headers(current), json=body)
    assert created.status_code == 201, created.text
    path = root + "/drafts/" + created.json()["id"]
    assert (
        await client.patch(
            path, headers=command_headers(current), json={**body, "expected_version": 2}
        )
    ).status_code == 409
    assert (
        await client.get(path.replace(str(company), str(uuid7())), headers=current)
    ).status_code == 403
    other_company, _, _, other = await stack_actor(factory, tenant_b)
    assert (
        await client.get(path.replace(str(company), str(other_company)), headers=other)
    ).status_code == 404
