import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import IdempotencyKey, Outbox
from catalog.models.returns import ReturnPolicyCondition, ReturnPolicyRevision
from tests.return_factories import auth
from tests.source_factories import all_facts
from tests.test_commercial_api import command_headers
from tests.test_return_api import setup_policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_return_condition_replacement_publication_and_history(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, _, current, master = await setup_policy(client, factory, tenant_a)
    renamed = await client.patch(
        master, headers=command_headers(current), json={"expected_version": 1, "code": "RETAIL"}
    )
    assert renamed.status_code == 200
    revisions = master + "/revisions"
    payload = {
        "returns_allowed": True,
        "window_days": 30,
        "condition_codes": ["UNUSED", "PROOF_OF_PURCHASE"],
    }
    receipt = command_headers(current)
    draft = await client.post(revisions, headers=receipt, json=payload)
    assert draft.status_code == 201 and draft.json()["condition_count"] == 2, draft.text
    assert (await client.post(revisions, headers=receipt, json=payload)).headers[
        "Idempotency-Replayed"
    ] == "true"
    detail = revisions + "/" + draft.json()["id"]
    children = detail + "/conditions"
    original = (await client.get(children, headers=current)).json()["items"]
    survivors = {row["condition_code"]: row["id"] for row in original}
    noop = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 1, "condition_codes": ["PROOF_OF_PURCHASE", "UNUSED"]},
    )
    assert noop.status_code == 200 and noop.json()["row_version"] == 1
    assert (
        await client.patch(
            master, headers=command_headers(current), json={"expected_version": 2, "code": "CHANGE"}
        )
    ).status_code == 409
    changed = await client.patch(
        detail,
        headers=command_headers(current),
        json={"expected_version": 1, "condition_codes": ["UNUSED", "UNDAMAGED"], "window_days": 14},
    )
    assert changed.status_code == 200 and changed.json()["row_version"] == 2
    now = (await client.get(children, headers=current)).json()["items"]
    assert {row["condition_code"] for row in now} == {"UNUSED", "UNDAMAGED"}
    assert (
        next(row["id"] for row in now if row["condition_code"] == "UNUSED") == survivors["UNUSED"]
    )
    page = await client.get(
        children, headers=current, params={"limit": 1, "sort": "condition_code"}
    )
    assert page.status_code == 200 and page.json()["page"]["has_more"]
    next_page = await client.get(
        children,
        headers=current,
        params={"limit": 1, "sort": "condition_code", "cursor": page.json()["page"]["next_cursor"]},
    )
    assert (
        next_page.status_code == 200 and next_page.json()["items"][0]["condition_code"] == "UNUSED"
    )
    assert (
        len(
            (
                await client.get(children, headers=current, params={"condition_code": "UNUSED"})
            ).json()["items"]
        )
        == 1
    )
    for query in ({"q": "unused"}, {"condition_code": "REFUND_ALL"}, {"sort": "window_days"}):
        assert (await client.get(children, headers=current, params=query)).status_code == 422
    publication = command_headers(current)
    assert (
        await client.post(detail + "/publish", headers=publication, json={"expected_version": 2})
    ).status_code == 200
    assert (
        await client.post(detail + "/publish", headers=publication, json={"expected_version": 2})
    ).headers["Idempotency-Replayed"] == "true"
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 3, "condition_codes": []},
        )
    ).status_code == 409
    disabled = await client.post(revisions, headers=command_headers(current), json={})
    assert disabled.status_code == 201 and disabled.json()["returns_allowed"] is False
    disabled_path = revisions + "/" + disabled.json()["id"]
    assert (
        await client.post(
            disabled_path + "/publish",
            headers=command_headers(current),
            json={"expected_version": 1},
        )
    ).status_code == 200
    for query in ({"published": "true"}, {"returns_allowed": "true"}):
        response = await client.get(revisions, headers=current, params=query)
        assert response.status_code == 200 and response.json()["items"]
    assert (await client.get(revisions, headers=current, params={"q": "retail"})).status_code == 422
    for invalid in (
        {"returns_allowed": True},
        {"returns_allowed": "false"},
        {"window_days": 0},
        {"returns_allowed": True, "window_days": -1},
        {"returns_allowed": True, "window_days": True},
        {"returns_allowed": True, "window_days": 36501},
        {"condition_codes": ["UNUSED"]},
        {**payload, "condition_codes": ["UNUSED", "UNUSED"]},
        {**payload, "condition_codes": ["CUSTOM_FORMULA"]},
        {**payload, "condition_count": 2},
    ):
        assert (
            await client.post(revisions, headers=command_headers(current), json=invalid)
        ).status_code == 422
    third = await client.post(
        revisions,
        headers=command_headers(current),
        json={"returns_allowed": True, "window_days": 0, "condition_codes": ["UNUSED"]},
    )
    assert third.status_code == 201
    third_path = revisions + "/" + third.json()["id"]
    for field in ("returns_allowed", "condition_codes"):
        assert (
            await client.patch(
                third_path,
                headers=command_headers(current),
                json={"expected_version": 1, field: None},
            )
        ).status_code == 422
    assert (
        await client.patch(
            third_path,
            headers=command_headers(current),
            json={"expected_version": 1, "returns_allowed": False},
        )
    ).status_code == 422
    cleared = await client.patch(
        third_path,
        headers=command_headers(current),
        json={
            "expected_version": 1,
            "returns_allowed": False,
            "window_days": None,
            "condition_codes": [],
        },
    )
    assert cleared.status_code == 200 and cleared.json()["condition_count"] == 0
    assert (await client.get(third_path + "/conditions", headers=current)).json()["items"] == []
    for action, version in (("deactivate", 2), ("activate", 3)):
        assert (
            await client.post(
                master + "/" + action,
                headers=command_headers(current),
                json={"expected_version": version},
            )
        ).status_code == 200
        if action == "deactivate":
            assert (
                await client.post(revisions, headers=command_headers(current), json={})
            ).status_code == 409
            assert (
                await client.patch(
                    third_path, headers=command_headers(current), json={"expected_version": 2}
                )
            ).status_code == 409
    options = await client.get(
        f"/v1/companies/{company}/option-sources/catalog.return_policies", headers=current
    )
    assert options.status_code == 200 and options.json()["items"][0]["code"] == "RETAIL"


async def test_return_child_policy_covers_add_remove_publish_replay_and_browsing(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, _, master = await setup_policy(client, factory, tenant_a)
    facts = all_facts(company, user)
    source = next(row for row in facts if row.kind == "field_policy")
    policy = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **source.data,
            "entity_type": "catalog.return_policy_condition",
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "condition_code",
            "access": "write",
            "condition": {"field": "condition_code", "cmp": "eq", "value": "UNUSED"},
        },
    )
    current = await auth(factory, tenant_a, company, user, version=3, facts=(*facts, policy))
    revisions = master + "/revisions"
    receipt = command_headers(current)
    rejected = {"returns_allowed": True, "window_days": 30, "condition_codes": ["UNUSED"]}
    assert (await client.post(revisions, headers=receipt, json=rejected)).status_code == 403
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ReturnPolicyRevision.id))) == 0
            assert await db.scalar(select(func.count(ReturnPolicyCondition.id))) == 0
            assert await db.scalar(select(func.count(IdempotencyKey.id))) == 1
            assert await db.scalar(select(func.count(Outbox.id))) == 1
    allowed = {**rejected, "condition_codes": ["UNDAMAGED"]}
    draft = await client.post(revisions, headers=receipt, json=allowed)
    assert draft.status_code == 201, draft.text
    # Current conditional policy on a retained receipt is deliberately conservative.
    assert (await client.post(revisions, headers=receipt, json=allowed)).status_code == 403
    detail = revisions + "/" + draft.json()["id"]
    metadata = await client.get(
        f"/v1/companies/{company}/entities/catalog.return_policy_condition/field-set",
        headers=current,
    )
    assert metadata.status_code == 200
    fields = {entry["key"]: entry for entry in metadata.json()["fields"]}
    assert fields["revision_id"]["writable"] is False
    deny = SnapshotRecord(
        kind="field_policy", id=policy.id, data={**policy.data, "condition": None}
    )
    current = await auth(factory, tenant_a, company, user, version=4, facts=(*facts, deny))
    for path, body in (
        (detail, {"expected_version": 1, "condition_codes": []}),
        (detail + "/publish", {"expected_version": 1}),
    ):
        response = await client.request(
            "POST" if path.endswith("publish") else "PATCH",
            path,
            headers=command_headers(current),
            json=body,
        )
        assert response.status_code == 403
    assert (await client.get(detail, headers=current)).json()["row_version"] == 1
    hidden = SnapshotRecord(kind="field_policy", id=policy.id, data={**deny.data, "access": "read"})
    current = await auth(factory, tenant_a, company, user, version=5, facts=(*facts, hidden))
    children = detail + "/conditions"
    page = await client.get(children, headers=current)
    assert page.status_code == 200 and "condition_code" not in page.json()["items"][0]
    for query in ({"condition_code": "UNDAMAGED"}, {"sort": "condition_code"}):
        assert (await client.get(children, headers=current, params=query)).status_code == 403
    for version, entity, field in (
        (6, "catalog.return_policy_condition", "revision_id"),
        (7, "catalog.return_policy_revision", "policy_id"),
    ):
        membership = SnapshotRecord(
            kind="field_policy",
            id=policy.id,
            data={**hidden.data, "entity_type": entity, "field_key": field},
        )
        current = await auth(
            factory, tenant_a, company, user, version=version, facts=(*facts, membership)
        )
        assert (await client.get(children, headers=current)).status_code == 403


async def test_return_restore_cannot_silently_drop_eligibility_conditions(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    _, _, current, master = await setup_policy(client, factory, tenant_a)
    revisions = master + "/revisions"
    receipt = command_headers(current)
    payload = {
        "returns_allowed": True,
        "window_days": 30,
        "condition_codes": ["UNUSED", "UNDAMAGED"],
    }
    draft = await client.post(revisions, headers=receipt, json=payload)
    assert draft.status_code == 201
    detail = revisions + "/" + draft.json()["id"]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            row = await db.scalar(
                select(ReturnPolicyCondition).where(
                    ReturnPolicyCondition.condition_code == "UNUSED"
                )
            )
            assert row is not None
            await db.delete(row)
    assert (await client.get(detail + "/conditions", headers=current)).status_code == 409
    assert (await client.post(revisions, headers=receipt, json=payload)).status_code == 409
    assert (
        await client.patch(
            detail,
            headers=command_headers(current),
            json={"expected_version": 1, "condition_codes": []},
        )
    ).status_code == 409
    assert (
        await client.post(
            detail + "/publish", headers=command_headers(current), json={"expected_version": 1}
        )
    ).status_code == 409
