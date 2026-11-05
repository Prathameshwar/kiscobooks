"""Reconciliation and period close enforce local and delivered posting facts."""

from decimal import Decimal
from typing import cast

import httpx
from fastapi import FastAPI
from identity_posting import PostingClient

from accounting.tasks.posting_delivery import deliver
from tests.test_charges_api import assessment, setup_charge
from tests.test_fiscal_api import BASE, change
from tests.test_ledger_api import journal_setup, ledger_headers
from tests.test_openings_sources import party_accounts, post_source, source


async def test_reconciliation_and_pending_confirmation_close_gate(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, period, authority = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client)
    invoice = await source(client, customer, journal["lines"][1]["account_id"])
    assert (await post_source(client, invoice)).status_code == 200
    for basis in ("BASE", "ORIGINAL"):
        response = await client.get(
            BASE + "/subledger/reconciliation",
            params={
                "account_id": customer["id"],
                "as_of": "2026-04-30",
                "currency": "INR",
                "basis": basis,
            },
            headers=ledger_headers(),
        )
        assert response.status_code == 200, response.text
        assert (
            Decimal(response.json()["ledger_balance"]) == 100
            and Decimal(response.json()["difference"]) == 0
        )
    blocked = await change(client, period, "SOFT_CLOSED")
    assert blocked.status_code == 409 and "confirmation" in blocked.text, blocked.text
    assert (await deliver(app.state.session_factory, cast(PostingClient, authority))).confirmed == 1
    closed = await change(client, period, "SOFT_CLOSED")
    assert closed.status_code == 200, closed.text


async def test_unapproved_charge_blocks_closing(client: httpx.AsyncClient, app: FastAPI) -> None:
    request, _, _, _ = await setup_charge(client, app)
    await assessment(client, request)
    periods = (await client.get(BASE + "/fiscal-periods", headers=ledger_headers())).json()["items"]
    blocked = await change(client, periods[0], "SOFT_CLOSED")
    assert blocked.status_code == 409 and "pending" in blocked.text, blocked.text
