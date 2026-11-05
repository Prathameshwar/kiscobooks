"""Identity's audit-safe field allowlist; unlisted values are redacted by default."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.outbox import audit_payload as platform_audit_payload

_SAFE_FIELDS = frozenset(
    {
        "permissions",
        "separation_of_duties_warnings",
        "scope_hint",
        "is_active",
        "effect",
        "status",
        "visibility",
        "requires_step_up",
        "enabled",
        "path",
        "parent_id",
        "company_id",
        "department_id",
        # A person's own landing company and department. The same class of value as
        # ``company_id`` above and no more sensitive; redacting them would make "who
        # changed their default company, and to what" unanswerable.
        "default_company_id",
        "default_department_id",
        "user_id",
        "role_id",
        "subject_id",
        "head_user_id",
        "kind",
        "last4",
        "valid_from",
        "valid_to",
        "is_primary",
        "amount_precision",
        "quantity_precision",
        "rounding_mode",
        "base_currency",
        "currency_code",
        "reporting_currency",
        "country_code",
        "state_code",
        "default_tax_system",
        "tax_treatment_default",
        "business_category_code",
        "business_roles",
        "store_format_code",
    }
)


def audit_payload(**values: Any) -> dict[str, Any]:
    changes = values.get("changes") or {}
    values["changes"] = {
        key: change if key in _SAFE_FIELDS else {"from": "[redacted]", "to": "[redacted]"}
        for key, change in changes.items()
    }
    return platform_audit_payload(**values)


def jsonable(value: Any) -> Any:
    """Coerce an audit ``changes`` value to something the JSON outbox column stores.

    Money stays a string (never a float — that is the whole point of ``Decimal``),
    dates become ISO strings and ids their canonical text; everything else is already
    JSON-native.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value
