"""User-approved permanent opening authority, not a per-user QA repair."""

import pytest
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import unfiltered
from sqlalchemy import select

from identity.domain.system_roles import get
from identity.models import Role, RolePermission
from identity.seeds.roles import seed_system_roles

OPENING = {
    "accounting.finance.manage",
    "ledger.post_journal",
    "period.post",
    "accounting.export.read",
    "opening_balance.read",
    "opening_balance.manage",
    "opening_balance.initialize_zero",
}


def test_tenant_admin_can_complete_native_openings_without_closing_or_self_approval():
    permissions = get("tenant_admin").permissions
    assert OPENING <= permissions
    assert not permissions & {
        "period.close",
        "period.reopen",
        "period.lock",
        "period.post_adjustment",
        "vouchers.approve",
        "vouchers.post",
        "user.impersonate",
        "audit.read_security",
    }
    assert "accounting.finance.manage" not in get("company_admin").permissions


@pytest.mark.asyncio
async def test_fresh_install_and_repeat_seed_keep_opening_authority(session):
    await seed_system_roles(session)
    with unfiltered():
        role = await session.scalar(
            select(Role).where(Role.tenant_id == SCOPE_ALL, Role.key == "tenant_admin")
        )
        retained_id = role.id
        permissions = set(
            await session.scalars(
                select(RolePermission.permission_key).where(RolePermission.role_id == role.id)
            )
        )
    assert OPENING <= permissions
    roles, grants = await seed_system_roles(session)
    assert not roles.changed and not grants.changed
    with unfiltered():
        role = await session.scalar(
            select(Role).where(Role.tenant_id == SCOPE_ALL, Role.key == "tenant_admin")
        )
    assert role.id == retained_id
