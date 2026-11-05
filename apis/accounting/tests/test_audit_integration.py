"""Use the production Accounting emitter, signed transport and Audit consumer together."""

import secrets
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from aio_pika.abc import AbstractExchange, AbstractIncomingMessage
from billing_platform.broker import BrokerSource, ConfirmedPublisher
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.delivery import publish_batch
from billing_platform.service_auth import ServiceKey
from fastapi import FastAPI
from pamqp.commands import Basic
from sqlalchemy import select

from accounting.events.audit_contract import AUDIT_EVENTS
from tests.conftest import COMPANY, TENANT, headers


@pytest.mark.parametrize("legacy", [False, True])
async def test_actual_command_signed_delivery_and_redelivery(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch, legacy: bool
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "audit/src"))
    from audit.metadata import service_metadata
    from audit.models import AuditEvent
    from audit.tasks.consume import receive_audit
    from audit.tasks.verify import verify_tenant_chain

    request_headers = headers()
    for _ in range(2):
        result = await client.post(
            f"/v1/companies/{COMPANY}/accounting-setup/initialize",
            json={},
            headers=request_headers,
        )
        assert result.status_code == 200, result.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            rows = list(await db.scalars(select(Outbox)))
            assert (
                len(rows) == 49
            )  # full starter chart, setup and one reporting change; replay added nothing
            for row in rows:
                assert row.payload["action"] == row.event_type
                if legacy and row.event_type != "accounting.reporting.captured":
                    row.payload = row.payload | {"action": row.event_type.rsplit(".", 1)[1]}

    engine = create_engine("sqlite+aiosqlite:///:memory:")
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
        exchange = MagicMock(spec=AbstractExchange)
        exchange.publish = AsyncMock(return_value=Basic.Ack())
        key = ServiceKey("accounting", "audit", AUDIT_EVENTS, secrets.token_bytes(32))
        publisher = ConfirmedPublisher(
            exchange, key_id="test", key=key, broker_user="accounting.test"
        )
        published = await publish_batch(
            app.state.session_factory, publisher, event_types=AUDIT_EVENTS
        )
        assert published.confirmed == 49
        for call in exchange.publish.call_args_list:
            outgoing, route = call.args
            incoming = MagicMock(spec=AbstractIncomingMessage)
            for name in ("headers", "body", "user_id", "message_id", "type", "content_type"):
                setattr(incoming, name, getattr(outgoing, name))
            incoming.routing_key = route
            incoming.ack, incoming.reject = AsyncMock(), AsyncMock()
            for _ in range(2):
                await receive_audit(
                    factory,
                    cast(AbstractIncomingMessage, incoming),
                    sources={"test": BrokerSource(key, "accounting.test")},
                    consumer_name="audit-integration",
                )
            incoming.reject.assert_not_awaited()
            assert incoming.ack.await_count == 2
        with tenant_scope(TENANT):
            async with factory() as db:
                events = list(await db.scalars(select(AuditEvent)))
                assert len(events) == 49
                assert all(
                    row.company_id == COMPANY and row.source_service == "accounting"
                    for row in events
                )
                assert {row.action for row in events} == (
                    {"create", "update", "accounting.reporting.captured"}
                    if legacy
                    else {row.event_type for row in rows}
                )
                assert await verify_tenant_chain(db, TENANT) == []
    finally:
        await engine.dispose()
