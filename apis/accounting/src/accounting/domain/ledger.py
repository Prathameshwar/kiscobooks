"""Exact journal arithmetic and immutable payment-term schedules."""

from __future__ import annotations

import calendar
import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal, DecimalException, localcontext

from billing_platform.constants import MONEY_MAX
from billing_platform.errors import ValidationFailedError
from billing_platform.money import MoneyError, RoundingMode, quantize_storage, round_for_display


@dataclass(frozen=True, slots=True)
class Entry:
    account_id: uuid.UUID
    side: str
    currency: str
    amount: Decimal
    exchange_rate: Decimal


@dataclass(frozen=True, slots=True)
class ValuedEntry:
    entry: Entry
    base_amount: Decimal


def exact_positive(value: Decimal, *, scale: int = 4, maximum: Decimal = MONEY_MAX) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or not 0 < value <= maximum:
        raise ValidationFailedError("amount must be a positive bounded exact decimal")
    try:
        with localcontext() as context:
            context.prec = 48
            if value != value.quantize(Decimal(1).scaleb(-scale)):
                raise ValidationFailedError("decimal exceeds the allowed storage scale")
    except DecimalException as exc:
        raise ValidationFailedError("decimal exceeds the supported range") from exc
    return value


def base_value(
    amount: Decimal,
    currency: str,
    exchange_rate: Decimal,
    base_currency: str,
    precision: int,
    rounding: RoundingMode,
) -> Decimal:
    """One conversion boundary for journals, credit, sources and overdue charges."""
    exact_positive(amount)
    exact_positive(exchange_rate, scale=8, maximum=Decimal("99999999999.99999999"))
    if currency == base_currency and exchange_rate != 1:
        raise ValidationFailedError("base currency exchange rate must be one")
    try:
        with localcontext() as context:
            context.prec = 48
            # Entered base money retains its four places; foreign results use company rounding.
            value = quantize_storage(
                amount
                if currency == base_currency
                else round_for_display(amount * exchange_rate, precision, rounding)
            )
    except (DecimalException, MoneyError) as exc:
        raise ValidationFailedError("converted amount exceeds the supported range") from exc
    if value <= 0:
        raise ValidationFailedError("converted amount must be positive")
    return value


def value_entries(
    entries: tuple[Entry, ...],
    base_currency: str,
    precision: int,
    rounding: RoundingMode,
    *,
    opening_values: tuple[Decimal | None, ...] | None = None,
) -> tuple[ValuedEntry, ...]:
    if not 2 <= len(entries) <= 200:
        raise ValidationFailedError("a journal requires between two and 200 lines")
    valued = []
    debit = Decimal(0)
    credit = Decimal(0)
    with localcontext() as context:
        context.prec = 48
        if opening_values is not None and len(opening_values) != len(entries):
            raise ValidationFailedError("opening carrying values must match the journal lines")
        for index, entry in enumerate(entries):
            if entry.side not in {"DEBIT", "CREDIT"} or not entry.account_id.int:
                raise ValidationFailedError(
                    "journal line requires an account and debit or credit side"
                )
            if (
                len(entry.currency) != 3
                or not entry.currency.isascii()
                or not entry.currency.isupper()
                or not entry.currency.isalpha()
            ):
                raise ValidationFailedError("journal line requires an ISO currency code")
            carried = opening_values[index] if opening_values is not None else None
            base = (
                base_value(
                    entry.amount,
                    entry.currency,
                    entry.exchange_rate,
                    base_currency,
                    precision,
                    rounding,
                )
                if carried is None
                else exact_positive(carried)
            )
            if carried is not None:
                exact_positive(entry.amount)
                exact_positive(
                    entry.exchange_rate, scale=8, maximum=Decimal("99999999999.99999999")
                )
                if entry.currency == base_currency and (
                    entry.exchange_rate != 1 or carried != entry.amount
                ):
                    raise ValidationFailedError(
                        "base-currency opening carrying value must equal its amount"
                    )
            valued.append(ValuedEntry(entry, base))
            if entry.side == "DEBIT":
                debit += base
            else:
                credit += base
        if debit != credit or debit > MONEY_MAX:
            raise ValidationFailedError(
                "journal debits and credits must balance within the supported range"
            )
    return tuple(valued)


@dataclass(frozen=True, slots=True)
class Term:
    sequence: int
    percentage: Decimal
    basis: str
    days: int


@dataclass(frozen=True, slots=True)
class Installment:
    sequence: int
    amount: Decimal
    due_date: dt.date


def payment_schedule(
    amount: Decimal,
    document_date: dt.date,
    terms: tuple[Term, ...],
    *,
    precision: int,
    rounding: RoundingMode,
) -> tuple[Installment, ...]:
    exact_positive(amount)
    if not 1 <= len(terms) <= 24:
        raise ValidationFailedError("payment terms require one to 24 installments")
    ordered = sorted(terms, key=lambda term: term.sequence)
    if len({term.sequence for term in ordered}) != len(ordered) or any(
        term.sequence < 1 for term in ordered
    ):
        raise ValidationFailedError("installment sequence must be positive and unique")
    for term in ordered:
        exact_positive(term.percentage, maximum=Decimal(100))
        if term.basis not in {"INVOICE_DATE", "MONTH_END"} or not 0 <= term.days <= 3650:
            raise ValidationFailedError("invalid payment term basis or days")
    if sum((term.percentage for term in ordered), Decimal(0)) != 100:
        raise ValidationFailedError("installment percentages must total 100")
    result = []
    remaining = amount
    with localcontext() as context:
        context.prec = 48
        for index, term in enumerate(ordered):
            portion = (
                remaining
                if index == len(ordered) - 1
                else min(
                    remaining,
                    round_for_display(amount * term.percentage / 100, precision, rounding),
                )
            )
            remaining -= portion
            anchor = document_date
            if term.basis == "MONTH_END":
                anchor = document_date.replace(
                    day=calendar.monthrange(document_date.year, document_date.month)[1]
                )
            try:
                due = anchor + dt.timedelta(days=term.days)
            except OverflowError as exc:
                raise ValidationFailedError(
                    "payment term due date exceeds the supported range"
                ) from exc
            if portion > 0:
                result.append(Installment(term.sequence, quantize_storage(portion), due))
    return tuple(result)
