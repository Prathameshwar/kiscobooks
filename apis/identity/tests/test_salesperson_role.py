"""Salesperson privileges, safe seed upgrades, and assignment/role API behavior."""

from __future__ import annotations

import datetime as dt
import uuid

import httpx
import pytest
from billing_platform.authz import Grant, Scope, ScopePath, resolve_permissions
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from billing_platform.permissions import PERMISSIONS, separation_of_duties_conflicts
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.system_roles import SYSTEM_ROLES, get
from identity.models import Role, RoleAssignment, RolePermission
from identity.seeds import roles as role_seed
from tests.api_support import actor_headers, grant
from tests.factories import build_company, build_user, seed_two_companies


def test_salesperson_is_a_limited_sales_preparation_role() -> None:
    role = get("salesperson")
    assert role.name == "Salesperson"
    assert role.scope_hint == "company"
    assert role.permissions == {
        "company.read",
        "item.read",
        "unit.read",
        "pack_type.read",
        "item_group.read",
        "category_scheme.read",
        "item_category.read",
        "brand.read",
        "brand_series.read",
        "manufacturer.read",
        "manufacturer_site.read",
        "brand_manufacturer.read",
        "product_type.read",
        "attribute_definition.read",
        "attribute_option.read",
        "attribute_set.read",
        "identifier_profile.read",
        "inventory_profile_template.read",
        "warranty_policy.read",
        "return_policy.read",
        "handling_profile.read",
        "product_configuration.read",
        "master_alias.read",
        "price_plan.read",
        "tax_rule.read",
        # Reads the stock location a sale issues from; cannot configure one
        # (docs/catalog-warehouses.md §7, tests/test_warehouse_roles.py).
        "warehouse.read",
        # Reads the layout a sales document prints on; authoring one is
        # `design.template.manage`, which this role does not hold
        # (docs/invoice-design.md §5.3).
        "design.template.read",
        "invoice.create",
        "invoice.read",
        "invoice.update",
    }
    assert role.permissions <= PERMISSIONS
    assert not separation_of_duties_conflicts(role.permissions)
    # Thirteen with Stock Operator (2026-10-28), fourteen with Purchase Clerk (2026-11-01).
    assert len(SYSTEM_ROLES) == 14


@pytest.mark.parametrize(
    "permission",
    [
        "invoice.post",
        "invoice.approve",
        "invoice.cancel",
        "invoice.export",
        "credit_note.create",
        "payment.read",
        "payment.record",
        "payment.refund",
        "ledger.read",
        "report.read",
        "price_plan.manage",
        "item.update",
        "role.assign",
        "role.manage",
        "period.post",
    ],
)
def test_salesperson_has_no_finance_approval_or_administration_authority(permission: str) -> None:
    assert permission not in get("salesperson").permissions


async def test_existing_installation_gains_only_salesperson_and_reseed_is_noop(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = tuple(role for role in SYSTEM_ROLES if role.key != "salesperson")
    with monkeypatch.context() as patch:
        patch.setattr(role_seed, "SYSTEM_ROLES", previous)
        patch.setattr(role_seed, "SYSTEM_ROLE_KEYS", frozenset(role.key for role in previous))
        await role_seed.seed_system_roles(session)
    with unfiltered():
        ids_before = dict((await session.execute(select(Role.key, Role.id))).tuples().all())
        grants_before = set(
            (
                await session.execute(select(RolePermission.role_id, RolePermission.permission_key))
            ).all()
        )
    outcome, grants = await role_seed.seed_system_roles(session)
    assert outcome.inserted == 1 and outcome.updated == 0 and outcome.deactivated == 0
    assert grants.inserted == len(get("salesperson").permissions) and grants.revoked == 0
    with unfiltered():
        ids_after = dict((await session.execute(select(Role.key, Role.id))).tuples().all())
        assert {
            key: value for key, value in ids_after.items() if key != "salesperson"
        } == ids_before
        retained = set(
            (
                await session.execute(
                    select(RolePermission.role_id, RolePermission.permission_key).where(
                        RolePermission.role_id.in_(ids_before.values())
                    )
                )
            ).all()
        )
        assert retained == grants_before
    repeated, repeated_grants = await role_seed.seed_system_roles(session)
    assert not repeated.changed and not repeated_grants.changed


async def _seed_salesperson(
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    company_id, _ = await seed_two_companies(session, tenant_a, tenant_b)
    await role_seed.seed_system_roles(session)
    await session.commit()
    with tenant_scope(tenant_a):
        role = (await session.scalars(select(Role).where(Role.key == "salesperson"))).one()
        assert role.tenant_id == SCOPE_ALL and role.is_system
        return role.id, company_id


async def test_salesperson_is_discoverable_readonly_and_cloneable(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    role_id, _ = await _seed_salesperson(session, tenant_a, tenant_b)
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[
            grant(
                [
                    "role.read",
                    "role.manage",
                    *get("salesperson").permissions,
                ]
            )
        ],
    )
    response = await client.get("/v1/roles?q=salesperson", headers=headers)
    assert response.status_code == 200, response.text
    assert [item["key"] for item in response.json()["items"]] == ["salesperson"]
    response = await client.get(f"/v1/roles/{role_id}", headers=headers)
    assert response.status_code == 200
    assert set(response.json()["permissions"]) == get("salesperson").permissions
    assert response.json()["is_system"] is True
    response = await client.patch(
        f"/v1/roles/{role_id}", headers=headers, json={"permissions": ["invoice.post"]}
    )
    assert response.status_code == 422
    response = await client.post(
        f"/v1/roles/{role_id}/clone",
        headers=headers,
        json={"key": "field_sales", "name": "Field Sales"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_system"] is False
    assert set(response.json()["permissions"]) == get("salesperson").permissions


async def test_salesperson_assignment_resolves_only_within_its_company(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    role_id, company_id = await _seed_salesperson(session, tenant_a, tenant_b)
    subject_id, other_company = uuid7(), uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=subject_id))
        session.add(build_company(tenant_id=tenant_a, company_id=other_company, code="OTHER"))
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a,
        user_id=uuid7(),
        grants=[
            grant(
                ["role.assign", *get("salesperson").permissions],
                scope_type="company",
                scope_id=company_id,
            )
        ],
    )
    body = {
        "subject_type": "user",
        "subject_id": str(subject_id),
        "role_id": str(role_id),
        "scope_type": "company",
        "scope_id": str(company_id),
    }
    response = await client.post("/v1/role-assignments", headers=headers, json=body)
    assert response.status_code == 201, response.text
    with tenant_scope(tenant_a):
        assignment = await session.get(RoleAssignment, uuid.UUID(response.json()["id"]))
        assert assignment is not None
        keys = frozenset(
            await session.scalars(
                select(RolePermission.permission_key).where(RolePermission.role_id == role_id)
            )
        )
        assigned = Grant(
            keys, Scope(assignment.scope_type, assignment.scope_id), assignment.valid_from
        )
        assert (
            resolve_permissions(
                [assigned], target=ScopePath(company_id=company_id), on_date=dt.date.today()
            )
            == get("salesperson").permissions
        )
        assert not resolve_permissions(
            [assigned], target=ScopePath(company_id=other_company), on_date=dt.date.today()
        )
    response = await client.post(
        "/v1/role-assignments", headers=headers, json=body | {"scope_id": str(other_company)}
    )
    assert response.status_code == 403
    response = await client.post(
        "/v1/role-assignments",
        headers=actor_headers(
            tenant_id=tenant_a,
            user_id=uuid7(),
            grants=[grant(["role.assign"])],
        ),
        json=body,
    )
    assert response.status_code == 403
    response = await client.post(
        "/v1/role-assignments",
        headers=actor_headers(
            tenant_id=tenant_b,
            user_id=uuid7(),
            grants=[grant(["role.assign", *get("salesperson").permissions])],
        ),
        json=body,
    )
    assert response.status_code == 422  # subject is not visible in the other tenant


async def test_seed_preserves_a_tenants_existing_custom_salesperson_role(
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    from tests.factories import build_role, build_role_permission

    await seed_two_companies(session, tenant_a, tenant_b)
    custom_id = uuid7()
    with tenant_scope(tenant_a):
        session.add(
            build_role(
                tenant_id=tenant_a, role_id=custom_id, key="salesperson", name="My Sales Team"
            )
        )
        await session.flush()
        session.add(
            build_role_permission(
                tenant_id=tenant_a, role_id=custom_id, permission_key="invoice.read"
            )
        )
        await session.commit()
    await role_seed.seed_system_roles(session)
    await session.commit()
    with tenant_scope(tenant_a):
        roles = list(await session.scalars(select(Role).where(Role.key == "salesperson")))
        assert len(roles) == 2
        custom = next(role for role in roles if role.id == custom_id)
        assert custom.name == "My Sales Team" and not custom.is_system
        keys = set(
            await session.scalars(
                select(RolePermission.permission_key).where(RolePermission.role_id == custom_id)
            )
        )
        assert keys == {"invoice.read"}
