"""Enrollment is committed with authorised company creation, not by Catalog itself."""

import uuid

from billing_platform.authz import ScopePath
from billing_platform.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from billing_platform.pagination import CursorCodec
from billing_platform.service_auth import CompanyServiceScope
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.config import Settings
from identity.models.catalog_enrollment import CatalogSourceEnrollment
from identity.models.company import Company
from identity.models.platform_installation import PlatformInstallation
from identity.models.tenant import Tenant
from identity.schemas.catalog_enrollment import EnrollmentPage, EnrollmentQuery
from identity.services.audit import record


async def enroll_created_company(db: AsyncSession, current: Actor, company: Company) -> None:
    current.require_scope("company.create", target=ScopePath())
    if (
        company.tenant_id != current.tenant_id
        or company.created_by != current.user_id
        or company.status != "active"
    ):
        raise PermissionDeniedError("Catalog enrollment requires an authorised new company")
    row = CatalogSourceEnrollment(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company.id,
        created_by=current.user_id,
        updated_by=current.user_id,
        is_active=True,
    )
    db.add(row)
    record(
        db,
        current,
        action="catalog_source.enrolled",
        entity="catalog_source_enrollment",
        entity_id=row.id,
        company_id=company.id,
        changes={"is_active": {"from": None, "to": True}},
    )
    await db.flush()


def active_enrollments() -> Select[tuple[CatalogSourceEnrollment]]:
    return (
        select(CatalogSourceEnrollment)
        .join(
            Company,
            (Company.id == CatalogSourceEnrollment.company_id)
            & (Company.tenant_id == CatalogSourceEnrollment.tenant_id),
        )
        .join(Tenant, Tenant.id == CatalogSourceEnrollment.tenant_id)
        .where(
            CatalogSourceEnrollment.is_active.is_(True),
            Company.status == "active",
            Tenant.status == "active",
        )
    )


async def is_enrolled(db: AsyncSession, company_id: uuid.UUID) -> bool:
    # Caller establishes tenant_scope; all three models retain session-level isolation.
    return (
        await db.scalar(
            active_enrollments().where(CatalogSourceEnrollment.company_id == company_id)
        )
        is not None
    )


async def discover_enrollments(
    db: AsyncSession, settings: Settings, *, key_id: str, query: EnrollmentQuery
) -> EnrollmentPage:
    credential = settings.catalog_source_credentials[key_id]
    if not credential.allow_enrolled_companies:
        raise PermissionDeniedError("enrollment discovery is not authorised")
    codec = CursorCodec(
        settings.cursor_signing_secret.get_secret_value().encode(),
        context=f"catalog-enrollments:v1:{key_id}:{query.limit}",
    )
    statement = active_enrollments()
    if query.cursor is not None:
        values = codec.decode(query.cursor)
        try:
            if set(values) != {"after"}:
                raise ValueError
            after = uuid.UUID(values["after"])
            if after.int == 0:
                raise ValueError
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationFailedError("invalid enrollment discovery cursor") from exc
        statement = statement.where(CatalogSourceEnrollment.id > after)
    rows = list(
        await db.scalars(statement.order_by(CatalogSourceEnrollment.id).limit(query.limit + 1))
    )
    visible = rows[: query.limit]
    cursor = codec.encode({"after": str(visible[-1].id)}) if len(rows) > query.limit else None
    evidence_id = uuid7()
    operating_tenant = await db.scalar(
        select(PlatformInstallation.tenant_id).where(
            PlatformInstallation.key == "platform", PlatformInstallation.completed_at.is_not(None)
        )
    )
    if operating_tenant is None or operating_tenant.int == 0:
        raise NotFoundError("platform setup has not been completed")
    emit(
        db,
        tenant_id=operating_tenant,
        aggregate_type="catalog_source_enrollment",
        aggregate_id=evidence_id,
        event_type="catalog_source.discovery_read",
        payload=audit_payload(
            action="catalog_source.discovery_read",
            category="security",
            entity_type="catalog_source_enrollment",
            entity_id=evidence_id,
            actor_user_id=None,
            changes={"scope_count": {"from": None, "to": len(visible)}},
        ),
    )
    return EnrollmentPage(
        scopes=tuple(
            CompanyServiceScope(tenant_id=row.tenant_id, company_id=row.company_id)
            for row in visible
        ),
        next_cursor=cursor,
    )
