"""Historical report dates remain bounded even before a company's books began."""

from decimal import Decimal

import httpx
from fastapi import FastAPI

from tests.test_fiscal_api import BASE
from tests.test_ledger_api import journal_setup, ledger_headers
from tests.test_openings_sources import party_accounts


async def test_ageing_validates_unsupported_dates_and_accepts_historical_queries(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await journal_setup(client, app)
    party, customer, _ = await party_accounts(client)
    response = await client.get(
        BASE + "/subledger/ageing",
        params={
            "as_of": "0001-01-01",
            "currency": "INR",
            "party_id": party["id"],
            "role": "CUSTOMER",
            "account_id": customer["id"],
        },
        headers=ledger_headers(),
    )
    assert response.status_code == 422, response.text
    response = await client.get(
        BASE + "/subledger/ageing",
        params={
            "as_of": "1000-01-01",
            "currency": "INR",
            "party_id": party["id"],
            "role": "CUSTOMER",
            "account_id": customer["id"],
        },
        headers=ledger_headers(),
    )
    assert response.status_code == 200, response.text
    assert all(
        Decimal(response.json()[key]) == 0
        for key in (
            "not_due",
            "days_1_30",
            "days_31_60",
            "days_61_90",
            "days_91_plus",
            "debt",
            "unapplied_credit",
        )
    )
