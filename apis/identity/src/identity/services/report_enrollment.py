"""Report-purpose enrollment, separate from Catalog provisioning authority."""

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Company, ReportSourceEnrollment, Tenant


def eligible(*, retained: bool = False) -> Select[tuple[ReportSourceEnrollment]]:
    query = (
        select(ReportSourceEnrollment)
        .join(
            Company,
            (Company.id == ReportSourceEnrollment.company_id)
            & (Company.tenant_id == ReportSourceEnrollment.tenant_id),
        )
        .join(Tenant, Tenant.id == ReportSourceEnrollment.tenant_id)
        .where(Tenant.status == "active")
    )
    if retained:
        return query.where(ReportSourceEnrollment.status.in_(("ACTIVE", "RETAINED")))
    return query.where(ReportSourceEnrollment.status == "ACTIVE", Company.status == "active")


async def is_enrolled(db: AsyncSession, company: uuid.UUID, *, retained: bool = False) -> bool:
    return (
        await db.scalar(
            eligible(retained=retained).where(ReportSourceEnrollment.company_id == company)
        )
        is not None
    )
