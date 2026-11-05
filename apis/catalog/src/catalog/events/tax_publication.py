"""Catalog GST publications for the Accounting tax replica (contract version 1).

The shapes are frozen by ``apis/accounting/contracts/catalog-tax-{classification,rule,rate}-
changed-v1.schema.json`` (docs/tax-accounting-plan.md Phase 5). This module only builds payloads
from rows a command already holds; it reads nothing and decides nothing.

``source_version`` is the company's ``CatalogPolicyState.generation`` *after* the command's bump,
so every publication of one command shares a generation and a later command always carries a
strictly larger one. Decimals travel as strings with exactly four places, never JSON numbers.

Withdrawal: Catalog keeps a withdrawn row unchanged and records a ``WITHDRAW`` history action.
Contract version 1 can only say "withdrawn" through ``valid_to`` (classifications, rates) or
``is_active = false`` (rules), and it requires ``valid_to >= valid_from``. A withdrawn
classification or rate is therefore published with ``valid_to = valid_from`` — the shortest
window the contract can express. Withdrawal only ever applies to strictly future rows. The
residual one-day window is an open contract item (docs/tax-accounting-plan.md Phase 5).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable
from decimal import Decimal
from typing import Any, Final, Literal

CLASSIFICATION_EVENT: Final = "catalog.tax_classification.changed"
RULE_EVENT: Final = "catalog.tax_rule.changed"
RATE_EVENT: Final = "catalog.tax_rate.changed"
TAX_PUBLICATION_EVENTS: Final = frozenset({CLASSIFICATION_EVENT, RULE_EVENT, RATE_EVENT})
SCHEMA_VERSION: Final = 1
#: Accounting's queue binds these on ``platform.sources``; only Accounting is the audience.
AUDIENCE: Final = "accounting"

Action = Literal["PUBLISH", "UPDATE", "WITHDRAW"]
#: When one command touches a row more than once, the strongest fact wins.
PRIORITY: Final[dict[str, int]] = {"UPDATE": 0, "PUBLISH": 1, "WITHDRAW": 2}

_PLACES: Final = Decimal("0.0001")
_GENERATION_MAX: Final = 2**63 - 1


def decimal_string(value: Decimal | None) -> str | None:
    """A non-negative ``DECIMAL(19,4)`` as a fixed four-place string; refuses anything else."""
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("tax publication decimals are finite, non-negative Decimals")
    exact = value.quantize(_PLACES)
    if exact != value:
        raise ValueError("tax publication decimals carry at most four places")
    text = format(exact, "f")
    if len(text.split(".", 1)[0]) > 15:
        raise ValueError("tax publication decimal exceeds DECIMAL(19,4)")
    return text


def _date(value: dt.date | None) -> str | None:
    return None if value is None else value.isoformat()


def _id(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)


def stronger(current: str | None, incoming: str) -> str:
    """Combine two actions on one row within a single command."""
    if current is None or PRIORITY[incoming] > PRIORITY[current]:
        return incoming
    return current


def envelope(
    row: Any, generation: int, action: str, key: str, body: dict[str, Any]
) -> dict[str, Any]:
    if type(generation) is not int or not 1 <= generation <= _GENERATION_MAX:
        raise ValueError("tax publication generation is out of range")
    if action not in PRIORITY:
        raise ValueError("unknown tax publication action")
    return {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": str(row.tenant_id),
        "company_id": str(row.company_id),
        "source_version": generation,
        "action": action,
        key: body,
    }


def _end(row: Any, action: str) -> str | None:
    # See the module docstring: version one expresses withdrawal only through the end date.
    return _date(row.valid_from if action == "WITHDRAW" else row.valid_to)


def classification_payload(row: Any, generation: int, action: str) -> dict[str, Any]:
    return envelope(
        row,
        generation,
        action,
        "classification",
        {
            "id": str(row.id),
            "jurisdiction": row.jurisdiction,
            "code_system": row.code_system,
            "code": row.code,
            "item_kind": row.item_kind,
            "description": row.description,
            "valid_from": _date(row.valid_from),
            "valid_to": _end(row, action),
            "source_reference": row.source_reference,
            "source_sha256": row.source_sha256,
        },
    )


def rule_payload(row: Any, generation: int, action: str) -> dict[str, Any]:
    if action == "WITHDRAW" and row.is_active:
        raise ValueError("a withdrawn tax rule is inactive")
    return envelope(
        row,
        generation,
        action,
        "rule",
        {
            "id": str(row.id),
            "code": row.code,
            "name": row.name,
            "tax_system": row.tax_system,
            "jurisdiction": row.jurisdiction,
            "item_kind": row.item_kind,
            "treatment": row.treatment,
            "tax_category_id": str(row.tax_category_id),
            "is_active": bool(row.is_active),
            "source_reference": row.source_reference,
            "source_sha256": row.source_sha256,
        },
    )


def component_payload(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "component_key": row.component_key,
        "component": row.component,
        "kind": row.kind,
        "percentage": decimal_string(row.percentage),
        "amount": decimal_string(row.amount),
        "currency": row.currency,
        "unit_id": _id(row.unit_id),
        "basis_quantity": decimal_string(row.basis_quantity),
        "rounding_mode": row.rounding_mode,
        "position": int(row.position),
    }


def rate_payload(
    row: Any, series: Any, components: Iterable[Any], generation: int, action: str
) -> dict[str, Any]:
    if series.id != row.series_id or series.company_id != row.company_id:
        raise ValueError("tax rate series belongs to another history")
    parts = sorted(components, key=lambda entry: (entry.position, str(entry.id)))
    if not 1 <= len(parts) <= 16 or any(entry.rate_id != row.id for entry in parts):
        raise ValueError("a published tax rate carries its own 1-16 components")
    return envelope(
        row,
        generation,
        action,
        "rate",
        {
            "id": str(row.id),
            "rule_id": str(series.rule_id),
            "series_id": str(series.id),
            "applicability": series.applicability,
            "valid_from": _date(row.valid_from),
            "valid_to": _end(row, action),
            "supersedes_id": _id(row.supersedes_id),
            "source_reference": row.source_reference,
            "source_sha256": row.source_sha256,
            "components": [component_payload(entry) for entry in parts],
        },
    )


__all__ = [
    "AUDIENCE",
    "CLASSIFICATION_EVENT",
    "RATE_EVENT",
    "RULE_EVENT",
    "SCHEMA_VERSION",
    "TAX_PUBLICATION_EVENTS",
    "Action",
    "classification_payload",
    "component_payload",
    "decimal_string",
    "rate_payload",
    "rule_payload",
    "stronger",
]
