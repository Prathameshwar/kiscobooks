"""Oversized FX results are validation failures, never unhandled money errors."""

import uuid

import httpx
import pytest
from fastapi import FastAPI

from tests.test_charges_api import approve, assessment, setup_charge
from tests.test_credit_api import check_body, request
from tests.test_finance_boundaries import command
from tests.test_ledger_api import journal_setup
from tests.test_openings_sources import party_accounts


@pytest.mark.parametrize("workflow", ["credit", "source"])
async def test_foreign_conversion_overflow_is_a_validation_response(
    client: httpx.AsyncClient, app: FastAPI, workflow: str
) -> None:
    journal, _, _ = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client, currency="USD")
    money = {"currency": "USD", "exchange_rate": "2", "amount": "999999999999999.9999"}
    if workflow == "credit":
        path = "/credit/check"
        body = check_body(request(customer)) | money
    else:
        path = "/source-documents"
        body = {
            "kind": "INVOICE",
            "account_id": customer["id"],
            "counterpart_account_id": journal["lines"][1]["account_id"],
            "document_date": "2026-04-02",
            "posting_date": "2026-04-02",
            "due_date": "2026-04-30",
            "reference": "OVERSIZED",
            "source_system": "billing",
            "source_type": "invoice",
            "source_id": str(uuid.uuid4()),
            "description": "Converted amount exceeds supported storage",
            **money,
        }
    response = await command(client, path, body, features={"multi_currency"})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


async def test_foreign_charge_conversion_overflow_is_a_validation_response(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _, _ = await setup_charge(
        client, app, currency="USD", exchange_rate="99999999999", rate="365000000000"
    )
    row = await assessment(client, body)
    response = await approve(client, row, features={"multi_currency"})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"
