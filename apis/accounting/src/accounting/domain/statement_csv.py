"""Bounded, non-posting mapped CSV statement normalization."""

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from billing_platform.errors import ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.money import MoneyError


@dataclass(frozen=True, slots=True)
class CsvMapping:
    account_id: UUID
    currency: str
    date_column: str
    debit_column: str
    credit_column: str
    reference_column: str
    description_column: str
    transaction_id_column: str | None = None
    currency_column: str | None = None
    account_column: str | None = None
    account_value: str | None = None
    balance_column: str | None = None
    date_format: str = "%Y-%m-%d"
    delimiter: str = ","


@dataclass(frozen=True, slots=True)
class StatementRow:
    line_number: int
    transaction_date: date
    side: str
    amount: Decimal
    reference: str
    description: str
    transaction_id: str | None
    row_sha256: str
    needs_duplicate_review: bool
    running_balance: Decimal | None = None


@dataclass(frozen=True, slots=True)
class StatementPreview:
    account_id: UUID
    currency: str
    file_sha256: str
    rows: tuple[StatementRow, ...]


def _safe_text(value: str, label: str) -> str:
    result = value.strip()
    if len(result) > 500 or any(ord(ch) < 32 for ch in result):
        raise ValidationFailedError(f"invalid bank statement {label}")
    if result.startswith(("=", "+", "-", "@")):
        raise ValidationFailedError(f"formula-like bank statement {label} is not accepted")
    return result


def _amount(value: str) -> Decimal:
    if not value:
        return Decimal(0)
    if not value.isascii() or not value.replace(".", "", 1).isdigit():
        raise ValidationFailedError("bank statement amount must be unsigned decimal")
    try:
        return exact_decimal(Decimal(value))
    except (InvalidOperation, MoneyError) as exc:
        raise ValidationFailedError("bank statement amount exceeds exact storage") from exc


def parse_statement(raw: bytes, mapping: CsvMapping) -> StatementPreview:
    """Normalize evidence only; neither imports nor matching can book money."""
    if not raw or len(raw) > 2 * 1024 * 1024:
        raise ValidationFailedError("bank statement file size is unsupported")
    if mapping.delimiter not in {",", ";", "\t"}:
        raise ValidationFailedError("unsupported bank statement delimiter")
    if (
        len(mapping.currency) != 3
        or not mapping.currency.isascii()
        or not mapping.currency.isalpha()
        or mapping.currency != mapping.currency.upper()
    ):
        raise ValidationFailedError("bank statement currency must be uppercase ISO code")
    required = (
        mapping.date_column,
        mapping.debit_column,
        mapping.credit_column,
        mapping.reference_column,
        mapping.description_column,
    )
    optional = (
        mapping.transaction_id_column,
        mapping.currency_column,
        mapping.account_column,
        mapping.balance_column,
    )
    columns = required + tuple(value for value in optional if value)
    if any(not name for name in columns) or len(set(columns)) != len(columns):
        raise ValidationFailedError("bank statement columns must be distinct")
    if bool(mapping.account_column) != bool(mapping.account_value):
        raise ValidationFailedError(
            "bank statement account mapping needs a column and expected value"
        )
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationFailedError("bank statement must be UTF-8") from exc
    reader = csv.DictReader(
        io.StringIO(decoded, newline=""), delimiter=mapping.delimiter, strict=True
    )
    if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValidationFailedError("bank statement headers must be unique")
    for header in reader.fieldnames:
        if _safe_text(header, "header") != header:
            raise ValidationFailedError("invalid bank statement header")
    if not set(columns) <= set(reader.fieldnames):
        raise ValidationFailedError("bank statement mapping references a missing column")
    rows: list[StatementRow] = []
    transaction_ids: set[str] = set()
    try:
        for row in reader:
            number = reader.line_num
            if len(rows) >= 10_000:
                raise ValidationFailedError("bank statement exceeds the row limit")
            if None in row or any(value is None for value in row.values()):
                raise ValidationFailedError("bank statement row has the wrong column count")
            for column, value in row.items():
                if column != mapping.balance_column:
                    _safe_text(value, "cell")
            if (
                mapping.currency_column
                and _safe_text(row[mapping.currency_column], "currency") != mapping.currency
            ):
                raise ValidationFailedError("bank statement mixes currencies")
            if (
                mapping.account_column
                and _safe_text(row[mapping.account_column], "account") != mapping.account_value
            ):
                raise ValidationFailedError("bank statement mixes bank accounts")
            try:
                transaction_date = datetime.strptime(
                    row[mapping.date_column], mapping.date_format
                ).date()
            except ValueError as exc:
                raise ValidationFailedError("invalid bank statement date") from exc
            debit = _amount(row[mapping.debit_column])
            credit = _amount(row[mapping.credit_column])
            if (debit > 0) == (credit > 0):
                raise ValidationFailedError("bank statement row needs exactly one debit or credit")
            side, amount = ("DEBIT", debit) if debit else ("CREDIT", credit)
            reference = _safe_text(row[mapping.reference_column], "reference")
            description = _safe_text(row[mapping.description_column], "description")
            transaction_id = (
                _safe_text(row[mapping.transaction_id_column], "transaction ID")
                if mapping.transaction_id_column
                else None
            )
            running_balance = None
            if mapping.balance_column:
                raw_balance = row[mapping.balance_column].strip()
                magnitude = raw_balance.removeprefix("-")
                if (
                    not magnitude
                    or not magnitude.isascii()
                    or not magnitude.replace(".", "", 1).isdigit()
                ):
                    raise ValidationFailedError("invalid bank statement running balance")
                running_balance = exact_decimal(Decimal(raw_balance))
            if transaction_id:
                if transaction_id in transaction_ids:
                    raise ValidationFailedError("duplicate bank transaction ID in statement")
                transaction_ids.add(transaction_id)
            identity = {
                "account_id": str(mapping.account_id),
                "currency": mapping.currency,
                "date": transaction_date.isoformat(),
                "side": side,
                "amount": str(amount),
                "reference": reference,
                "description": description,
                "transaction_id": transaction_id,
                "running_balance": str(running_balance) if running_balance is not None else None,
            }
            digest = hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            rows.append(
                StatementRow(
                    number,
                    transaction_date,
                    side,
                    amount,
                    reference,
                    description,
                    transaction_id or None,
                    digest,
                    not bool(transaction_id),
                    running_balance,
                )
            )
    except csv.Error as exc:
        raise ValidationFailedError("malformed bank statement CSV") from exc
    if not rows:
        raise ValidationFailedError("bank statement has no transactions")
    return StatementPreview(
        mapping.account_id, mapping.currency, hashlib.sha256(raw).hexdigest(), tuple(rows)
    )
