"""Catalog evidence policy; use the command's pre-mutation snapshots without extra reads."""

import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from billing_platform.audit_evidence import scalar
from billing_platform.gateway import Actor
from billing_platform.outbox import audit_payload, emit
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.events.audit_contract import audit_event
from catalog.events.audit_policy import category, safe_fields


def changes(
    entity: str,
    fields: frozenset[str],
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    creating: bool = False,
) -> dict[str, Any]:
    """``creating`` says there is no prior state, so a safe field reads ``{"from": None, ...}``.

    Callers derive it from an empty ``before`` rather than from the action's name: a first write
    whose audited action is its own verb — ``publish`` for a policy release — carries the same
    evidence as one named ``create``, or the values an auditor reads the release *for* would
    render as bare change markers (docs/audit.md §5.2).
    """
    allowed = safe_fields(entity)
    old, new = before or {}, after or {}
    result: dict[str, Any] = {}
    for key in sorted(fields):
        if key in allowed and key in new and (key in old or creating):
            result[key] = {"from": scalar(old.get(key)), "to": scalar(new[key])}
        elif key in allowed and key in old and after is not None and key not in new:
            result[key] = {"from": scalar(old[key]), "to": None}
        else:
            result[key] = {"changed": True}
    if any(isinstance(new.get(key), Decimal) for key in fields & allowed):
        for key in ("currency", "unit_id", "base_unit_id", "unit_revision_id"):
            if key in allowed and key in new and key not in result:
                result[key] = {"from": scalar(old.get(key, new[key])), "to": scalar(new[key])}
    return result


def audit_change(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    object_id: uuid.UUID,
    action: str,
    changed: frozenset[str],
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
) -> None:
    event = audit_event(entity, action)
    payload = audit_payload(
        action=event,
        category=category(entity, action),
        entity_type=entity,
        entity_id=object_id,
        actor_user_id=actor.user_id,
        company_id=company,
        changes=changes(entity, changed, before=before, after=after, creating=not before),
    )
    payload["actor_type"] = "user"
    emit(
        db,
        aggregate_type=entity,
        aggregate_id=object_id,
        event_type=event,
        tenant_id=actor.tenant_id,
        payload=payload,
    )


def report_access(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    job_id: uuid.UUID,
    *,
    count: int,
    file_format: str,
) -> None:
    if not 0 <= count <= 5000 or file_format not in {"CSV", "XLSX"}:
        raise ValueError("invalid report audit metadata")
    entity = "catalog.bulk_job"
    event = audit_event(entity, "export")
    payload = audit_payload(
        action=event,
        category="access",
        entity_type=entity,
        entity_id=job_id,
        actor_user_id=actor.user_id,
        company_id=company,
    )
    payload.update(actor_type="user", context={"count": count, "format": file_format})
    emit(
        db,
        aggregate_type=entity,
        aggregate_id=job_id,
        event_type=event,
        tenant_id=actor.tenant_id,
        payload=payload,
    )


def source_change(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company: uuid.UUID,
    entity: str,
    object_id: uuid.UUID,
    action: str,
    changed: frozenset[str],
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
) -> None:
    """``audit_change`` for a row a trusted service wrote, with no user behind it.

    ``actor_user_id`` is ``None`` and ``actor_type`` is ``service``. Attributing a consumer's
    acknowledgement to whoever happened to publish the release would be a false statement in
    the one record that has to be trustworthy: nobody authorized this write, a signed event
    did (docs/audit.md §5.2).

    Emitted through the same outbox in the same transaction as the row, so an ingestion that
    rolls back leaves no claim behind (CLAUDE.md §6.8, §6.10).
    """
    event = audit_event(entity, action)
    payload = audit_payload(
        action=event,
        category=category(entity, action, system=True),
        entity_type=entity,
        entity_id=object_id,
        actor_user_id=None,
        company_id=company,
        changes=changes(entity, changed, before=before, after=after, creating=not before),
    )
    payload["actor_type"] = "service"
    emit(
        db,
        aggregate_type=entity,
        aggregate_id=object_id,
        event_type=event,
        tenant_id=tenant_id,
        payload=payload,
    )
