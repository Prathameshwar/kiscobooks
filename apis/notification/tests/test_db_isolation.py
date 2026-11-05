"""Two-tenant isolation on the session-level filter (CLAUDE.md §7), and a smoke that the
DB harness works for notification models. Seed one row per tenant, query scoped to one,
assert the other's row is absent."""

from __future__ import annotations

import uuid

import pytest
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import ProviderAccount, RecipientEndpoint

pytestmark = pytest.mark.asyncio


def _provider(tenant_id: uuid.UUID, key: str, callback_key: str) -> ProviderAccount:
    return ProviderAccount(
        id=uuid7(),
        tenant_id=tenant_id,
        status="active",
        key=key,
        callback_key=callback_key,
        channel="email",
        provider_key="ses",
        display_name="Primary SES",
        credential_ref="env:SES",
        callback_secret_ref="env:SES_CB",
    )


def _endpoint(tenant_id: uuid.UUID) -> RecipientEndpoint:
    return RecipientEndpoint(
        id=uuid7(),
        tenant_id=tenant_id,
        subject_type="user",
        subject_id=uuid7(),
        channel="email",
        destination_ciphertext=b"x",
        destination_hmac=b"0" * 32,
        destination_masked="a***@example.com",
        locale="en-IN",
        timezone="Asia/Kolkata",
        verification_status="verified",
        health_status="healthy",
        source_version=1,
    )


async def _count(session: AsyncSession, model: object, tenant_id: uuid.UUID) -> int:
    with tenant_scope(tenant_id):
        return int(await session.scalar(select(func.count(model.id))) or 0)  # type: ignore[attr-defined]


async def test_provider_account_isolation(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    with unfiltered():
        session.add(_provider(tenant_a, "ses", "k" * 43))
        session.add(_provider(tenant_b, "ses", "j" * 43))
        await session.commit()
    assert await _count(session, ProviderAccount, tenant_a) == 1
    assert await _count(session, ProviderAccount, tenant_b) == 1
    with tenant_scope(tenant_a):
        rows = (await session.scalars(select(ProviderAccount))).all()
    assert {r.tenant_id for r in rows} == {tenant_a}


async def test_recipient_endpoint_isolation(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    with unfiltered():
        session.add(_endpoint(tenant_a))
        session.add(_endpoint(tenant_b))
        await session.commit()
    assert await _count(session, RecipientEndpoint, tenant_a) == 1
    assert await _count(session, RecipientEndpoint, tenant_b) == 1
