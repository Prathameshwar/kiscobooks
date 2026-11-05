import datetime as dt
import os

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from fastapi import FastAPI
from sqlalchemy import select

from tests.conftest import COMPANY, TENANT, headers
from tests.test_masters import new_party, prepare

BASE = f"/v1/companies/{COMPANY}"


async def test_safe_before_after_and_correlation(client: httpx.AsyncClient, app: FastAPI) -> None:
    await prepare(client)
    body = {
        "code": "P",
        "name": "Private name",
        "legal_name": "Private legal",
        "country_code": "IN",
    }
    created = await new_party(
        client,
        code=body["code"],
        name=body["name"],
        legal_name=body["legal_name"],
        country_code=body["country_code"],
    )
    trace = "a" * 32
    response = await client.patch(
        BASE + "/parties/" + created["id"],
        json=body
        | {
            "country_code": "US",
            "legal_name": "Another private name",
            "expected_version": created["row_version"],
        },
        headers=headers() | {"X-Trace-Id": trace},
    )
    assert response.status_code == 200, response.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            event = await db.scalar(
                select(Outbox).where(Outbox.event_type == "accounting.party.update")
            )
            assert event is not None
            assert event.payload["changes"]["country_code"] == {"from": "IN", "to": "US"}
            assert event.payload["changes"]["legal_name"] == {"changed": True}
            assert "private" not in str(event.payload).lower()
            assert event.trace_id == trace


async def test_export_access_event_is_scoped_and_does_not_change_history(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await client.post(BASE + "/accounting-setup/initialize", json={}, headers=headers())
    result = await client.get(BASE + "/exports/account-heads", headers=headers())
    assert result.status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            events = list(
                await db.scalars(
                    select(Outbox).where(Outbox.event_type == "accounting.account_head.export")
                )
            )
            assert len(events) == 1
            assert events[0].payload["category"] == "access"
            assert events[0].payload["company_id"] == str(COMPANY)
            assert events[0].payload["context"] == {"count": 5}


async def test_sensitive_read_emits_once_and_denied_read_leaves_no_success_event(
    client: httpx.AsyncClient,
    app: FastAPI,
) -> None:
    await prepare(client)
    party = await new_party(client, code="BANKPROOF", name="Private", legal_name="Private")
    bank = await client.post(
        BASE + "/party-bank-accounts",
        json={
            "party_id": party["id"],
            "label": "Primary",
            "beneficiary_name": "Private",
            "bank_name": "Private Bank",
            "country_code": "IN",
            "currency": "INR",
            "account_number": "123456789012",
        },
        headers=headers(),
    )
    assert bank.status_code == 201, bank.text
    path = BASE + "/party-bank-accounts/" + bank.json()["id"]
    assert (await client.get(path, headers=headers(permissions=frozenset()))).status_code == 403
    assert (await client.get(path, headers=headers())).status_code == 200
    assert (
        await client.get(BASE + "/parties/" + party["id"], headers=headers())
    ).status_code == 200
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(await db.scalars(select(Outbox).where(Outbox.event_type.like("%.read"))))
            assert len(rows) == 1
            assert rows[0].payload["entity_id"] == bank.json()["id"]
            assert rows[0].payload["category"] == "access"
            assert "123456789012" not in str(rows[0].payload)


@pytest.mark.parametrize(
    "old,new",
    [
        ("50000.1250", "50000.5625"),
        pytest.param(
            "900719925474099.1234",
            "900719925474099.5678",
            marks=pytest.mark.skipif(
                not os.environ.get("ACCOUNTING_TEST_DATABASE_URL"),
                reason="SQLite numeric affinity rounds large decimals; verify on native MySQL",
            ),
        ),
    ],
)
async def test_monetary_evidence_preserves_exact_old_new_amounts_and_currency(
    client: httpx.AsyncClient, app: FastAPI, old: str, new: str
) -> None:
    from tests.test_masters import party, post

    await prepare(client)
    customer = await party(client)
    policy = await post(
        client,
        "/party-credit-policies",
        {
            "party_id": customer["id"],
            "currency": "INR",
            "limit_amount": old,
            "valid_from": (dt.date.today() + dt.timedelta(days=1)).isoformat(),
        },
    )
    result = await client.patch(
        BASE + "/party-credit-policies/" + policy["id"],
        json={"expected_version": policy["row_version"], "limit_amount": new},
        headers=headers(),
    )
    assert result.status_code == 200, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            event = await db.scalar(
                select(Outbox).where(Outbox.event_type == "accounting.party_credit_policy.update")
            )
            assert event is not None
            assert event.payload["changes"]["limit_amount"] == {"from": old, "to": new}
            assert event.payload["changes"]["currency"] == {"from": "INR", "to": "INR"}
