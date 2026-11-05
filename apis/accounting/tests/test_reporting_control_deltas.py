from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from reporting_contract.contract import Control

from accounting.domain.reporting_controls import Contribution, advance
from accounting.tasks import reporting_feed as feed
from tests.conftest import COMPANY, TENANT
from tests.test_ledger_api import create_journal, journal_setup, post_journal


async def test_ordinary_posting_uses_deltas_and_matches_independent_full_controls(
    app, client, monkeypatch
):
    body, _, _ = await journal_setup(client, app)
    full_controls = feed.controls

    def refuse_full_company_scan(*args):
        raise AssertionError("ordinary commits must not rescan the company ledger")

    monkeypatch.setattr(feed, "controls", refuse_full_company_scan)
    draft = await create_journal(client, body)
    result = await post_journal(client, draft)
    assert result.status_code == 200, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            receipt = await db.run_sync(lambda sync: feed.head(sync, COMPANY))
            expected = await db.run_sync(lambda sync: full_controls(sync, COMPANY))
            assert Control.model_validate(receipt.manifest["control"]) == expected


def test_control_deltas_cover_append_post_rollback_delete_and_exact_multi_currency():
    absent, draft = Contribution(False), Contribution(True)
    posted = Contribution(True, "INR", Decimal("900719925474.1234"), Decimal("900719925474.1234"))
    counts, totals = advance(
        {"journal": 0, "account": 2},
        {},
        [
            ("journal", absent, draft),
            ("journal", draft, posted),
            ("account", draft, absent),
            ("journal", posted, posted),
        ],
    )
    assert counts == {"journal": 1, "account": 1}
    assert totals == {"INR": {"DEBIT": "900719925474.1234", "CREDIT": "900719925474.1234"}}
    counts, totals = advance(
        counts,
        totals,
        [
            ("journal", posted, absent),
            ("journal", absent, Contribution(True, "USD", Decimal("0.0001"), Decimal("0.0001"))),
        ],
    )
    assert counts["journal"] == 1
    assert totals == {"USD": {"DEBIT": "0.0001", "CREDIT": "0.0001"}}


@pytest.mark.parametrize(
    "value",
    [
        (True, None, "1", "1"),
        (False, "INR", "1", "1"),
        (True, "INR", "0", "0"),
        (True, "INR", "1", "2"),
        (True, "INR", "NaN", "NaN"),
        (True, "INR", "1", "Infinity"),
        (True, "INR", "1.23456", "1.23456"),
        (True, "INR", "1000000000000000", "1000000000000000"),
    ],
)
def test_control_contribution_rejects_invalid_money(value):
    present, currency, debit, credit = value
    with pytest.raises(ValueError):
        Contribution(present, currency, Decimal(debit), Decimal(credit))


@pytest.mark.parametrize(
    "counts,totals,changes",
    [
        ({"journal": 0}, {}, [("journal", Contribution(True), Contribution(False))]),
        ({"journal": 0}, {"INR": {"DEBIT": "1", "CREDIT": "2"}}, []),
        ({"journal": 0}, {"INR": {"DEBIT": "-1", "CREDIT": "-1"}}, []),
        ({"journal": 0}, {"INR": {"DEBIT": "NaN", "CREDIT": "NaN"}}, []),
        ({"journal": 0}, {"INR": {"DEBIT": "1"}}, []),
    ],
)
def test_control_advance_rejects_inconsistent_previous_evidence(counts, totals, changes):
    with pytest.raises(ValueError):
        advance(counts, totals, changes)
