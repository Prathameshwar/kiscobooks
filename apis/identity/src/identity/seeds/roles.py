"""Write the shipped system roles and their grants.

docs/roles-permissions.md §6. Idempotent and re-runnable, which is the whole reason a
role catalogue is a seed and not a migration (CLAUDE.md §2): running it twice changes
nothing the second time, and running it after a permission is added to a shipped role
applies exactly that.

The natural key is ``(SCOPE_ALL, key)``. **Role keys are immutable** — assignments
reference the role by id, but seeds, tests and support runbooks all reference it by key,
so a rename reads as a new role to every one of them. ``name``, ``description`` and
``scope_hint`` are updated in place.

Two directions of withdrawal, deliberately different:

* A **role** removed from the catalogue is **deactivated, never deleted** — assignments
  reference it (CLAUDE.md invariant 12), and ``role.is_active`` false means "not
  assignable to anyone new", not "revoked from everyone who holds it".
* A **permission** removed from a shipped role's set *is* deleted. ``role_permission``
  carries no lifecycle switch: a deactivated row would keep occupying the unique key and
  silently refuse the re-grant. What changed lives in the audit trail.

Which is why the grants of a *deactivated* role are left alone. Its assignments still
resolve — that is what deactivating rather than deleting means — and stripping the rows
would quietly reduce what those people can do.

The upsert is a read-then-write rather than MariaDB's ``INSERT ... ON DUPLICATE KEY
UPDATE``, for the same two reasons as the reference seed: one code path on every dialect,
so it is tested against SQLite rather than only under Docker, and it can report what
actually changed, which is what makes ``--dry-run`` before a production seed worth
running.

**No audit event is emitted.** Invariant 8 is about state changes with an actor and a
tenant, and this has neither: it is a platform-wide deploy step whose record is the
versioned catalogue in code plus the deploy itself. The same is true of the reference
seed. A synthetic actor row would be a worse answer than an honest absence.

Runs under ``unfiltered()``: ``role`` and ``role_permission`` are tenant-scoped models
and there is no tenant in context, because ``SCOPE_ALL`` is not a tenant.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.session import (
    create_engine,
    create_session_factory,
    database_url,
)
from billing_platform.db.tenant_context import unfiltered
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.permissions import assert_known_permission
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.system_roles import SYSTEM_ROLE_KEYS, SYSTEM_ROLES
from identity.models import Role, RolePermission

#: The fields the seed owns on an existing row. ``key`` and ``tenant_id`` are absent
#: because they are the natural key, and ``is_active`` is handled separately — it is the
#: withdrawal mechanism, not a description of the role.
_MANAGED_FIELDS: tuple[str, ...] = ("name", "description", "scope_hint")


@dataclass(frozen=True, slots=True)
class RoleSeedOutcome:
    """What one table's seed did. Printed by the CLI and asserted by the tests.

    Shaped like ``billing_platform.reference.seed.SeedOutcome`` but not that class: this
    one counts ``revoked`` grants, which no reference table has, and reference rows are
    deactivated where grants are deleted. Sharing the type would mean one of the two
    seeds reporting a column that can never be non-zero.
    """

    table: str
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    revoked: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.inserted or self.updated or self.deactivated or self.revoked)

    def __str__(self) -> str:
        return (
            f"{self.table:<16} inserted={self.inserted:<4} updated={self.updated:<4} "
            f"unchanged={self.unchanged:<4} deactivated={self.deactivated:<4} "
            f"revoked={self.revoked}"
        )


async def _seed_roles(session: AsyncSession) -> tuple[RoleSeedOutcome, dict[str, uuid.UUID]]:
    """Upsert the role rows. Returns the outcome and ``{key: id}`` for the grants."""
    existing = {
        row.key: row
        for row in (await session.execute(select(Role).where(Role.tenant_id == SCOPE_ALL)))
        .scalars()
        .all()
    }

    role_ids: dict[str, uuid.UUID] = {}
    inserted = updated = unchanged = 0

    for role in SYSTEM_ROLES:
        current = existing.get(role.key)
        if current is None:
            role_id = uuid7()
            # Keyword construction from the code catalogue, never `**request`
            # (CLAUDE.md §5.6 — no mass assignment).
            session.add(
                Role(
                    id=role_id,
                    tenant_id=SCOPE_ALL,
                    key=role.key,
                    name=role.name,
                    description=role.description,
                    scope_hint=role.scope_hint,
                )
            )
            role_ids[role.key] = role_id
            inserted += 1
            continue

        role_ids[role.key] = current.id
        changes: dict[str, Any] = {
            field: getattr(role, field)
            for field in _MANAGED_FIELDS
            if getattr(current, field) != getattr(role, field)
        }
        if not current.is_active:
            # Back in the catalogue after a withdrawal. Clearing the tombstone as well
            # as the flag, or a reactivated role would read as deactivated on some date.
            changes |= {"is_active": True, "deactivated_at": None, "deactivated_by": None}

        if not changes:
            unchanged += 1
            continue
        for field, value in changes.items():
            setattr(current, field, value)
        updated += 1

    deactivated = 0
    for key, row in existing.items():
        if key not in SYSTEM_ROLE_KEYS and row.is_active:
            row.is_active = False
            row.deactivated_at = utcnow()
            deactivated += 1

    await session.flush()
    return RoleSeedOutcome("role", inserted, updated, unchanged, deactivated), role_ids


async def _seed_grants(session: AsyncSession, role_ids: dict[str, uuid.UUID]) -> RoleSeedOutcome:
    """Upsert each shipped role's permission rows, deleting the ones it no longer grants."""
    wanted: dict[uuid.UUID, frozenset[str]] = {}
    for role in SYSTEM_ROLES:
        for permission in sorted(role.permissions):
            # The compensating control for `role_permission.permission_key` having no
            # foreign key (CLAUDE.md invariant 13). The catalogue is already checked at
            # import; re-checked at the write because this is the row that would
            # otherwise sit in the database granting nothing, silently, forever.
            assert_known_permission(permission, named_by=f"system role {role.key!r}")
        wanted[role_ids[role.key]] = role.permissions

    held: dict[uuid.UUID, dict[str, RolePermission]] = {}
    for row in (
        (await session.execute(select(RolePermission).where(RolePermission.tenant_id == SCOPE_ALL)))
        .scalars()
        .all()
    ):
        held.setdefault(row.role_id, {})[row.permission_key] = row

    inserted = unchanged = revoked = 0
    for role_id, permissions in wanted.items():
        current = held.get(role_id, {})

        for permission in sorted(permissions - current.keys()):
            session.add(
                RolePermission(
                    id=uuid7(),
                    tenant_id=SCOPE_ALL,
                    role_id=role_id,
                    permission_key=permission,
                )
            )
            inserted += 1

        unchanged += len(current.keys() & permissions)

        for permission in sorted(current.keys() - permissions):
            await session.delete(current[permission])
            revoked += 1

    await session.flush()
    return RoleSeedOutcome("role_permission", inserted, 0, unchanged, 0, revoked)


async def seed_system_roles(session: AsyncSession) -> list[RoleSeedOutcome]:
    """Apply the catalogue. Flushes but does **not** commit.

    The caller owns the transaction, so this can be part of a larger provisioning step
    or rolled back for a dry run.
    """
    with unfiltered():
        roles, role_ids = await _seed_roles(session)
        grants = await _seed_grants(session, role_ids)
    return [roles, grants]


async def apply_role_seed(url: str, *, dry_run: bool = False) -> list[RoleSeedOutcome]:
    """Seed one identity database, committing unless ``dry_run``."""
    engine = create_engine(url)
    try:
        async with create_session_factory(engine)() as session:
            outcomes = await seed_system_roles(session)
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
        return outcomes
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """The CLI. No ``service`` argument, unlike the reference seed: ``role`` exists only
    in ``identity``, and accepting a service name would invite pointing it at a database
    that has no such table."""
    parser = argparse.ArgumentParser(
        prog="seeds.roles",
        description="Seed the system roles and their permissions into identity.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change, then roll back",
    )
    args = parser.parse_args(argv)

    outcomes = asyncio.run(apply_role_seed(database_url("identity"), dry_run=args.dry_run))
    for outcome in outcomes:
        print(outcome)  # noqa: T201  a CLI's only output channel
    if args.dry_run:
        print("dry run: rolled back")  # noqa: T201
    return 0
