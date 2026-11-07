"""Durable Identity confirmation/abort delivery; never called inside a ledger transaction."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import time
import uuid
from typing import Literal

import httpx
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.delivery import OutgoingMessage, PublishResult, publish_batch
from billing_platform.messages import MessageEnvelope
from billing_platform.outbox_ops import inventory
from identity_posting import PostingClient, ReservationRejectedError
from identity_posting.stock import (
    StockPostingClient,
    StockReservationIntent,
    StockTerminalRequest,
    TrackingTerminalRequest,
    tracking_root,
)
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounting.config import Settings
from accounting.schemas.masters import Input

EVENT_TYPES = frozenset({"accounting.company_posting.confirm", "accounting.company_posting.abort"})
STOCK_EVENT_TYPES = frozenset(
    {"accounting.stock_posting.confirm", "accounting.stock_posting.abort"}
)
TRACKING_EVENT_TYPES = frozenset(
    {"accounting.tracking_feature.confirm", "accounting.tracking_feature.abort"}
)
LOG = logging.getLogger("accounting.posting_delivery")


def check_configuration(settings: Settings) -> None:
    if settings.identity_posting_url is None and settings.stock_identity_url is None:
        raise ValueError("first-use delivery requires a configured Identity connection")


class IntentPayload(Input):
    reference_kind: Literal["JOURNAL", "STOCK"] = "JOURNAL"
    company_id: uuid.UUID
    operation_id: uuid.UUID
    actor_user_id: uuid.UUID
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    features: list[str] = Field(max_length=32)
    posted_at: dt.datetime | None


class StockIntentPayload(IntentPayload):
    stock_execution_id: uuid.UUID


async def deliver_stock_terminal(
    client: StockPostingClient,
    tenant_id: uuid.UUID,
    payload: StockIntentPayload,
    outcome: Literal["confirmed", "aborted"],
    intent: StockReservationIntent,
) -> None:
    """Terminate a retained reservation before offering an abort fallback.

    An older reservation can have a narrower feature set than the now-correct
    accepted command. Identity already knows its immutable reservation; passing
    a newly reconstructed intent would make its request hash differ. Only a
    missing reservation needs the retained intent to seal an abort.
    """
    reference = (
        "accounting-stock:" if payload.reference_kind == "STOCK" else "accounting-journal:"
    ) + str(payload.operation_id)
    terminal = StockTerminalRequest(terminal_reference=reference, posted_at=payload.posted_at)
    try:
        await client.terminal(
            tenant_id, payload.company_id, payload.operation_id, outcome, terminal
        )
    except ReservationRejectedError as error:
        if outcome != "aborted" or error.status_code != 404:
            raise
        await client.terminal(
            tenant_id,
            payload.company_id,
            payload.operation_id,
            outcome,
            StockTerminalRequest(terminal_reference=reference, intent=intent),
        )


def connection(settings: Settings) -> tuple[httpx.AsyncClient, PostingClient] | None:
    if settings.identity_posting_url is None:
        return None
    assert settings.identity_posting_secret is not None
    assert settings.identity_posting_key_id is not None
    http = httpx.AsyncClient(base_url=settings.identity_posting_url)
    client = PostingClient(
        http,
        key_id=settings.identity_posting_key_id,
        request_secret=settings.identity_posting_secret.get_secret_value().encode(),
        response_keys={
            key: value.get_secret_value().encode()
            for key, value in settings.identity_posting_response_keys.items()
        },
        issuer="accounting",
    )
    return http, client


async def deliver(
    factory: async_sessionmaker[AsyncSession],
    client: PostingClient | None,
    *,
    limit: int = 20,
    stock_client: StockPostingClient | None = None,
) -> PublishResult:
    selected_events = (EVENT_TYPES if client is not None else frozenset()) | (
        STOCK_EVENT_TYPES | TRACKING_EVENT_TYPES if stock_client is not None else frozenset()
    )

    async def send(message: OutgoingMessage) -> bool:
        envelope = MessageEnvelope.model_validate_json(message.body)
        if (
            envelope.schema_version != 1
            or envelope.event_type != message.routing_key
            or envelope.event_type not in selected_events
        ):
            raise ValueError("unsupported company posting event")
        if envelope.event_type in TRACKING_EVENT_TYPES:
            assert stock_client is not None
            company_id = uuid.UUID(envelope.payload["company_id"])
            terminal = TrackingTerminalRequest.model_validate({
                key: value for key, value in envelope.payload.items() if key != "company_id"
            })
            tracking_outcome = (
                "confirmed" if envelope.event_type.endswith(".confirm") else "aborted"
            )
            if (terminal.committed_at is not None) != (tracking_outcome == "confirmed"):
                raise ValueError("tracking terminal evidence differs from its outcome")
            receipt = await stock_client.request(
                tracking_root(envelope.tenant_id, company_id)
                + f"/{terminal.intent.operation_id}/{tracking_outcome}",
                "tracking-" + tracking_outcome, terminal,
            )
            if (receipt.operation_id != terminal.intent.operation_id
                or receipt.status != tracking_outcome):
                raise ValueError("tracking terminal receipt differs")
            return True
        is_stock = envelope.event_type in STOCK_EVENT_TYPES
        payload = (
            StockIntentPayload.model_validate(envelope.payload)
            if is_stock
            else IntentPayload.model_validate(envelope.payload)
        )
        outcome: Literal["confirmed", "aborted"] = (
            "confirmed" if envelope.event_type.endswith(".confirm") else "aborted"
        )
        if outcome == "confirmed" and payload.posted_at is None:
            raise ValueError("posting confirmation requires its committed timestamp")
        if is_stock:
            from voucher_execution import ExecutionCommand

            from accounting.models.voucher_money import VoucherMoneyIntent
            from accounting.tasks.stock_identity import reservation_intent

            assert stock_client is not None and isinstance(payload, StockIntentPayload)
            with tenant_scope(envelope.tenant_id):
                async with factory() as db:
                    retained = await db.scalar(
                        select(VoucherMoneyIntent).where(
                            VoucherMoneyIntent.company_id == payload.company_id,
                            VoucherMoneyIntent.execution_id == payload.stock_execution_id,
                        )
                    )
                    if (
                        retained is None
                        or (retained.journal_id or retained.id) != payload.operation_id
                    ):
                        raise ValueError(
                            "stock terminal reference differs from retained native intent"
                        )
                    command = ExecutionCommand.model_validate(retained.command)
                    body = reservation_intent(
                        command,
                        operation_id=payload.operation_id,
                        actor_user_id=payload.actor_user_id,
                        configuration_hash=payload.configuration_hash,
                        features=payload.features,
                    )
            await deliver_stock_terminal(
                stock_client, envelope.tenant_id, payload, outcome, body
            )
            return True
        assert client is not None
        await client.terminal(
            envelope.tenant_id,
            payload.company_id,
            operation_id=payload.operation_id,
            outcome=outcome,
            reference=(
                "accounting-stock:" if payload.reference_kind == "STOCK" else "accounting-journal:"
            )
            + str(payload.operation_id),
            posted_at=payload.posted_at,
            intent={
                "operation_id": str(payload.operation_id),
                "actor_user_id": str(payload.actor_user_id),
                "configuration_hash": payload.configuration_hash,
                "features": payload.features,
            }
            if outcome == "aborted"
            else None,
        )
        return True

    return await publish_batch(
        factory,
        send,
        limit=limit,
        timeout_seconds=15,
        event_types=selected_events,
        # Financial confirmations must not become permanently silent after a
        # schema or network fault. Keep retrying at a bounded five-minute rate.
        maximum_attempts=None,
        retry_cap_seconds=300,
    )


async def run(settings: Settings, *, once: bool) -> None:
    configured = connection(settings)
    from accounting.tasks.stock_identity import connection as stock_connection

    configured_stock = stock_connection(settings)
    if configured is None and configured_stock is None:
        raise ValueError("Identity posting credentials are required")
    client = configured[1] if configured else None
    stock_client = configured_stock[1].client if configured_stock else None
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    last_backlog_check = 0.0
    try:
        while True:
            result = await deliver(factory, client, stock_client=stock_client)
            now = time.monotonic()
            if now - last_backlog_check >= 60:
                last_backlog_check = now
                routes = (EVENT_TYPES if client is not None else frozenset()) | (
                    STOCK_EVENT_TYPES | TRACKING_EVENT_TYPES
                    if stock_client is not None else frozenset()
                )
                status = await inventory(factory, routes, maximum_attempts=12, sample_limit=5)
                if status["pending"] and status["oldest_age_seconds"] >= 60:
                    LOG.error(
                        "posting confirmation backlog pending=%s aged_seconds=%s "
                        "attempts_12_or_more=%s sample=%s",
                        status["pending"],
                        status["oldest_age_seconds"],
                        status["exhausted"],
                        status["sample"],
                    )
            if once:
                return
            await asyncio.sleep(1 if result.confirmed else 5)
    finally:
        if configured:
            await configured[0].aclose()
        if configured_stock:
            await configured_stock[0].aclose()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--env-file")
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)  # type: ignore[call-arg] # BaseSettings loads environment-only required values from this file.
    check_configuration(settings)
    if not args.check_config:
        asyncio.run(run(settings, once=args.once))


if __name__ == "__main__":
    main()
