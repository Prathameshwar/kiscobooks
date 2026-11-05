"""Two-year continuity reviews retain balances, bill identities and snapshot evidence."""

import datetime as dt
import uuid

import pytest
from billing_platform.errors import ConflictError
from financial_fixture import financial_dataset
from fixtures import source
from pydantic import ValidationError

from reports.domain.statements import calculate
from reports.schemas.requests import RunRequest


def query(**changes):
    return RunRequest.model_validate(
        {
            "code": "BALANCE_CONTINUITY",
            "generation_id": str(uuid.uuid4()),
            "date_from": "2027-04-01",
            "date_to": "2028-03-31",
            **changes,
        }
    )


def test_continuity_keeps_original_bills_and_prior_earnings_before_next_year_movements():
    facts, ids = financial_dataset()
    rows, evidence = calculate(facts, query(), dt.date(2026, 4, 1))
    control = rows[0]
    assert control["row_kind"] == "CONTINUITY_CONTROL"
    assert control["reconciled"] is True and control["difference"] == "0.0000"
    assert control["previous_closing_date"] == "2027-03-31"
    assert control["next_opening_date"] == "2027-04-01"
    cash = next(row for row in rows if row.get("account_id") == ids["cash"])
    assert cash["previous_closing"] == cash["next_opening"] == "180.0000"
    bill = next(row for row in rows if row["row_kind"] == "BILL_CONTINUITY")
    assert bill["previous_closing"] == bill["next_opening"] == "150.0000"
    assert bill["due_date"] == "2026-04-02"
    assert bill["item_id"] in {str(fact.source_id) for fact in facts if fact.entity == "open_item"}
    advance = next(row for row in rows if row["row_kind"] == "ADVANCE_CONTINUITY")
    assert advance["next_opening"] == "70.0000"
    earnings = next(row for row in rows if row["row_kind"] == "EARNINGS_CONTINUITY")
    assert earnings["previous_closing"] == earnings["next_opening"] == "160.0000"
    assert evidence["continuity_basis"] == "RETAINED_LEDGER_BEFORE_FIRST_MOVEMENT"
    # The April settlement remains in the existing ordinary as-of report, never reset.
    later, _ = calculate(
        facts, query(code="OUTSTANDING_BILLS", date_to="2027-04-30"), dt.date(2026, 4, 1)
    )
    assert (
        next(row for row in later if row["item_id"] == bill["item_id"])["remaining"] == "120.0000"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"account_id": str(uuid.uuid4())},
        {"comparative_from": "2026-04-01", "comparative_to": "2027-03-31"},
        {"basis": "TRANSACTION", "currency": "INR"},
        {"grain": "MONTH"},
    ],
)
def test_continuity_requires_complete_base_currency_source(change):
    with pytest.raises(ValidationError):
        query(**change)


def test_continuity_rejects_incomplete_original_history_and_non_calendar_ranges():
    facts, _ = financial_dataset()
    with pytest.raises(ConflictError, match="original books"):
        calculate(facts, query(), dt.date(2026, 5, 1))
    with pytest.raises(ConflictError, match="complete financial year"):
        calculate(facts, query(date_to="2027-04-30"), dt.date(2026, 4, 1))


def test_continuity_requires_a_contiguous_previous_calendar():
    facts, _ = financial_dataset()
    facts = [
        fact
        for fact in facts
        if fact.entity != "fiscal_year" or fact.data["start_date"] != "2026-04-01"
    ]
    with pytest.raises(ConflictError, match="previous financial year"):
        calculate(facts, query(), dt.date(2026, 4, 1))


def test_continuity_refuses_a_noncanonical_previous_calendar_in_the_frozen_source():
    facts, _ = financial_dataset()
    prior = next(
        fact
        for fact in facts
        if fact.entity == "fiscal_year" and fact.data["start_date"] == "2026-04-01"
    )
    prior.data["start_date"] = "2026-04-02"
    with pytest.raises(ConflictError, match="frozen company calendar"):
        calculate(facts, query(), dt.date(2026, 4, 1))


def test_extra_annual_opening_is_exposed_as_a_difference_instead_of_certified():
    facts, ids = financial_dataset()
    journal = next(
        fact
        for fact in facts
        if fact.entity == "journal" and fact.data["posting_date"] == "2027-04-02"
    )
    identity = uuid.uuid4()
    facts.append(
        source(
            "journal",
            identity,
            journal.data
            | {"posting_date": "2027-04-01", "kind": "OPENING", "reversal_of_id": None},
        )
    )
    template = next(fact.data for fact in facts if fact.entity == "journal_line")
    for index, side, account in ((1, "DEBIT", ids["cash"]), (2, "CREDIT", ids["equity"])):
        facts.append(
            source(
                "journal_line",
                uuid.uuid4(),
                template
                | {
                    "journal_id": str(identity),
                    "sequence": index,
                    "side": side,
                    "account_id": account,
                    "party_id": None,
                    "role": None,
                    "amount": "100.0000",
                    "base_amount": "100.0000",
                },
            )
        )
    rows, _ = calculate(facts, query(), dt.date(2026, 4, 1))
    assert rows[0]["reconciled"] is False and rows[0]["difference"] == "200.0000"
    assert (
        next(row for row in rows if row.get("account_id") == ids["cash"])["difference"]
        == "100.0000"
    )
