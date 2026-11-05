"""Exact balances and bill evidence captured with a new master, without posting."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from pydantic import ValidationError

from accounting.domain.master_opening import entry
from accounting.schemas.master_opening import MasterOpeningInput

DATE = dt.date(2026, 4, 1)
ACCOUNT = uuid.uuid4()


def opening(**values):
    return MasterOpeningInput.model_validate(
        {"amount": "100", "side": "DEBIT", "opening_date": str(DATE)} | values
    )


def plan(body=None, **values):
    return entry(
        body or opening(),
        account_id=ACCOUNT,
        role=None,
        party=False,
        currency="INR",
        base_currency="INR",
        opening_date=DATE,
        **values,
    )


def bill(**values):
    return {
        "reference": "INV-1",
        "amount": "60",
        "original_amount": "100",
        "document_kind": "INVOICE",
        "document_date": "2026-03-10",
        "due_date": "2026-04-10",
    } | values


def test_simple_balance_is_exact_and_has_no_general_account_bills():
    result = plan(opening(amount="100.0001"))
    assert result.amount == Decimal("100.0001") and isinstance(result.amount, Decimal)
    assert result.base_amount == result.amount and result.exchange_rate == Decimal(1)
    assert result.documents == []
    assert result.source_key == "mob-" + ACCOUNT.hex


def test_party_on_account_keeps_unknown_document_dates():
    result = entry(
        opening(),
        account_id=ACCOUNT,
        role="CUSTOMER",
        party=True,
        currency="INR",
        base_currency="INR",
        opening_date=DATE,
    )
    assert len(result.documents) == 1
    assert result.documents[0].document_kind == "ON_ACCOUNT"
    assert result.documents[0].document_date is None and result.documents[0].due_date is None


@pytest.mark.parametrize(
    "base, total, valid",
    [(None, "8300", False), ("0", "8300", False), ("8299", "8300", False), ("8300", "8300", True)],
)
def test_foreign_bills_preserve_explicit_historical_carrying_values(base, total, valid):
    if base == "0":
        with pytest.raises(ValidationError):
            opening(
                amount="100",
                exchange_rate="83",
                base_amount=total,
                documents=[bill(amount="100", base_amount=base)],
            )
        return
    body = opening(
        amount="100",
        exchange_rate="83.12345678",
        base_amount=total,
        documents=[bill(amount="100", base_amount=base)],
    )

    def make():
        return entry(
            body,
            account_id=ACCOUNT,
            role="CUSTOMER",
            party=True,
            currency="USD",
            base_currency="INR",
            opening_date=DATE,
        )

    if valid:
        value = make()
        assert value.base_amount == Decimal(total) and value.documents[0].base_amount == Decimal(
            base
        )
    else:
        with pytest.raises(ValidationFailedError):
            make()


def test_bill_sequence_and_company_currency_carrying_are_checked():
    for changes in ({"line_sequence": 2}, {"base_amount": "99"}):
        with pytest.raises(ValidationFailedError):
            entry(
                opening(documents=[bill(amount="100", **changes)]),
                account_id=ACCOUNT,
                role="CUSTOMER",
                party=True,
                currency="INR",
                base_currency="INR",
                opening_date=DATE,
            )


def test_bills_keep_original_evidence_and_only_pending_is_the_opening():
    body = opening(
        amount="100",
        documents=[bill(), bill(reference="INV-2", amount="40", original_amount="250")],
    )
    result = entry(
        body,
        account_id=ACCOUNT,
        role="CUSTOMER",
        party=True,
        currency="INR",
        base_currency="INR",
        opening_date=DATE,
    )
    assert result.amount == Decimal(100)
    assert sum(doc.original_amount for doc in result.documents) == Decimal(350)
    assert [doc.amount for doc in result.documents] == [Decimal(60), Decimal(40)]


@pytest.mark.parametrize(
    "values",
    [
        {"amount": "0"},
        {"amount": "-1"},
        {"amount": "1.00001"},
        {"side": "DR"},
        {"opening_date": "invalid"},
    ],
)
def test_rejects_invalid_basic_input(values):
    with pytest.raises(ValidationError):
        opening(**values)


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": "101"},
        {"original_amount": None},
        {"original_amount": "0"},
        {"document_date": "2026-04-01"},
        {"due_date": "2026-03-01"},
        {"document_kind": "BILL"},
    ],
)
def test_rejects_invalid_bill_evidence(changes):
    with pytest.raises((ValidationError, ValidationFailedError)):
        entry(
            opening(amount="60", documents=[bill(**changes)]),
            account_id=ACCOUNT,
            role="CUSTOMER",
            party=True,
            currency="INR",
            base_currency="INR",
            opening_date=DATE,
        )


def test_rejects_bill_totals_duplicates_and_general_account_documents():
    for documents in ([bill()], [bill(amount="50"), bill(amount="50", reference=" inv-1 ")]):
        with pytest.raises(ValidationFailedError):
            entry(
                opening(documents=documents),
                account_id=ACCOUNT,
                role="CUSTOMER",
                party=True,
                currency="INR",
                base_currency="INR",
                opening_date=DATE,
            )
    with pytest.raises(ValidationFailedError):
        plan(opening(amount="60", documents=[bill()]))


def test_opening_date_must_equal_company_cutover():
    with pytest.raises(ValidationFailedError):
        plan(opening(opening_date="2026-04-02"))


def test_foreign_balance_keeps_entered_historical_value():
    result = entry(
        opening(exchange_rate="82.12345678", base_amount="8100.0001"),
        account_id=ACCOUNT,
        role=None,
        party=False,
        currency="USD",
        base_currency="INR",
        opening_date=DATE,
    )
    assert result.base_amount == Decimal("8100.0001")
    assert result.exchange_rate == Decimal("82.12345678")
    with pytest.raises(ValidationFailedError):
        entry(
            opening(),
            account_id=ACCOUNT,
            role=None,
            party=False,
            currency="USD",
            base_currency="INR",
            opening_date=DATE,
        )


def test_base_rate_and_value_cannot_change():
    for values in ({"exchange_rate": "2"}, {"base_amount": "101"}):
        with pytest.raises(ValidationFailedError):
            plan(opening(**values))


@pytest.mark.parametrize(
    "role,side,kind",
    [
        ("CUSTOMER", "DEBIT", "INVOICE"),
        ("SUPPLIER", "CREDIT", "BILL"),
        ("CUSTOMER", "CREDIT", "ADVANCE"),
        ("SUPPLIER", "DEBIT", "CREDIT_NOTE"),
    ],
)
def test_document_kind_matches_party_role_and_direction(role, side, kind):
    result = entry(
        opening(amount="60", side=side, documents=[bill(document_kind=kind)]),
        account_id=ACCOUNT,
        role=role,
        party=True,
        currency="INR",
        base_currency="INR",
        opening_date=DATE,
    )
    assert result.documents[0].document_kind == kind
