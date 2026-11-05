"""The system-role seed (docs/roles-permissions.md §6).

The seed is idempotent and re-runnable — that is the whole reason a role catalogue is a
seed and not a migration (CLAUDE.md §2). These tests were referenced by
``seeds/roles/__main__.py``'s docstring but did not exist; this is that coverage.
"""

from __future__ import annotations

import pytest
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import unfiltered
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.system_roles import SYSTEM_ROLES, get
from identity.models import Role, RolePermission
from identity.seeds.roles import seed_system_roles

pytestmark = pytest.mark.asyncio

_TOTAL_GRANTS = sum(len(role.permissions) for role in SYSTEM_ROLES)


async def test_first_run_inserts_every_role_and_grant(session: AsyncSession) -> None:
    role_outcome, grant_outcome = await seed_system_roles(session)
    assert role_outcome.inserted == len(SYSTEM_ROLES)
    assert role_outcome.updated == 0
    assert grant_outcome.inserted == _TOTAL_GRANTS
    assert grant_outcome.revoked == 0

    with unfiltered():
        role_count = await session.scalar(select(func.count(Role.id)))
        grant_count = await session.scalar(select(func.count(RolePermission.id)))
    assert role_count == len(SYSTEM_ROLES)
    assert grant_count == _TOTAL_GRANTS


async def test_second_run_is_a_no_op(session: AsyncSession) -> None:
    await seed_system_roles(session)
    role_outcome, grant_outcome = await seed_system_roles(session)
    assert role_outcome.inserted == 0
    assert role_outcome.updated == 0
    assert role_outcome.unchanged == len(SYSTEM_ROLES)
    assert grant_outcome.inserted == 0
    assert grant_outcome.revoked == 0
    assert grant_outcome.unchanged == _TOTAL_GRANTS
    assert not role_outcome.changed and not grant_outcome.changed


async def test_seeded_roles_are_system_scoped_with_correct_grants(session: AsyncSession) -> None:
    await seed_system_roles(session)
    with unfiltered():
        clerk = (
            await session.scalars(
                select(Role).where(Role.tenant_id == SCOPE_ALL, Role.key == "billing_clerk")
            )
        ).one()
        assert clerk.is_system is True
        grants = set(
            (
                await session.scalars(
                    select(RolePermission.permission_key).where(RolePermission.role_id == clerk.id)
                )
            ).all()
        )
    assert grants == set(get("billing_clerk").permissions)


async def test_counter_duties_are_separate_in_shipped_roles() -> None:
    clerk = get("billing_clerk").permissions
    approver = get("billing_approver").permissions
    auditor = get("tenant_auditor").permissions
    admin = get("company_admin").permissions
    assert {"vouchers.counter.operate", "vouchers.counter.close"} <= clerk
    assert "vouchers.counter.supervise" not in clerk
    assert {
        "vouchers.counter.read",
        "vouchers.counter.supervise",
        "vouchers.counter.close",
    } <= approver
    assert "vouchers.counter.operate" not in approver
    assert "vouchers.counter.read" in auditor
    assert not any(key.startswith("vouchers.counter.") for key in admin)


async def test_company_admin_bootstrap_and_tenant_admin_opening_policy() -> None:
    """Both administrators bootstrap; tenant admin also has approved opening authority.

    Company admin stays bounded; fiscal closing remains separate for both.
    """
    bootstrap = {
        "accounting.finance.read",
        "accounting.finance.initialize",
        "period.read",
        "period.manage",
    }
    withheld = {
        "accounting.finance.manage",
        "opening_balance.manage",
        "ledger.post_journal",
        "period.post",
        "period.post_adjustment",
        "period.close",
        "period.reopen",
        "period.lock",
    }
    assert bootstrap <= get("tenant_admin").permissions
    held = get("company_admin").permissions
    assert bootstrap <= held
    assert not (withheld & held)
    assert not get("tenant_admin").permissions & {
        "period.close",
        "period.reopen",
        "period.lock",
        "period.post_adjustment",
    }
    # The controller keeps the authority the administrators do not have. `period.lock`
    # is held by no shipped role: it follows a statutory filing and is assigned
    # deliberately, which is why it is in the withheld set above and not here.
    controller = get("controller").permissions
    assert {"accounting.finance.manage", "period.close", "period.reopen"} <= controller
    assert not any("period.lock" in role.permissions for role in SYSTEM_ROLES)


async def test_company_creation_is_offered_to_both_administrator_roles() -> None:
    """The route requires the grant at tenant scope, so holding the key at company scope
    does nothing — but an administrator assigned tenant-wide should be able to create a
    company and finish its setup without a second person."""
    for key in ("tenant_admin", "company_admin"):
        assert "company.create" in get(key).permissions, key
    assert "company.create" not in get("controller").permissions


async def test_reseed_reflects_a_changed_display_name(session: AsyncSession) -> None:
    """A role's ``name`` is seed-owned and updated in place; ``key`` is the immutable
    natural key, so a display-name drift is corrected on the next run."""
    await seed_system_roles(session)
    with unfiltered():
        clerk = (await session.scalars(select(Role).where(Role.key == "billing_clerk"))).one()
        clerk.name = "Drifted Name"
        await session.flush()

    role_outcome, _ = await seed_system_roles(session)
    assert role_outcome.updated == 1
    with unfiltered():
        refreshed = (await session.scalars(select(Role).where(Role.key == "billing_clerk"))).one()
    assert refreshed.name == get("billing_clerk").name
