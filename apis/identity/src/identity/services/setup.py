"""Key-gated, atomic first-administrator bootstrap. No general provisioning bypass."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    PermissionDeniedError,
)
from billing_platform.ids import uuid7
from billing_platform.oidc import VerifiedClaims
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.config import Settings
from identity.models import Role, RoleAssignment, Tenant, User
from identity.models.platform_installation import PlatformInstallation
from identity.schemas.base import looks_like_email
from identity.schemas.setup import SetupRequest, SetupResult, SetupStatus
from identity.services.audit import record
from identity.services.tenant_provisioning import validate_defaults


def check_key(settings: Settings, supplied: str | None) -> None:
    expected = settings.setup_key
    if (
        expected is None
        or supplied is None
        or not hmac.compare_digest(expected.get_secret_value().encode(), supplied.encode())
    ):
        raise PermissionDeniedError("a valid installation setup key is required")


def check_administrator(claims: VerifiedClaims) -> str:
    if claims.auth_time is None or not 0 <= time.time() - claims.auth_time <= 300:
        raise AuthenticationRequiredError("sign in again to complete platform setup")
    if not claims.email_verified or not claims.email:
        raise PermissionDeniedError("a verified identity-provider email is required")
    try:
        return looks_like_email(claims.email)
    except ValueError as exc:
        raise PermissionDeniedError("a verified identity-provider email is required") from exc


async def status(db: AsyncSession, settings: Settings) -> SetupStatus:
    row = await db.scalar(
        select(PlatformInstallation).where(PlatformInstallation.key == "platform")
    )
    completed = row is not None and row.completed_at is not None
    with unfiltered():
        existing = await db.scalar(select(Tenant.id).limit(1))
    return SetupStatus(
        available=row is not None
        and not completed
        and existing is None
        and settings.setup_key is not None,
        completed=completed,
    )


async def provision(db: AsyncSession, body: SetupRequest, claims: VerifiedClaims) -> SetupResult:
    email = check_administrator(claims)
    digest = hashlib.sha256(
        json.dumps(
            {**body.model_dump(), "subject": claims.sub, "email": email},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    row = await db.scalar(
        select(PlatformInstallation).where(PlatformInstallation.key == "platform").with_for_update()
    )
    if row is None:
        raise ConflictError("run the Identity installation command before setup")
    if row.completed_at is not None:
        if row.administrator_subject != claims.sub or row.request_hash != digest:
            raise ConflictError("platform setup has already completed")
        assert (
            row.tenant_id is not None and row.administrator_id is not None and row.name is not None
        )
        return SetupResult(
            tenant_id=row.tenant_id, administrator_id=row.administrator_id, platform_name=row.name
        )
    if claims.org_id is not None:
        raise PermissionDeniedError("tenant-bound identities cannot bootstrap the platform")
    with unfiltered():
        if await db.scalar(select(Tenant.id).limit(1)) is not None:
            raise ConflictError("existing installations cannot use first-run setup")
        role = await db.scalar(
            select(Role).where(
                Role.tenant_id == SCOPE_ALL, Role.key == "platform_admin", Role.is_active.is_(True)
            )
        )
    if role is None:
        raise ConflictError("seed system roles before setup")
    await validate_defaults(db, body.country_code, body.currency_code, body.timezone, body.locale)
    tenant_id, user_id, assignment_id = uuid7(), uuid7(), uuid7()
    now = utcnow()
    with tenant_scope(tenant_id):
        db.add(
            Tenant(
                id=tenant_id,
                name=body.workspace_name.strip(),
                slug=body.workspace_slug,
                status="active",
                primary_contact_email=email,
                default_country_code=body.country_code,
                default_currency_code=body.currency_code,
                default_locale=body.locale,
                default_timezone=body.timezone,
                created_by=user_id,
                updated_by=user_id,
            )
        )
        await db.flush()
        db.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                authentik_sub=claims.sub,
                user_type="platform_admin",
                status="active",
                first_name=body.administrator_name.strip(),
                display_name=body.administrator_name.strip(),
                email=email,
                email_verified_at=now,
                locale=body.locale,
                timezone=body.timezone,
                created_by=user_id,
                updated_by=user_id,
            )
        )
        await db.flush()
        db.add(
            RoleAssignment(
                id=assignment_id,
                tenant_id=tenant_id,
                subject_type="user",
                subject_id=user_id,
                role_id=role.id,
                scope_type="tenant",
                scope_id=SCOPE_ALL,
                is_active=True,
                valid_from=now.date(),
                granted_by=user_id,
                grant_reason="first-run platform administrator bootstrap",
                created_by=user_id,
                updated_by=user_id,
            )
        )
        current = Actor(tenant_id, user_id)
        for action, entity, entity_id in (
            ("tenant.provisioned", "tenant", tenant_id),
            ("user.activated", "user", user_id),
            ("role_assignment.granted", "role_assignment", assignment_id),
            ("platform.setup_completed", "platform_installation", row.id),
        ):
            record(
                db,
                current,
                action=action,
                entity=entity,
                entity_id=entity_id,
                reason="first-run installation",
            )
        row.name, row.public_url = body.platform_name.strip(), body.public_url
        row.completed_at, row.tenant_id = now, tenant_id
        row.administrator_id, row.administrator_subject = user_id, claims.sub
        row.request_hash = digest
        await db.flush()
    return SetupResult(tenant_id=tenant_id, administrator_id=user_id, platform_name=row.name)
