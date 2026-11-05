"""Transactional notification audit policy for every ORM mutation.

Evidence contains reference IDs, safe lifecycle values and changed field names only.
Sensitive destinations, configuration, content and provider payloads never enter Audit.
The hook is scoped to notification models, including worker-owned replica changes.
"""

from __future__ import annotations

import uuid
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from notification.models import DeliveryEvent, NotificationDelivery

_SAFE_VALUES = frozenset(
    {
        "status",
        "verification_status",
        "health_status",
        "approval_status",
        "scan_status",
        "processing_status",
        "is_active",
        "is_enabled",
        "state",
        "attempt_count",
        "outcome",
    }
)


@event.listens_for(Session, "before_flush")
def record_mutations(db: Session, context: Any, instances: Any) -> None:
    for row in list(db.new | db.dirty | db.deleted):
        if type(row).__module__ != "notification.models":
            continue
        state = inspect(row)
        if row in db.dirty and not db.is_modified(row, include_collections=False):
            continue
        operation = "created" if row in db.new else "deleted" if row in db.deleted else "updated"
        tenant_id = row.tenant_id
        entity_id = getattr(row, "id", None) or getattr(row, "delivery_id", None)
        if entity_id is None:
            entity_id = uuid7()
            row.id = entity_id
        entity_type = f"notification.{row.__tablename__}"
        action = f"{entity_type}.{operation}"
        fields = sorted(
            attr.key
            for attr in state.mapper.column_attrs
            if state.attrs[attr.key].history.has_changes()
        )
        changes: dict[str, Any] = {}
        for name in fields:
            history = state.attrs[name].history
            if name in _SAFE_VALUES and (row in db.new or history.deleted):
                changes[name] = {
                    "from": history.deleted[0] if history.deleted else None,
                    "to": None if row in db.deleted else getattr(row, name),
                }
            else:
                changes[name] = {"changed": True}
        space_id = getattr(row, "space_id", None) or entity_id
        platform = space_id != tenant_id
        actor_id: uuid.UUID | None = db.info.get("notification_actor_id")
        payload = audit_payload(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_id,
            category="admin" if actor_id else "system",
            changes=changes,
            company_id=None
            if platform or getattr(row, "company_id", None) == SCOPE_ALL
            else getattr(row, "company_id", None),
        )
        payload["source_service"] = "notification"
        payload["actor_type"] = "user" if actor_id else "service"
        payload["context"] = {
            "notification_realm": "platform" if platform else "tenant",
            "notification_space_id": str(space_id),
        }
        emit(
            db,
            aggregate_type=entity_type,
            aggregate_id=entity_id,
            event_type=action,
            tenant_id=tenant_id,
            payload=payload,
        )
        if isinstance(row, NotificationDelivery) and row not in db.deleted and row not in db.new:
            history = state.attrs.status.history
            if not history.has_changes():
                continue
            previous = history.deleted[0] if history.deleted else None
            existing = [
                fact
                for fact in db.new
                if isinstance(fact, DeliveryEvent)
                and fact.delivery_id == row.id
                and fact.to_status == row.status
            ]
            if not existing:
                db.add(
                    DeliveryEvent(
                        id=uuid7(),
                        tenant_id=tenant_id,
                        space_id=row.space_id,
                        delivery_id=row.id,
                        source="state_change",
                        source_event_key=str(uuid7()),
                        from_status=previous,
                        to_status=row.status,
                        reason_code=row.status_reason,
                        observed_at=utcnow(),
                    )
                )
            # Domain status publishers in existing paths already stage this event.
            has_status = any(
                getattr(item, "event_type", None) == "notification.delivery.status_changed"
                and getattr(item, "aggregate_id", None) == row.id
                for item in db.new
            )
            if not has_status:
                emit(
                    db,
                    aggregate_type="notification_delivery",
                    aggregate_id=row.id,
                    event_type="notification.delivery.status_changed",
                    tenant_id=tenant_id,
                    payload={
                        "delivery_id": str(row.id),
                        "request_id": str(row.request_id),
                        "from_status": previous,
                        "to_status": row.status,
                        "reason_code": row.status_reason,
                    },
                )
