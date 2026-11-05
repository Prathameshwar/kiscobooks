"""Financial acceptance boundaries: invalid commands leave valid business facts intact."""

import datetime as dt
from decimal import Decimal
from typing import Any

import httpx
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from fastapi import FastAPI

from tests.test_allocations import items
from tests.test_charges_api import approve, assessment, setup_charge
from tests.test_credit_api import check_body, policy, request
from tests.test_finance_review2 import policy as denial
from tests.test_fiscal_api import BASE, facts
from tests.test_ledger_api import create_journal, journal_setup, ledger_headers, post_journal
from tests.test_masters import activate, post
from tests.test_openings_sources import party_accounts, post_source, source


async def command(
    client: httpx.AsyncClient, path: str, body: dict[str, Any], **headers: Any
) -> httpx.Response:
    return await client.post(BASE + path, json=body, headers=ledger_headers(**headers))


async def test_opening_validation_void_and_prepared_cancellation(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, authority = await journal_setup(client, app, zero_opening=False)
    _, account, _ = await party_accounts(client)
    journal["lines"][0]["account_id"] = account["id"]
    bill = {
        "line_sequence": 1,
        "reference": "OPEN-1",
        "amount": "100.25",
        "document_date": "2026-03-01",
        "due_date": "2026-03-31",
    }
    body = {
        "posting_date": "2026-04-01",
        "description": "Opening import",
        "lines": journal["lines"],
        "bills": [bill],
    }
    invalid = [
        body | {"posting_date": "2026-04-02"},
        body | {"lines": []},
        body | {"bills": [bill | {"line_sequence": 2}]},
        body | {"bills": [bill | {"document_date": "2026-04-02"}]},
        body | {"bills": [bill | {"due_date": "2026-02-28"}]},
        body | {"bills": [bill, bill]},
        body | {"bills": [bill | {"amount": "100"}]},
    ]
    for payload in invalid:
        result = await command(client, "/opening-batches/preview", payload)
        assert result.status_code == 422, result.text
    result = await command(client, "/opening-batches", body | {"replacement_of_id": str(uuid7())})
    assert result.status_code == 409
    opening = await command(client, "/opening-batches", body)
    assert opening.status_code == 201
    row = opening.json()
    assert (
        await command(
            client,
            f"/opening-batches/{row['id']}/finalize-zero",
            {"expected_version": row["row_version"]},
        )
    ).status_code == 409
    assert (
        await command(client, f"/opening-batches/{row['id']}/void", {"expected_version": 99})
    ).status_code == 409
    void = await command(
        client, f"/opening-batches/{row['id']}/void", {"expected_version": row["row_version"]}
    )
    assert void.status_code == 200 and void.json()["status"] == "VOID"
    second = await command(client, "/opening-batches", body)
    row = second.json()
    draft = (
        await client.get(BASE + "/journals/" + row["journal_id"], headers=ledger_headers())
    ).json()
    authority.fail = True
    assert (await post_journal(client, draft)).status_code == 503
    assert (
        await command(
            client, f"/opening-batches/{row['id']}/void", {"expected_version": row["row_version"]}
        )
    ).status_code == 409
    current = (
        await client.get(BASE + "/journals/" + row["journal_id"], headers=ledger_headers())
    ).json()
    assert (
        await command(
            client,
            f"/journals/{current['id']}/void",
            {"expected_version": current["row_version"], "reason": "Cancel import"},
        )
    ).status_code == 200
    assert (
        await command(
            client, f"/opening-batches/{row['id']}/void", {"expected_version": row["row_version"]}
        )
    ).status_code == 200


async def test_dated_installments_and_source_validation(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app)
    p, account, supplier = await party_accounts(client)
    term = await post(client, "/payment-terms", {"code": "SPLIT", "name": "Two installments"})
    for sequence, percentage, basis, days in (
        (1, "40", "INVOICE_DATE", 10),
        (2, "60", "MONTH_END", 15),
    ):
        await post(
            client,
            "/payment-term-lines",
            {
                "payment_term_id": term["id"],
                "sequence": sequence,
                "percentage": percentage,
                "basis": basis,
                "days": days,
            },
        )
    term = await activate(client, "/payment-terms", term)
    await post(
        client,
        "/party-accounting-policies",
        {
            "party_id": p["id"],
            "role": "CUSTOMER",
            "payment_term_id": term["id"],
            "settlement_currency": "INR",
            "valid_from": "2026-04-01",
        },
    )
    doc = await source(client, account, journal["lines"][1]["account_id"])
    assert doc["payload"]["terms"]["term_id"] == term["id"]
    assert [i["due_date"] for i in doc["payload"]["installments"]] == ["2026-04-12", "2026-05-15"]
    assert (await post_source(client, doc)).status_code == 200
    assert sorted(Decimal(i["amount"]) for i in await items(client)) == [Decimal(40), Decimal(60)]
    body = doc["payload"]["request"]
    for delta in (
        {"kind": "PAYMENT"},
        {"counterpart_account_id": account["id"]},
        {"kind": "RECEIPT"},
        {"due_date": "2026-04-01"},
    ):
        invalid = await command(
            client, "/source-documents", body | delta | {"source_id": str(uuid7())}
        )
        assert invalid.status_code == 422, invalid.text
    for entity, field in (
        ("party", "status"),
        ("party_accounting_policy", "payment_term_id"),
        ("payment_term", "status"),
        ("payment_term_line", "percentage"),
    ):
        denied = await command(
            client,
            "/source-documents",
            body | {"source_id": str(uuid7())},
            policies=[denial(entity, field)],
        )
        assert denied.status_code == 403, denied.text
    cash = body | {
        "kind": "RECEIPT",
        "counterpart_account_id": journal["lines"][0]["account_id"],
        "source_id": str(uuid7()),
    }
    capped = await command(
        client,
        "/source-documents",
        cash,
        finance=facts().model_copy(update={"cash_receipt_limit": Decimal(99)}),
    )
    assert capped.status_code == 409
    cash_result = await command(client, "/source-documents", cash)
    assert cash_result.status_code == 201
    receipt_journal = (
        await client.get(
            BASE + "/journals/" + cash_result.json()["journal_id"], headers=ledger_headers()
        )
    ).json()
    assert (
        await post_journal(
            client,
            receipt_journal,
            finance=facts().model_copy(update={"cash_receipt_limit": Decimal(99)}),
        )
    ).status_code == 409

    # Post the first cash receipt (amount 100) with sufficient limit
    assert (
        await post_journal(
            client,
            receipt_journal,
            finance=facts().model_copy(update={"cash_receipt_limit": Decimal(200)}),
        )
    ).status_code == 200

    # Second cash receipt of 100 on the same date for the same party with limit 150
    # Individually 100 <= 150, but aggregate is 100 + 100 = 200 > 150 (§269ST violation)
    cash_second = body | {
        "kind": "RECEIPT",
        "counterpart_account_id": journal["lines"][0]["account_id"],
        "source_id": str(uuid7()),
    }
    aggregate_blocked = await command(
        client,
        "/source-documents",
        cash_second,
        finance=facts().model_copy(update={"cash_receipt_limit": Decimal(150)}),
    )
    assert aggregate_blocked.status_code == 409

    stale = await command(client, "/source-documents", body | {"due_date": "2026-05-20"})
    assert stale.status_code == 409


async def test_charge_policy_and_disposition_boundaries(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    body, account, journal, _ = await setup_charge(client, app)
    policy_body = {
        "account_id": account["id"],
        "offset_account_id": journal["lines"][1]["account_id"],
        "currency": "INR",
        "valid_from": "2026-04-01",
        "accrual_start_date": "2026-04-01",
        "method": "INTEREST",
        "rate": "36.5",
        "tax_treatment": "NON_TAXABLE",
        "tax_reason": "Fixture exemption",
    }
    for delta in (
        {"offset_account_id": journal["lines"][0]["account_id"]},
        {"currency": "USD"},
        {"valid_to": "2026-03-31"},
        {"minimum": "20", "cap": "10"},
        {"method": "FIXED", "compound": "DAILY"},
    ):
        invalid = await command(client, "/charge-policies", policy_body | delta)
        assert invalid.status_code == 422, invalid.text
    assert (await command(client, "/charge-policies", policy_body)).status_code == 409
    for delta in (
        {"coverage_end_date": "9999-12-31"},
        {"posting_date": "2026-04-10"},
        {"due_date": "2026-04-01"},
    ):
        invalid = await command(client, "/charge-assessments/preview", body | delta)
        assert invalid.status_code == 422, invalid.text
    row = await assessment(client, body)
    path = f"/charge-policies/{body['policy_id']}/close"
    assert (
        await command(client, path, {"expected_version": 99, "valid_to": "2026-04-12"})
    ).status_code == 409
    assert (
        await command(client, path, {"expected_version": 1, "valid_to": "2026-03-31"})
    ).status_code == 422
    assert (
        await command(client, path, {"expected_version": 1, "valid_to": "2026-04-11"})
    ).status_code == 409
    approved = await approve(client, row)
    assert approved.status_code == 200
    assert (await approve(client, row)).status_code == 409
    path = f"/charge-assessments/{row['id']}/waive"
    assert (
        await command(client, path, {"expected_version": 2, "reason": "Self waiver"})
    ).status_code == 403
    waived = await command(
        client, path, {"expected_version": 2, "reason": "Reviewed concession"}, user=uuid7()
    )
    assert waived.status_code == 200 and waived.json()["status"] == "WAIVED"
    draft = (
        await client.get(
            BASE + "/journals/" + approved.json()["journal_id"], headers=ledger_headers()
        )
    ).json()
    assert draft["status"] == "VOID"
    assert (
        await command(
            client, path, {"expected_version": 3, "reason": "Repeat waiver"}, user=uuid7()
        )
    ).status_code == 409
    next_body = body | {"coverage_end_date": "2026-04-20", "posting_date": "2026-04-20"}
    next_row = await assessment(client, next_body)
    next_approved = await approve(client, next_row)
    app.state.posting_client.fail = True
    assert (await post_source(client, next_approved.json())).status_code == 503
    rejected = await command(
        client,
        f"/charge-assessments/{next_row['id']}/reject",
        {"expected_version": 2, "reason": "Reserved elsewhere"},
    )
    assert rejected.status_code == 409


async def test_credit_reservation_identity_and_approval_boundaries(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app)
    p, account, _ = await party_accounts(client)
    body = request(account)
    created = await command(client, "/credit-reservations", body)
    assert created.status_code == 201
    assert (await command(client, "/credit-reservations", body)).json()["id"] == created.json()[
        "id"
    ]
    assert (
        await command(client, "/credit-reservations", body | {"amount": "61"})
    ).status_code == 409
    path = f"/credit-reservations/{created.json()['id']}"
    renewal = {
        "expected_version": 99,
        "expires_at": (utcnow() + dt.timedelta(hours=2)).isoformat(),
        "posting_date": "2026-04-02",
        "exchange_rate": "1",
    }
    assert (await command(client, path + "/renew", renewal)).status_code == 409
    assert (await command(client, path + "/release", {"expected_version": 99})).status_code == 409
    assert (await command(client, path + "/release", {"expected_version": 1})).status_code == 200
    assert (
        await command(client, path + "/renew", renewal | {"expected_version": 2})
    ).status_code == 409
    invalid = await command(client, "/credit/check", check_body(body) | {"exchange_rate": "2"})
    assert invalid.status_code == 422
    assert (
        await command(client, "/credit-overrides", body | {"reason": "Not necessary"})
    ).status_code == 409
    assert (
        await command(
            client,
            "/credit-overrides",
            body | {"reason": "Invalid reference", "override_id": str(uuid7())},
        )
    ).status_code == 422
    await policy(client, p, enforcement="OVERRIDE", limit_amount="0")
    row = await command(
        client,
        "/credit-overrides",
        body | {"reason": "Review exception"},
        features={"credit_limits"},
    )
    assert row.status_code == 201
    approve_path = f"/credit-overrides/{row.json()['id']}/approve"
    approval = {"expected_version": 1, "approve": False, "reason": "Declined exception"}
    rejected = await command(client, approve_path, approval, user=uuid7())
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    assert (await command(client, approve_path, approval, user=uuid7())).status_code == 409
    for field in ("limit_amount", "enforcement"):
        denied = await command(
            client,
            "/credit/check",
            check_body(body),
            policies=[denial("party_credit_policy", field)],
        )
        assert denied.status_code == 403


async def test_manual_draft_edit_preserves_exact_values_and_versions(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app)
    draft = await create_journal(client, journal)
    body = journal | {
        "expected_version": 1,
        "description": "Corrected draft",
        "lines": [line | {"amount": "200.1111"} for line in journal["lines"]],
    }
    denied = await client.put(
        BASE + "/journals/" + draft["id"],
        json=body,
        headers=ledger_headers(policies=[denial("journal", "lines", access="write")]),
    )
    assert denied.status_code == 403
    edited = await client.put(
        BASE + "/journals/" + draft["id"], json=body, headers=ledger_headers()
    )
    assert edited.status_code == 200 and Decimal(edited.json()["total_debit"]) == Decimal(
        "200.1111"
    ), edited.text
    assert (
        await client.put(BASE + "/journals/" + draft["id"], json=body, headers=ledger_headers())
    ).status_code == 409
    assert (await post_journal(client, edited.json())).status_code == 200
