"""Regression coverage for direct and indirect administrative delegation."""

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.field_access import CompanyAccess
from identity.models import FieldPolicy, Outbox, RolePermission, UserGroupMember
from tests.api_support import actor_headers, grant
from tests.factories import (
    build_company,
    build_field_policy,
    build_role,
    build_role_assignment,
    build_role_permission,
    build_user,
    build_user_group,
    build_user_group_member,
    seed_two_companies,
)


@pytest.mark.parametrize(
    "subject_type,own,scheduled",
    [
        ("user", False, False),
        ("user", True, False),
        ("user_group", True, False),
        ("user_group", False, True),
    ],
)
async def test_used_role_edit_checks_assignment_authority(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    subject_type: str,
    own: bool,
    scheduled: bool,
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    editor, subject, role_id = uuid7(), uuid7(), uuid7()
    if own and subject_type == "user":
        subject = editor
    with tenant_scope(tenant_a):
        session.add(build_role(tenant_id=tenant_a, role_id=role_id, key="review_role"))
        if subject_type == "user":
            session.add(build_user(tenant_id=tenant_a, user_id=subject))
        else:
            session.add(build_user_group(tenant_id=tenant_a, group_id=subject))
            if own:
                session.add(build_user(tenant_id=tenant_a, user_id=editor))
        await session.flush()
        if own and subject_type == "user_group":
            session.add(
                build_user_group_member(tenant_id=tenant_a, user_group_id=subject, user_id=editor)
            )
        session.add(
            build_role_assignment(
                tenant_id=tenant_a,
                role_id=role_id,
                subject_id=subject,
                subject_type=subject_type,
                valid_from=dt.date.today() + dt.timedelta(days=7) if scheduled else dt.date.today(),
            )
        )
        await session.commit()
    permissions = ["role.manage", "invoice.read"] + (["role.assign"] if own else [])
    headers = actor_headers(tenant_id=tenant_a, user_id=editor, grants=[grant(permissions)])
    response = await client.patch(
        f"/v1/roles/{role_id}", headers=headers, json={"permissions": ["invoice.read"]}
    )
    assert response.status_code == 403, response.text
    with tenant_scope(tenant_a):
        assert list(await session.scalars(select(RolePermission))) == []
        assert list(await session.scalars(select(Outbox))) == []
    # Metadata does not change the effective grant and remains separately editable.
    response = await client.patch(
        f"/v1/roles/{role_id}", headers=headers, json={"name": "Reviewed role"}
    )
    assert response.status_code == 200, response.text


async def test_authorized_used_role_edit_records_permission_diff(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    subject, role_id = uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=subject))
        session.add(build_role(tenant_id=tenant_a, role_id=role_id, key="review_role"))
        await session.flush()
        session.add(
            build_role_permission(
                tenant_id=tenant_a, role_id=role_id, permission_key="invoice.read"
            )
        )
        session.add(
            build_role_assignment(
                tenant_id=tenant_a,
                role_id=role_id,
                subject_id=subject,
                scope_type="company",
                scope_id=company,
            )
        )
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[
            grant(["role.manage", "invoice.read", "invoice.create"]),
            grant(["role.assign"], scope_type="company", scope_id=company),
        ],
    )
    response = await client.patch(
        f"/v1/roles/{role_id}",
        headers=headers,
        json={"permissions": ["invoice.read", "invoice.create"]},
    )
    assert response.status_code == 200, response.text
    with tenant_scope(tenant_a):
        event = await session.scalar(select(Outbox).where(Outbox.event_type == "role.updated"))
        assert event is not None
        assert event.payload["changes"]["permissions"] == {
            "from": ["invoice.read"],
            "to": ["invoice.create", "invoice.read"],
        }
        assert event.payload["changes"]["separation_of_duties_warnings"] == {
            "from": [],
            "to": [],
        }


async def test_a_policy_on_an_unregistered_entity_does_not_block_the_role(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    """A row left by a contract revision is skipped, not a 422 on every role edit.

    No such row can be created through the API — the request schema admits exactly
    the registered entities — so it is seeded directly, which is the only way it
    could arise.
    """
    await seed_two_companies(session, tenant_a, tenant_b)
    subject, role_id = uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=subject))
        session.add(build_role(tenant_id=tenant_a, role_id=role_id, key="orphan_policy_role"))
        await session.flush()
        session.add(
            build_role_permission(
                tenant_id=tenant_a, role_id=role_id, permission_key="invoice.read"
            )
        )
        session.add(
            build_field_policy(
                tenant_id=tenant_a,
                subject_type="role",
                subject_id=role_id,
                entity_type="catalog.withdrawn_entity",
                field_key="whatever",
                access="read",
                effect="allow",
            )
        )
        session.add(build_role_assignment(tenant_id=tenant_a, role_id=role_id, subject_id=subject))
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["role.manage", "role.assign", "invoice.read", "invoice.create"])],
    )
    response = await client.patch(
        f"/v1/roles/{role_id}",
        headers=headers,
        json={"permissions": ["invoice.read", "invoice.create"]},
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("operation", ["remove", "deactivate"])
async def test_authorized_group_change_is_allowed_for_a_role_bearing_group(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    operation: str,
) -> None:
    """A group-level change is checked against its assignments, not refused outright.

    The guard had no subject to name for a change that is not one person joining, and
    the placeholder it passed was the 'all' sentinel, which the assignment change
    rejects as a subject. Every removal from a role-bearing group answered 422.
    """
    await seed_two_companies(session, tenant_a, tenant_b)
    editor, subject, group_id, role_id = uuid7(), uuid7(), uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=editor, email="editor@alpha.example"))
        session.add(build_user(tenant_id=tenant_a, user_id=subject, email="subject@alpha.example"))
        session.add(build_user_group(tenant_id=tenant_a, group_id=group_id))
        session.add(build_role(tenant_id=tenant_a, role_id=role_id, key="group_role"))
        await session.flush()
        session.add(
            build_role_permission(
                tenant_id=tenant_a, role_id=role_id, permission_key="invoice.read"
            )
        )
        session.add(
            build_role_assignment(
                tenant_id=tenant_a,
                role_id=role_id,
                subject_id=group_id,
                subject_type="user_group",
            )
        )
        session.add(
            build_user_group_member(tenant_id=tenant_a, user_group_id=group_id, user_id=subject)
        )
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=editor,
        grants=[grant(["group.manage", "role.assign", "invoice.read"])],
    )
    base = f"/v1/user-groups/{group_id}"
    if operation == "remove":
        response = await client.delete(base + f"/members/{subject}", headers=headers)
        assert response.status_code == 204, response.text
        with tenant_scope(tenant_a):
            assert list(await session.scalars(select(UserGroupMember))) == []
    else:
        response = await client.post(
            base + "/lifecycle", headers=headers, json={"is_active": False, "reason": "Retired"}
        )
        assert response.status_code == 200, response.text
        assert not response.json()["is_active"]
    # An editor who cannot grant what the group carries still cannot change it.
    unable = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["group.manage", "role.assign"])]
    )
    refused = await client.post(
        base + "/lifecycle", headers=unable, json={"is_active": True, "reason": "Restore"}
    )
    assert refused.status_code == 403, refused.text


async def test_metadata_only_role_edit_is_audited_and_keeps_its_warnings(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    """Renaming a role is not a no-op event, and it does not resolve its conflicts."""
    await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["role.manage", "role.assign", "audit.read_security"])],
    )
    created = await client.post(
        "/v1/roles",
        headers=headers,
        json={
            "key": "renamed_role",
            "name": "Before",
            "scope_hint": "tenant",
            "permissions": ["role.assign", "audit.read_security"],
        },
    )
    assert created.status_code == 201, created.text
    warnings = created.json()["separation_of_duties_warnings"]
    assert warnings
    updated = await client.patch(
        f"/v1/roles/{created.json()['role']['id']}",
        headers=headers,
        json={"name": "After", "scope_hint": "company"},
    )
    assert updated.status_code == 200, updated.text
    # The pair is still held, so the response must not read as "now resolved".
    assert updated.json()["separation_of_duties_warnings"] == warnings
    with tenant_scope(tenant_a):
        event = await session.scalar(select(Outbox).where(Outbox.event_type == "role.updated"))
    assert event is not None
    assert event.payload["changes"]["scope_hint"] == {"from": "tenant", "to": "company"}
    assert event.payload["changes"]["name"] == {"from": "[redacted]", "to": "[redacted]"}
    assert "permissions" not in event.payload["changes"]


async def test_group_join_resolves_the_editors_authority_once(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One join checks many policies; the editor's own authority is loaded once.

    Each role assignment on the group carries its own field policies, and resolving
    the editor's authority is several queries. Without the request-scoped memo this
    is quadratic in (assignments x policies) on a single POST.
    """
    await seed_two_companies(session, tenant_a, tenant_b)
    editor, subject, group_id = uuid7(), uuid7(), uuid7()
    roles = [uuid7(), uuid7(), uuid7()]
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=editor, email="editor@alpha.example"))
        session.add(build_user(tenant_id=tenant_a, user_id=subject, email="subject@alpha.example"))
        session.add(build_user_group(tenant_id=tenant_a, group_id=group_id))
        for index, role_id in enumerate(roles):
            session.add(build_role(tenant_id=tenant_a, role_id=role_id, key=f"shared_{index}"))
        await session.flush()
        for role_id in roles:
            session.add(
                build_role_permission(
                    tenant_id=tenant_a, role_id=role_id, permission_key="company.read"
                )
            )
            session.add(
                build_role_assignment(
                    tenant_id=tenant_a,
                    role_id=role_id,
                    subject_id=group_id,
                    subject_type="user_group",
                )
            )
            session.add(
                build_field_policy(
                    tenant_id=tenant_a,
                    subject_type="role",
                    subject_id=role_id,
                    entity_type="identity.company",
                    field_key="credit_limit_default",
                    access="read",
                    effect="allow",
                )
            )
        await session.commit()
    loads = 0
    original = CompanyAccess.load

    async def counted(db: AsyncSession, current: Any) -> CompanyAccess:
        nonlocal loads
        loads += 1
        return await original(db, current)

    monkeypatch.setattr(CompanyAccess, "load", counted)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=editor,
        grants=[grant(["group.manage", "field_policy.manage", "company.read", "role.assign"])],
    )
    response = await client.post(
        f"/v1/user-groups/{group_id}/members", headers=headers, json={"user_id": str(subject)}
    )
    assert response.status_code == 201, response.text
    assert loads == 1


async def test_policy_condition_change_is_recorded_as_a_marker(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    """Relaxing a deny by narrowing its condition is an access change, so it is audited."""
    await seed_two_companies(session, tenant_a, tenant_b)
    subject = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=subject))
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["field_policy.manage", "company.read", "company.update"])],
    )
    body = {
        "entity_type": "identity.company",
        "subject_type": "user",
        "subject_id": str(subject),
        "field_key": "trade_name",
        "access": "write",
        "effect": "deny",
        "reason": "Restricted while under review",
    }
    created = await client.post("/v1/field-policies", headers=headers, json=body)
    assert created.status_code == 201, created.text
    policy_id = created.json()["id"]
    narrowed = await client.put(
        f"/v1/field-policies/{policy_id}",
        headers=headers,
        json={**body, "condition": {"field": "country_code", "cmp": "eq", "value": "IN"}},
    )
    assert narrowed.status_code == 200, narrowed.text
    with tenant_scope(tenant_a):
        events = list(
            await session.scalars(
                select(Outbox)
                .where(Outbox.event_type == "field_policy.updated")
                .order_by(Outbox.id)
            )
        )
    assert len(events) == 1
    # The clause can name a business value, so only the fact of the change is stored.
    assert events[0].payload["changes"]["condition"] == {
        "from": "[redacted]",
        "to": "[redacted]",
    }
    unchanged = await client.put(
        f"/v1/field-policies/{policy_id}",
        headers=headers,
        json={**body, "condition": {"field": "country_code", "cmp": "eq", "value": "IN"}},
    )
    assert unchanged.status_code == 200, unchanged.text
    with tenant_scope(tenant_a):
        events = list(
            await session.scalars(
                select(Outbox)
                .where(Outbox.event_type == "field_policy.updated")
                .order_by(Outbox.id)
            )
        )
    assert len(events) == 2
    assert "condition" not in events[1].payload["changes"]


@pytest.mark.parametrize(
    "entity,field,permission",
    [
        ("catalog.item", "sku", "item.read"),
        ("catalog.product_family", "code", "item.read"),
        ("vouchers.voucher", "document_date", "vouchers.read"),
        ("vouchers.voucher_item", "actual_quantity", "vouchers.read"),
        ("vouchers.configuration", "code", "vouchers.read"),
    ],
)
async def test_document_policies_can_be_revoked_with_scope_and_audit(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    entity: str,
    field: str,
    permission: str,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    subject = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=subject))
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[
            grant(
                ["field_policy.manage", permission],
                scope_type="company",
                scope_id=company,
            )
        ],
    )
    body = {
        "entity_type": entity,
        "subject_type": "user",
        "subject_id": str(subject),
        "field_key": field,
        "access": "read",
        "effect": "allow",
        "scope_type": "company",
        "scope_id": str(company),
        "reason": "Temporary exception",
    }
    created = await client.post("/v1/field-policies", headers=headers, json=body)
    assert created.status_code == 201, created.text
    policy_id = created.json()["id"]
    revoke = {**body, "is_active": False, "reason": "Access revoked"}
    unauthorized = actor_headers(tenant_id=tenant_a, user_id=uuid7(), grants=[grant([permission])])
    assert (
        await client.put(f"/v1/field-policies/{policy_id}", headers=unauthorized, json=revoke)
    ).status_code == 403
    foreign = actor_headers(
        tenant_id=tenant_b,
        user_id=uuid7(),
        grants=[
            grant(
                ["field_policy.manage", permission],
            )
        ],
    )
    assert (
        await client.put(f"/v1/field-policies/{policy_id}", headers=foreign, json=revoke)
    ).status_code == 404
    response = await client.put(f"/v1/field-policies/{policy_id}", headers=headers, json=revoke)
    assert response.status_code == 200, response.text
    assert not response.json()["is_active"]
    with tenant_scope(tenant_a):
        row = await session.scalar(
            select(FieldPolicy).where(FieldPolicy.id == uuid.UUID(policy_id))
        )
        assert row is not None and not row.is_active and row.deactivated_at is not None
        event = await session.scalar(
            select(Outbox).where(Outbox.event_type == "field_policy.updated")
        )
        assert event is not None
        assert event.payload["company_id"] == str(company)
        assert event.payload["changes"] == {
            "is_active": {"from": True, "to": False},
            "effect": {"from": "allow", "to": "allow"},
        }


@pytest.mark.parametrize("operation", ["join", "activate", "remove"])
async def test_group_changes_cannot_delegate_denied_field_access(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    operation: str,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    editor, subject, group_id = uuid7(), uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=editor, email="editor@alpha.example"))
        session.add(build_user(tenant_id=tenant_a, user_id=subject, email="subject@alpha.example"))
        session.add(
            build_user_group(
                tenant_id=tenant_a, group_id=group_id, is_active=operation != "activate"
            )
        )
        await session.flush()
        session.add(
            build_field_policy(
                tenant_id=tenant_a,
                subject_type="user",
                subject_id=editor,
                entity_type="identity.company",
                field_key="credit_limit_default",
                access="read",
            )
        )
        session.add(
            build_field_policy(
                tenant_id=tenant_a,
                subject_type="user_group",
                subject_id=group_id,
                entity_type="identity.company",
                field_key="credit_limit_default",
                access="read",
                effect="deny" if operation == "remove" else "allow",
                scope_type="company",
                scope_id=company,
            )
        )
        if operation != "join":
            session.add(
                build_user_group_member(tenant_id=tenant_a, user_group_id=group_id, user_id=subject)
            )
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=editor,
        grants=[
            grant(
                ["group.manage", "field_policy.manage", "company.read"],
            )
        ],
    )
    base = f"/v1/user-groups/{group_id}"
    if operation == "join":
        response = await client.post(
            base + "/members", headers=headers, json={"user_id": str(subject)}
        )
    elif operation == "activate":
        response = await client.post(
            base + "/lifecycle",
            headers=headers,
            json={"is_active": True, "reason": "Enable access"},
        )
    else:
        response = await client.delete(base + f"/members/{subject}", headers=headers)
    assert response.status_code == 403, response.text
    with tenant_scope(tenant_a):
        members = list(await session.scalars(select(UserGroupMember)))
        assert len(members) == (0 if operation == "join" else 1)
        assert list(await session.scalars(select(Outbox))) == []


@pytest.mark.parametrize("operation", ["assign", "revoke", "regrant", "lifecycle"])
async def test_role_assignment_cannot_delegate_a_field_exception(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    operation: str,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    editor, subject, role_id, assignment_id = uuid7(), uuid7(), uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=editor, email="editor@alpha.example"))
        session.add(build_user(tenant_id=tenant_a, user_id=subject, email="subject@alpha.example"))
        session.add(build_role(tenant_id=tenant_a, role_id=role_id, key="field_exception"))
        await session.flush()
        session.add(
            build_role_permission(
                tenant_id=tenant_a, role_id=role_id, permission_key="company.read"
            )
        )
        session.add(
            build_field_policy(
                tenant_id=tenant_a,
                subject_type="user",
                subject_id=editor,
                entity_type="identity.company",
                field_key="credit_limit_default",
                access="read",
            )
        )
        session.add(
            build_field_policy(
                tenant_id=tenant_a,
                subject_type="role",
                subject_id=role_id,
                entity_type="identity.company",
                field_key="credit_limit_default",
                access="read",
                effect="allow",
                scope_type="company",
                scope_id=company,
            )
        )
        if operation != "assign":
            session.add(
                build_role_assignment(
                    tenant_id=tenant_a,
                    id=assignment_id,
                    role_id=role_id,
                    subject_id=subject,
                    is_active=operation != "regrant",
                )
            )
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=editor,
        grants=[
            grant(
                ["role.manage", "role.assign", "company.read", "field_policy.manage"],
            )
        ],
    )
    if operation == "assign":
        response = await client.post(
            "/v1/role-assignments",
            headers=headers,
            json={
                "subject_type": "user",
                "subject_id": str(subject),
                "role_id": str(role_id),
                "scope_type": "tenant",
            },
        )
    elif operation == "lifecycle":
        response = await client.post(
            f"/v1/roles/{role_id}/lifecycle",
            headers=headers,
            json={"is_active": False, "reason": "Change role access"},
        )
    else:
        response = await client.post(
            f"/v1/role-assignments/{assignment_id}/{operation}",
            headers={**headers, "Idempotency-Key": "field-guard-review"},
            json={"reason": "Change role access"},
        )
    assert response.status_code == 403, response.text
    with tenant_scope(tenant_a):
        assert list(await session.scalars(select(Outbox))) == []


async def test_role_edit_cannot_remove_permissions_editor_does_not_hold(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    role_id, subject = uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=subject))
        session.add(build_role(tenant_id=tenant_a, role_id=role_id, key="broad_role"))
        await session.flush()
        for key in ["invoice.read", "invoice.create"]:
            session.add(
                build_role_permission(tenant_id=tenant_a, role_id=role_id, permission_key=key)
            )
        session.add(build_role_assignment(tenant_id=tenant_a, role_id=role_id, subject_id=subject))
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[
            grant(
                ["role.manage", "role.assign", "invoice.read"],
            )
        ],
    )
    response = await client.patch(
        f"/v1/roles/{role_id}", headers=headers, json={"permissions": ["invoice.read"]}
    )
    assert response.status_code == 403, response.text
    with tenant_scope(tenant_a):
        assert set(await session.scalars(select(RolePermission.permission_key))) == {
            "invoice.read",
            "invoice.create",
        }


async def test_role_edit_requires_assignment_authority_for_every_company(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    first, _ = await seed_two_companies(session, tenant_a, tenant_b)
    second, subject, role_id = uuid7(), uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add(build_company(tenant_id=tenant_a, company_id=second, code="SECOND"))
        session.add(build_user(tenant_id=tenant_a, user_id=subject))
        session.add(build_role(tenant_id=tenant_a, role_id=role_id, key="shared_scope_role"))
        await session.flush()
        for company in [first, second]:
            session.add(
                build_role_assignment(
                    tenant_id=tenant_a,
                    role_id=role_id,
                    subject_id=subject,
                    scope_type="company",
                    scope_id=company,
                )
            )
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[
            grant(["role.manage", "invoice.read"]),
            grant(["role.assign"], scope_type="company", scope_id=first),
        ],
    )
    response = await client.patch(
        f"/v1/roles/{role_id}", headers=headers, json={"permissions": ["invoice.read"]}
    )
    assert response.status_code == 403, response.text
    with tenant_scope(tenant_a):
        assert list(await session.scalars(select(RolePermission))) == []
        assert list(await session.scalars(select(Outbox))) == []


async def test_role_conflict_warnings_survive_audit_redaction(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[grant(["role.manage", "role.assign", "audit.read_security"])],
    )
    created = await client.post(
        "/v1/roles",
        headers=headers,
        json={
            "key": "conflicted_audit_role",
            "name": "Review conflict evidence",
            "permissions": ["role.assign", "audit.read_security"],
        },
    )
    assert created.status_code == 201, created.text
    warnings = created.json()["separation_of_duties_warnings"]
    assert warnings
    updated = await client.patch(
        f"/v1/roles/{created.json()['role']['id']}",
        headers=headers,
        json={"permissions": ["audit.read_security"]},
    )
    assert updated.status_code == 200, updated.text
    with tenant_scope(tenant_a):
        for action, expected in [
            ("role.created", {"from": None, "to": warnings}),
            ("role.updated", {"from": warnings, "to": []}),
        ]:
            event = await session.scalar(select(Outbox).where(Outbox.event_type == action))
            assert event is not None
            assert event.payload["changes"]["separation_of_duties_warnings"] == expected
