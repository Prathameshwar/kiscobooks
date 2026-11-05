"""First-time zero confirmation never implies opening entry or correction authority."""

import base64
import datetime as dt
import hashlib
import hmac
import json
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from sqlalchemy import func, select

from accounting.models.ledger import Journal
from accounting.models.stock import StockPosting
from accounting.models.subledger import OpeningBatch
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_fiscal_api import BASE, change, finance_headers, fiscal_setup

NARROW = {"accounting.finance.read", "opening_balance.initialize_zero"}
REVIEW = BASE + "/financial-setup/zero-opening-review"
CONFIRM = BASE + "/financial-setup/confirm-zero-opening"


async def configured(client):
    periods = await fiscal_setup(client)
    first = min(periods, key=lambda row: row["start_date"])
    assert (await change(client, first, "OPEN")).status_code == 200
    return (await client.get(BASE + "/financial-setup", headers=finance_headers())).json()


async def test_first_zero_confirmation_has_exact_replay_audits_and_no_financial_effects(
    app, client
):
    books = await configured(client)
    reviewed = await client.get(REVIEW, headers=finance_headers(permissions=NARROW))
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["eligible"] is True
    body = {
        "expected_setup_version": books["row_version"],
        "reason": "Confirmed no opening balances",
    }
    auth = finance_headers(permissions=NARROW, key=str(uuid.uuid4()))
    result = await client.post(CONFIRM, json=body, headers=auth)
    assert result.status_code == 201, result.text
    data = result.json()
    assert data["status"] == "FINALIZED" and data["journal_id"] is None
    assert data["payload"]["lines"] == [] and data["payload"]["bills"] == []
    assert data["posting_date"] == books["books_begin_date"]
    replay = await client.post(CONFIRM, json=body, headers=auth)
    assert replay.status_code == 201 and replay.json() == data
    duplicate = await client.post(CONFIRM, json=body, headers=finance_headers(permissions=NARROW))
    assert duplicate.status_code == 409
    assert (await client.get(REVIEW, headers=finance_headers(permissions=NARROW))).json()[
        "eligible"
    ] is False
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(OpeningBatch.id))) == 1
            assert await db.scalar(select(func.count(Journal.id))) == 0
            assert await db.scalar(select(func.count(StockPosting.id))) == 0
            events = list(
                await db.scalars(
                    select(Outbox.event_type).where(
                        Outbox.event_type.in_(
                            ("accounting.opening_batch.create", "accounting.opening_batch.finalize")
                        )
                    )
                )
            )
            assert sorted(events) == [
                "accounting.opening_batch.create",
                "accounting.opening_batch.finalize",
            ]
    for suffix in ("void", "reopen-zero", "finalize-zero"):
        denied = await client.post(
            BASE + "/opening-batches/" + data["id"] + "/" + suffix,
            json={"expected_version": data["row_version"], "reason": "Attempt correction"}
            if suffix == "reopen-zero"
            else {"expected_version": data["row_version"]},
            headers=finance_headers(permissions=NARROW),
        )
        assert denied.status_code == 403, denied.text
    assert (
        await client.post(
            BASE + "/opening-batches",
            json={
                "posting_date": data["posting_date"],
                "description": "Attempt balance import",
                "lines": [],
            },
            headers=finance_headers(permissions=NARROW),
        )
    ).status_code == 403


async def test_zero_confirmation_requires_scope_current_setup_open_period_and_field_authority(
    app, client
):
    periods = await fiscal_setup(client)
    books = (await client.get(BASE + "/financial-setup", headers=finance_headers())).json()
    body = {"expected_setup_version": books["row_version"], "reason": "Confirm first zero opening"}
    assert (await client.get(REVIEW)).status_code == 401
    assert (
        await client.post(
            CONFIRM, json=body, headers=finance_headers(permissions={"accounting.finance.read"})
        )
    ).status_code == 403
    assert (
        await client.post(
            CONFIRM, json=body, headers=finance_headers(permissions=NARROW, company=uuid.uuid4())
        )
    ).status_code == 401  # The signed company context does not match the route.
    scoped = finance_headers(permissions=NARROW)
    decoded = json.loads(base64.urlsafe_b64decode(scoped["X-Actor-Context"] + "=="))
    decoded["grants"][0]["scope_id"] = str(uuid.uuid4())
    raw = json.dumps(decoded, separators=(",", ":")).encode()
    scoped["X-Actor-Context"] = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    scoped["X-Actor-Signature"] = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert (await client.post(CONFIRM, json=body, headers=scoped)).status_code == 403
    pending = await client.get(REVIEW, headers=finance_headers(permissions=NARROW))
    assert pending.json()["blocker"] == "BOOKS_PERIOD_NOT_OPEN"
    assert (
        await client.post(CONFIRM, json=body, headers=finance_headers(permissions=NARROW))
    ).status_code == 409
    assert (
        await change(client, min(periods, key=lambda row: row["start_date"]), "OPEN")
    ).status_code == 200
    stale = await client.post(
        CONFIRM,
        json=body | {"expected_setup_version": 999},
        headers=finance_headers(permissions=NARROW),
    )
    assert stale.status_code == 409
    for entity, field, access in (
        ("financial_setup", "books_begin_date", "read"),
        ("opening_batch", "payload", "write"),
    ):
        denied = await client.post(
            CONFIRM,
            json=body,
            headers=finance_headers(
                permissions=NARROW,
                policies=[
                    {
                        "entity_type": "accounting." + entity,
                        "field_key": field,
                        "access": access,
                        "effect": "deny",
                        "scope_type": "company",
                        "scope_id": str(COMPANY),
                    }
                ],
            ),
        )
        assert denied.status_code == 403, denied.text
    for extra in (
        {"lines": []},
        {"amount": "1"},
        {"posting_date": "2026-04-01"},
        {"replacement_of_id": str(uuid.uuid4())},
    ):
        assert (
            await client.post(
                CONFIRM, json=body | extra, headers=finance_headers(permissions=NARROW)
            )
        ).status_code == 422
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(OpeningBatch.id))) == 0


@pytest.mark.parametrize("existing", ["voided_opening", "prepared_stock"])
async def test_zero_confirmation_cannot_replace_history_or_race_prepared_work(
    app, client, existing
):
    from accounting.models.voucher_money import VoucherMoneyIntent
    from tests.test_stock_ledger import values

    books = await configured(client)
    opening_day = dt.date.fromisoformat(books["books_begin_date"])
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            if existing == "voided_opening":
                db.add(
                    OpeningBatch(
                        **values(),
                        status="VOID",
                        posting_date=opening_day,
                        description="Retained voided opening",
                        payload={},
                        journal_id=None,
                        replacement_of_id=None,
                        finalized_at=None,
                    )
                )
            else:
                db.add(
                    VoucherMoneyIntent(
                        **values(),
                        execution_id=uuid.uuid4(),
                        voucher_id=uuid.uuid4(),
                        request_hash="a" * 64,
                        kind="RECEIPT_NOTE",
                        posting_date=opening_day,
                        status="PREPARED",
                        command={},
                        journal_id=None,
                    )
                )
    reviewed = await client.get(REVIEW, headers=finance_headers(permissions=NARROW))
    assert reviewed.json()["blocker"] == "EXISTING_OPENING_OR_ACTIVITY"
    refused = await client.post(
        CONFIRM,
        json={
            "expected_setup_version": books["row_version"],
            "reason": "Attempt to reset opening history",
        },
        headers=finance_headers(permissions=NARROW),
    )
    assert refused.status_code == 409
