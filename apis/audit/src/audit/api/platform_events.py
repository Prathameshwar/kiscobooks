"""Platform administrative history in the operating tenant, separate from business evidence."""

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import decode_actor_context
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from audit.api.auth import Actor, actor
from audit.api.dependencies import session
from audit.api.listing import cursor_codec, keyset_page
from audit.api.query import validate_query
from audit.api.routes import _detail
from audit.api.schemas import AuditEventDetail, AuditEventItem, AuditEventPage, PageMeta
from audit.domain.categories import CATEGORIES
from audit.domain.platform_events import ENTITIES, EVENTS
from audit.models import AuditEvent

router = APIRouter(prefix="/v1/platform-events", dependencies=[Depends(validate_query)])


def families(request: Request, current: Actor) -> list[tuple[str, frozenset[str]]]:
    # Verify the raw context again to inspect its signed purpose marker; request
    # headers and a client's user_type can never grant platform authority.
    import base64
    import json

    token = request.headers["x-actor-context"]
    decode_actor_context(
        token,
        request.headers["x-actor-signature"],
        request.app.state.settings.actor_signing_secret.get_secret_value().encode(),
    )
    values = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    if values.get("user_type") != "platform_operator" or current.impersonation_id is not None:
        raise PermissionDeniedError("a verified platform operator is required")
    result: list[tuple[str, frozenset[str]]] = []
    for permission, group in EVENTS.items():
        if current.allows_scope(permission, target=ScopePath()):
            result.extend(group.items())
    if not result:
        raise PermissionDeniedError("platform history permission is required")
    return result


def statement_for(allowed: list[tuple[str, frozenset[str]]]) -> Select[tuple[AuditEvent]]:
    return select(AuditEvent).where(
        or_(
            AuditEvent.source_service == "identity",
            and_(
                AuditEvent.source_service == "notification",
                AuditEvent.context["notification_realm"].as_string() == "platform",
            ),
        ),
        AuditEvent.company_id.is_(None),
        AuditEvent.department_id.is_(None),
        or_(
            *(
                and_(AuditEvent.entity_type == entity, AuditEvent.action.in_(actions))
                for entity, actions in allowed
            )
        ),
    )


@router.get("", response_model=AuditEventPage)
async def listing(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    entity_type: str | None = Query(None, max_length=80),
    entity_id: uuid.UUID | None = Query(None),
    category: str | None = Query(None, max_length=20),
    occurred_from: AwareDatetime | None = Query(None),
    occurred_to: AwareDatetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    sort: str = Query("-occurred_at"),
) -> AuditEventPage:
    statement = statement_for(families(request, current))
    if entity_type is not None and entity_type not in ENTITIES:
        raise ValidationFailedError("unknown platform subject")
    if category is not None:
        if category not in CATEGORIES:
            raise ValidationFailedError("unknown audit category")
        statement = statement.where(AuditEvent.category == category)
    if occurred_from and occurred_to and occurred_from >= occurred_to:
        raise ValidationFailedError("occurred_from must precede occurred_to")
    for column, value in ((AuditEvent.entity_type, entity_type), (AuditEvent.entity_id, entity_id)):
        if value is not None:
            statement = statement.where(column == value)
    if occurred_from:
        statement = statement.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to:
        statement = statement.where(AuditEvent.occurred_at < occurred_to)
    statement = statement.options(
        load_only(*(getattr(AuditEvent, key) for key in AuditEventItem.model_fields))
    )
    rows, next_cursor, has_more = await keyset_page(
        db,
        statement,
        model=AuditEvent,
        page=PageRequest(limit=limit, cursor=cursor),
        sort=sort,
        allowed=frozenset({"occurred_at", "sequence"}),
        default="-occurred_at",
        codec=cursor_codec(request, "platform-events", current),
    )
    return AuditEventPage(
        items=[AuditEventItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/{event_id}", response_model=AuditEventDetail)
async def detail(
    event_id: uuid.UUID,
    request: Request,
    occurred_at: AwareDatetime = Query(...),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> AuditEventDetail:
    statement = statement_for(families(request, current)).where(
        AuditEvent.id == event_id, AuditEvent.occurred_at == occurred_at
    )
    event = await db.scalar(statement)
    if event is None:
        raise NotFoundError("platform event not found")
    result = _detail(event, current)
    return result.model_copy(
        update={
            "reason": None,
            "context": None,
            "changes": safe_evidence(event.changes or {}),
            "actor_ip": None,
            "actor_user_agent": None,
        }
    )


def safe_evidence(changes: dict[str, Any]) -> dict[str, Any]:
    """Conservative projection also protects previously stored platform evidence."""
    states = {
        "active",
        "suspended",
        "closed",
        "pending",
        "approved",
        "rejected",
        "queued",
        "completed",
        "blocked",
        "invited",
        "approve",
        "reject",
        "reopen",
    }

    def safe(key: str, value: Any) -> bool:
        if key in {"status", "action"}:
            return isinstance(value, str) and value in states
        if key in {
            "attested",
            "needs_attention",
            "provider_active",
            "provider_verified",
            "is_active",
        }:
            return type(value) is bool
        if key in {"count", "version"}:
            return type(value) is int and 0 <= value <= 2**63 - 1
        if key in {"command_id", "administrator_id", "assignment_id"}:
            try:
                return isinstance(value, str) and str(uuid.UUID(value)) == value
            except ValueError:
                return False
        if key == "kind":
            return value in ("country", "state", "currency", "language")
        if key == "delivery":
            return value in ("link", "email")
        if key == "code":
            import re

            return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9-]{2,6}", value) is not None
        if key == "error_code":
            return value in ("provider_unavailable", "profile_changed")
        return False

    result = {}
    for key, value in changes.items():
        allowed = (
            (
                bool(value)
                and set(value) <= {"from", "to"}
                and all(safe(key, part) for part in value.values())
            )
            if isinstance(value, dict)
            else safe(key, value)
        )
        result[key] = value if allowed else {"changed": True}
    return result
