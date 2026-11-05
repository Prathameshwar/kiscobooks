"""A consistent transactional audit adapter for new Identity workflows."""

from __future__ import annotations

import uuid
from typing import Any

from billing_platform.db.platform_models import Outbox
from billing_platform.outbox import emit
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor


def record(
    db: AsyncSession,
    current: Actor,
    *,
    action: str,
    entity: str,
    entity_id: uuid.UUID,
    reason: str | None = None,
    changes: dict[str, Any] | None = None,
    company_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    category: str = "security",
) -> Outbox:
    payload = audit_payload(
        action=action,
        category=category,
        entity_type=entity,
        entity_id=entity_id,
        actor_user_id=current.user_id,
        company_id=company_id,
        department_id=department_id,
        reason=reason,
        changes=changes,
    )
    if action.startswith("platform."):
        # Administrative references and states are useful evidence; free text and
        # profile values cannot safely be retained in the immutable audit store.
        from identity.services.platform_evidence import safe_changes

        payload["changes"] = safe_changes(changes or {})
        payload["reason"] = None
    return emit(
        db,
        tenant_id=current.tenant_id,
        aggregate_type=entity,
        aggregate_id=entity_id,
        event_type=action,
        payload=payload,
    )
