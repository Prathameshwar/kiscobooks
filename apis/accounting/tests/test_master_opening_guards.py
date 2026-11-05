"""Capture refusals use native accounts, field authority and exact source values."""

import pytest
from tests.test_fiscal_api import BASE, finance_headers, fiscal_setup
from tests.test_master_opening_api import opening, party
from tests.test_field_policy import policy


@pytest.mark.parametrize(
    "kind, reason, field",
    [("INVENTORY_CONTROL", None, "amount"), ("CASH", "Bad reason\x7f", "credit_cash_reason")],
)
async def test_control_accounts_and_credit_cash_evidence_are_refused(client, kind, reason, field):
    await fiscal_setup(client)
    accounts = (await client.get(BASE + "/accounts?kind=CASH", headers=finance_headers())).json()[
        "items"
    ]
    account = (
        await client.get(BASE + "/accounts/" + accounts[0]["id"], headers=finance_headers())
    ).json()
    body = {
        "code": "GUARD",
        "name": "Capture guard",
        "kind": kind,
        "group_id": account["group_id"],
        "inventory_affected": False,
    }
    valid = await client.post(BASE + "/accounts", json=body, headers=finance_headers())
    assert valid.status_code == 201, valid.text
    captured = opening(**({"credit_cash_reason": reason} if reason else {}))
    refused = await client.post(
        BASE + "/accounts",
        json=body | {"code": "GUARD-OPEN", "opening": captured},
        headers=finance_headers(),
    )
    assert refused.status_code == 422, refused.text
    assert "opening." + field in refused.json()["error"]["fields"]


async def test_party_opening_rechecks_outstanding_bill_write_authority(client):
    await fiscal_setup(client)
    response = await client.post(
        BASE + "/parties/create-with-details",
        json=party(opening=opening()),
        headers=finance_headers(
            policies=[policy("reference", access="write", entity="accounting.open_item")]
        ),
    )
    assert response.status_code == 403, response.text
