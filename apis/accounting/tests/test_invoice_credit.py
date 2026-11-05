from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError

from accounting.domain.invoice_credit import (
    CreditEvent,
    CreditEvidence,
    CreditTerms,
    credit_deadline,
    position,
)

DAY = date(2026, 4, 1)
TERMS = CreditTerms(DAY, False, True)
PROOF = CreditEvidence(
    True, True, True, True, True, True, True, True, "Verified documents and return ARN"
)


def event(kind, amount="100", day=DAY, proof=PROOF):
    return CreditEvent(kind, Decimal(amount), day, proof)


def test_record_verify_claim_partial_reversal_and_payment_reclaim_do_not_duplicate_credit():
    history = (event("RECORD"),)
    assert position(TERMS, history).pending == 100
    history += (event("VERIFY", "70"), event("BLOCK", "30"), event("CLAIM", "60"))
    state = position(TERMS, history)
    assert (state.pending, state.blocked, state.eligible_unclaimed, state.claimed) == (
        0,
        30,
        10,
        60,
    )
    history += (
        event("REVERSE_PAYMENT", "20", date(2026, 10, 1), replace(PROOF, supplier_paid=False)),
    )
    assert position(TERMS, history).suspended == 20
    history += (event("RECLAIM_PAYMENT", "20", date(2028, 1, 1)),)
    assert position(TERMS, history).claimed == 60
    with pytest.raises(ValidationFailedError, match="exceeds"):
        position(TERMS, (*history, event("RECLAIM_PAYMENT", "1", date(2028, 1, 1))))


def test_rcm_deposit_or_invoice_alone_cannot_enable_credit():
    terms = replace(TERMS, reverse_charge=True)
    recorded = (event("RECORD"),)
    with pytest.raises(ValidationFailedError, match="discharge"):
        position(terms, (*recorded, event("VERIFY")))
    with pytest.raises(ValidationFailedError, match="offset"):
        position(terms, (*recorded, event("RCM_DISCHARGE", proof=None)))
    history = (*recorded, event("RCM_DISCHARGE", "40"), event("VERIFY", "40"), event("CLAIM", "40"))
    state = position(terms, history)
    assert state.rcm_discharged == state.claimed == 40 and state.pending == 60
    with pytest.raises(ValidationFailedError, match="discharge"):
        position(terms, (*history, event("VERIFY", "1")))


@pytest.mark.parametrize(
    "field",
    [
        "document_verified",
        "supply_received",
        "business_use",
        "restrictions_checked",
        "supplier_report_matched",
        "tax_payment_verified",
    ],
)
def test_each_credit_condition_is_independent(field):
    with pytest.raises(ValidationFailedError):
        position(TERMS, (event("RECORD"), event("VERIFY", proof=replace(PROOF, **{field: False}))))


def test_statutory_year_time_limit_is_not_gl_year_and_return_can_close_it_early():
    assert credit_deadline(replace(TERMS, supplier_invoice_date=date(2026, 3, 31))) == date(
        2026, 11, 30
    )
    assert credit_deadline(TERMS) == date(2027, 11, 30)
    early = replace(TERMS, annual_return_filed_on=date(2027, 9, 1))
    assert credit_deadline(early) == date(2027, 9, 1)
    with pytest.raises(ValidationFailedError, match="expired"):
        position(early, (event("RECORD"), event("VERIFY", day=date(2027, 9, 2))))
    with pytest.raises(ValidationFailedError, match="180|unpaid"):
        position(
            TERMS,
            (
                event("RECORD"),
                event("VERIFY", day=date(2026, 12, 1), proof=replace(PROOF, supplier_paid=False)),
            ),
        )


@pytest.mark.parametrize(
    "kind,amount",
    [
        ("RECORD", "1"),
        ("VERIFY", "101"),
        ("CLAIM", "1"),
        ("BLOCK", "101"),
        ("RCM_DISCHARGE", "1"),
        ("REVERSE_PAYMENT", "1"),
        ("RECLAIM_PAYMENT", "1"),
        ("UNKNOWN", "1"),
        ("VERIFY", "0"),
        ("VERIFY", "-1"),
    ],
)
def test_credit_history_cannot_exceed_its_source_or_skip_states(kind, amount):
    with pytest.raises(ValidationFailedError):
        position(TERMS, (event("RECORD"), event(kind, amount)))


def test_blocked_and_unacknowledged_credit_never_becomes_claimed():
    assert position(replace(TERMS, recoverable=False), (event("RECORD"),)).blocked == 100
    with pytest.raises(ValidationFailedError):
        position(replace(TERMS, recoverable=False), (event("RECORD"), event("VERIFY")))
    with pytest.raises(ValidationFailedError, match="acknowledged"):
        position(
            TERMS,
            (
                event("RECORD"),
                event("VERIFY"),
                event("CLAIM", proof=replace(PROOF, return_filed=False)),
            ),
        )
