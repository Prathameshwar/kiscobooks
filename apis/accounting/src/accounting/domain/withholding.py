"""TDS/TCS withholding over company-entered masters; no HTTP or database dependency.

No statutory section, rate or threshold lives here. Every number comes from a
company master row that carries its own source evidence; this module only
selects the effective rows for a posting date and applies them.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.money import RoundingMode, quantize_storage, round_for_display

KINDS = ("TDS", "TCS")
FEATURES = {"TDS": "tds", "TCS": "tcs"}
DEDUCTEE_TYPES = (
    "INDIVIDUAL",
    "HUF",
    "COMPANY",
    "FIRM",
    "AOP_BOI",
    "LOCAL_AUTHORITY",
    "ARTIFICIAL_JURIDICAL_PERSON",
    "GOVERNMENT",
    "COOPERATIVE",
    "TRUST",
    "NON_RESIDENT_COMPANY",
    "NON_RESIDENT_OTHER",
    "OTHER",
)
PAN_STATUSES = ("VERIFIED", "NOT_AVAILABLE", "INOPERATIVE")
THRESHOLD_BASES = ("TRANSACTION", "AGGREGATE", "EXCESS")
RateSource = Literal["CERTIFICATE", "NO_PAN", "NORMAL"]
Reason = Literal["WITHHELD", "NOT_DEDUCTIBLE", "BELOW_THRESHOLD"]
HUNDRED = Decimal(100)
ZERO = Decimal(0)


@dataclass(frozen=True)
class RateTerms:
    id: uuid.UUID
    deductee_type: str
    rate_percent: Decimal
    no_pan_rate_percent: Decimal
    single_transaction_threshold: Decimal | None
    aggregate_annual_threshold: Decimal | None
    threshold_basis: str
    valid_from: dt.date
    valid_to: dt.date | None


@dataclass(frozen=True)
class ProfileTerms:
    id: uuid.UUID
    kind: str
    deductible: bool
    deductee_type: str
    pan_status: str
    valid_from: dt.date
    valid_to: dt.date | None


@dataclass(frozen=True)
class CertificateTerms:
    id: uuid.UUID
    rate_percent: Decimal
    amount_limit: Decimal | None
    valid_from: dt.date
    valid_to: dt.date | None


@dataclass(frozen=True)
class WithholdingPortion:
    base_amount: Decimal
    rate_percent: Decimal
    rate_source: RateSource
    amount: Decimal


@dataclass(frozen=True)
class WithholdingResult:
    applies: bool
    reason: Reason
    profile_id: uuid.UUID
    rate_id: uuid.UUID | None
    certificate_id: uuid.UUID | None
    threshold_crossed: bool
    base_amount: Decimal
    withholding_amount: Decimal
    portions: tuple[WithholdingPortion, ...]


def _percent(value: Decimal, label: str) -> None:
    if not ZERO <= value <= HUNDRED:
        raise ValidationFailedError(f"{label} must be between 0 and 100")


def validate_rate_terms(values: dict[str, Any]) -> None:
    """Shape rules for a withholding rate row; statutory values are never asserted."""
    rate, no_pan = values["rate_percent"], values["no_pan_rate_percent"]
    _percent(rate, "rate_percent")
    _percent(no_pan, "no_pan_rate_percent")
    if no_pan < rate:
        raise ValidationFailedError("the no-PAN rate cannot be lower than the normal rate")
    single = values.get("single_transaction_threshold")
    aggregate = values.get("aggregate_annual_threshold")
    for threshold in (single, aggregate):
        if threshold is not None and threshold <= ZERO:
            raise ValidationFailedError("withholding thresholds must be positive")
    basis = values["threshold_basis"]
    if basis in {"AGGREGATE", "EXCESS"} and aggregate is None:
        raise ValidationFailedError("aggregate threshold basis requires an annual threshold")
    if basis == "EXCESS" and single is not None:
        raise ValidationFailedError("excess basis uses only the annual threshold")
    if single is not None and aggregate is not None and single > aggregate:
        raise ValidationFailedError("single threshold cannot exceed the annual threshold")


def validate_profile_terms(values: dict[str, Any]) -> None:
    status, identifier = values["pan_status"], values.get("pan_identifier_id")
    if status == "VERIFIED" and identifier is None:
        raise ValidationFailedError("a verified PAN status requires the party PAN identifier")
    if status == "NOT_AVAILABLE" and identifier is not None:
        raise ValidationFailedError("an unavailable PAN cannot reference a PAN identifier")


def validate_certificate_terms(values: dict[str, Any]) -> None:
    _percent(values["rate_percent"], "rate_percent")
    limit = values.get("amount_limit")
    if limit is not None and limit <= ZERO:
        raise ValidationFailedError("certificate amount limit must be positive")
    if (limit is None) != (values.get("currency") is None):
        raise ValidationFailedError("a certificate amount limit requires its currency")


def _effective(rows: Sequence[Any], on: dt.date) -> list[Any]:
    return [row for row in rows if row.valid_from <= on <= (row.valid_to or dt.date.max)]


def _one(rows: list[Any], missing: str | None, label: str) -> Any:
    if len(rows) > 1:
        raise ConflictError(f"more than one effective {label} applies on the posting date")
    if not rows:
        if missing is None:
            return None
        raise ConflictError(missing)
    return rows[0]


def taxable_base(
    rate: RateTerms, amount: Decimal, ytd_amount: Decimal, ytd_withheld_base: Decimal
) -> tuple[bool, Decimal]:
    """Return whether the threshold is crossed and the amount withholding applies to.

    ``ytd_amount`` is the party's prior amount for this section in the fiscal year,
    and ``ytd_withheld_base`` the part of it that already bore withholding. Crossing
    means strictly greater than a threshold.
    """
    single, aggregate = rate.single_transaction_threshold, rate.aggregate_annual_threshold
    running = ytd_amount + amount
    if rate.threshold_basis == "EXCESS":
        if aggregate is None:
            raise ValidationFailedError("excess basis requires an annual threshold")
        excess = min(amount, max(ZERO, running - max(aggregate, ytd_amount)))
        return running > aggregate, excess
    if single is None and aggregate is None:
        return True, amount
    aggregate_crossed = aggregate is not None and running > aggregate
    single_crossed = single is not None and amount > single
    if not (aggregate_crossed or single_crossed):
        return False, ZERO
    if rate.threshold_basis == "AGGREGATE" and aggregate_crossed:
        return True, running - ytd_withheld_base
    return True, amount


def resolve_withholding(
    *,
    kind: str,
    rates: Sequence[RateTerms],
    profiles: Sequence[ProfileTerms],
    certificates: Sequence[CertificateTerms],
    posting_date: dt.date,
    amount: Decimal,
    ytd_amount: Decimal = ZERO,
    ytd_withheld_base: Decimal = ZERO,
    certificate_consumed: Decimal = ZERO,
    precision: int,
    rounding: RoundingMode,
) -> WithholdingResult:
    """Resolve one section's withholding for one party on a posting date.

    Rate precedence: a lower/nil certificate, then the no-PAN rate, then the
    normal rate. ``rates`` and ``certificates`` are already limited to the
    section; ``profiles`` to the party.
    """
    if kind not in KINDS:
        raise ValidationFailedError("unknown withholding kind")
    for value in (amount, ytd_amount, ytd_withheld_base, certificate_consumed):
        if not isinstance(value, Decimal):
            raise ValidationFailedError("withholding amounts must be Decimal")
        if value < ZERO:
            raise ValidationFailedError("withholding amounts cannot be negative")
    if ytd_withheld_base > ytd_amount:
        raise ValidationFailedError("withheld base cannot exceed the year-to-date amount")
    profile: ProfileTerms = _one(
        [row for row in _effective(profiles, posting_date) if row.kind == kind],
        "party has no effective withholding profile on the posting date",
        "withholding profile",
    )
    if not profile.deductible:
        return WithholdingResult(
            False, "NOT_DEDUCTIBLE", profile.id, None, None, False, ZERO, ZERO, ()
        )
    rate: RateTerms = _one(
        [
            row
            for row in _effective(rates, posting_date)
            if row.deductee_type == profile.deductee_type
        ],
        "section has no effective rate for the deductee type on the posting date",
        "withholding rate",
    )
    crossed, base = taxable_base(rate, amount, ytd_amount, ytd_withheld_base)
    if not crossed or base <= ZERO:
        return WithholdingResult(
            False, "BELOW_THRESHOLD", profile.id, rate.id, None, crossed, ZERO, ZERO, ()
        )
    certificate: CertificateTerms | None = _one(
        _effective(certificates, posting_date), None, "withholding certificate"
    )
    fallback: tuple[Decimal, RateSource] = (
        (rate.rate_percent, "NORMAL")
        if profile.pan_status == "VERIFIED"
        else (rate.no_pan_rate_percent, "NO_PAN")
    )
    shares: list[tuple[Decimal, Decimal, RateSource]] = []
    remaining = base
    if certificate is not None:
        available = (
            remaining
            if certificate.amount_limit is None
            else max(ZERO, certificate.amount_limit - certificate_consumed)
        )
        covered = min(remaining, available)
        if covered > ZERO:
            shares.append((covered, certificate.rate_percent, "CERTIFICATE"))
            remaining -= covered
    if remaining > ZERO:
        shares.append((remaining, fallback[0], fallback[1]))
    raw = [(share, percent, source, share * percent / HUNDRED) for share, percent, source in shares]
    portions = tuple(
        WithholdingPortion(quantize_storage(share), rate_percent, source, quantize_storage(value))
        for share, rate_percent, source, value in raw
    )
    total = round_for_display(sum((value for *_, value in raw), ZERO), precision, rounding)
    used_certificate = any(portion.rate_source == "CERTIFICATE" for portion in portions)
    return WithholdingResult(
        True,
        "WITHHELD",
        profile.id,
        rate.id,
        certificate.id if certificate is not None and used_certificate else None,
        True,
        quantize_storage(base),
        total,
        portions,
    )
