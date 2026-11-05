"""Stored-message transport through native adapters and signed callback normalization."""

import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy import select

from notification.models import (
    DeliveryAttempt,
    NotificationDelivery,
    ProviderAccount,
    ProviderTemplateBinding,
    RecipientEndpoint,
    RoutingRule,
    SenderIdentity,
    TemplateVariant,
    TemplateVersion,
)
from notification.providers import MetaWhatsAppAdapter, TwilioSmsAdapter
from notification.security import AesGcmCipher
from notification.tasks.consume import handle_send_command
from notification.tasks.dispatch import Dispatcher
from notification.tasks.normalize import normalize_pending
from tests.api_support import actor_headers
from tests.notif_seed import CIPHER, KEY_REF, envelope, seed_email_route


@pytest.mark.parametrize("channel", ["sms", "whatsapp"])
async def test_stored_message_native_send_receipt_and_history(
    client, app, session, factory, tenant_a, tenant_b, monkeypatch, channel
):
    company, subject = uuid7(), uuid7()
    await seed_email_route(session, tenant=tenant_a, company=company, subject=subject)
    secret = "test-native-callback"
    monkeypatch.setenv("VERIFY", secret)
    with tenant_scope(tenant_a):
        provider = (await session.scalars(select(ProviderAccount))).one()
        provider.channel = channel
        provider.provider_key = "twilio" if channel == "sms" else "meta"
        provider.callback_secret_ref = "env:VERIFY"
        endpoint = (await session.scalars(select(RecipientEndpoint))).one()
        endpoint.channel = channel
        endpoint.destination_ciphertext = CIPHER.encrypt(
            b"+15551234567", nonce=b"d" * 12, associated_data=endpoint.id.bytes
        )
        sender = (await session.scalars(select(SenderIdentity))).one()
        sender.sender_type = channel
        sender.external_sender_id = "+15557654321" if channel == "sms" else "phone-id"
        route = (await session.scalars(select(RoutingRule))).one()
        route.channel = channel
        variant = (await session.scalars(select(TemplateVariant))).one()
        variant.channel = channel
        version = (await session.scalars(select(TemplateVersion))).one()
        if channel == "whatsapp":
            version.channel_payload = {"template_parameters": ["name"]}
            session.add(
                ProviderTemplateBinding(
                    tenant_id=tenant_a,
                    template_version_id=version.id,
                    provider_account_id=provider.id,
                    external_template_id="template-id",
                    external_name="hello",
                    external_language="en",
                    approval_status="approved",
                    synced_at=utcnow(),
                )
            )
        await session.commit()
        result = await handle_send_command(
            session,
            envelope(tenant_a, company, subject, channels=[channel]),
            cipher=CIPHER,
            key_ref=KEY_REF,
        )
        assert result.deliveries_created == 1
        await session.commit()
        delivery = (await session.scalars(select(NotificationDelivery))).one()
        # Dispatch must use the frozen rendered values even if retained request variables change.
        version.body_text = "Changed local text"
        await session.commit()
    callback_path = f"/v1/callbacks/{channel}/{provider.callback_key}"
    callback_url = app.state.settings.callback_public_origin + callback_path
    key = f"{delivery.id}:1"
    signed_callback_url = None

    async def transport(request):
        nonlocal signed_callback_url
        if channel == "sms":
            values = parse_qs(request.content.decode())
            assert values["Body"] == ["Hello Ada"]
            assert values["To"] == ["+15551234567"]
            signed_callback_url = values["StatusCallback"][0]
            assert parse_qs(urlsplit(signed_callback_url).query)["attempt_key"] == [key]
            return httpx.Response(201, json={"sid": "native-message"})
        payload = json.loads(request.content)
        assert payload["biz_opaque_callback_data"] == key
        assert payload["template"]["name"] == "hello"
        assert payload["template"]["components"][0]["parameters"] == [
            {"type": "text", "text": "Ada"}
        ]
        return httpx.Response(200, json={"messages": [{"id": "native-message"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as external:
        adapter = (
            TwilioSmsAdapter(
                external, account_sid="test", auth_token="test", callback_url=callback_url
            )
            if channel == "sms"
            else MetaWhatsAppAdapter(external, access_token="test")
        )
        result = await Dispatcher(factory, {provider.id: adapter}).dispatch_stored(
            tenant_a, delivery.id, cipher=CIPHER, key_ref=KEY_REF
        )
        assert result.outcome == "accepted"

    if channel == "sms":
        fields = {"MessageSid": "native-message", "MessageStatus": "delivered"}
        message = signed_callback_url + "".join(k + fields[k] for k in sorted(fields))
        signature = base64.b64encode(
            hmac.new(secret.encode(), message.encode(), hashlib.sha1).digest()
        ).decode()
        response = await client.post(
            callback_path + "?" + urlsplit(signed_callback_url).query,
            data=fields,
            headers={"X-Twilio-Signature": signature},
        )
    else:
        body = json.dumps(
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "statuses": [
                                        {
                                            "id": "native-message",
                                            "status": "delivered",
                                            "biz_opaque_callback_data": key,
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        ).encode()
        response = await client.post(
            callback_path,
            content=body,
            headers={
                "X-Hub-Signature-256": "sha256="
                + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
            },
        )
    assert response.status_code == 202
    async with factory() as db:
        assert await normalize_pending(db, cipher=AesGcmCipher(app.state.data_key)) == 1
        await db.commit()
    proof = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), permissions=["notification.delivery.read"]
    )
    detail = await client.get(f"/v1/deliveries/{delivery.id}", headers=proof)
    assert detail.status_code == 200 and detail.json()["status"] == "delivered"
    history = await client.get(f"/v1/deliveries/{delivery.id}/events", headers=proof)
    assert any(row["to_status"] == "delivered" for row in history.json()["items"])
    other = actor_headers(
        tenant_id=tenant_b, user_id=uuid7(), permissions=["notification.delivery.read"]
    )
    assert (await client.get(f"/v1/deliveries/{delivery.id}", headers=other)).status_code == 404
    with tenant_scope(tenant_a):
        attempt = (await session.scalars(select(DeliveryAttempt))).one()
        assert attempt.attempt_key == key and attempt.provider_message_id == "native-message"
