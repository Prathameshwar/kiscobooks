"""Rules that turn a party import's opening columns into one declaration entry; no I/O.

The import row says how much the business owes or is owed and, optionally, which bill it is. This
module only normalises and checks that statement. It posts nothing: the declaration that finally
takes the line must still balance, and the actor balances it.
"""

import dataclasses
import datetime as dt
import uuid
from collections.abc import Iterable
from decimal import Decimal
from typing import Literal

from billing_platform.errors import ValidationFailedError

Side = Literal["DEBIT", "CREDIT"]
Role = Literal["CUSTOMER", "SUPPLIER"]
Kind = Literal["ON_ACCOUNT", "INVOICE", "BILL"]

# `TO_RECEIVE` is what the other side owes the company, whatever role the party holds: it is a
# debit balance. `TO_PAY` is a credit balance. A supplier we have overpaid is TO_RECEIVE; a customer
# who paid in advance is TO_PAY.
BALANCE_SIDES: dict[str, Side] = {
    "DR": "DEBIT",
    "CR": "CREDIT",
    "TO_RECEIVE": "DEBIT",
    "TO_PAY": "CREDIT",
}
ON_ACCOUNT_REFERENCE = "Opening balance"
# The books-begin period may simply not be open yet. Everything else that blocks an opening
# declaration also blocks a held balance, because nothing could ever take it.
ALWAYS_TOLERATED = frozenset({"BOOKS_BEGIN_PERIOD_NOT_OPEN"})


@dataclasses.dataclass(frozen=True)
class StagedBalance:
    side: Side
    currency: str
    amount: Decimal
    exchange_rate: Decimal
    base_amount: Decimal
    document_kind: Kind | None
    document_reference: str
    document_date: dt.date | None
    due_date: dt.date | None


def source_key(party_id: uuid.UUID) -> str:
    """The same key names the staged line and the declaration entry that includes it."""
    return "pob-" + party_id.hex


def reject(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(message, fields={field: message})


def document_kind(role: Role, side: Side) -> Kind | None:
    """A dated bill is only named when role and direction settle what it is.

    The party owes the company for a customer's debit and the company owes the party for a
    supplier's credit. The opposite direction could be a credit note or an advance, and the import
    cannot tell which, so it stays an unnamed dated document.
    """
    if role == "CUSTOMER" and side == "DEBIT":
        return "INVOICE"
    if role == "SUPPLIER" and side == "CREDIT":
        return "BILL"
    return None


def plan(
    *,
    role: Role,
    balance_type: str | None,
    amount: Decimal | None,
    currency: str | None,
    exchange_rate: Decimal | None,
    base_amount: Decimal | None,
    account_code: str | None,
    bill_reference: str | None,
    bill_date: dt.date | None,
    due_date: dt.date | None,
    base_currency: str,
    covered_through: dt.date,
) -> StagedBalance | None:
    """None when the row carries no opening columns; otherwise the checked, normalised line."""
    given = (
        balance_type,
        amount,
        currency,
        exchange_rate,
        base_amount,
        account_code,
        bill_reference,
        bill_date,
        due_date,
    )
    if all(value is None for value in given):
        return None
    if amount is None:
        raise reject("opening_amount", "enter the opening amount")
    if balance_type is None:
        raise reject("opening_balance_type", "choose DR, CR, TO_RECEIVE or TO_PAY")
    side = BALANCE_SIDES[balance_type]
    unit = currency or base_currency
    if unit == base_currency:
        if exchange_rate is not None and exchange_rate != 1:
            raise reject("opening_exchange_rate", "a base-currency balance has rate 1")
        if base_amount is not None and base_amount != amount:
            raise reject("opening_base_amount", "a base-currency balance equals its amount")
        rate, carrying = Decimal(1), amount
    else:
        if exchange_rate is None:
            raise reject("opening_exchange_rate", "enter the exchange rate")
        if base_amount is None:
            raise reject(
                "opening_base_amount",
                "enter the historical carrying value in company currency",
            )
        rate, carrying = exchange_rate, base_amount
    dated = (bill_reference, bill_date, due_date)
    if any(value is not None for value in dated) and any(value is None for value in dated):
        raise reject(
            "opening_bill_reference",
            "a bill needs its reference, date and due date together",
        )
    if bill_reference is None:
        return StagedBalance(
            side, unit, amount, rate, carrying, "ON_ACCOUNT", ON_ACCOUNT_REFERENCE, None, None
        )
    assert bill_date is not None and due_date is not None  # all three were present
    if any(ord(char) < 32 for char in bill_reference) or not bill_reference.strip():
        raise reject("opening_bill_reference", "enter a printable bill reference")
    if bill_date > covered_through:
        raise reject("opening_bill_date", "the bill must predate the opening")
    if due_date < bill_date:
        raise reject("opening_bill_due_date", "the due date cannot precede the bill date")
    return StagedBalance(
        side,
        unit,
        amount,
        rate,
        carrying,
        document_kind(role, side),
        bill_reference.strip(),
        bill_date,
        due_date,
    )


def refused_blockers(blockers: Iterable[str], *, resumable: bool) -> list[str]:
    """What stops a held balance. An existing batch only counts as resumable when it is an
    unfinished worksheet declaration with nothing posted; a legacy or already-posted batch is not,
    since the worksheet cannot take new lines for it.
    """
    tolerated = ALWAYS_TOLERATED | ({"RESUME_EXISTING_OPENING"} if resumable else frozenset())
    return sorted(set(blockers) - tolerated)
