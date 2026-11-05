"""Financial arithmetic invariants without persistence."""

import datetime as dt
from dataclasses import replace
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.money import RoundingMode

from accounting.domain.ledger import Entry, Term, exact_positive, payment_schedule, value_entries


def test_balanced_conversion_and_rounding_boundary() -> None:
    entries = (
        Entry(uuid7(), "DEBIT", "USD", Decimal("10"), Decimal("83.12345678")),
        Entry(uuid7(), "CREDIT", "INR", Decimal("831.23"), Decimal(1)),
    )
    valued = value_entries(entries, "INR", 2, RoundingMode.HALF_UP)
    assert valued[0].base_amount == Decimal("831.2300")
    assert type(valued[0].base_amount) is Decimal
    assert valued[0].entry.exchange_rate == Decimal("83.12345678")


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1", "0", "0.00001", "1000000000000000"])
def test_exact_money_rejects_invalid_values(amount: str) -> None:
    with pytest.raises(ValidationFailedError):
        exact_positive(Decimal(amount))


@pytest.mark.parametrize(
    "changes",
    [
        {"side": "OTHER"},
        {"currency": "inr"},
        {"currency": "12A"},
        {"exchange_rate": Decimal(2)},
        {"exchange_rate": Decimal("0")},
        {"exchange_rate": Decimal("1.000000001")},
        {"amount": Decimal("1.0001")},
    ],
)
def test_invalid_or_unbalanced_entries_are_rejected(changes: dict[str, object]) -> None:
    entry = Entry(uuid7(), "DEBIT", "INR", Decimal(1), Decimal(1))
    # Pydantic and service callers validate types; dataclass replacement keeps domain checks direct.
    from typing import Any, cast

    incoming = replace(entry, **cast(dict[str, Any], changes))
    with pytest.raises(ValidationFailedError):
        value_entries((incoming, replace(entry, side="CREDIT")), "INR", 4, RoundingMode.HALF_UP)


def test_journal_line_count_and_tiny_conversion() -> None:
    entry = Entry(uuid7(), "DEBIT", "USD", Decimal("0.0001"), Decimal("0.00000001"))
    for entries in ((entry,), (entry,) * 201, (entry, replace(entry, side="CREDIT"))):
        with pytest.raises(ValidationFailedError):
            value_entries(entries, "INR", 2, RoundingMode.HALF_UP)
    huge = Entry(uuid7(), "DEBIT", "USD", Decimal("999999999999999"), Decimal("99999999999"))
    with pytest.raises(ValidationFailedError):
        value_entries((huge, replace(huge, side="CREDIT")), "INR", 2, RoundingMode.HALF_UP)


def test_installments_keep_residual_and_month_end_basis() -> None:
    schedule = payment_schedule(
        Decimal("10.0001"),
        dt.date(2024, 2, 15),
        (
            Term(2, Decimal("33.3333"), "MONTH_END", 1),
            Term(1, Decimal("33.3333"), "INVOICE_DATE", 15),
            Term(3, Decimal("33.3334"), "INVOICE_DATE", 60),
        ),
        precision=2,
        rounding=RoundingMode.HALF_UP,
    )
    assert [part.amount for part in schedule] == [
        Decimal("3.33"),
        Decimal("3.33"),
        Decimal("3.3401"),
    ]
    assert schedule[0].due_date == dt.date(2024, 3, 1)
    assert schedule[1].due_date == dt.date(2024, 3, 1)
    assert sum((part.amount for part in schedule), Decimal(0)) == Decimal("10.0001")


def test_small_amount_never_creates_zero_or_negative_installment() -> None:
    schedule = payment_schedule(
        Decimal("0.01"),
        dt.date(2026, 4, 1),
        (
            Term(1, Decimal("50"), "INVOICE_DATE", 0),
            Term(2, Decimal("50"), "INVOICE_DATE", 30),
        ),
        precision=2,
        rounding=RoundingMode.HALF_UP,
    )
    assert len(schedule) == 1 and schedule[0].amount == Decimal("0.01")


@pytest.mark.parametrize(
    "terms",
    [
        (),
        (Term(1, Decimal(99), "INVOICE_DATE", 0),),
        (Term(1, Decimal(50), "INVOICE_DATE", 0), Term(1, Decimal(50), "INVOICE_DATE", 0)),
        (Term(0, Decimal(100), "INVOICE_DATE", 0),),
        (Term(1, Decimal(100), "OTHER", 0),),
        (Term(1, Decimal(100), "INVOICE_DATE", -1),),
    ],
)
def test_invalid_installment_terms_are_rejected(terms: tuple[Term, ...]) -> None:
    with pytest.raises(ValidationFailedError):
        payment_schedule(
            Decimal(100), dt.date(2026, 4, 1), terms, precision=2, rounding=RoundingMode.HALF_UP
        )


def test_installment_date_overflow_is_a_validation_error() -> None:
    with pytest.raises(ValidationFailedError):
        payment_schedule(
            Decimal(100),
            dt.date(9999, 12, 31),
            (Term(1, Decimal(100), "INVOICE_DATE", 1),),
            precision=2,
            rounding=RoundingMode.HALF_UP,
        )


def test_base_currency_journal_preserves_entered_storage_precision() -> None:
    entry = Entry(uuid7(), "DEBIT", "INR", Decimal("0.0001"), Decimal(1))
    valued = value_entries((entry, replace(entry, side="CREDIT")), "INR", 2, RoundingMode.HALF_UP)
    assert valued[0].base_amount == valued[1].base_amount == Decimal("0.0001")
