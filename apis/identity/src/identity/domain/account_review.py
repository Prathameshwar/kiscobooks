"""Public-registration eligibility and review transitions; no framework or provider I/O."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class Applicant:
    provider_id: int
    provider_uuid: uuid.UUID
    name: str
    username: str
    email: str
    path: str
    user_type: str
    is_active: bool
    verified: bool
    groups: tuple[int, ...]
    roles: tuple[str, ...]
    country_code: str
    state_code: str
    workspace_name: str | None = None


def eligible(row: Applicant) -> bool:
    return (
        row.path == "bill/pending-registration"
        and row.user_type == "external"
        and not row.groups
        and not row.roles
        and bool(row.name.strip() and row.username.strip() and row.email.strip())
    )


def fingerprint(row: Applicant) -> str:
    values = asdict(row)
    if values["workspace_name"] is None:
        values.pop("workspace_name")  # Preserve fingerprints imported before this field existed.
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def transition(status: str, action: str) -> str:
    target = {
        ("pending", "approve"): "approved",
        ("pending", "reject"): "rejected",
        ("rejected", "reopen"): "pending",
    }.get((status, action))
    if target is None:
        raise ValueError("this decision is not available for the current review status")
    return target
