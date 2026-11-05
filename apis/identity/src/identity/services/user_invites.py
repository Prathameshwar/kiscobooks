"""Shared invitation creation; each route checks its own object authority first."""

from __future__ import annotations

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor
from identity.config import Settings
from identity.models import Company, User
from identity.schemas.user import UserInvite


async def create_invited_user(
    db: AsyncSession, current: Actor, body: UserInvite, settings: Settings
) -> User:
    existing = await db.scalar(select(User.id).where(User.email == body.email))
    if existing is not None:
        raise ConflictError("a user with this email already exists in this tenant")
    if body.default_company_id is not None:
        company = await db.get(Company, body.default_company_id)
        if company is None or company.status != "active":
            raise ValidationFailedError(
                "unknown company", fields={"default_company_id": "not found in this tenant"}
            )
    if body.reporting_manager_id is not None:
        manager = await db.get(User, body.reporting_manager_id)
        if manager is None or manager.status != "active":
            raise ValidationFailedError(
                "unknown manager", fields={"reporting_manager_id": "not found in this tenant"}
            )

    display = body.display_name or " ".join(
        part for part in (body.first_name, body.last_name) if part
    )
    now = utcnow()
    row = User(
        id=uuid7(),
        tenant_id=current.tenant_id,
        authentik_sub=None,
        user_type=body.user_type,
        salutation=body.salutation,
        first_name=body.first_name,
        middle_name=body.middle_name,
        last_name=body.last_name,
        display_name=display,
        email=body.email,
        email_verified_at=None,
        phone_country_code=body.phone_country_code,
        phone=body.phone,
        phone_verified_at=None,
        employee_code=body.employee_code,
        job_title=body.job_title,
        reporting_manager_id=body.reporting_manager_id,
        default_company_id=body.default_company_id,
        default_department_id=None,
        date_of_joining=body.date_of_joining,
        date_of_exit=None,
        locale=None,
        timezone=None,
        date_format=None,
        datetime_format=None,
        digit_grouping=None,
        currency_display=None,
        theme=None,
        landing_page=None,
        status="invited",
        invited_by=current.user_id,
        invited_at=now,
        activated_at=None,
        last_active_at=None,
        deactivated_at=None,
        deactivated_by=None,
        deactivation_reason=None,
        anonymized_at=None,
        terms_accepted_at=None,
        terms_version=None,
        privacy_accepted_at=None,
        custom_fields=None,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(row)
    await db.flush()
    emit(
        db,
        aggregate_type="user",
        aggregate_id=row.id,
        event_type="user.invited",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="user.invited",
            entity_type="user",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
        ),
    )
    from identity.services.invitations import issue_invitation

    await issue_invitation(db, current, row, settings)
    return row
