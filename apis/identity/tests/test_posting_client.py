from __future__ import annotations

import secrets
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from fastapi import FastAPI
from identity_posting import PostingClient, ReservationError, ReservationRejectedError
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import CatalogSourceCredential, CatalogSourceScope
from tests.factories import build_user, seed_two_companies


async def test_billing_client_verified_receipts_replay_and_terminal(
    app: FastAPI,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _ = await seed_two_companies(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        user = build_user(tenant_id=tenant_a)
        session.add(user)
        await session.commit()
    secret, response_secret = secrets.token_hex(32), secrets.token_hex(32)
    app.state.settings.billing_reservation_credentials = {
        "client": CatalogSourceCredential(
            secret=SecretStr(secret),
            scopes=(CatalogSourceScope(tenant_id=tenant_a, company_id=company),),
        )
    }
    app.state.settings.billing_reservation_response_secret = SecretStr(response_secret)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://identity.test"
    ) as http:
        client = PostingClient(
            http,
            key_id="client",
            request_secret=secret.encode(),
            response_keys={"current": response_secret.encode()},
        )
        config = await client.configuration(tenant_a, company)
        for outcome in ("confirmed", "aborted"):
            operation = uuid7()
            params = {
                "operation_id": operation,
                "actor_user_id": user.id,
                "configuration_hash": config.configuration_hash,
                "features": [],
            }
            first = await client.reserve(tenant_a, company, **params)
            assert first.status == "pending"
            assert await client.reserve(tenant_a, company, **params) == first
            posted_at = utcnow() if outcome == "confirmed" else None
            for _ in range(2):
                result = await client.terminal(
                    tenant_a,
                    company,
                    operation_id=operation,
                    outcome=outcome,
                    reference="billing-outbox:" + str(operation),
                    posted_at=posted_at,
                )
                assert result.status == outcome
            with pytest.raises(ReservationRejectedError) as error:
                await client.terminal(
                    tenant_a,
                    company,
                    operation_id=operation,
                    outcome="aborted" if outcome == "confirmed" else "confirmed",
                    reference="different",
                    posted_at=None if outcome == "confirmed" else utcnow(),
                )
            assert error.value.status_code == 409
        wrong = PostingClient(
            http,
            key_id="client",
            request_secret=secret.encode(),
            response_keys={"current": secrets.token_bytes(32)},
        )
        with pytest.raises(ReservationError):
            await wrong.configuration(tenant_a, company)


@pytest.mark.parametrize("failure", ["redirect", "unsigned", "oversized", "timeout"])
async def test_billing_adapter_fails_closed(failure):
    def transport(request):
        if failure == "redirect":
            return httpx.Response(307, headers={"location": "https://evil.test"})
        if failure == "timeout":
            raise httpx.ReadTimeout("test timeout")
        return httpx.Response(200, content=b"x" * (65537 if failure == "oversized" else 10))

    async with httpx.AsyncClient(
        base_url="https://identity.test", transport=httpx.MockTransport(transport)
    ) as http:
        client = PostingClient(
            http,
            key_id="client",
            request_secret=secrets.token_bytes(32),
            response_keys={"current": secrets.token_bytes(32)},
        )
        with pytest.raises(ReservationError):
            await client.configuration(uuid7(), uuid7())


async def test_publisher_routes_and_credentials_do_not_overlap(monkeypatch):
    from identity.tasks import notification_publisher, posting_publisher

    for module, audience, exchange, event in (
        (
            notification_publisher,
            "notification",
            "platform.notification",
            "identity.invitation.requested",
        ),
        (posting_publisher, "billing", "platform.billing", "identity.posting_reservation.terminal"),
    ):
        runner = AsyncMock()
        monkeypatch.setattr(module, "run_publisher", runner)
        settings = module.Settings(
            IDENTITY_DATABASE_URL="sqlite+aiosqlite://",
            broker_url="amqp://test",
            broker_user="test",
            secret=SecretStr(secrets.token_hex(32)),
        )
        await module.run(settings)
        config = runner.call_args.args[0]
        assert config.key.audience == audience
        assert config.exchange == exchange
        assert event in config.key.operations
        assert config.maximum_attempts == 12
