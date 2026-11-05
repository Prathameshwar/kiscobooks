"""HTTP tests for the per-channel provider-callback capture (docs/notification.md §2.2).

The only unauthenticated ingress: it verifies the provider HMAC over the raw body,
channel must match the account, and a valid callback lands one encrypted ``provider_event``
(a duplicate is acknowledged idempotently).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid

import httpx
import pytest
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.models import ProviderAccount, ProviderEvent
from tests.sns_fixture import TOPIC
from tests.sns_fixture import envelope as sns_envelope

pytestmark = pytest.mark.asyncio

_SECRET = "callback-secret-not-real"
_CALLBACK_KEY = "k" * 43
_SMS_KEY = "s" * 43


async def _seed_account(session: AsyncSession, tenant: uuid.UUID) -> None:
    with unfiltered():
        session.add(
            ProviderAccount(
                id=uuid7(),
                tenant_id=tenant,
                status="active",
                key="ses",
                callback_key=_CALLBACK_KEY,
                channel="email",
                provider_key="ses",
                capabilities={"sns_topic_arn": TOPIC},
                display_name="SES",
                credential_ref="env:SES",
                callback_secret_ref="env:NOTIF_TEST_CB_SECRET",
            )
        )
        await session.commit()


def _headers(body: bytes, *, event_id: str) -> dict[str, str]:
    signature = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        "x-provider-signature": signature,
        "x-provider-event-id": event_id,
        "x-provider-message-id": "PMID-1",
        "x-provider-event-type": "Delivery",
    }


@pytest.fixture(autouse=True)
def _secret_env() -> None:
    os.environ["NOTIF_TEST_CB_SECRET"] = _SECRET


async def _count(session: AsyncSession, tenant: uuid.UUID) -> int:
    with tenant_scope(tenant):
        return int(await session.scalar(select(func.count(ProviderEvent.id))) or 0)


async def test_valid_callback_is_captured(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_account(session, tenant_a)
    body = sns_envelope(b'{"status":"delivered"}')
    resp = await client.post(
        f"/v1/callbacks/email/{_CALLBACK_KEY}", content=body, headers=_headers(body, event_id="e1")
    )
    assert resp.status_code == 202
    assert await _count(session, tenant_a) == 1


async def test_duplicate_callback_is_idempotent(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_account(session, tenant_a)
    body = sns_envelope(b'{"status":"delivered"}')
    headers = _headers(body, event_id="dup")
    url = f"/v1/callbacks/email/{_CALLBACK_KEY}"
    first = await client.post(url, content=body, headers=headers)
    second = await client.post(url, content=body, headers=headers)
    assert first.status_code == 202 and second.status_code == 202
    assert await _count(session, tenant_a) == 1  # one row, not two


async def test_bad_signature_is_rejected(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_account(session, tenant_a)
    body = sns_envelope(b'{"status":"delivered"}')
    headers = _headers(body, event_id="e2")
    damaged = json.loads(body)
    damaged["Signature"] = "deadbeef"
    body = json.dumps(damaged).encode()
    resp = await client.post(f"/v1/callbacks/email/{_CALLBACK_KEY}", content=body, headers=headers)
    assert resp.status_code == 403
    assert await _count(session, tenant_a) == 0


async def test_channel_mismatch_is_404(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_account(session, tenant_a)  # an email account
    body = b"{}"
    resp = await client.post(
        f"/v1/callbacks/sms/{_CALLBACK_KEY}", content=body, headers=_headers(body, event_id="e3")
    )
    assert resp.status_code == 404


async def test_unknown_callback_key_is_404(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_account(session, tenant_a)
    body = b"{}"
    resp = await client.post(
        f"/v1/callbacks/email/{'z' * 43}", content=body, headers=_headers(body, event_id="e4")
    )
    assert resp.status_code == 404


async def _seed_sms_account(session: AsyncSession, tenant: uuid.UUID) -> None:
    with unfiltered():
        session.add(
            ProviderAccount(
                id=uuid7(),
                tenant_id=tenant,
                status="active",
                key="twilio",
                callback_key=_SMS_KEY,
                channel="sms",
                provider_key="twilio",
                display_name="Twilio",
                credential_ref="env:TW",
                callback_secret_ref="env:NOTIF_TEST_CB_SECRET",
            )
        )
        await session.commit()


def _twilio_signature(url: str, params: dict[str, str]) -> str:
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(_SECRET.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


async def test_twilio_sms_callback_is_captured(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_sms_account(session, tenant_a)
    body = b"MessageSid=SM1&MessageStatus=delivered"
    url = f"http://notification.test/v1/callbacks/sms/{_SMS_KEY}"
    signature = _twilio_signature(url, {"MessageSid": "SM1", "MessageStatus": "delivered"})
    headers = {
        "x-twilio-signature": signature,
        "x-provider-event-id": "tw1",
        "x-provider-message-id": "SM1",
        "x-provider-event-type": "delivered",
    }
    resp = await client.post(f"/v1/callbacks/sms/{_SMS_KEY}", content=body, headers=headers)
    assert resp.status_code == 202, resp.text
    assert await _count(session, tenant_a) == 1


async def test_twilio_sms_bad_signature_is_403(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_sms_account(session, tenant_a)
    body = b"MessageSid=SM1&MessageStatus=delivered"
    headers = {"x-twilio-signature": "bad", "x-provider-event-id": "tw2"}
    resp = await client.post(f"/v1/callbacks/sms/{_SMS_KEY}", content=body, headers=headers)
    assert resp.status_code == 403
    assert await _count(session, tenant_a) == 0


async def test_signed_body_metadata_cannot_be_overridden_by_unsigned_headers(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_account(session, tenant_a)
    body = sns_envelope(b'{"eventType":"Delivery","mail":{"messageId":"REAL-ID"}}')
    headers = _headers(body, event_id="forged-event")
    headers.update({"x-provider-message-id": "OTHER-ID", "x-provider-event-type": "Bounce"})
    response = await client.post(
        f"/v1/callbacks/email/{_CALLBACK_KEY}", content=body, headers=headers
    )
    assert response.status_code == 202
    with tenant_scope(tenant_a):
        event = (await session.scalars(select(ProviderEvent))).one()
    assert event.provider_message_id == "REAL-ID"
    assert event.event_type == "delivery"
    assert event.external_event_key != "forged-event"


async def test_unsigned_event_headers_cannot_bypass_callback_deduplication(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_account(session, tenant_a)
    body = sns_envelope(b'{"status":"delivered"}')
    url = f"/v1/callbacks/email/{_CALLBACK_KEY}"
    for event_id in ("first", "replay"):
        response = await client.post(url, content=body, headers=_headers(body, event_id=event_id))
        assert response.status_code == 202
    assert await _count(session, tenant_a) == 1


async def test_successive_message_statuses_are_distinct_events(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_sms_account(session, tenant_a)
    url = f"http://notification.test/v1/callbacks/sms/{_SMS_KEY}"
    for state in ("sent", "delivered", "delivered"):
        params = {"MessageSid": "SM-status", "MessageStatus": state}
        signature = _twilio_signature(url, params)
        response = await client.post(
            url,
            content=f"MessageSid=SM-status&MessageStatus={state}".encode(),
            headers={"x-twilio-signature": signature},
        )
        assert response.status_code == 202
    with tenant_scope(tenant_a):
        events = list((await session.scalars(select(ProviderEvent))).all())
    assert len(events) == 2
    assert {event.event_type for event in events} == {"sent", "delivered"}
