"""Recovery and foreign-credit operational boundaries using persisted financial facts."""

import asyncio
import datetime as dt
import json
import runpy
import secrets
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.delivery import PublishResult
from billing_platform.ids import uuid7
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from accounting.config import Settings
from accounting.models.subledger import OpenItem
from accounting.tasks import posting_delivery
from tests.conftest import TENANT
from tests.test_credit_api import check_body, policy, request
from tests.test_finance_boundaries import command
from tests.test_fiscal_api import BASE, change
from tests.test_ledger_api import journal_setup, ledger_headers
from tests.test_openings_sources import party_accounts, post_source, source


def worker_settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=SecretStr(secrets.token_hex(32)),
        identity_posting_url="https://identity.invalid",
        identity_posting_key_id="accounting.test",
        identity_posting_secret=SecretStr(secrets.token_hex(32)),
        identity_posting_response_keys={"identity.test": SecretStr(secrets.token_hex(32))},
    )


@pytest.mark.asyncio
async def test_identity_posting_accepts_only_local_loopback_http() -> None:
    local = worker_settings().model_copy(update={"identity_posting_url": "http://127.0.0.1:8001"})
    connection = posting_delivery.connection(local)
    assert connection is not None
    await connection[0].aclose()
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            actor_signing_secret=SecretStr(secrets.token_hex(32)),
            identity_posting_url="http://example.com",
            identity_posting_key_id="accounting.test",
            identity_posting_secret=SecretStr(secrets.token_hex(32)),
            identity_posting_response_keys={"current": SecretStr(secrets.token_hex(32))},
        )


async def test_worker_connection_cleanup_and_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = worker_settings()
    configured = posting_delivery.connection(settings)
    assert configured is not None
    http, _ = configured
    assert str(http.base_url) == "https://identity.invalid"
    await http.aclose()
    missing = settings.model_copy(update={"identity_posting_url": None})
    with pytest.raises(ValueError, match="credentials"):
        await posting_delivery.run(missing, once=True)
    http = AsyncMock()
    engine = AsyncMock()
    monkeypatch.setattr(posting_delivery, "connection", lambda _: (http, object()))
    monkeypatch.setattr(posting_delivery, "create_engine", lambda _: engine)
    monkeypatch.setattr(posting_delivery, "create_session_factory", lambda *a, **k: object())
    send = AsyncMock(return_value=PublishResult(1, 0))
    monkeypatch.setattr(posting_delivery, "deliver", send)
    await posting_delivery.run(settings, once=True)
    http.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    pause = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    monkeypatch.setattr(asyncio, "sleep", pause)
    send.side_effect = [PublishResult(1, 0), PublishResult(0, 1)]
    with pytest.raises(asyncio.CancelledError):
        await posting_delivery.run(settings, once=False)
    assert [c.args[0] for c in pause.await_args_list] == [1, 5]
    assert http.aclose.await_count == engine.dispose.await_count == 2


def test_delivery_and_publisher_entrypoints(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = worker_settings()
    for key, value in settings.model_dump().items():
        if isinstance(value, SecretStr):
            monkeypatch.setenv("ACCOUNTING_" + key.upper(), value.get_secret_value())
    monkeypatch.setenv("ACCOUNTING_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("ACCOUNTING_IDENTITY_POSTING_URL", "https://identity.invalid")
    monkeypatch.setenv("ACCOUNTING_IDENTITY_POSTING_KEY_ID", "accounting.test")
    monkeypatch.setenv(
        "ACCOUNTING_IDENTITY_POSTING_RESPONSE_KEYS",
        json.dumps({"identity.test": secrets.token_hex(32)}),
    )
    # The process entrypoints must parse environment/argv and enter the shared runners.
    invoked: list[str] = []

    def run(coroutine: Any) -> None:
        invoked.append(coroutine.cr_code.co_name)
        coroutine.close()

    monkeypatch.setattr(asyncio, "run", run)
    monkeypatch.setattr("sys.argv", ["posting_delivery", "--once"])
    runpy.run_path(str(posting_delivery.__file__), run_name="__main__")
    monkeypatch.setenv("ACCOUNTING_FINANCIAL_BROKER_URL", "amqp://fixture.invalid")
    monkeypatch.setenv("ACCOUNTING_FINANCIAL_BROKER_USER", "accounting")
    monkeypatch.setenv("ACCOUNTING_FINANCIAL_EVENT_SECRET", secrets.token_hex(32))
    runpy.run_module("accounting.tasks.financial_publisher", run_name="__main__")
    assert invoked == ["run", "run_publisher"]


async def test_malformed_outbox_is_retained_and_blocks_close(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, period, _ = await journal_setup(client, app)
    _, customer, _ = await party_accounts(client)
    doc = await source(client, customer, journal["lines"][1]["account_id"])
    assert (await post_source(client, doc)).status_code == 200
    for invalid in ("version", "timestamp"):
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db, db.begin():
                event = await db.scalar(
                    select(Outbox).where(Outbox.event_type == "accounting.company_posting.confirm")
                )
                assert event is not None
                original = dict(event.payload)
                event.schema_version = 2 if invalid == "version" else 1
                if invalid == "timestamp":
                    event.payload = original | {"posted_at": None}
                event.available_at = utcnow() - dt.timedelta(seconds=1)
        result = await posting_delivery.deliver(app.state.session_factory, app.state.posting_client)
        assert result.confirmed == 0 and result.deferred == 1
        blocked = await change(client, period, "SOFT_CLOSED")
        assert blocked.status_code == 409 and "failed outbox" in blocked.text
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db, db.begin():
                event = await db.scalar(
                    select(Outbox).where(Outbox.event_type == "accounting.company_posting.confirm")
                )
                assert event is not None and event.published_at is None
                assert event.last_error == "ValueError"
                event.payload = original
                event.schema_version = 1
                event.available_at = utcnow() - dt.timedelta(seconds=1)
    assert (
        await posting_delivery.deliver(app.state.session_factory, app.state.posting_client)
    ).confirmed == 1
    # A damaged imported subledger cannot be hidden by closing the period.
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            item = await db.scalar(select(OpenItem))
            assert item is not None
            item.amount += Decimal(1)
    blocked = await change(client, period, "SOFT_CLOSED")
    assert blocked.status_code == 409 and "reconcile" in blocked.text
    for query in ({}, {"account_id": journal["lines"][0]["account_id"]}):
        invalid_response = await client.get(
            BASE + "/subledger/reconciliation",
            params={"as_of": "2026-04-30", "currency": "INR", **query},
            headers=ledger_headers(),
        )
        assert invalid_response.status_code == 422


async def test_foreign_override_reservation_is_bound_and_consumed(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    journal, _, _ = await journal_setup(client, app)
    party, customer, _ = await party_accounts(client, currency="USD")
    await policy(client, party, currency="USD", enforcement="OVERRIDE", limit_amount="50")
    body = request(customer) | {"currency": "USD", "exchange_rate": "83"}
    flags = {"multi_currency", "credit_limits"}
    assert (await command(client, "/credit/check", check_body(body))).status_code == 409
    tiny = check_body(body) | {"amount": "0.0001", "exchange_rate": "0.00000001"}
    assert (await command(client, "/credit/check", tiny, features=flags)).status_code == 422
    assert (await command(client, "/credit-reservations", body, features=flags)).status_code == 409
    too_long = body | {"expires_at": (utcnow() + dt.timedelta(days=8)).isoformat()}
    assert (
        await command(client, "/credit-reservations", too_long, features=flags)
    ).status_code == 422
    override = await command(
        client, "/credit-overrides", body | {"reason": "Temporary limit"}, features=flags
    )
    assert override.status_code == 201, override.text
    approved = await command(
        client,
        f"/credit-overrides/{override.json()['id']}/approve",
        {"expected_version": 1, "approve": True, "reason": "Independent review"},
        user=uuid7(),
        features=flags,
    )
    assert approved.status_code == 200, approved.text
    reserve_body = body | {"override_id": override.json()["id"]}
    reserved = await command(client, "/credit-reservations", reserve_body, features=flags)
    assert reserved.status_code == 201, reserved.text
    row = reserved.json()
    decision = await command(client, "/credit/check", check_body(body), features=flags)
    assert decision.json()["currency"] == "USD" and Decimal(decision.json()["reserved"]) == 60
    renewal = {
        "expected_version": 1,
        "posting_date": "2026-04-02",
        "exchange_rate": "84",
        "expires_at": (utcnow() + dt.timedelta(hours=2)).isoformat(),
    }
    path = f"/credit-reservations/{row['id']}/renew"
    assert (await command(client, path, renewal, features=flags)).status_code == 409
    renewed = await command(client, path, renewal | {"exchange_rate": "83"}, features=flags)
    assert renewed.status_code == 200, renewed.text
    doc = await source(
        client,
        customer,
        journal["lines"][1]["account_id"],
        amount="60",
        currency="USD",
        rate="83",
        source_system=body["source_system"],
        source_type=body["source_type"],
        source_id=body["source_id"],
        credit_reservation_id=row["id"],
    )
    posted = await post_source(client, doc)
    assert posted.status_code == 200, posted.text
    decision = await command(client, "/credit/check", check_body(body), features=flags)
    assert Decimal(decision.json()["exposure"]) == 60 and Decimal(decision.json()["reserved"]) == 0
    consumed = await client.get(
        BASE + f"/credit-reservations/{row['id']}", headers=ledger_headers()
    )
    assert consumed.json()["status"] == "CONSUMED"
