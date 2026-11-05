"""Party-import opening balance rules: pure, with no database."""

import datetime as dt
import re
import uuid
from decimal import Decimal
from typing import Any

import pytest
from billing_platform.errors import ValidationFailedError
from pydantic import ValidationError

from accounting.domain import party_opening as rules
from accounting.schemas.party_opening import OPENING_FIELDS, ReadyPartyCreate

COVERED = dt.date(2026, 3, 31)


def plan(**given: Any) -> rules.StagedBalance | None:
    values: dict[str, Any] = {
        "role": "SUPPLIER",
        "balance_type": None,
        "amount": None,
        "currency": None,
        "exchange_rate": None,
        "base_amount": None,
        "account_code": None,
        "bill_reference": None,
        "bill_date": None,
        "due_date": None,
        "base_currency": "INR",
        "covered_through": COVERED,
    }
    return rules.plan(**(values | given))


def refused(**given: Any) -> str:
    with pytest.raises(ValidationFailedError) as caught:
        plan(**given)
    (field,) = caught.value.extra["fields"]
    return str(field)


def test_a_row_without_opening_columns_stages_nothing() -> None:
    assert plan() is None


@pytest.mark.parametrize(
    ("balance_type", "side"),
    [("DR", "DEBIT"), ("TO_RECEIVE", "DEBIT"), ("CR", "CREDIT"), ("TO_PAY", "CREDIT")],
)
@pytest.mark.parametrize("role", ["CUSTOMER", "SUPPLIER"])
def test_balance_type_sets_the_side_whatever_the_role(
    balance_type: str, side: str, role: str
) -> None:
    staged = plan(role=role, balance_type=balance_type, amount=Decimal("125.50"))
    assert staged is not None and staged.side == side


def test_an_undated_balance_is_held_on_account_in_company_currency() -> None:
    staged = plan(balance_type="TO_PAY", amount=Decimal("10"))
    assert staged == rules.StagedBalance(
        "CREDIT",
        "INR",
        Decimal("10"),
        Decimal(1),
        Decimal("10"),
        "ON_ACCOUNT",
        rules.ON_ACCOUNT_REFERENCE,
        None,
        None,
    )


def test_the_amount_and_the_type_come_together() -> None:
    assert refused(balance_type="TO_PAY") == "opening_amount"
    assert refused(amount=Decimal("5")) == "opening_balance_type"
    assert refused(currency="INR") == "opening_amount"


def test_a_base_currency_balance_has_rate_one_and_an_equal_base_amount() -> None:
    kind: dict[str, Any] = {"balance_type": "DR", "amount": Decimal("100")}
    assert refused(**kind, exchange_rate=Decimal("2")) == "opening_exchange_rate"
    assert refused(**kind, base_amount=Decimal("99")) == "opening_base_amount"
    staged = plan(**kind, currency="INR", exchange_rate=Decimal(1), base_amount=Decimal("100"))
    assert staged is not None and staged.base_amount == Decimal("100")


def test_a_foreign_balance_needs_its_rate_and_its_historical_carrying_value() -> None:
    kind: dict[str, Any] = {"balance_type": "DR", "amount": Decimal("100"), "currency": "USD"}
    assert refused(**kind) == "opening_exchange_rate"
    assert refused(**kind, exchange_rate=Decimal("83.2")) == "opening_base_amount"
    staged = plan(**kind, exchange_rate=Decimal("83.2"), base_amount=Decimal("8300"))
    assert staged is not None
    assert (staged.currency, staged.exchange_rate, staged.base_amount) == (
        "USD",
        Decimal("83.2"),
        Decimal("8300"),
    )


def test_the_carrying_value_is_not_recomputed_from_the_rate() -> None:
    staged = plan(
        balance_type="DR",
        amount=Decimal("100"),
        currency="USD",
        exchange_rate=Decimal("83.2"),
        base_amount=Decimal("8000"),
    )
    assert staged is not None and staged.base_amount == Decimal("8000")


def test_a_bill_needs_its_reference_date_and_due_date_together() -> None:
    kind: dict[str, Any] = {"balance_type": "TO_PAY", "amount": Decimal("100")}
    day = dt.date(2026, 3, 1)
    assert refused(**kind, bill_reference="B-1") == "opening_bill_reference"
    assert refused(**kind, bill_reference="B-1", bill_date=day) == "opening_bill_reference"
    assert refused(**kind, bill_date=day, due_date=day) == "opening_bill_reference"


def test_a_bill_must_predate_the_opening_and_fall_due_after_it_was_issued() -> None:
    kind: dict[str, Any] = {
        "balance_type": "TO_PAY",
        "amount": Decimal("100"),
        "bill_reference": "B-1",
    }
    assert refused(**kind, bill_date=dt.date(2026, 4, 1), due_date=dt.date(2026, 4, 9)) == (
        "opening_bill_date"
    )
    assert refused(**kind, bill_date=COVERED, due_date=dt.date(2026, 3, 30)) == (
        "opening_bill_due_date"
    )
    ok = plan(**kind, bill_date=COVERED, due_date=COVERED)
    assert ok is not None and ok.document_date == COVERED


@pytest.mark.parametrize("reference", ["  ", "A\tB", "A\nB"])
def test_a_bill_reference_must_be_printable(reference: str) -> None:
    assert (
        refused(
            balance_type="TO_PAY",
            amount=Decimal("1"),
            bill_reference=reference,
            bill_date=COVERED,
            due_date=COVERED,
        )
        == "opening_bill_reference"
    )


@pytest.mark.parametrize(
    ("role", "balance_type", "kind"),
    [
        ("CUSTOMER", "TO_RECEIVE", "INVOICE"),
        ("SUPPLIER", "TO_PAY", "BILL"),
        ("CUSTOMER", "TO_PAY", None),
        ("SUPPLIER", "TO_RECEIVE", None),
    ],
)
def test_a_dated_bill_is_named_only_when_role_and_direction_decide_it(
    role: str, balance_type: str, kind: str | None
) -> None:
    staged = plan(
        role=role,
        balance_type=balance_type,
        amount=Decimal("50"),
        bill_reference=" INV-9 ",
        bill_date=dt.date(2026, 2, 1),
        due_date=dt.date(2026, 3, 1),
    )
    assert staged is not None
    assert staged.document_kind == kind
    assert staged.document_reference == "INV-9"


def test_source_key_is_stable_and_valid_for_a_declaration_entry() -> None:
    party = uuid.uuid4()
    key = rules.source_key(party)
    assert key == rules.source_key(party) != rules.source_key(uuid.uuid4())
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", key)


def base_row(**extra: Any) -> dict[str, Any]:
    return {
        "code": "S1",
        "name": "Supplier",
        "legal_name": "Supplier Ltd",
        "country_code": "IN",
    } | extra


def test_the_ready_row_accepts_opening_columns_and_lists_them_for_the_template() -> None:
    row = ReadyPartyCreate.model_validate(
        base_row(opening_balance_type="TO_PAY", opening_amount="1250.5")
    )
    assert row.opening_amount == Decimal("1250.5")
    properties = ReadyPartyCreate.model_json_schema()["properties"]
    assert OPENING_FIELDS <= set(properties)
    assert {name for name in properties if name.startswith("opening_")} == set(OPENING_FIELDS)
    assert "required" not in properties["opening_amount"]
    assert set(ReadyPartyCreate.model_json_schema()["required"]) == {
        "code",
        "name",
        "legal_name",
        "country_code",
    }


@pytest.mark.parametrize(
    ("extra", "column"),
    [
        ({"opening_balance_type": "TO_PAY"}, "opening_amount"),
        ({"opening_account_code": "ACC-1"}, "opening_amount"),
        ({"opening_bill_reference": "B-1"}, "opening_amount"),
        ({"opening_currency": "USD"}, "opening_amount"),
    ],
)
def test_opening_columns_without_an_amount_are_reported_against_the_amount_column(
    extra: dict[str, Any], column: str
) -> None:
    """The schema stays permissive so the opening rules, not a bare type error, name the column."""
    row = ReadyPartyCreate.model_validate(base_row(**extra))
    with pytest.raises(ValidationFailedError) as caught:
        plan(
            balance_type=row.opening_balance_type,
            currency=row.opening_currency,
            account_code=row.opening_account_code,
            bill_reference=row.opening_bill_reference,
        )
    assert list(caught.value.extra["fields"]) == [column]


@pytest.mark.parametrize(
    ("blockers", "resumable", "refused"),
    [
        ([], False, []),
        (["BOOKS_BEGIN_PERIOD_NOT_OPEN"], False, []),
        (["RESUME_EXISTING_OPENING"], True, []),
        (["RESUME_EXISTING_OPENING"], False, ["RESUME_EXISTING_OPENING"]),
        (["OPENING_ALREADY_FINALIZED"], True, ["OPENING_ALREADY_FINALIZED"]),
        (["LATER_BOOKS_CLOSED", "BOOKS_BEGIN_PERIOD_NOT_OPEN"], False, ["LATER_BOOKS_CLOSED"]),
        (["LEGACY_ACTIVITY_REQUIRES_REVIEW"], False, ["LEGACY_ACTIVITY_REQUIRES_REVIEW"]),
        (
            ["FINANCIAL_SETUP_NOT_INITIALIZED", "ACCOUNTING_NOT_INITIALIZED"],
            True,
            [
                "ACCOUNTING_NOT_INITIALIZED",
                "FINANCIAL_SETUP_NOT_INITIALIZED",
            ],
        ),
    ],
)
def test_only_blockers_a_declaration_could_clear_are_tolerated(
    blockers: list[str], resumable: bool, refused: list[str]
) -> None:
    assert rules.refused_blockers(blockers, resumable=resumable) == refused


@pytest.mark.parametrize(
    "extra",
    [
        {"opening_amount": 10.5, "opening_balance_type": "DR"},
        {"opening_amount": "0", "opening_balance_type": "DR"},
        {"opening_amount": "-3", "opening_balance_type": "DR"},
        {"opening_amount": "1.12345", "opening_balance_type": "DR"},
        {"opening_amount": "1", "opening_balance_type": "debit"},
        {"opening_amount": "1", "opening_balance_type": "DR", "opening_currency": "usd"},
        {"opening_amount": "1", "opening_balance_type": "DR", "surprise": "x"},
    ],
)
def test_malformed_opening_columns_are_rejected(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ReadyPartyCreate.model_validate(base_row(**extra))
