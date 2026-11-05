"""Company-scoped commercial salesperson master."""

import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor, actor
from identity.api.common import load_company
from identity.api.dependencies import session
from identity.api.listing import cursor_codec, keyset_page
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import CommercialSalesperson, Membership, User
from identity.schemas.base import PageMeta
from identity.schemas.commercial_salesperson import (
    SalespersonCreate,
    SalespersonItem,
    SalespersonPage,
    SalespersonUpdate,
)

router = APIRouter(
    prefix="/v1/companies/{company_id}/salespeople",
    responses=ERROR_RESPONSES,
    route_class=StrictRoute,
)


async def _linked_user(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
    if user_id is None:
        return
    user = await db.get(User, user_id)
    member = await db.scalar(
        select(Membership.id)
        .where(
            Membership.company_id == company_id,
            Membership.user_id == user_id,
            Membership.is_active.is_(True),
        )
        .limit(1)
    )
    if user is None or user.status != "active" or member is None:
        raise ValidationFailedError("salesperson user must be an active company member")


async def _row(
    db: AsyncSession, company_id: uuid.UUID, object_id: uuid.UUID
) -> CommercialSalesperson:
    row = await db.get(CommercialSalesperson, object_id)
    if row is None or row.company_id != company_id:
        raise NotFoundError("salesperson not found")
    return row


def _event(db: AsyncSession, current: Actor, row: CommercialSalesperson, action: str) -> None:
    event = f"salesperson.{action}"
    emit(
        db,
        aggregate_type="salesperson",
        aggregate_id=row.id,
        event_type=event,
        tenant_id=current.tenant_id,
        payload=audit_payload(
            company_id=row.company_id,
            action=event,
            entity_type="salesperson",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
        ),
    )


@router.post("", response_model=SalespersonItem, status_code=status.HTTP_201_CREATED)
async def create_salesperson(
    company_id: uuid.UUID,
    body: SalespersonCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CommercialSalesperson:
    current.require_scope("company.update", target=ScopePath(company_id=company_id))
    company = await load_company(db, company_id)
    if company.status != "active":
        raise ConflictError("company is inactive")
    await _linked_user(db, company_id, body.user_id)
    if (
        await db.scalar(
            select(CommercialSalesperson.id).where(
                CommercialSalesperson.company_id == company_id,
                CommercialSalesperson.code == body.code,
            )
        )
        is not None
    ):
        raise ConflictError("salesperson code already exists")
    now = utcnow()
    row = CommercialSalesperson(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company_id,
        code=body.code,
        name=body.name,
        user_id=body.user_id,
        is_active=True,
        row_version=1,
        created_at=now,
        updated_at=now,
        created_by=current.user_id,
        updated_by=current.user_id,
    )
    db.add(row)
    _event(db, current, row, "created")
    await db.flush()
    return row


@router.get("", response_model=SalespersonPage)
async def list_salespeople(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
) -> SalespersonPage:
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    await load_company(db, company_id)
    rows, next_cursor, has_more = await keyset_page(
        db,
        select(CommercialSalesperson).where(CommercialSalesperson.company_id == company_id),
        model=CommercialSalesperson,
        projection=SalespersonItem,
        page=PageRequest(limit, cursor),
        sort="code",
        allowed=frozenset({"code"}),
        default="code",
        codec=cursor_codec(request, "salespeople"),
    )
    return SalespersonPage(
        items=[SalespersonItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/{salesperson_id}", response_model=SalespersonItem)
async def get_salesperson(
    company_id: uuid.UUID,
    salesperson_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CommercialSalesperson:
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    await load_company(db, company_id)
    return await _row(db, company_id, salesperson_id)


@router.patch("/{salesperson_id}", response_model=SalespersonItem)
async def update_salesperson(
    company_id: uuid.UUID,
    salesperson_id: uuid.UUID,
    body: SalespersonUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CommercialSalesperson:
    current.require_scope("company.update", target=ScopePath(company_id=company_id))
    await load_company(db, company_id)
    row = await _row(db, company_id, salesperson_id)
    if row.row_version != body.expected_version:
        raise ConflictError("salesperson changed; reload before retrying")
    if "user_id" in body.model_fields_set:
        await _linked_user(db, company_id, body.user_id)
        row.user_id = body.user_id
    if body.name is not None:
        row.name = body.name
    if body.is_active is not None:
        row.is_active = body.is_active
    row.row_version += 1
    row.updated_at = utcnow()
    row.updated_by = current.user_id
    _event(db, current, row, "updated")
    await db.flush()
    return row
