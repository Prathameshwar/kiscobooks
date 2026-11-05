"""Source contract readiness, freshness and version decisions without I/O."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from billing_platform.errors import ConflictError, PlatformError, ValidationFailedError


class SourceUnavailableError(PlatformError):
    status_code = 503
    code = "source_unavailable"


@dataclass(frozen=True, slots=True)
class SourceContract:
    key: str
    owner: Literal["identity", "billing"]
    proposed_version: int
    adopted_version: int | None
    capabilities: frozenset[str]


SOURCE_CONTRACTS = (
    SourceContract("identity.company", "identity", 1, 1, frozenset({"masters", "products"})),
    SourceContract("identity.features", "identity", 1, 1, frozenset({"products", "configuration"})),
    SourceContract("identity.fields", "identity", 1, 1, frozenset({"masters", "products"})),
    SourceContract(
        "billing.party", "billing", 1, None, frozenset({"customer_prices", "supplier_terms"})
    ),
    SourceContract("billing.customer_type", "billing", 1, None, frozenset({"customer_prices"})),
    SourceContract("billing.customer_pricing", "billing", 1, None, frozenset({"customer_prices"})),
    SourceContract("billing.lots", "billing", 1, None, frozenset({"lot_prices"})),
    SourceContract("billing.declarations", "billing", 1, None, frozenset({"declaration_prices"})),
    SourceContract("billing.fiscal", "billing", 1, None, frozenset({"fiscal_custom_sequences"})),
    SourceContract(
        "billing.policy_ack", "billing", 1, None, frozenset({"location_enforcement", "promotions"})
    ),
)


def version_action(
    *,
    existing_version: int | None,
    existing_digest: str | None,
    incoming_version: int,
    incoming_digest: str,
) -> Literal["apply", "ignore"]:
    if type(incoming_version) is not int or incoming_version < 1:
        raise ValidationFailedError("source version must be positive")
    if existing_version is None or incoming_version > existing_version:
        return "apply"
    if incoming_version == existing_version and incoming_digest != existing_digest:
        raise ConflictError("source reused a version with different contents")
    return "ignore"


def require_fresh_source(
    *, complete: bool, generated_at: dt.datetime | None, maximum_age: dt.timedelta, now: dt.datetime
) -> None:
    if maximum_age <= dt.timedelta(0) or now.tzinfo is None:
        raise ValueError("positive source lifetime and aware current time required")
    if not complete or generated_at is None:
        raise SourceUnavailableError("required source snapshot is unavailable")
    if generated_at.tzinfo is None or generated_at > now or now - generated_at > maximum_age:
        raise SourceUnavailableError("required source snapshot is not current")
