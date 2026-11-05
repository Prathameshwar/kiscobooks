"""Verify the current conservative balance policy in disposable fixtures only."""

from tests.test_field_policy import policy
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import (
    create_journal,
    journal_setup,
    ledger_headers,
    post_journal,
)


async def test_balance_requires_both_monetary_field_permissions(app, client):
    body, _, _ = await journal_setup(client, app)
    journal = await create_journal(client, body)
    assert (await post_journal(client, journal)).status_code == 200
    query = {
        "as_of": body["posting_date"],
        "account_id": body["lines"][0]["account_id"],
        "currency": "INR",
    }
    for basis, unused in (("BASE", "amount"), ("ORIGINAL", "base_amount")):
        response = await client.get(
            BASE + "/ledger/balance",
            params=query | {"basis": basis},
            headers=ledger_headers(),
        )
        assert response.status_code == 200 and response.json()["debit"] == "100.2500"
        policies = [policy(unused, entity="accounting.journal_line")]
        denied = await client.get(
            BASE + "/ledger/balance",
            params=query | {"basis": basis},
            headers=ledger_headers(policies=policies),
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["message"] == "balance inputs are not readable"
