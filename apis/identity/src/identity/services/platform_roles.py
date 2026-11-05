"""Read only system scope; apply only the validated shipped role catalogue."""

import hashlib
import json
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db import unfiltered
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.system_roles import SYSTEM_ROLES
from identity.models import Role, RolePermission
from identity.schemas.platform_roles import RoleSeedChange, RoleSeedPlan


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def plan(db: AsyncSession, *, lock: bool = False) -> RoleSeedPlan:
    with unfiltered():
        roles_query = select(Role).where(Role.tenant_id == SCOPE_ALL).order_by(Role.key)
        grants_query = (
            select(RolePermission)
            .where(RolePermission.tenant_id == SCOPE_ALL)
            .order_by(RolePermission.id)
        )
        rows = list(await db.scalars(roles_query.with_for_update() if lock else roles_query))
        grants = list(await db.scalars(grants_query.with_for_update() if lock else grants_query))
    permissions = {
        row.id: sorted(g.permission_key for g in grants if g.role_id == row.id) for row in rows
    }
    installed = [
        {
            "id": str(row.id),
            "key": row.key,
            "name": row.name,
            "description": row.description,
            "scope_hint": row.scope_hint,
            "is_active": row.is_active,
            "permissions": permissions[row.id],
        }
        for row in rows
    ]
    current = {row.key: row for row in rows}
    changes: list[RoleSeedChange] = []
    wanted: list[dict[str, Any]] = []
    for role in SYSTEM_ROLES:
        wanted.append(
            {
                "key": role.key,
                "name": role.name,
                "description": role.description,
                "scope_hint": role.scope_hint,
                "permissions": sorted(role.permissions),
            }
        )
        row = current.get(role.key)
        held = set(permissions[row.id]) if row else set()
        added, removed = sorted(role.permissions - held), sorted(held - role.permissions)
        metadata_changed = (
            row is None
            or not row.is_active
            or any(
                getattr(row, field) != getattr(role, field)
                for field in ("name", "description", "scope_hint")
            )
        )
        if added or removed or metadata_changed:
            changes.append(
                RoleSeedChange(
                    key=role.key, added=added, removed=removed, metadata_changed=metadata_changed
                )
            )
    known = {role.key for role in SYSTEM_ROLES}
    for row in rows:
        if row.key not in known and row.is_active:
            changes.append(
                RoleSeedChange(
                    key=row.key, added=[], removed=[], metadata_changed=False, deactivate=True
                )
            )
    return RoleSeedPlan(
        current_digest=digest(installed), catalogue_digest=digest(wanted), changes=changes
    )
