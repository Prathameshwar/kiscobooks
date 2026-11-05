"""Resolve only explicitly operator-registered credential bindings."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from billing_platform.errors import ValidationFailedError

from notification.config import Settings
from notification.ownership import current_space


def validate_reference(settings: Settings, reference: str | None, tenant_id: uuid.UUID) -> None:
    if reference is None:
        return
    binding = settings.credential_bindings.get(reference)
    if binding is None or binding.tenant_id != tenant_id or binding.space_id != current_space():
        raise ValidationFailedError("credential reference is not registered for this owner")


def resolve_secret(
    settings: Settings, reference: str, *, tenant_id: uuid.UUID, space_id: uuid.UUID
) -> bytes:
    binding = settings.credential_bindings.get(reference)
    if binding is None or binding.tenant_id != tenant_id or binding.space_id != space_id:
        raise ValueError("credential ownership is unavailable")
    value = os.environ.get(binding.environment_variable)
    if not value:
        raise ValueError("credential is unavailable")
    return value.encode()


def resolve_credentials(
    settings: Settings, reference: str, *, tenant_id: uuid.UUID, space_id: uuid.UUID
) -> dict[str, Any]:
    value = json.loads(resolve_secret(settings, reference, tenant_id=tenant_id, space_id=space_id))
    if not isinstance(value, dict):
        raise ValueError("credential must be a JSON object")
    return value


def validate_sender(settings: Settings, reference: str, sender: str, tenant_id: uuid.UUID) -> None:
    validate_reference(settings, reference, tenant_id)
    binding = settings.credential_bindings[reference]
    if sender not in binding.allowed_senders:
        raise ValidationFailedError("sender identity is not granted to this owner")
