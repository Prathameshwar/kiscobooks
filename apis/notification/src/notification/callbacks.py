"""Verified callback inbox capture and provider normalization."""

from __future__ import annotations

import hashlib
import hmac
import os
from urllib.parse import parse_qsl

from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from billing_platform.ids import uuid7
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from notification.domain.constants import CHANNELS
from notification.models import NotificationJob, ProviderAccount, ProviderEvent
from notification.ownership import space_scope
from notification.providers.normalize import (
    extract_callback_facts,
    extract_callback_metadata,
    valid_attempt_key,
)
from notification.providers.sns import certificate, verify_sns
from notification.providers.verify import verify_callback
from notification.security import AesGcmCipher

# Per-channel callback paths (docs/notification.md §2.2): the channel in the path lets
# nginx route per provider type and lets us select the right signature verifier, while
# the callback_key remains the globally unique (non-secret) route id.
router = APIRouter(prefix="/v1/callbacks")


async def _account(request: Request, callback_key: str) -> ProviderAccount:
    async with request.app.state.session_factory() as db:
        # Sole pre-tenant lookup: callback_key is globally unique but never authority.
        with unfiltered():
            row: ProviderAccount | None = await db.scalar(
                select(ProviderAccount).where(ProviderAccount.callback_key == callback_key)
            )
        if row is None:
            raise NotFoundError("callback route not found")
        return row


@router.post("/{channel}/{callback_key}", status_code=status.HTTP_202_ACCEPTED)
async def capture(channel: str, callback_key: str, request: Request) -> Response:
    if channel not in CHANNELS:
        raise NotFoundError("unknown callback channel")
    address = request.client.host if request.client else "unknown"
    if not request.app.state.callback_limiter.allow(address, limit=300):
        return Response(status_code=429)
    collected = bytearray()
    async for chunk in request.stream():
        collected.extend(chunk)
        if len(collected) > request.app.state.settings.callback_max_body_bytes:
            raise ValidationFailedError("callback body is too large")
    body = bytes(collected)
    account = await _account(request, callback_key)
    # The path channel must match the resolved account's channel — a mismatched pairing
    # is a misrouted or forged callback, not a valid one.
    if account.channel != channel:
        raise NotFoundError("callback route not found")
    sns_message = None
    with tenant_scope(account.tenant_id), space_scope(account.space_id):
        if channel == "email":
            topic = (account.capabilities or {}).get("sns_topic_arn")
            binding = (
                request.app.state.settings.sns_topic_bindings.get(topic)
                if isinstance(topic, str)
                else None
            )
            allowed = (
                [topic]
                if (
                    isinstance(topic, str)
                    and binding is not None
                    and binding.tenant_id == account.tenant_id
                    and binding.space_id == account.space_id
                )
                else []
            )
            sns_message = await verify_sns(
                body,
                allowed_topics=allowed,
                load_certificate=getattr(request.app.state, "sns_certificate_loader", certificate),
            )
        else:
            signature = request.headers.get(
                "x-twilio-signature" if channel == "sms" else "x-hub-signature-256", ""
            )
            secret = request.app.state.secret_resolver(account.callback_secret_ref)
            origin = request.app.state.settings.callback_public_origin
            if channel == "sms" and not origin:
                raise PermissionDeniedError("public callback origin is not configured")
            url = origin.rstrip("/") + request.url.path if origin else str(request.url)
            if origin and request.url.query:
                url += "?" + request.url.query
            form_params: dict[str, list[str]] = {}
            if channel == "sms":
                try:
                    form = body.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise PermissionDeniedError("invalid callback encoding") from exc
                for name, value in parse_qsl(form, keep_blank_values=True):
                    form_params.setdefault(name, []).append(value)
            verify_callback(
                channel,
                body=body,
                secret=secret,
                signature=signature,
                url=url,
                form_params=form_params,
            )
    body_msg_id, body_event_type, body_ext_key = extract_callback_metadata(channel, body)
    facts = extract_callback_facts(channel, body)
    attempt_key = facts[0].attempt_key if len(facts) == 1 else None
    if channel == "sms":
        # Twilio's native URL signature covers this query reference.
        values = request.query_params.getlist("attempt_key")
        attempt_key = valid_attempt_key(values[0]) if len(values) == 1 else None
    # Provider signatures authenticate the envelope, not caller-supplied metadata
    # headers. Never let unsigned headers redirect a receipt or defeat deduplication.
    external_key = (
        str(sns_message["MessageId"])
        if sns_message
        else (body_ext_key or hashlib.sha256(body).hexdigest())
    )
    provider_message_id = body_msg_id
    event_type = (body_event_type or "unknown")[:80]
    if sns_message and sns_message["Type"] != "Notification":
        event_type = "sns." + sns_message["Type"]
    key = request.app.state.data_key
    encrypted = AesGcmCipher(key).encrypt(
        body, nonce=os.urandom(12), associated_data=account.id.bytes
    )
    with tenant_scope(account.tenant_id), space_scope(account.space_id):
        async with request.app.state.session_factory() as db:
            event_id = uuid7()
            db.add(
                ProviderEvent(
                    id=event_id,
                    tenant_id=account.tenant_id,
                    provider_account_id=account.id,
                    external_event_key=external_key[:255],
                    attempt_key=attempt_key,
                    provider_message_id=provider_message_id,
                    event_type=event_type,
                    signature_verified=True,
                    provider_occurred_at=None,
                    received_at=utcnow(),
                    payload_ciphertext=encrypted,
                    payload_sha256=hashlib.sha256(body).digest(),
                    encryption_key_ref=request.app.state.settings.data_encryption_key_ref,
                    delivery_id=None,
                    processing_status="processed"
                    if event_type == "sns.UnsubscribeConfirmation"
                    else "pending",
                    processed_at=utcnow() if event_type == "sns.UnsubscribeConfirmation" else None,
                    processing_error=None,
                )
            )
            try:
                await db.flush()
                if event_type == "sns.SubscriptionConfirmation":
                    db.add(
                        NotificationJob(
                            id=uuid7(),
                            tenant_id=account.tenant_id,
                            request_key=hashlib.sha256(
                                f"sns:{account.id}:{external_key}".encode()
                            ).digest(),
                            kind="sns.confirm",
                            target_id=event_id,
                            actor_user_id=None,
                        )
                    )
                await db.commit()
            except IntegrityError:
                await db.rollback()
                duplicate = await db.scalar(
                    select(ProviderEvent.id).where(
                        ProviderEvent.provider_account_id == account.id,
                        ProviderEvent.external_event_key == external_key[:255],
                    )
                )
                if duplicate is None:
                    raise
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/whatsapp/{callback_key}", response_class=PlainTextResponse)
async def meta_challenge(callback_key: str, request: Request) -> Response:
    """Public provider onboarding only: verify the owner-bound challenge token."""
    address = request.client.host if request.client else "unknown"
    if not request.app.state.callback_limiter.allow(address, limit=300):
        return Response(status_code=429)
    account = await _account(request, callback_key)
    params = request.query_params
    if account.channel != "whatsapp" or params.get("hub.mode") != "subscribe":
        raise PermissionDeniedError("invalid provider verification challenge")
    with tenant_scope(account.tenant_id), space_scope(account.space_id):
        ref = (account.capabilities or {}).get("verification_token_ref")
        secret = request.app.state.secret_resolver(ref)
    value = params.get("hub.verify_token", "").encode()
    challenge = params.get("hub.challenge", "")
    if not hmac.compare_digest(value, secret) or not challenge or len(challenge) > 256:
        raise PermissionDeniedError("invalid provider verification challenge")
    return PlainTextResponse(challenge)
