"""Policy for the explicitly authorized fixed tenant-administrator platform boundary."""

from __future__ import annotations

import uuid
from typing import Literal
from urllib.parse import urlencode

from billing_platform.constants import SCOPE_ALL
from billing_platform.db import unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError
from billing_platform.ids import uuid7
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.config import Settings
from identity.domain.system_roles import SYSTEM_ROLES
from identity.models import (
    PlatformInstallation,
    Role,
    RoleAssignment,
    RolePermission,
    Tenant,
    User,
    UserInvitation,
)
from identity.schemas.platform_access import (
    AdministratorCommand,
    AdministratorInvite,
    AdministratorReceipt,
    AdministratorTenant,
    PlatformAdministrator,
    PlatformAdministratorRole,
)
from identity.schemas.user import UserInvite
from identity.services.audit import record
from identity.services.identity_provider import recovery_supported


async def is_platform_operator(db: AsyncSession, settings: Settings, user: User) -> bool:
    """Whether the user is the platform's operator — a fact of configuration, not of any role.

    The operator test (``api.platform.platform_actor``) is the installation's configured operators
    or the administrator the first-run setup recorded. Neither is a grant, so a permission check
    cannot see it: anything that hands out a way into an account must ask this separately.
    """
    if user.authentik_sub and settings.platform_operators.get(user.authentik_sub) == user.id:
        return True
    recorded = await db.scalar(
        select(PlatformInstallation.id).where(
            PlatformInstallation.key == "platform",
            PlatformInstallation.completed_at.is_not(None),
            PlatformInstallation.administrator_id == user.id,
        )
    )
    return recorded is not None


async def administrator_role(db: AsyncSession) -> PlatformAdministratorRole:
    # The only unfiltered role read is the fixed, installation-owned system role.
    with unfiltered():
        row = await db.scalar(
            select(Role).where(Role.tenant_id == SCOPE_ALL, Role.key == "tenant_admin")
        )
        if row is None or not row.is_active:
            raise ConflictError("the tenant-administrator system role needs the current role seed")
        permissions = set(
            await db.scalars(
                select(RolePermission.permission_key).where(
                    RolePermission.tenant_id == SCOPE_ALL, RolePermission.role_id == row.id
                )
            )
        )
    canonical = next(role for role in SYSTEM_ROLES if role.key == "tenant_admin")
    if permissions != canonical.permissions:
        raise ConflictError("the tenant-administrator system role needs the current role seed")
    return PlatformAdministratorRole(
        id=row.id, name=row.name, description=row.description, permissions=sorted(permissions)
    )


async def target_tenant(
    db: AsyncSession, tenant_id: uuid.UUID, current: Actor, *, write: bool = False
) -> Tenant:
    if tenant_id in {current.tenant_id, SCOPE_ALL}:
        raise NotFoundError("select a customer tenant")
    row = await db.scalar(
        select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        if write
        else select(Tenant).where(Tenant.id == tenant_id)
    )
    if row is None:
        raise NotFoundError("tenant not found")
    if write and row.status == "closed":
        raise ConflictError("a closed tenant cannot change administrator access")
    return row


def assignments(tenant_id: uuid.UUID, role_id: uuid.UUID) -> Select[tuple[RoleAssignment]]:
    return select(RoleAssignment).where(
        RoleAssignment.tenant_id == tenant_id,
        RoleAssignment.role_id == role_id,
        RoleAssignment.subject_type == "user",
        RoleAssignment.scope_type == "tenant",
        RoleAssignment.scope_id == SCOPE_ALL,
    )


def administrator_users(tenant_id: uuid.UUID, role_id: uuid.UUID) -> Select[tuple[User]]:
    subjects = assignments(tenant_id, role_id).with_only_columns(RoleAssignment.subject_id)
    return select(User).where(
        User.tenant_id == tenant_id, User.user_type == "tenant_user", User.id.in_(subjects)
    )


async def administrator(
    db: AsyncSession, tenant_id: uuid.UUID, role_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[User, RoleAssignment]:
    row = await db.scalar(
        administrator_users(tenant_id, role_id).where(User.id == user_id).with_for_update()
    )
    assignment = await db.scalar(
        assignments(tenant_id, role_id)
        .where(RoleAssignment.subject_id == user_id)
        .with_for_update()
    )
    if row is None or assignment is None or row.tenant_id != tenant_id:
        raise NotFoundError("tenant administrator not found")
    return row, assignment


async def last_active(db: AsyncSession, row: User, assignment: RoleAssignment) -> bool:
    today = utcnow().date()
    if not (
        row.status == "active"
        and assignment.is_active
        and assignment.valid_from <= today
        and (assignment.valid_to is None or assignment.valid_to >= today)
    ):
        return False
    effective = (
        assignments(row.tenant_id, assignment.role_id)
        .where(
            RoleAssignment.is_active.is_(True),
            RoleAssignment.valid_from <= today,
            or_(RoleAssignment.valid_to.is_(None), RoleAssignment.valid_to >= today),
        )
        .with_only_columns(RoleAssignment.subject_id)
    )
    another = await db.scalar(
        select(User.id)
        .where(
            User.tenant_id == row.tenant_id,
            User.status == "active",
            User.user_type == "tenant_user",
            User.id != row.id,
            User.id.in_(effective),
        )
        .limit(1)
    )
    return another is None


async def detail(
    db: AsyncSession,
    tenant: Tenant,
    row: User,
    assignment: RoleAssignment,
    settings: Settings | None = None,
) -> PlatformAdministrator:
    deliveries: list[Literal["link", "email"]] = []
    local = settings is not None and settings.auth_provider == "local"
    # Recovery is offered only when the active provider can actually perform it: the local provider
    # needs its own configuration (and never emails yet); Authentik needs its recovery integration.
    ready = settings is not None and (
        settings.local_auth is not None
        if local
        else bool(settings.authentik_recovery_url and settings.authentik_recovery_token)
    )
    if (
        settings
        and ready
        and tenant.status == "active"
        and row.status == "active"
        and row.authentik_sub
        and recovery_supported(settings, row.authentik_sub)
        and assignment.is_active
        and assignment.valid_from <= utcnow().date()
        and (assignment.valid_to is None or assignment.valid_to >= utcnow().date())
    ):
        deliveries.append("link")
        if not local and settings.authentik_recovery_email_stage:
            deliveries.append("email")
    return PlatformAdministrator(
        id=row.id,
        display_name=row.display_name,
        email=row.email,
        status=row.status,
        updated_at=row.updated_at,
        tenant=AdministratorTenant.model_validate(tenant),
        assignment_id=assignment.id,
        assignment_updated_at=assignment.updated_at,
        assignment_active=assignment.is_active,
        valid_from=assignment.valid_from,
        valid_to=assignment.valid_to,
        last_active_administrator=await last_active(db, row, assignment),
        recovery_deliveries=deliveries,
    )


def receipt(
    row: User,
    assignment: RoleAssignment,
    settings: Settings,
    invitation: UserInvitation | None = None,
) -> AdministratorReceipt:
    return AdministratorReceipt(
        tenant_id=row.tenant_id,
        administrator_id=row.id,
        assignment_id=assignment.id,
        status=row.status,
        assignment_active=assignment.is_active,
        updated_at=row.updated_at,
        assignment_updated_at=assignment.updated_at,
        invitation_id=invitation.id if invitation else None,
        invitation_expires_at=invitation.expires_at if invitation else None,
        invitation_url=(settings.public_auth_url or "").rstrip("/")
        + "/accept?"
        + urlencode({"tenant": str(row.tenant_id), "invitation": str(invitation.id)})
        if invitation
        else None,
    )


async def invite(
    db: AsyncSession,
    current: Actor,
    tenant: Tenant,
    role: PlatformAdministratorRole,
    body: AdministratorInvite,
    settings: Settings,
) -> AdministratorReceipt:
    from identity.services.user_invites import create_invited_user

    target = Actor(tenant.id, current.user_id)
    row = await create_invited_user(
        db,
        target,
        UserInvite(email=body.email, first_name=body.display_name, display_name=body.display_name),
        settings,
    )
    now = utcnow()
    assignment = RoleAssignment(
        id=uuid7(),
        tenant_id=tenant.id,
        subject_type="user",
        subject_id=row.id,
        role_id=role.id,
        scope_type="tenant",
        scope_id=SCOPE_ALL,
        granted_by=current.user_id,
        grant_reason=body.reason,
        is_active=True,
        valid_from=now.date(),
        valid_to=None,
        created_by=current.user_id,
        updated_by=current.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(assignment)
    await db.flush()
    record(
        db,
        target,
        action="role_assignment.granted",
        entity="role_assignment",
        entity_id=assignment.id,
        reason=body.reason,
    )
    invitation = await db.scalar(
        select(UserInvitation).where(
            UserInvitation.user_id == row.id, UserInvitation.status == "pending"
        )
    )
    return receipt(row, assignment, settings, invitation)


async def change(
    db: AsyncSession,
    current: Actor,
    row: User,
    assignment: RoleAssignment,
    body: AdministratorCommand,
    settings: Settings,
) -> AdministratorReceipt:
    if (
        row.updated_at != body.expected_updated_at
        or assignment.updated_at != body.expected_assignment_updated_at
    ):
        raise ConflictError("administrator details changed; refresh and review before trying again")
    if row.status not in {"active", "invited", "suspended"}:
        raise ConflictError("this administrator account cannot be changed")
    target = Actor(row.tenant_id, current.user_id)
    invitation = None
    if body.action in {"suspend", "revoke"} and await last_active(db, row, assignment):
        raise ConflictError(
            "activate another administrator before removing the last active administrator"
        )
    if body.action == "edit":
        assert body.display_name is not None
        row.display_name = body.display_name
    elif body.action == "suspend":
        if row.status != "active":
            raise ConflictError("only an active administrator can be suspended")
        row.status = "suspended"
    elif body.action == "restore":
        if row.status == "suspended":
            row.status = "active"
        assignment.is_active, assignment.deactivated_at, assignment.deactivated_by = (
            True,
            None,
            None,
        )
        assignment.valid_from, assignment.valid_to = utcnow().date(), None
        assignment.granted_by, assignment.grant_reason = current.user_id, body.reason
    elif body.action == "revoke":
        assignment.is_active, assignment.deactivated_at, assignment.deactivated_by = (
            False,
            utcnow(),
            current.user_id,
        )
        # Pending invitations must not activate an account with a revoked bootstrap grant.
        if row.status == "invited":
            for pending in await db.scalars(
                select(UserInvitation).where(
                    UserInvitation.user_id == row.id, UserInvitation.status == "pending"
                )
            ):
                pending.status, pending.cancelled_at, pending.updated_by = (
                    "cancelled",
                    utcnow(),
                    current.user_id,
                )
                record(
                    db,
                    target,
                    action="user.invitation_cancelled",
                    entity="user_invitation",
                    entity_id=pending.id,
                    reason=body.reason,
                )
    else:
        if not assignment.is_active:
            raise ConflictError(
                "restore the administrator assignment before resending an invitation"
            )
        from identity.services.invitations import issue_invitation

        invitation = await issue_invitation(db, target, row, settings)
    now = utcnow()
    row.updated_at, row.updated_by = now, current.user_id
    assignment.updated_at, assignment.updated_by = now, current.user_id
    record(
        db,
        target,
        action="user.updated" if body.action == "edit" else "user.lifecycle_changed",
        entity="user",
        entity_id=row.id,
        reason=body.reason,
        changes={"fields": ["display_name"]} if body.action == "edit" else {"status": row.status},
    )
    if body.action in {"revoke", "restore"}:
        record(
            db,
            target,
            action="role_assignment.revoked"
            if body.action == "revoke"
            else "role_assignment.regranted",
            entity="role_assignment",
            entity_id=assignment.id,
            reason=body.reason,
        )
    await db.flush()
    return receipt(row, assignment, settings, invitation)
