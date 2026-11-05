"""Shared atomic bootstrap: one tenant, one administrator, fixed system grant."""

from __future__ import annotations

import uuid
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.reference_models import Country, Currency, State
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.config import Settings
from identity.models import Language, Role, RoleAssignment, Tenant, Timezone, User
from identity.schemas.base import StrictModel
from identity.services.audit import record
from identity.services.invitations import issue_invitation
from identity.services.reference_availability import lock_configuration, require_delivered


async def validate_defaults(
    db: AsyncSession,
    country_code: str,
    currency_code: str,
    timezone: str,
    locale: str,
    state_code: str | None = None,
) -> None:
    await lock_configuration(db)
    for kind, code in [
        ("currency", currency_code),
        ("country", country_code),
        ("state", state_code),
        ("language", locale),
    ]:
        if code is not None:
            model: Any = {
                "currency": Currency,
                "country": Country,
                "state": State,
                "language": Language,
            }[kind]
            await db.scalar(select(model).where(model.code == code).with_for_update())
            await require_delivered(db, kind, code)
    country, currency = await db.get(Country, country_code), await db.get(Currency, currency_code)
    if country is None or not country.is_active or currency is None or not currency.is_active:
        raise ValidationFailedError("choose an active country and currency")
    if state_code is not None:
        state = await db.get(State, state_code)
        if state is None or not state.is_active or state.country_code != country_code:
            raise ValidationFailedError(
                "choose an active state belonging to this country",
                fields={"state_code": "unknown, inactive or mismatched state"},
            )
    language, zone = await db.get(Language, locale), await db.get(Timezone, timezone)
    if language is None or not language.is_active:
        raise ValidationFailedError(
            "choose an active language", fields={"locale": "unknown or inactive language"}
        )
    if zone is None or not zone.is_active:
        raise ValidationFailedError(
            "choose an active timezone", fields={"timezone": "unknown or inactive timezone"}
        )
    try:
        ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValidationFailedError("unknown timezone") from exc


async def resolve_defaults(db: AsyncSession, data: dict[str, object]) -> dict[str, str]:
    """Creation policy lives here, not in browser defaults or client timezones."""
    country = await db.get(Country, data["country_code"])
    if country is None or not country.is_active:
        raise ValidationFailedError("choose an active country", fields={"country_code": "inactive"})
    return {
        "currency_code": str(data.get("currency_code") or country.default_currency_code),
        "timezone": str(
            data.get("timezone") or ("Asia/Kolkata" if country.code == "IN" else "UTC")
        ),
        "locale": str(data.get("locale") or "en"),
    }


async def create_tenant(
    db: AsyncSession,
    body: StrictModel,
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
    subject: str | None = None,
) -> Tenant:
    data = body.model_dump(exclude={"administrator_password"})
    data.update(await resolve_defaults(db, data))
    await validate_defaults(
        db,
        data["country_code"],
        data["currency_code"],
        data["timezone"],
        data["locale"],
        data.get("state_code"),
    )
    slug = "workspace-" + tenant_id.hex
    with unfiltered():
        if await db.scalar(select(Tenant.id).where(Tenant.slug == slug)) is not None:
            raise ConflictError("tenant slug is already in use")
        role = await db.scalar(
            select(Role).where(
                Role.tenant_id == SCOPE_ALL,
                Role.key == "tenant_admin",
                Role.is_active.is_(True),
            )
        )
    if role is None:
        raise ConflictError("seed system roles before tenant provisioning")
    now = utcnow()
    with tenant_scope(tenant_id):
        tenant = Tenant(
            id=tenant_id,
            name=data["name"],
            slug=slug,
            status="active",
            primary_contact_email=data["administrator_email"],
            default_country_code=data["country_code"],
            default_state_code=data.get("state_code"),
            default_currency_code=data["currency_code"],
            default_locale=data["locale"],
            default_timezone=data["timezone"],
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(tenant)
        await db.flush()
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            authentik_sub=subject,
            first_name=data["administrator_name"],
            display_name=data["administrator_name"],
            email=data["administrator_email"],
            user_type="tenant_user",
            locale=data["locale"],
            timezone=data["timezone"],
            status="active" if subject else "invited",
            email_verified_at=now if subject else None,
            activated_at=now if subject else None,
            invited_at=None if subject else now,
            invited_by=None if subject else actor_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(user)
        await db.flush()
        assignment = RoleAssignment(
            id=uuid7(),
            tenant_id=tenant_id,
            subject_type="user",
            subject_id=user.id,
            role_id=role.id,
            scope_type="tenant",
            scope_id=SCOPE_ALL,
            is_active=True,
            valid_from=now.date(),
            granted_by=actor_id,
            grant_reason="initial administrator bootstrap",
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(assignment)
        current = Actor(tenant_id, actor_id)
        for action, entity, identifier in [
            ("tenant.provisioned", "tenant", tenant_id),
            ("user.activated" if subject else "user.invited", "user", user_id),
            ("role_assignment.granted", "role_assignment", assignment.id),
        ]:
            record(
                db,
                current,
                action=action,
                entity=entity,
                entity_id=identifier,
                reason="initial administrator bootstrap",
            )
        if not subject:
            await issue_invitation(db, current, user, settings)
        await db.flush()
        return tenant
