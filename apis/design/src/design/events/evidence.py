"""Audit emission for the design service (CLAUDE.md §6.8, docs/audit.md §5.2).

Every state change stages its event on the caller's session through the outbox, so the
event and the row commit together and a rolled-back request leaves no claim behind.
Nothing here reads the database: the caller already holds the values, and an extra read
inside the write transaction is how a cheap audit trail becomes an expensive one.

``changes`` carries business columns only, from an explicit allowlist. A layout tree is
never copied into an audit row — it is large, it is already versioned immutably, and the
auditable fact is *which version* became live, not its bytes.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.audit_evidence import scalar
from billing_platform.gateway import Actor
from billing_platform.outbox import audit_payload, emit
from sqlalchemy.ext.asyncio import AsyncSession

from design.events.audit_contract import audit_event

#: Exact vocabulary, never suffix matching. A field outside this set records as a bare
#: ``{"changed": true}`` marker rather than leaking an unreviewed value.
SAFE_FIELDS: frozenset[str] = frozenset(
    """
status code name description paper_size page_orientation page_width_mm page_height_mm
unit_of_measure is_system is_active current_version_id version_number schema_version
layout_digest change_summary published_at priority voucher_kind voucher_type_id branch_id
currency_code customer_tax_category template_id specific_version_id company_id
asset_name asset_type file_name mime_type file_size_bytes storage_backend storage_path
content_digest image_width_px image_height_px component_category code
voucher_id voucher_revision_id template_version_id output_format render_channel
checksum_sha256 render_duration_ms
""".split()
)

#: Everything this service records is configuration, except a read that happened rather
#: than a change made — print evidence, and a private asset's bytes being disclosed
#: (plan P4, 2026-11-03) — which is ``access`` in the audit vocabulary (docs/audit.md §3).
_CATEGORIES: Mapping[str, str] = {"invoice_render_snapshot": "access"}


def changes(
    fields: frozenset[str],
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    creating: bool = False,
) -> dict[str, Any]:
    old, new = before or {}, after or {}
    result: dict[str, Any] = {}
    for key in sorted(fields):
        if key not in SAFE_FIELDS:
            result[key] = {"changed": True}
        elif key in new and (key in old or creating):
            result[key] = {"from": scalar(old.get(key)), "to": scalar(new[key])}
        elif key in old and after is not None and key not in new:
            result[key] = {"from": scalar(old[key]), "to": None}
        else:
            result[key] = {"changed": True}
    return result


def audit_change(
    db: AsyncSession,
    actor: Actor,
    company_id: uuid.UUID,
    entity: str,
    object_id: uuid.UUID,
    action: str,
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    changed: frozenset[str] | None = None,
) -> None:
    """Stage one audit event for a design change. Commits nothing.

    The changed-field set defaults to the keys the caller actually passed, so a route
    cannot name a field it does not supply — or supply one it forgot to name. Pass
    ``changed`` explicitly only to record a field whose value is deliberately withheld.
    """
    fields = changed if changed is not None else frozenset(after or {}) | frozenset(before or {})
    event = audit_event(entity, action)
    payload = audit_payload(
        action=event,
        category="access" if action == "download" else _CATEGORIES.get(entity, "admin"),
        entity_type=f"design.{entity}",
        entity_id=object_id,
        actor_user_id=actor.user_id,
        company_id=company_id,
        changes=changes(fields, before=before, after=after, creating=not before),
    )
    payload["actor_type"] = "user"
    payload["source_service"] = "design"
    emit(
        db,
        aggregate_type=f"design.{entity}",
        aggregate_id=object_id,
        event_type=event,
        tenant_id=actor.tenant_id,
        payload=payload,
    )
