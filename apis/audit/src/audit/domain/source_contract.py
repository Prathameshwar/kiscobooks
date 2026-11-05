"""Exact, authenticated compatibility with original Accounting/Audit v1 emitters."""

import json
from pathlib import Path
from typing import Any

from billing_platform.errors import ValidationFailedError
from billing_platform.messages import MessageEnvelope

_LEGACY: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).resolve().parents[1] / "data/accounting-legacy-v1.json").read_text()
)


def validate_source(envelope: MessageEnvelope, issuer: str) -> None:
    payload: dict[str, Any] = envelope.payload
    if payload.get("source_service") not in (None, issuer):
        raise ValidationFailedError("audit source does not match its route")
    if issuer in {"accounting", "catalog", "vouchers", "reports", "notification", "design"}:
        entity = envelope.event_type.rsplit(".", 1)[0]
        if not entity.startswith(issuer + ".") or payload.get("entity_type") != entity:
            raise ValidationFailedError("audit entity does not match its source route")
    if payload.get("action") == envelope.event_type:
        return
    legacy = _LEGACY.get(envelope.event_type) if issuer == "accounting" else None
    if (
        envelope.schema_version == 1
        and legacy is not None
        and all(payload.get(key) == value for key, value in legacy.items())
    ):
        return  # Preserve the original short action; never rewrite signed evidence.
    if (
        issuer == "audit"
        and envelope.schema_version == 1
        and envelope.event_type == "audit.exported"
        and payload.get("action") == "exported"
        and payload.get("entity_type") == "audit_event"
    ):
        return
    raise ValidationFailedError("audit action does not match its route")
