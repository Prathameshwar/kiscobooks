"""Financial review regressions: corrections, date boundaries and credit identity."""

import httpx
from billing_platform.ids import uuid7
from fastapi import FastAPI

from tests.test_charges_api import assessment, setup_charge
from tests.test_credit_api import check_body, request
from tests.test_fiscal_api import BASE
from tests.test_ledger_api import create_journal, journal_setup, ledger_headers, post_journal
from tests.test_openings_sources import party_accounts, post_source, source


async def test_voided_reversal_draft_does_not_prevent_a_replacement(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _ = await journal_setup(client, app)
    original = await create_journal(client, body)
    assert (await post_journal(client, original)).status_code == 200
    payload = {"posting_date": "2026-04-03", "reason": "Correction"}
    first = await client.post(
        BASE + f"/journals/{original['id']}/reversal", json=payload, headers=ledger_headers()
    )
    assert first.status_code == 201
    void = await client.post(
        BASE + f"/journals/{first.json()['id']}/void",
        json={"expected_version": 1, "reason": "Use another correction date"},
        headers=ledger_headers(),
    )
    assert void.status_code == 200
    replacement = await client.post(
        BASE + f"/journals/{original['id']}/reversal",
        json=payload | {"posting_date": "2026-04-04"},
        headers=ledger_headers(),
    )
    assert replacement.status_code == 201, replacement.text
    assert (await post_journal(client, replacement.json())).status_code == 200


async def test_finalized_zero_opening_can_be_corrected_before_trading(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await journal_setup(client, app)
    row = (await client.get(BASE + "/opening-batches", headers=ledger_headers())).json()["items"][0]
    reopened = await client.post(
        BASE + f"/opening-batches/{row['id']}/reopen-zero",
        json={"expected_version": row["row_version"], "reason": "Import omitted opening balances"},
        headers=ledger_headers(),
    )
    assert reopened.status_code == 200 and reopened.json()["status"] == "REVERSED", reopened.text
    replacement = await client.post(
        BASE + "/opening-batches",
        json={
            "posting_date": "2026-04-01",
            "description": "Replacement opening",
            "replacement_of_id": row["id"],
        },
        headers=ledger_headers(),
    )
    assert replacement.status_code == 201, replacement.text


async def test_policy_close_accepts_last_included_charge_day(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, _, _, _ = await setup_charge(client, app)
    row = await assessment(client, body)
    waived = await client.post(
        BASE + f"/charge-assessments/{row['id']}/waive",
        json={"expected_version": 1, "reason": "Waive reviewed charge"},
        headers=ledger_headers(user=uuid7()),
    )
    assert waived.status_code == 200
    closed = await client.post(
        BASE + f"/charge-policies/{body['policy_id']}/close",
        json={"expected_version": 1, "valid_to": "2026-04-12"},
        headers=ledger_headers(),
    )
    assert closed.status_code == 200, closed.text


async def test_fixed_fee_is_once_per_bill_across_policy_versions(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, account, journal, _ = await setup_charge(
        client, app, method="FIXED", rate="10", valid_to="2026-04-12"
    )
    row = await assessment(client, body)
    waived = await client.post(
        BASE + f"/charge-assessments/{row['id']}/waive",
        json={"expected_version": 1, "reason": "Fixed fee waived"},
        headers=ledger_headers(user=uuid7()),
    )
    assert waived.status_code == 200
    policy = await client.post(
        BASE + "/charge-policies",
        json={
            "account_id": account["id"],
            "offset_account_id": journal["lines"][1]["account_id"],
            "currency": "INR",
            "valid_from": "2026-04-13",
            "accrual_start_date": "2026-04-13",
            "method": "FIXED",
            "rate": "20",
            "tax_treatment": "NON_TAXABLE",
            "tax_reason": "Fixture exemption",
        },
        headers=ledger_headers(),
    )
    assert policy.status_code == 201
    preview = await client.post(
        BASE + "/charge-assessments/preview",
        json=body
        | {
            "policy_id": policy.json()["id"],
            "coverage_end_date": "2026-04-20",
            "posting_date": "2026-04-20",
        },
        headers=ledger_headers(),
    )
    assert preview.status_code == 200 and preview.json()["amount"] in {"0", "0.0000"}, preview.text


async def test_credit_reservation_rejects_account_currency_mismatch(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await journal_setup(client, app)
    _, customer, _ = await party_accounts(client)
    result = await client.post(
        BASE + "/credit/check",
        json=check_body(request(customer)) | {"currency": "USD", "exchange_rate": "83"},
        headers=ledger_headers(features={"multi_currency", "credit_limits"}),
    )
    assert result.status_code == 422, result.text


async def test_credit_reservation_cannot_follow_an_already_posted_source(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client)
    body = request(customer)
    document = await source(
        client,
        customer,
        journal["lines"][1]["account_id"],
        amount=body["amount"],
        source_system=body["source_system"],
        source_type=body["source_type"],
        source_id=body["source_id"],
    )
    assert (await post_source(client, document)).status_code == 200
    result = await client.post(
        BASE + "/credit-reservations", json=body, headers=ledger_headers(features={"credit_limits"})
    )
    assert result.status_code == 409, result.text
