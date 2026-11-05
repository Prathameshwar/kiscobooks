"""Voucher commands must be source-authenticated and company-scoped."""

import datetime as dt
from typing import Any

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import CompanyServiceScope, ServiceKey, sign_service_body
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.config import Settings, VoucherSource
from notification.models import NotificationRequest
from notification.tasks.vouchers import receive_voucher


class Incoming:
    def __init__(self, envelope: MessageEnvelope, *, secret: bytes, user: str = "vouchers"):
        self.body = envelope.model_dump_json().encode()
        self.routing_key = envelope.event_type
        self.message_id = str(envelope.message_id)
        self.type = envelope.event_type
        self.content_type = "application/json"
        self.user_id = user
        self.acked = False
        self.rejected = False
        self.headers = {
            "key_id": "vouchers.current",
            "issuer": "vouchers",
            "audience": "notification",
            "signed_at": "1700000000",
            "signature": sign_service_body(
                ServiceKey("vouchers", "notification", frozenset({"notification.send"}), secret),
                key_id="vouchers.current",
                operation=envelope.event_type,
                timestamp=1700000000,
                body=self.body,
            ),
        }

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, *, requeue: bool) -> None:
        self.rejected = not requeue


def command(tenant: Any, company: Any, *, event_type: str = "notification.send") -> MessageEnvelope:
    return MessageEnvelope(
        message_id=uuid7(),
        tenant_id=tenant,
        event_type=event_type,
        schema_version=1,
        occurred_at=dt.datetime.now(dt.UTC),
        payload={
            "company_id": str(company),
            "source_service": "vouchers",
            "source_event_key": "vouchers.voucher.share",
            "event_key": "voucher.shared",
            "source_version": 1,
            "category": "transactional",
            "aggregate_type": "voucher",
            "aggregate_id": str(uuid7()),
            "subject_type": "party_invoicing",
            "subject_id": str(uuid7()),
            "channels": ["email"],
            "variables": {"number": "A-1"},
        },
    )


@pytest.mark.asyncio
async def test_voucher_source_scope_and_redelivery(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: Any,
) -> None:
    company = uuid7()
    secret = b"s" * 32
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=SecretStr("a" * 32),
        cursor_signing_secret=SecretStr("c" * 32),
        data_encryption_key=SecretStr("d" * 32),
        voucher_sources={
            "vouchers.current": VoucherSource(
                secret=SecretStr(secret.decode()),
                broker_user="vouchers",
                scopes=[CompanyServiceScope(tenant_id=tenant_a, company_id=company)],
            )
        },
    )
    envelope = command(tenant_a, company)
    incoming = Incoming(envelope, secret=secret)
    await receive_voucher(factory, incoming, settings=settings)  # type: ignore[arg-type]
    assert incoming.acked
    repeat = Incoming(envelope, secret=secret)
    await receive_voucher(factory, repeat, settings=settings)  # type: ignore[arg-type]
    assert repeat.acked
    with tenant_scope(tenant_a):
        async with factory() as session:
            rows = list((await session.scalars(select(NotificationRequest))).all())
            assert len(rows) == 1

    outside = Incoming(command(tenant_a, uuid7()), secret=secret)
    await receive_voucher(factory, outside, settings=settings)  # type: ignore[arg-type]
    assert outside.rejected and not outside.acked
    with tenant_scope(tenant_a):
        async with factory() as session:
            assert len(list((await session.scalars(select(NotificationRequest))).all())) == 1
