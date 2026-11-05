import uuid
from typing import TypeVar

from billing_platform.db.access import company_object
from billing_platform.db.base import Base
from billing_platform.db.claims import insert_candidate
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reports.events.audit_contract import AUDIT_EVENTS
from reports.models import core as m

T = TypeVar("T", bound=Base)


async def get(
    db: AsyncSession, company: uuid.UUID, model: type[T], identity: uuid.UUID, *, lock: bool = False
) -> T:
    return await company_object(db, model, identity, company_id=company, lock=lock)


async def company_lock(db: AsyncSession, tenant: uuid.UUID, company: uuid.UUID) -> m.ReportCompany:
    await insert_candidate(
        db,
        m.ReportCompany,
        {"id": uuid7(), "tenant_id": tenant, "company_id": company, "row_version": 1},
    )
    row = await db.scalar(
        select(m.ReportCompany).where(m.ReportCompany.company_id == company).with_for_update()
    )
    assert row is not None
    return row


def audit(
    db: AsyncSession,
    tenant: uuid.UUID,
    company: uuid.UUID,
    identity: uuid.UUID,
    action: str,
    actor: uuid.UUID | None = None,
) -> None:
    event = "reports.report." + action
    if event not in AUDIT_EVENTS:
        raise ValueError("undeclared report audit event")
    emit(
        db,
        aggregate_type="reports.report",
        aggregate_id=identity,
        event_type=event,
        tenant_id=tenant,
        payload=audit_payload(
            action=event,
            category="access" if action == "exported" else "admin",
            entity_type="reports.report",
            entity_id=identity,
            actor_user_id=actor,
            company_id=company,
            changes={},
        )
        | {"actor_type": "user" if actor else "system", "source_service": "reports"},
    )
