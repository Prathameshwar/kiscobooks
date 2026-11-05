"""Ordinary selection, direction and clearing rules without persistence."""

import datetime as dt
import uuid
from dataclasses import replace

import pytest
from billing_platform.errors import ConflictError, ValidationFailedError
from voucher_execution.money import MoneyInput, MoneyPolicy

from accounting.domain.banking import next_event
from accounting.domain.voucher_money import MoneyAccount, validate_accounts


def fixture():
    ids, keys = [uuid.uuid4() for _ in range(2)], [uuid.uuid4() for _ in range(2)]
    body = {
        "purpose": "GENERAL",
        "accounts": [
            {
                "line_key": keys[index],
                "account_id": identity,
                "source_version": 1,
                "side": side,
                "currency": "INR",
                "amount": "100",
            }
            for index, (identity, side) in enumerate(zip(ids, ("CREDIT", "DEBIT"), strict=True))
        ],
        "tenders": [
            {
                "tender_key": uuid.uuid4(),
                "line_key": keys[0],
                "mode": "CASH",
                "amount": "100",
                "currency": "INR",
            }
        ],
    }
    accounts = {
        ids[0]: MoneyAccount(ids[0], "CASH", "MANUAL_ALLOWED", None, 1),
        ids[1]: MoneyAccount(ids[1], "GENERAL", "MANUAL_ALLOWED", None, 1),
    }
    return body, accounts, ids


def test_contra_without_split_payments_still_records_both_transfer_legs():
    body, accounts, ids = fixture()
    body["purpose"] = "TRANSFER"
    accounts[ids[1]] = replace(accounts[ids[1]], kind="CASH")
    body["tenders"].append(
        body["tenders"][0]
        | {"tender_key": uuid.uuid4(), "line_key": body["accounts"][1]["line_key"]}
    )
    validate_accounts(
        MoneyInput.model_validate(body),
        MoneyPolicy(split_tenders_allowed=False),
        accounts,
        kind="CONTRA",
        profile="STANDARD",
        base_currency="INR",
        posting_date=dt.date(2026, 4, 1),
    )


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "version",
        "allowed_kind",
        "foreign",
        "party_tracking",
        "party_adjustment",
        "protected",
        "tracking",
        "cash_adjustment",
        "journal_cash",
        "direction",
        "contra_general",
        "contra_same",
        "advance_role",
        "advance_tracking",
        "refund_role",
        "cash_required",
        "party_required",
        "tender_required",
        "mode_mismatch",
        "unsupported_kind",
        "unsupported_profile",
    ],
)
def test_money_roles_and_evidence(case):
    body, accounts, ids = fixture()
    first, second = body["accounts"]
    policy = MoneyPolicy(settlement_adjustments_allowed=True)
    kind = "PAYMENT"
    if case == "version":
        accounts[ids[0]] = replace(accounts[ids[0]], version=2)
    if case == "allowed_kind":
        policy = MoneyPolicy(allowed_account_kinds=frozenset({"GENERAL"}))
    if case == "foreign":
        first["currency"] = body["tenders"][0]["currency"] = "USD"
    if case.startswith("party_") and case != "party_required":
        accounts[ids[1]] = replace(accounts[ids[1]], kind="PARTY", party_role="CUSTOMER")
        if case == "party_adjustment":
            second.update(tracking="ON_ACCOUNT", purpose="FEE")
    if case == "protected":
        accounts[ids[1]] = replace(accounts[ids[1]], posting_policy="SOURCE_ONLY")
    if case == "tracking":
        second["tracking"] = "ON_ACCOUNT"
    if case == "cash_adjustment":
        first["purpose"] = "DISCOUNT"
    if case == "journal_cash":
        kind = "JOURNAL"
    if case == "direction":
        first["side"] = "DEBIT"
    if case.startswith("contra_"):
        kind, body["purpose"] = "CONTRA", "TRANSFER"
        if case == "contra_same":
            second["account_id"] = ids[0]
    if case in {"advance_role", "advance_tracking", "refund_role"}:
        body["purpose"] = "REFUND" if case == "refund_role" else "ADVANCE"
        accounts[ids[1]] = replace(
            accounts[ids[1]],
            kind="PARTY",
            party_role="CUSTOMER" if case == "advance_role" else "SUPPLIER",
        )
        second["tracking"] = "ON_ACCOUNT" if case == "advance_tracking" else "ADVANCE"
    if case == "cash_required":
        accounts[ids[0]] = replace(accounts[ids[0]], kind="GENERAL")
        body["tenders"] = []
    if case == "party_required":
        body["purpose"] = "ADVANCE"
    if case == "tender_required":
        body["tenders"] = []
    if case == "mode_mismatch":
        body["tenders"][0].update(mode="NEFT", reference="WIRE-1")
    if case == "unsupported_kind":
        kind = "SALES"
    data = MoneyInput.model_validate(body)
    arguments = {
        "kind": kind,
        "profile": "UNSUPPORTED" if case == "unsupported_profile" else "STANDARD",
        "base_currency": "INR",
        "posting_date": dt.date(2026, 4, 1),
    }
    if case == "valid":
        validate_accounts(data, policy, accounts, **arguments)
    else:
        with pytest.raises(ValidationFailedError):
            validate_accounts(data, policy, accounts, **arguments)


@pytest.mark.parametrize(
    "previous,action",
    [
        ("BOOKED", "PRESENTED"),
        ("DISHONOURED", "PRESENTED"),
        ("BOOKED", "CLEARED"),
        ("PRESENTED", "CLEARED"),
        ("PRESENTED", "DISHONOURED"),
        ("CLEARED", "RECONCILED"),
        ("UNRECONCILED", "RECONCILED"),
        ("RECONCILED", "UNRECONCILED"),
    ],
)
def test_bank_events_append_without_money(previous, action):
    next_event(
        previous,
        action,
        last_date=dt.date(2026, 4, 1),
        date=dt.date(2026, 4, 2),
        instrument_date=dt.date(2026, 4, 2),
        reference="STATEMENT-1",
    )


@pytest.mark.parametrize(
    "previous,action,last,date,instrument,reference,error",
    [
        ("REVERSED", "CLEARED", 2, 3, None, None, ConflictError),
        ("BOOKED", "PRESENTED", 3, 2, None, None, ValidationFailedError),
        ("BOOKED", "CLEARED", 1, 2, 3, None, ValidationFailedError),
        ("CLEARED", "RECONCILED", 1, 2, None, None, ValidationFailedError),
    ],
)
def test_bank_rejects_invalid_order_or_evidence(
    previous, action, last, date, instrument, reference, error
):
    with pytest.raises(error):
        next_event(
            previous,
            action,
            last_date=dt.date(2026, 4, last),
            date=dt.date(2026, 4, date),
            instrument_date=dt.date(2026, 4, instrument) if instrument else None,
            reference=reference,
        )
