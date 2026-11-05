"""The audit read surfaces (docs/audit.md §1, §5) — all thin, all deny-by-default.

Four surfaces, three permissions:

* ``GET /v1/audit-events`` (``audit.read``) — the audit trail, every category **except**
  ``security``, which is gated separately (§5.1).
* ``GET /v1/audit-events/security`` (``audit.read_security``) — the ``security`` category
  only.
* ``GET /v1/audit-events/{id}`` (``audit.read`` / ``audit.read_security`` by the row's
  category) — one event in full, including the before/after values and chain proof.
* ``GET /v1/activity`` (``activity.read``) — the friendlier feed, non-security.
* ``POST /v1/audit-events/export`` (``audit.export``) — a bounded export that is **itself
  recorded as an ``access`` event** (§5.3), staged on the outbox so it flows through the
  single chain writer.

Object-level scope (CLAUDE.md §5.2): a tenant-wide read needs the permission at *tenant*
scope; a company-scoped reader must name ``company_id`` and holds only that company's
trail. The session-level tenant filter already makes another tenant's rows invisible; this
guards the wrong *company within the same tenant*.
"""

from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import NotFoundError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from audit.api.auth import Actor, actor
from audit.api.dependencies import session
from audit.api.evidence import visible_changes, visible_context
from audit.api.listing import cursor_codec, keyset_page
from audit.api.query import validate_query
from audit.api.schemas import (
    ActivityItem,
    ActivityPage,
    AuditEventDetail,
    AuditEventItem,
    AuditEventPage,
    ExportResult,
    IntegrationLogCreate,
    IntegrationLogItem,
    IntegrationLogPage,
    PageMeta,
)
from audit.domain.categories import CATEGORIES, SECURITY_CATEGORY
from audit.models import AuditEvent, IntegrationLog

router = APIRouter(prefix="/v1", dependencies=[Depends(validate_query)])

_SORTABLE = frozenset({"occurred_at", "sequence"})
_DEFAULT_SORT = "-occurred_at"
#: The export never streams the whole table inline; a run past this is truncated and says
#: so, and the caller narrows the filter (the signed-URL bulk path is the deployment hook).
_EXPORT_CAP = 5000


def _row_scope(event: AuditEvent) -> ScopePath:
    """The object scope of one event, for the per-row object-level check."""
    if event.company_id is None:
        return ScopePath()
    if event.department_id is not None:
        return ScopePath(company_id=event.company_id, department_id=event.department_id)
    return ScopePath(company_id=event.company_id)


def _query_scope(company_id: uuid.UUID | None) -> ScopePath:
    """The scope a *list* read is asserted against — tenant-wide unless a company is named."""
    return ScopePath() if company_id is None else ScopePath(company_id=company_id)


def _apply_filters(
    statement: Select[tuple[AuditEvent]],
    *,
    company_id: uuid.UUID | None,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    action: str | None,
    occurred_from: dt.datetime | None,
    occurred_to: dt.datetime | None,
) -> Select[tuple[AuditEvent]]:
    """Typed, allowlisted filters only (api-conventions §list) — never free-form."""
    realm = AuditEvent.context["notification_realm"].as_string()
    statement = statement.where(
        or_(AuditEvent.source_service != "notification", realm.is_(None), realm != "platform")
    )
    if occurred_from and occurred_to and occurred_from >= occurred_to:
        raise ValidationFailedError("occurred_from must precede occurred_to")
    if company_id is not None:
        statement = statement.where(AuditEvent.company_id == company_id)
    if entity_type is not None:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        statement = statement.where(AuditEvent.entity_id == entity_id)
    if action is not None:
        statement = statement.where(AuditEvent.action == action)
    if occurred_from is not None:
        statement = statement.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        statement = statement.where(AuditEvent.occurred_at < occurred_to)
    return statement


@router.get("/audit-events", response_model=AuditEventPage)
async def list_audit_events(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    company_id: uuid.UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None, max_length=80),
    entity_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=60),
    category: str | None = Query(default=None, max_length=20),
    occurred_from: AwareDatetime | None = Query(default=None),
    occurred_to: AwareDatetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    sort: str = Query(default=_DEFAULT_SORT),
) -> AuditEventPage:
    current.require("audit.read")
    current.require_scope("audit.read", target=_query_scope(company_id))
    current.require_audit_scope(company_id)

    if category is not None:
        if category == SECURITY_CATEGORY:
            # Security is a separate surface with its own permission (§5.1).
            raise ValidationFailedError(
                "security events are read via /v1/audit-events/security",
                fields={"category": "not readable on the general trail"},
            )
        if category not in CATEGORIES:
            raise ValidationFailedError(
                "unknown category", fields={"category": f"one of {', '.join(sorted(CATEGORIES))}"}
            )

    statement = select(AuditEvent).where(AuditEvent.category != SECURITY_CATEGORY)
    if category is not None:
        statement = statement.where(AuditEvent.category == category)
    statement = _apply_filters(
        statement,
        company_id=company_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
    )

    statement = statement.options(
        load_only(
            *(getattr(AuditEvent, key) for key in set(AuditEventItem.model_fields) | {"sequence"})
        )
    )
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=AuditEvent,
        page=PageRequest(limit=limit, cursor=cursor),
        sort=sort,
        allowed=_SORTABLE,
        default=_DEFAULT_SORT,
        codec=cursor_codec(request, "audit-events", current),
    )
    return AuditEventPage(
        items=[AuditEventItem.model_validate(r) for r in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/audit-events/security", response_model=AuditEventPage)
async def list_security_events(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    company_id: uuid.UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None, max_length=80),
    entity_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=60),
    occurred_from: AwareDatetime | None = Query(default=None),
    occurred_to: AwareDatetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    sort: str = Query(default=_DEFAULT_SORT),
) -> AuditEventPage:
    current.require("audit.read_security")
    current.require_scope("audit.read_security", target=_query_scope(company_id))
    current.require_audit_scope(company_id)

    statement = select(AuditEvent).where(AuditEvent.category == SECURITY_CATEGORY)
    statement = _apply_filters(
        statement,
        company_id=company_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
    )
    statement = statement.options(
        load_only(
            *(getattr(AuditEvent, key) for key in set(AuditEventItem.model_fields) | {"sequence"})
        )
    )
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=AuditEvent,
        page=PageRequest(limit=limit, cursor=cursor),
        sort=sort,
        allowed=_SORTABLE,
        default=_DEFAULT_SORT,
        codec=cursor_codec(request, "audit-events-security", current),
    )
    return AuditEventPage(
        items=[AuditEventItem.model_validate(r) for r in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/activity", response_model=ActivityPage)
async def list_activity(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    company_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    sort: str = Query(default=_DEFAULT_SORT),
) -> ActivityPage:
    current.require("activity.read")
    current.require_scope("activity.read", target=_query_scope(company_id))
    current.require_audit_scope(company_id)

    statement = select(AuditEvent).where(AuditEvent.category != SECURITY_CATEGORY)
    if company_id is not None:
        statement = statement.where(AuditEvent.company_id == company_id)
    realm = AuditEvent.context["notification_realm"].as_string()
    statement = statement.where(
        or_(AuditEvent.source_service != "notification", realm.is_(None), realm != "platform")
    )

    statement = statement.options(
        load_only(
            *(getattr(AuditEvent, key) for key in set(ActivityItem.model_fields) | {"sequence"})
        )
    )
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=AuditEvent,
        page=PageRequest(limit=limit, cursor=cursor),
        sort=sort,
        allowed=_SORTABLE,
        default=_DEFAULT_SORT,
        codec=cursor_codec(request, "activity", current),
    )
    return ActivityPage(
        items=[ActivityItem.model_validate(r) for r in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


def _detail(event: AuditEvent, current: Actor) -> AuditEventDetail:
    return AuditEventDetail(
        id=event.id,
        occurred_at=event.occurred_at,
        sequence=event.sequence,
        category=event.category,
        action=event.action,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        actor_type=event.actor_type,
        actor_user_id=event.actor_user_id,
        on_behalf_of_user_id=event.on_behalf_of_user_id,
        actor_ip=event.actor_ip,
        actor_user_agent=event.actor_user_agent,
        api_client_id=event.api_client_id,
        company_id=event.company_id,
        department_id=event.department_id,
        changes=visible_changes(event, current),
        context=visible_context(event),
        reason=(
            None
            if event.entity_type.startswith(("accounting.", "catalog.", "vouchers."))
            else event.reason
        ),
        source_service=event.source_service,
        trace_id=event.trace_id,
        request_id=event.request_id,
        message_id=event.message_id,
        prev_hash=event.prev_hash.hex() if event.prev_hash is not None else None,
        row_hash=event.row_hash.hex(),
    )


@router.get("/audit-events/{event_id}", response_model=AuditEventDetail)
async def get_audit_event(
    event_id: uuid.UUID,
    company_id: uuid.UUID | None = Query(default=None),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    occurred_at: AwareDatetime = Query(
        ...,
        description=(
            "The event's occurred_at (from the list item). Required so the lookup prunes "
            "to one monthly partition instead of scanning the largest table in the system."
        ),
    ),
) -> AuditEventDetail:
    # Endpoint gate first: a caller holding no audit read permission at all gets a fast 403,
    # consistent with the list surfaces, before any row is read.
    if not (current.permissions & {"audit.read", "audit.read_security"}):
        current.require("audit.read")

    event = await db.scalar(
        select(AuditEvent).where(AuditEvent.id == event_id, AuditEvent.occurred_at == occurred_at)
    )
    if event is None or (
        event.source_service == "notification"
        and (event.context or {}).get("notification_realm") == "platform"
    ):
        raise NotFoundError("audit event not found")

    # Category decides which permission is required; scope decides whether it reaches *this*
    # company's row (§5.2). Both, every time. A reader who lacks the permission for this row's
    # category (e.g. only ``audit.read`` for a ``security`` row) must not be able to tell it
    # exists — return 404, not 403, so the endpoint is not an existence oracle for security
    # events. Scope denial stays 403, matching the list surfaces.
    permission = "audit.read_security" if event.category == SECURITY_CATEGORY else "audit.read"
    if permission not in current.permissions:
        raise NotFoundError("audit event not found")
    current.require_scope(permission, target=_row_scope(event))
    current.require_audit_scope(event.company_id)
    if company_id is not None and company_id != event.company_id:
        raise NotFoundError("audit event not found")
    return _detail(event, current)


@router.post("/audit-events/export", response_model=ExportResult)
async def export_audit_events(
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    company_id: uuid.UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None, max_length=80),
    entity_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=60),
    category: str | None = Query(default=None, max_length=20),
    occurred_from: AwareDatetime | None = Query(default=None),
    occurred_to: AwareDatetime | None = Query(default=None),
) -> ExportResult:
    current.require("audit.export")
    current.require_scope("audit.export", target=_query_scope(company_id))
    current.require_audit_scope(company_id)

    # An export never silently includes security rows; those need read_security and a
    # dedicated run. The trail export is the non-security categories.
    statement = (
        _apply_filters(
            select(AuditEvent).where(AuditEvent.category != SECURITY_CATEGORY),
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
        .order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc())
        .limit(_EXPORT_CAP + 1)
    )

    if category is not None:
        if category not in CATEGORIES or category == SECURITY_CATEGORY:
            raise ValidationFailedError("category is not available on this export")
        statement = statement.where(AuditEvent.category == category)
    rows = list((await db.scalars(statement)).all())
    truncated = len(rows) > _EXPORT_CAP
    rows = rows[:_EXPORT_CAP]

    # The export is itself an access event (§5.3). Staged on the outbox in this same
    # transaction, so it flows back through the single chain writer rather than being
    # written straight to audit_event — one writer, one chain (§4.2, invariant 8/10).
    export_id = uuid7()
    emit(
        db,
        aggregate_type="audit_event",
        aggregate_id=export_id,
        event_type="audit.exported",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="audit.exported",
            company_id=company_id,
            category="access",
            entity_type="audit_event",
            entity_id=export_id,
            actor_user_id=current.user_id,
            changes=None,
            reason=None,
        )
        | {
            "context": {
                "count": len(rows),
                "truncated": truncated,
                "company_id": str(company_id) if company_id else None,
            }
        },
    )
    return ExportResult(
        export_id=export_id,
        count=len(rows),
        truncated=truncated,
        events=[_detail(r, current) for r in rows],
    )


# Deferred until its migrations and ingestion contract ship (docs/audit.md §7).
# Keep these routes out of the published OpenAPI/client contract meanwhile.
@router.post(
    "/integration-logs", response_model=IntegrationLogItem, status_code=201, include_in_schema=False
)
async def create_integration_log(
    body: IntegrationLogCreate,
    company_id: uuid.UUID | None = Query(default=None),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> IntegrationLog:
    current.require("audit.read")
    current.require_scope("audit.read", target=_query_scope(company_id))
    current.require_audit_scope(company_id)

    log_id = uuid7()
    now = utcnow()
    row = IntegrationLog(
        id=log_id,
        occurred_at=now,
        tenant_id=current.tenant_id,
        company_id=company_id,
        integration_name=body.integration_name,
        direction=body.direction,
        status=body.status,
        response_code=body.response_code,
        retry_count=body.retry_count,
        error_message=body.error_message,
        metadata_json=body.metadata_json,
    )
    db.add(row)
    await db.flush()
    return row


@router.get("/integration-logs", response_model=IntegrationLogPage, include_in_schema=False)
async def list_integration_logs(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    company_id: uuid.UUID | None = Query(default=None),
    integration_name: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    sort: str = Query(default=_DEFAULT_SORT),
) -> IntegrationLogPage:
    current.require("audit.read")
    current.require_scope("audit.read", target=_query_scope(company_id))
    current.require_audit_scope(company_id)

    statement = select(IntegrationLog)
    if company_id is not None:
        statement = statement.where(IntegrationLog.company_id == company_id)
    if integration_name is not None:
        statement = statement.where(IntegrationLog.integration_name == integration_name)

    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=IntegrationLog,
        page=PageRequest(limit=limit, cursor=cursor),
        sort=sort,
        allowed=_SORTABLE,
        default=_DEFAULT_SORT,
        codec=cursor_codec(request, "integration-logs", current),
    )
    return IntegrationLogPage(
        items=[IntegrationLogItem.model_validate(r) for r in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get(
    "/integration-logs/{log_id}", response_model=IntegrationLogItem, include_in_schema=False
)
async def get_integration_log(
    log_id: uuid.UUID,
    occurred_at: AwareDatetime = Query(...),
    company_id: uuid.UUID | None = Query(default=None),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> IntegrationLog:
    current.require("audit.read")
    current.require_scope("audit.read", target=_query_scope(company_id))
    current.require_audit_scope(company_id)

    row = await db.scalar(
        select(IntegrationLog).where(
            IntegrationLog.id == log_id, IntegrationLog.occurred_at == occurred_at
        )
    )
    if row is None:
        raise NotFoundError("integration log not found")
    if company_id is not None and row.company_id != company_id:
        raise NotFoundError("integration log not found")
    return row
