"""Credit reservations, current exposure and separation-of-duties integration."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from fastapi import FastAPI
from sqlalchemy import func, select

from accounting.models.credit import CreditOverride, CreditReservation
from tests.test_fiscal_api import BASE, facts
from tests.test_ledger_api import journal_setup, ledger_headers
from tests.test_masters import activate, post
from tests.test_openings_sources import party_accounts, post_source, source


def request(account: dict[str, Any], amount: str = "60") -> dict[str, Any]:
    return {
        "account_id": account["id"],
        "currency": "INR",
        "amount": amount,
        "exchange_rate": "1",
        "posting_date": "2026-04-02",
        "source_system": "billing",
        "source_type": "invoice",
        "source_id": str(uuid.uuid4()),
        "expires_at": (utcnow() + dt.timedelta(hours=1)).isoformat(),
    }


def check_body(body: dict[str, Any]) -> dict[str, Any]:
    return {
        key: body[key]
        for key in ("account_id", "currency", "amount", "exchange_rate", "posting_date")
    }


async def policy(client: httpx.AsyncClient, party: dict[str, Any], **values: Any) -> dict[str, Any]:
    return await post(
        client,
        "/party-credit-policies",
        {
            "party_id": party["id"],
            "role": "CUSTOMER",
            "currency": "INR",
            "limit_mode": "LIMITED",
            "limit_amount": "100",
            "enforcement": "BLOCK",
            "overdue_days": 3650,
            "overdue_tolerance": "0",
            "valid_from": "2026-04-01",
            **values,
        },
    )


async def test_reservation_counts_then_consumes_once_with_source_posting(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app)
    p, customer, _ = await party_accounts(client)
    await policy(client, p)
    body = request(customer)
    h = ledger_headers(features={"credit_limits"}, key="reserve-one")
    reserved = await client.post(BASE + "/credit-reservations", json=body, headers=h)
    assert reserved.status_code == 201, reserved.text
    assert (await client.post(BASE + "/credit-reservations", json=body, headers=h)).json()[
        "id"
    ] == reserved.json()["id"]
    decision = await client.post(
        BASE + "/credit/check",
        json=check_body(body),
        headers=ledger_headers(features={"credit_limits"}),
    )
    assert decision.status_code == 200 and decision.json()["status"] == "BLOCK", decision.text
    assert (
        Decimal(decision.json()["reserved"]) == 60 and Decimal(decision.json()["projected"]) == 120
    )
    assert (
        await client.post(
            BASE + "/credit-reservations",
            json=request(customer),
            headers=ledger_headers(features={"credit_limits"}),
        )
    ).status_code == 409
    doc = await source(
        client,
        customer,
        journal["lines"][1]["account_id"],
        amount="60",
        source_system=body["source_system"],
        source_type=body["source_type"],
        source_id=body["source_id"],
        credit_reservation_id=reserved.json()["id"],
    )
    posted = await post_source(client, doc)
    assert posted.status_code == 200, posted.text
    consumed = (
        await client.get(
            BASE + f"/credit-reservations/{reserved.json()['id']}", headers=ledger_headers()
        )
    ).json()
    assert consumed["status"] == "CONSUMED" and consumed["journal_id"] == doc["journal_id"]
    assert (await post_source(client, doc)).status_code == 200
    decision = await client.post(
        BASE + "/credit/check",
        json=check_body(body),
        headers=ledger_headers(features={"credit_limits"}),
    )
    assert Decimal(decision.json()["reserved"]) == 0 and Decimal(decision.json()["exposure"]) == 60
    with tenant_scope(uuid7()):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(CreditReservation.id))) == 0
            assert await db.scalar(select(func.count(CreditOverride.id))) == 0


async def test_override_requires_other_approver_and_binds_source(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app)
    p, customer, _ = await party_accounts(client)
    await policy(client, p, enforcement="OVERRIDE", limit_amount="0")
    body = request(customer) | {"reason": "Approved temporary commercial exception"}
    requested = await client.post(
        BASE + "/credit-overrides", json=body, headers=ledger_headers(features={"credit_limits"})
    )
    assert requested.status_code == 201, requested.text
    approval = {"expected_version": 1, "approve": True, "reason": "Reviewed exception"}
    path = BASE + f"/credit-overrides/{requested.json()['id']}/approve"
    assert (
        await client.post(path, json=approval, headers=ledger_headers(features={"credit_limits"}))
    ).status_code == 403
    approved = await client.post(
        path, json=approval, headers=ledger_headers(features={"credit_limits"}, user=uuid7())
    )
    assert approved.status_code == 200, approved.text
    doc = await source(
        client,
        customer,
        journal["lines"][1]["account_id"],
        amount="60",
        source_system=body["source_system"],
        source_type=body["source_type"],
        source_id=body["source_id"],
        credit_override_id=requested.json()["id"],
    )
    assert (await post_source(client, doc)).status_code == 200
    used = (
        await client.get(
            BASE + f"/credit-overrides/{requested.json()['id']}", headers=ledger_headers()
        )
    ).json()
    assert used["status"] == "USED"
    stolen = await source(
        client,
        customer,
        journal["lines"][1]["account_id"],
        credit_override_id=requested.json()["id"],
    )
    assert (await post_source(client, stolen)).status_code == 409


async def test_expiry_release_renew_and_supplier_defaults(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await journal_setup(client, app)
    _, customer, supplier = await party_accounts(client)
    body = request(customer)
    created = await client.post(
        BASE + "/credit-reservations", json=body, headers=ledger_headers(features={"credit_limits"})
    )
    assert created.status_code == 201, created.text
    renewal = await client.post(
        BASE + f"/credit-reservations/{created.json()['id']}/renew",
        json={
            "expected_version": 1,
            "expires_at": (utcnow() + dt.timedelta(hours=2)).isoformat(),
            "posting_date": "2026-04-02",
            "exchange_rate": "1",
        },
        headers=ledger_headers(features={"credit_limits"}),
    )
    assert renewal.status_code == 200, renewal.text
    released = await client.post(
        BASE + f"/credit-reservations/{created.json()['id']}/release",
        json={"expected_version": renewal.json()["row_version"]},
        headers=ledger_headers(),
    )
    assert released.status_code == 200
    decision = await client.post(
        BASE + "/credit/check",
        json=check_body(body),
        headers=ledger_headers(features={"credit_limits"}),
    )
    assert Decimal(decision.json()["reserved"]) == 0
    expired = await client.post(
        BASE + "/credit-reservations",
        json=request(customer) | {"expires_at": (utcnow() - dt.timedelta(seconds=1)).isoformat()},
        headers=ledger_headers(),
    )
    assert expired.status_code == 422
    default = facts().model_copy(update={"credit_limit_default": Decimal(0)})
    supplier_check = await client.post(
        BASE + "/credit/check",
        json=check_body(request(supplier)),
        headers=ledger_headers(features={"credit_limits"}, finance=default),
    )
    assert (
        supplier_check.status_code == 200
        and supplier_check.json()["limit"] is None
        and supplier_check.json()["status"] == "ALLOW"
    ), supplier_check.text


async def test_block_warn_and_explicit_holds_with_feature_disabled(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app)
    p, customer, _ = await party_accounts(client)
    await policy(client, p, enforcement="WARN", limit_amount="0")
    decision = await client.post(
        BASE + "/credit/check",
        json=check_body(request(customer)),
        headers=ledger_headers(features={"credit_limits"}),
    )
    assert decision.json()["status"] == "WARN"
    doc = await source(client, customer, journal["lines"][1]["account_id"])
    assert (await post_source(client, doc)).status_code == 200
    term = await post(client, "/payment-terms", {"code": "CASH", "name": "Immediate"})
    await post(
        client,
        "/payment-term-lines",
        {"payment_term_id": term["id"], "sequence": 1, "percentage": "100", "days": 0},
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
            "transaction_hold": True,
            "valid_from": "2026-04-01",
        },
    )
    held = await client.post(
        BASE + "/credit/check", json=check_body(request(customer)), headers=ledger_headers()
    )
    assert held.status_code == 409 and "hold" in held.text
