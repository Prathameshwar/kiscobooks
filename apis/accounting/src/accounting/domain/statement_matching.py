"""Exact bank-statement match preflight; commit must lock owner rows atomically."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.money import MoneyError


@dataclass(frozen=True, slots=True)
class MatchSource:
    id: UUID
    tenant_id: UUID
    company_id: UUID
    bank_account_id: UUID
    currency: str
    side: str
    remaining: Decimal


@dataclass(frozen=True, slots=True)
class MatchPart:
    statement_row_id: UUID
    instrument_id: UUID
    amount: Decimal


@dataclass(frozen=True, slots=True)
class MatchPreview:
    statement_residuals: dict[UUID, Decimal]
    instrument_residuals: dict[UUID, Decimal]


def _validated(source: MatchSource) -> Decimal:
    if source.side not in {"DEBIT", "CREDIT"}:
        raise ValidationFailedError("unsupported bank match direction")
    if (
        len(source.currency) != 3
        or not source.currency.isascii()
        or not source.currency.isalpha()
        or source.currency != source.currency.upper()
    ):
        raise ValidationFailedError("invalid bank match currency")
    try:
        amount = exact_decimal(source.remaining)
    except MoneyError as exc:
        raise ValidationFailedError("bank match residual exceeds exact storage") from exc
    if amount < 0:
        raise ValidationFailedError("bank match residual cannot be negative")
    return amount


def preview(
    statements: tuple[MatchSource, ...],
    instruments: tuple[MatchSource, ...],
    parts: tuple[MatchPart, ...],
) -> MatchPreview:
    """Cap all sides of grouped/partial matches without making a bank event."""
    if not parts or len(parts) > 1000 or len(statements) > 1000 or len(instruments) > 1000:
        raise ValidationFailedError("bank match size is unsupported")
    if (
        len({row.id for row in statements}) != len(statements)
        or len({row.id for row in instruments}) != len(instruments)
    ):
        raise ValidationFailedError("bank match source identities must be distinct")
    if len({(row.statement_row_id, row.instrument_id) for row in parts}) != len(parts):
        raise ValidationFailedError("bank match pairs must be distinct")
    bank_rows = {row.id: row for row in statements}
    instrument_rows = {row.id: row for row in instruments}
    bank_left = {row.id: _validated(row) for row in statements}
    instrument_left = {row.id: _validated(row) for row in instruments}
    for part in parts:
        bank = bank_rows.get(part.statement_row_id)
        instrument = instrument_rows.get(part.instrument_id)
        if bank is None or instrument is None:
            raise ValidationFailedError("bank match references an unknown owner row")
        if (
            bank.tenant_id != instrument.tenant_id
            or bank.company_id != instrument.company_id
            or bank.bank_account_id != instrument.bank_account_id
            or bank.currency != instrument.currency
            or bank.side != instrument.side
        ):
            raise ValidationFailedError(
                "bank match crosses company, account, currency or direction"
            )
        try:
            amount = exact_decimal(part.amount)
        except MoneyError as exc:
            raise ValidationFailedError("bank match amount exceeds exact storage") from exc
        if amount <= 0 or amount > bank_left[bank.id] or amount > instrument_left[instrument.id]:
            raise ValidationFailedError("bank match exceeds an available residual")
        bank_left[bank.id] -= amount
        instrument_left[instrument.id] -= amount
    return MatchPreview(bank_left, instrument_left)
