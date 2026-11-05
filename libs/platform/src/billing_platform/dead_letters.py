"""Bounded dead-letter inspection/replay preserving the authenticated original body."""

import uuid
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from pamqp.commands import Basic
from pydantic import ValidationError

from billing_platform.broker import BrokerSource, authenticated_envelope, confirmed_channel
from billing_platform.errors import AuthenticationRequiredError, ValidationFailedError
from billing_platform.publisher import PublisherConfig


class _OriginalRoute:
    def __init__(self, message: AbstractIncomingMessage) -> None:
        self.message = message

    def __getattr__(self, name: str) -> Any:
        return self.message.type if name == "routing_key" else getattr(self.message, name)


async def recover_dead_letters(
    config: PublisherConfig,
    queue_name: str,
    message_ids: list[uuid.UUID],
    *,
    apply: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if (
        not 1 <= limit <= 100
        or len(message_ids) > limit
        or len(set(message_ids)) != len(message_ids)
    ):
        raise ValueError("recovery is bounded to 100 distinct message IDs")
    if apply and not message_ids:
        raise ValueError("recovery requires explicit message IDs")
    if not queue_name or len(queue_name) > 120:
        raise ValueError("an explicit dead-letter queue is required")
    selected = {str(mid) for mid in message_ids}
    report: list[dict[str, Any]] = []
    async with confirmed_channel(config.broker_url) as channel:
        queue = await channel.declare_queue(queue_name, passive=True)
        exchange = await channel.get_exchange(config.exchange, ensure=True)
        # Messages are held unacked while scanning, then requeued when the channel closes.
        # This prevents repeatedly reading the same nonselected message at the queue head.
        held = []
        for _ in range(min(limit, queue.declaration_result.message_count or 0)):
            incoming = await queue.get(fail=False, timeout=5)
            if incoming is None:
                break
            held.append(incoming)
        try:
            ready = []
            for incoming in held:
                if incoming.type not in config.key.operations:
                    continue
                try:
                    safe_id = str(uuid.UUID(incoming.message_id or ""))
                except ValueError:
                    safe_id = None
                item: dict[str, Any] = {
                    "message_id": safe_id,
                    "event_type": incoming.type,
                    "verified": False,
                    "applied": False,
                }
                if selected and incoming.message_id not in selected:
                    continue
                # DLX rewrites routing_key; the original signed operation remains message.type.
                # Verify against the original operation using a read-only adapter.
                try:
                    authenticated_envelope(
                        _OriginalRoute(incoming),  # type: ignore[arg-type] # adapter restores the signed route after DLX
                        sources={config.key_id: BrokerSource(config.key, config.broker_user)},
                        audience=config.key.audience,
                    )
                except (AuthenticationRequiredError, ValidationFailedError, ValidationError):
                    if selected:
                        raise  # Explicit recovery remains all-or-nothing validation before publish.
                    report.append(item)
                    continue
                item["verified"] = True
                ready.append((incoming, item))
                report.append(item)
            if selected and {str(item["message_id"]) for item in report} != selected:
                raise ValueError(
                    "not every selected ID is in this bounded queue window and publisher"
                )
            if apply:
                for incoming, item in ready:
                    message = aio_pika.Message(
                        body=incoming.body,
                        headers=dict(incoming.headers),
                        message_id=incoming.message_id,
                        type=incoming.type,
                        content_type=incoming.content_type,
                        user_id=config.broker_user,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    )
                    confirmation = await exchange.publish(
                        message, routing_key=incoming.type or "", mandatory=True, timeout=5
                    )
                    if not isinstance(confirmation, Basic.Ack):
                        raise RuntimeError("dead-letter replay was not confirmed")
                    await incoming.ack()
                    item["applied"] = True
        finally:
            for incoming in held:
                if not incoming.processed:
                    await incoming.nack(requeue=True)
    return report
