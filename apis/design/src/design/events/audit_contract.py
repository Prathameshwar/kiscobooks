"""Exact audit routes for the design service.

The Audit service validates an event against the route that carried it: the event type
must begin with the issuing service's name and the payload's ``entity_type`` must equal
the event's entity prefix (``audit/domain/source_contract.py``). So these names are a
contract, not a label — an event outside this set is rejected at ingestion, and the
publisher's ``ServiceKey`` is minted from exactly this set.
"""

from __future__ import annotations

from typing import Final

ENTITIES: Final[tuple[str, ...]] = (
    "invoice_template",
    "invoice_template_version",
    "invoice_template_assignment",
    "invoice_template_asset",
    "invoice_template_component",
    "invoice_render_snapshot",
)

AUDIT_EVENTS: Final[frozenset[str]] = frozenset(
    {
        *(f"design.{entity}.{action}" for entity in ENTITIES for action in ("create", "update")),
        # A template's own lifecycle: publishing a version makes it the live layout, and
        # archiving retires it. Both change what future documents look like, so both are
        # their own audited act rather than an `update`.
        "design.invoice_template.publish",
        "design.invoice_template.archive",
        "design.invoice_template_version.publish",
        "design.invoice_template_assignment.deactivate",
        "design.invoice_template_asset.deactivate",
        # A private-disk asset's bytes are only ever disclosed against a signed token
        # (CLAUDE.md §5.14); each disclosure is its own audited read, not an `update`,
        # since nothing about the asset itself changes (designer plan P4, 2026-11-03).
        "design.invoice_template_asset.download",
        "design.invoice_template_component.deactivate",
    }
)


def audit_event(entity: str, action: str) -> str:
    """The event name for an entity and action, refusing anything off-contract."""
    event = f"design.{entity}.{action}"
    if event not in AUDIT_EVENTS:
        raise ValueError(f"undeclared design audit event: {event}")
    return event
