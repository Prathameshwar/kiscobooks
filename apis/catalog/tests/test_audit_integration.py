"""Use the production Catalog emitter, signed transport and Audit consumer together."""

import secrets
import uuid
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
from billing_platform.ids import uuid7
from billing_platform.service_auth import ServiceKey
from fastapi import FastAPI
from pamqp.commands import Basic
from sqlalchemy import select

from catalog.events.audit_contract import AUDIT_EVENTS
from tests.test_api import headers
from tests.test_unit_api import UNIT_BODY, seed_context


async def test_actual_command_signed_delivery_and_redelivery(
    client: httpx.AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch, tenant_a: uuid.UUID
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "audit/src"))
    # Resolved off the path prepended above, never as a dependency: Catalog depending on the Audit
    # package would make the two services deploy together. mypy cannot see a runtime path insert.
    from audit.metadata import service_metadata  # type: ignore[import-not-found]
    from audit.models import AuditEvent  # type: ignore[import-not-found]
    from audit.tasks.consume import receive_audit  # type: ignore[import-not-found]
    from audit.tasks.verify import verify_tenant_chain  # type: ignore[import-not-found]

    company, user = uuid7(), uuid7()
    await seed_context(app.state.session_factory, tenant_a, company, user)
    request_headers = headers(company, tenant=tenant_a, user=user, permission="unit.manage")
    request_headers["Idempotency-Key"] = str(uuid7())
    for _ in range(2):
        result = await client.post(
            f"/v1/companies/{company}/units",
            json=UNIT_BODY,
            headers=request_headers,
        )
        assert result.status_code == 201, result.text
    with tenant_scope(tenant_a):
        async with app.state.session_factory() as db:
            rows = list(await db.scalars(select(Outbox)))
            assert len(rows) == 1
            assert rows[0].payload["action"] == rows[0].event_type

    engine = create_engine("sqlite+aiosqlite:///:memory:")
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
        exchange = MagicMock(spec=AbstractExchange)
        exchange.publish = AsyncMock(return_value=Basic.Ack())
        key = ServiceKey("catalog", "audit", AUDIT_EVENTS, secrets.token_bytes(32))
        publisher = ConfirmedPublisher(exchange, key_id="test", key=key, broker_user="catalog.test")
        published = await publish_batch(
            app.state.session_factory, publisher, event_types=AUDIT_EVENTS
        )
        assert published.confirmed == 1
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
                    sources={"test": BrokerSource(key, "catalog.test")},
                    consumer_name="audit-integration",
                )
            incoming.reject.assert_not_awaited()
            assert incoming.ack.await_count == 2
        with tenant_scope(tenant_a):
            async with factory() as db:
                events = list(await db.scalars(select(AuditEvent)))
                assert len(events) == 1
                assert all(
                    row.company_id == company and row.source_service == "catalog" for row in events
                )
                assert {row.action for row in events} == {row.event_type for row in rows}
                assert await verify_tenant_chain(db, tenant_a) == []
    finally:
        await engine.dispose()
