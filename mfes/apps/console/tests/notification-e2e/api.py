"""Disposable browser-test API. Never imported by the production application.

Uses production routes, guards, planning, dispatch and native receipt verification.
Only external Identity/provider account checks and transport acceptance are fixtures.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import sys
import uuid
from pathlib import Path

import httpx
import uvicorn
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from fastapi import HTTPException, Request
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "apis/notification"))

from notification.config import CredentialBinding, OwnershipBinding, Settings
from notification.main import create_app
from notification.metadata import service_metadata
from notification.models import NotificationDelivery, NotificationSpace, ProviderAccount, RecipientEndpoint
from notification.ownership import space_scope
from notification.providers import SendResult
from notification.providers.inspection import Inspection
from notification.security import AesGcmCipher, keyed_destination_hash
from notification.tasks import configuration
from notification.tasks.consume import handle_send_command
from notification.tasks.dispatch import Dispatcher
from notification.tasks.normalize import normalize_pending
from notification.tasks.platform import EVENT, handle_platform
from tests.api_support import ACTOR_SECRET, actor_headers
from tests.sns_fixture import TOPIC, certificate, envelope as sns_envelope

TENANT = uuid.UUID("019a0000-0000-7000-8000-000000000001")
SPACE = uuid.UUID("019a0000-0000-7000-8000-000000000005")
COMPANY = uuid.UUID("019a0000-0000-7000-8000-000000000006")
USER = uuid.UUID("019a0000-0000-7000-8000-000000000007")
CALLBACK_SECRET = "notification-browser-test-callback"
INGRESS_SECRET = "notification-browser-test-ingress"
settings = Settings(
    database_url=os.environ["NOTIFICATION_E2E_DATABASE"],
    actor_signing_secret=ACTOR_SECRET,
    cursor_signing_secret="notification-browser-test-cursor-secret",
    data_encryption_key="notification-browser-test-data-key",
    platform_owner_tenant_id=TENANT,
    platform_space_id=SPACE,
    platform_ingress_keys={"fixture": INGRESS_SECRET},
    callback_public_origin="http://127.0.0.1:" + os.environ["NOTIFICATION_E2E_WEB_PORT"] + "/notification",
    sns_topic_bindings={TOPIC: OwnershipBinding(tenant_id=TENANT, space_id=SPACE)},
    credential_bindings={
        f"env:{realm}_{kind}": CredentialBinding(tenant_id=TENANT, space_id=SPACE if realm == "PLATFORM" else TENANT,
                                                environment_variable=f"{realm}_{kind}", allowed_senders=["noreply@example.invalid", "+15557654321", "fixture-phone-id"])
        for realm in ("PLATFORM", "TENANT") for kind in ("PROVIDER", "CALLBACK")
    },
)
for realm in ("PLATFORM", "TENANT"):
    os.environ[realm + "_PROVIDER"] = "{}"
    os.environ[realm + "_CALLBACK"] = CALLBACK_SECRET
app = create_app(settings)
app.state.sns_certificate_loader = certificate
factory = app.state.session_factory
cipher = AesGcmCipher(app.state.data_key)


async def inspect_fixture(provider, credentials, kind, **kwargs):
    return Inspection(True, "fixture_checked", verification_status="verified" if kind.startswith("sender.") else None,
                      approval_status="approved" if kind == "binding.sync" else None)


configuration.inspect_provider = inspect_fixture
original_lifespan = app.router.lifespan_context


@contextlib.asynccontextmanager
async def lifespan(application):
    async with original_lifespan(application):
        async with app.state.engine.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
        async def jobs():
            while True:
                await configuration.run_configuration_jobs(factory, settings)
                await asyncio.sleep(0.2)
        task = asyncio.create_task(jobs())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app.router.lifespan_context = lifespan


@app.post("/__fixture__/send", include_in_schema=False)
async def stage_message(request: Request):
    if request.headers.get("x-fixture-control") != "local-browser-test":
        raise HTTPException(403)
    body = await request.json()
    owner, channel = body["owner"], body["channel"]
    assert owner in {"tenant", "platform"} and channel in {"email", "sms", "whatsapp"}
    space = SPACE if owner == "platform" else TENANT
    subject = uuid7()
    destination = "staff@example.invalid" if channel == "email" else "+15551234567"
    with tenant_scope(TENANT), space_scope(space):
        async with factory() as db:
            if owner == "platform":
                message_id = uuid7()
                payload = json.dumps({"destinations": {channel: destination}, "variables": {"message": "A browser-tested alert"}}).encode()
                encrypted = AesGcmCipher(hashlib.sha256(INGRESS_SECRET.encode()).digest()).encrypt(
                    payload, nonce=secrets.token_bytes(12), associated_data=message_id.bytes + SPACE.bytes + b"platform.staff.alert")
                envelope = MessageEnvelope(message_id=message_id, tenant_id=TENANT, event_type=EVENT, schema_version=1, occurred_at=utcnow(), payload={
                    "space_id": str(SPACE), "use_case": "platform.staff.alert", "trigger_key": EVENT,
                    "recipient_ref": str(subject), "channels": [channel], "locale": "en", "expires_at": (utcnow() + dt.timedelta(hours=1)).isoformat(),
                    "key_id": "fixture", "encrypted_payload": base64.b64encode(encrypted).decode(),
                })
                await handle_platform(db, envelope, settings=settings)
            else:
                endpoint = RecipientEndpoint(tenant_id=TENANT, company_id=COMPANY, subject_type="user", subject_id=subject, channel=channel,
                    destination_hmac=keyed_destination_hash(destination, app.state.data_key), destination_masked="***4567", locale="en", timezone="UTC",
                    verification_status="verified", health_status="healthy", source_version=1)
                db.add(endpoint)
                await db.flush()
                endpoint.destination_ciphertext = cipher.encrypt(destination.encode(), nonce=secrets.token_bytes(12), associated_data=endpoint.id.bytes)
                envelope = MessageEnvelope(message_id=uuid7(), tenant_id=TENANT, event_type="notification.send", schema_version=1, occurred_at=utcnow(), payload={
                    "company_id": str(COMPANY), "source_service": "vouchers", "source_event_key": "vouchers.voucher.share", "event_key": "voucher.shared",
                    "category": "transactional", "aggregate_type": "voucher", "aggregate_id": str(uuid7()), "subject_type": "user", "subject_id": str(subject),
                    "channels": [channel], "locale": "en", "variables": {"message": "A browser-tested alert"},
                })
                planned = await handle_send_command(db, envelope, cipher=cipher, key_ref=settings.data_encryption_key_ref)
                assert planned.deliveries_created == 1, f"Unexpected planning outcomes: {planned.outcomes}"
            await db.commit()
            delivery = await db.scalar(select(NotificationDelivery).order_by(NotificationDelivery.created_at.desc()).limit(1))
            assert delivery is not None and delivery.status == "pending", "No executable notification was planned"
            account = await db.get(ProviderAccount, delivery.provider_account_id)
            identity, request_id, endpoint_id = delivery.id, delivery.request_id, delivery.recipient_endpoint_id

        class ProviderFixture:
            async def send(self, command):
                assert command.body == "Notice A browser-tested alert"
                return SendResult("accepted", "fixture-message-" + str(identity))

        await Dispatcher(factory, {account.id: ProviderFixture()}).dispatch_stored(TENANT, identity, cipher=cipher, key_ref=settings.data_encryption_key_ref)
        message_id = "fixture-message-" + str(identity)
        key = str(identity) + ":1"
        path = f"/v1/callbacks/{channel}/{account.callback_key}"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://notification.fixture") as client:
            if channel == "email":
                payload = json.dumps({"eventType": "Delivery", "mail": {"messageId": message_id, "tags": {"attempt_key": [key.replace(":", "_")]}}}).encode()
                receipt = await client.post(path, content=sns_envelope(payload))
            elif channel == "sms":
                fields = {"MessageSid": message_id, "MessageStatus": "delivered"}
                url = settings.callback_public_origin + path + "?attempt_key=" + key
                signature = base64.b64encode(hmac.new(CALLBACK_SECRET.encode(), (url + "".join(k + fields[k] for k in sorted(fields))).encode(), hashlib.sha1).digest()).decode()
                receipt = await client.post(path + "?attempt_key=" + key, data=fields, headers={"X-Twilio-Signature": signature})
            else:
                payload = json.dumps({"entry": [{"changes": [{"value": {"statuses": [{"id": message_id, "status": "delivered", "biz_opaque_callback_data": key}]}}]}]}).encode()
                receipt = await client.post(path, content=payload, headers={"X-Hub-Signature-256": "sha256=" + hmac.new(CALLBACK_SECRET.encode(), payload, hashlib.sha256).hexdigest()})
            assert receipt.status_code == 202, receipt.text
        async with factory() as db:
            await normalize_pending(db, cipher=cipher)
            await db.commit()
    return {"delivery_id": str(identity), "request_id": str(request_id), "endpoint_id": str(endpoint_id), "subject_id": str(subject)}


class GatewayFixture:
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/notification/"):
            return await app(scope, receive, send)
        headers = dict(scope["headers"])
        token = headers.get(b"authorization", b"").decode()
        if token not in {"Bearer fixture-admin", "Bearer fixture-reader"}:
            await send({"type": "http.response.start", "status": 401, "headers": []})
            return await send({"type": "http.response.body", "body": b"{}"})
        path = scope["path"].removeprefix("/notification")
        platform = path.startswith("/v1/platform/")
        prefix = "platform.notification_" if platform else "notification."
        permissions = [prefix + family + ".read" for family in ("provider", "template", "route", "recipient", "request", "delivery")]
        if token.endswith("admin"):
            permissions += [prefix + family + ".manage" for family in ("provider", "template", "route", "consent", "suppression")]
            permissions.append(prefix + "delivery.retry")
        proof = actor_headers(tenant_id=TENANT, user_id=USER, permissions=permissions)
        if platform:
            body = json.loads(base64.urlsafe_b64decode(proof["X-Actor-Context"] + "=="))
            body.update(user_type="platform_notification_operator", notification_authority={"path": path, "method": scope["method"]})
            raw = json.dumps(body).encode()
            proof = {"X-Actor-Context": base64.urlsafe_b64encode(raw).rstrip(b"=").decode(), "X-Actor-Signature": hmac.new(ACTOR_SECRET.encode(), raw, hashlib.sha256).hexdigest()}
        scoped = {**scope, "path": path, "raw_path": path.encode(), "headers": [(key, value) for key, value in scope["headers"] if not key.startswith(b"x-actor-")] + [(key.lower().encode(), value.encode()) for key, value in proof.items()]}
        await app(scoped, receive, send)


if __name__ == "__main__":
    uvicorn.run(GatewayFixture(), host="127.0.0.1", port=int(os.environ["NOTIFICATION_E2E_API_PORT"]), access_log=False)
