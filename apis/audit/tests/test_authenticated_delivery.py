from __future__ import annotations

import json
import logging
import time
import uuid
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aio_pika.abc import AbstractIncomingMessage
from billing_platform.broker import BrokerSource
from billing_platform.db.tenant_context import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import ServiceKey, sign_service_body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from audit.models import AuditEvent
from audit.tasks.consume import receive_audit

KEY = ServiceKey(
    "identity", "audit", frozenset({"company.updated"}), b"test-identity-audit-key-32-bytes!!"
)
SOURCES = {"identity.current": BrokerSource(KEY, "identity.publisher")}


async def test_rejected_delivery_logs_safe_message_reference(tenant_a, caplog):
    incoming = message(tenant_a)
    incoming.headers["signature"] = "private invalid signature"
    with caplog.at_level(logging.WARNING):
        await receive_audit(MagicMock(), incoming, sources=SOURCES, consumer_name="audit-test")
    diagnostic = json.loads(caplog.records[-1].getMessage())
    assert diagnostic["event"] == "audit.rejected"
    assert diagnostic["message_id"] == incoming.message_id
    assert diagnostic["event_type"] == "company.updated"
    assert "private" not in caplog.text
    incoming.reject.assert_awaited_once_with(requeue=False)


def message(tenant_id: uuid.UUID, **changes: object) -> MagicMock:
    envelope = MessageEnvelope(
        message_id=uuid.uuid4(),
        tenant_id=tenant_id,
        event_type="company.updated",
        schema_version=1,
        occurred_at=utcnow(),
        payload={
            "action": "company.updated",
            "category": "admin",
            "entity_type": "company",
            "company_id": str(uuid.uuid4()),
            "changes": {"name": {"to": "[redacted]"}},
        },
    )
    body = envelope.model_dump_json().encode()
    now = int(time.time())
    headers = {
        "key_id": "identity.current",
        "issuer": "identity",
        "audience": "audit",
        "signed_at": str(now),
        "signature": sign_service_body(
            KEY,
            key_id="identity.current",
            operation=envelope.event_type,
            timestamp=now,
            body=body,
        ),
    }
    result = MagicMock(spec=AbstractIncomingMessage)
    for key, value in {
        "headers": headers,
        "body": body,
        "user_id": "identity.publisher",
        "message_id": str(envelope.message_id),
        "routing_key": envelope.event_type,
        "type": envelope.event_type,
        "content_type": "application/json",
        **changes,
    }.items():
        setattr(result, key, value)
    result.ack = AsyncMock()
    result.reject = AsyncMock()
    return result


async def test_authenticated_delivery_preserves_scope_and_deduplicates(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    incoming = message(tenant_a)
    for _ in range(2):
        await receive_audit(
            factory,
            cast(AbstractIncomingMessage, incoming),
            sources=SOURCES,
            consumer_name="audit-test",
        )
    assert incoming.ack.await_count == 2
    incoming.reject.assert_not_awaited()
    with tenant_scope(tenant_a):
        async with factory() as db:
            rows = list(await db.scalars(select(AuditEvent)))
            assert len(rows) == 1
            assert rows[0].company_id is not None
            assert rows[0].source_service == "identity"
            assert rows[0].changes == {"name": {"to": "[redacted]"}}


@pytest.mark.parametrize(
    "changes",
    [
        {"headers": {}},
        {"user_id": "other.publisher"},
        {"body": b"{}"},
        {"routing_key": "user.created"},
        {"message_id": str(uuid.uuid4())},
    ],
)
async def test_untrusted_delivery_has_no_effect(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    changes: dict[str, object],
) -> None:
    incoming = message(tenant_a, **changes)
    await receive_audit(
        factory,
        cast(AbstractIncomingMessage, incoming),
        sources=SOURCES,
        consumer_name="audit-test",
    )
    incoming.reject.assert_awaited_once_with(requeue=False)
    incoming.ack.assert_not_awaited()
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert not list(await db.scalars(select(AuditEvent)))


async def test_database_outage_is_not_acknowledged(tenant_a: uuid.UUID) -> None:
    incoming = message(tenant_a)
    factory = MagicMock(side_effect=RuntimeError("database unavailable"))
    with pytest.raises(RuntimeError):
        await receive_audit(
            factory,
            cast(AbstractIncomingMessage, incoming),
            sources=SOURCES,
            consumer_name="audit-test",
        )
    incoming.ack.assert_not_awaited()
    incoming.reject.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value",
    [
        ("reason", "x" * 501),
        ("actor_type", "x" * 33),
        ("actor_ip", "x" * 46),
        ("actor_user_agent", "x" * 401),
        ("request_id", "x" * 65),
        ("entity_type", "x" * 81),
        ("changes", {"value": float("nan")}),
        ("context", {"nested": [float("inf")]}),
    ],
)
async def test_authenticated_invalid_payload_dead_letters_before_database_access(
    tenant_a: uuid.UUID,
    field: str,
    value: object,
) -> None:
    incoming = message(tenant_a)
    body = json.loads(incoming.body)
    body["payload"][field] = value
    incoming.body = json.dumps(body).encode()
    incoming.headers["signature"] = sign_service_body(
        KEY,
        key_id="identity.current",
        operation=incoming.type,
        timestamp=int(incoming.headers["signed_at"]),
        body=incoming.body,
    )
    factory = MagicMock(side_effect=AssertionError("invalid payload opened the database"))
    await receive_audit(
        factory,
        cast(AbstractIncomingMessage, incoming),
        sources=SOURCES,
        consumer_name="audit-test",
    )
    factory.assert_not_called()
    incoming.reject.assert_awaited_once_with(requeue=False)
    incoming.ack.assert_not_awaited()
