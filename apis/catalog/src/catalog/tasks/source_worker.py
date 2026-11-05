"""Durable event capture precedes snapshot bootstrap; expired leases fail closed.

Run python -m catalog.tasks.source_worker separately from the HTTP process.
Credentials and either explicit subscriptions or enrolled-company discovery are deployment data.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Self

from aio_pika.abc import AbstractQueue
from billing_platform.broker import (
    BrokerSource,
    confirmed_channel,
    declare_consumer_queue,
    receive_one,
)
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.service_auth import CompanyServiceScope as Subscription
from billing_platform.service_auth import ServiceKey
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.schemas.identity_source import IdentityChange
from catalog.tasks.identity_source import (
    IdentitySourceSettings,
    fetch_enrollments,
    fetch_identity_snapshot,
)
from catalog.tasks.projections import activate_snapshot, buffer_change

EVENT_TYPE = "identity.catalog_context.changed"
logger = logging.getLogger(__name__)


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CATALOG_", extra="ignore", hide_input_in_errors=True
    )
    database_url: str = Field(repr=False)
    identity_source: IdentitySourceSettings
    source_subscriptions: tuple[Subscription, ...] = Field(default=(), max_length=1000)
    source_discovery: bool = False
    source_broker_url: SecretStr
    source_broker_user: str = Field(min_length=1, max_length=200)
    source_event_secret: SecretStr = Field(min_length=32)
    source_event_key_id: str = Field(default="current", pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    source_exchange: str = Field(default="platform.sources", min_length=1, max_length=120)
    source_queue: str = Field(default="catalog.identity_context", min_length=1, max_length=120)
    source_dead_exchange: str = Field(
        default="platform.source_errors", min_length=1, max_length=120
    )
    source_refresh_seconds: int = Field(default=10, strict=True, ge=1, le=20)

    @model_validator(mode="after")
    def configured_enrollment(self) -> Self:
        if not self.source_subscriptions and not self.source_discovery:
            raise ValueError("Catalog source requires explicit subscriptions or discovery")
        return self


@dataclass
class EnrollmentRegistry:
    scopes: tuple[Subscription, ...] = ()

    @property
    def tenants(self) -> frozenset[uuid.UUID]:
        return frozenset(scope.tenant_id for scope in self.scopes)


async def handle_change(
    db: AsyncSession,
    envelope: MessageEnvelope,
    *,
    allowed_tenants: frozenset[uuid.UUID],
    ignore_unenrolled: bool = False,
) -> None:
    if envelope.event_type != EVENT_TYPE or envelope.schema_version != 1:
        raise ValidationFailedError("source message is outside the configured subscription")
    change = IdentityChange.model_validate(envelope.payload)
    if change.tenant_id != envelope.tenant_id:
        raise ValidationFailedError("source payload and authenticated envelope scopes differ")
    if envelope.tenant_id not in allowed_tenants:
        if ignore_unenrolled:
            # This signed, schema-validated event grants no authority. A future
            # enrolled company's complete snapshot establishes its own barrier.
            return
        raise ValidationFailedError("source message is outside the configured subscription")
    try:
        await buffer_change(db, message_id=envelope.message_id, change=change)
    except ConflictError as exc:
        raise ValidationFailedError(
            "Identity source generation failed integrity verification"
        ) from exc


async def refresh_once(
    factory: async_sessionmaker[AsyncSession],
    settings: WorkerSettings,
    registry: EnrollmentRegistry | None = None,
    *,
    strict: bool = False,
    product_defaults_only: bool = False,
) -> None:
    subscriptions = settings.source_subscriptions
    if settings.source_discovery:
        try:
            discovered = await fetch_enrollments(settings.identity_source)
        except Exception as exc:
            if strict:
                raise
            logger.warning("Catalog enrollment discovery failed: %s", type(exc).__name__)
            return  # No complete current list: no company lease is extended.
        subscriptions = tuple(dict.fromkeys((*subscriptions, *discovered)))
    if registry is not None:
        registry.scopes = subscriptions
    semaphore = asyncio.Semaphore(4)

    async def renew(subscription: Subscription) -> None:
        async with semaphore:
            try:
                source = await fetch_identity_snapshot(
                    settings.identity_source,
                    tenant_id=subscription.tenant_id,
                    company_id=subscription.company_id,
                    request_id=uuid7(),
                )
                with tenant_scope(subscription.tenant_id):
                    async with factory.begin() as db:
                        await activate_snapshot(db, source)
                    # Fixed, bounded onboarding defaults use verified company facts.
                    # A seed failure must not roll back the independently valid source lease.
                    from catalog.tasks.company_configuration_defaults import (
                        ensure_configuration_defaults,
                    )
                    from catalog.tasks.company_pricing_defaults import ensure_pricing_defaults
                    from catalog.tasks.company_product_defaults import ensure_product_defaults
                    from catalog.tasks.tax_defaults import ensure_tax_defaults
                    from catalog.tasks.unit_defaults import ensure_unit_defaults
                    from catalog.tasks.warehouse_defaults import ensure_warehouse_defaults

                    default_provisioners = (
                        ensure_unit_defaults,
                        ensure_tax_defaults,
                        ensure_warehouse_defaults,
                        ensure_product_defaults,
                        ensure_pricing_defaults,
                        ensure_configuration_defaults,
                    )
                    provisioners = (
                        (ensure_product_defaults,)
                        if product_defaults_only
                        else default_provisioners
                    )
                    for provisioner in provisioners:
                        try:
                            async with factory.begin() as db:
                                defaults = await provisioner(db, subscription.company_id)
                                if defaults.status == "NEEDS_REVIEW":
                                    raise ConflictError("company starter defaults require review")
                        except Exception as exc:
                            if strict:
                                raise
                            # A failed unit/pack setup must not suppress tax setup,
                            # or undo the independently verified source lease.
                            logger.warning(
                                "Catalog %s failed: %s", provisioner.__name__, type(exc).__name__
                            )
            except Exception as exc:
                if strict:
                    raise
                # Source failures retain the prior lease. A defaults failure keeps the
                # verified snapshot and retries the independent provisioning transaction.
                logger.warning("Catalog source/default refresh failed: %s", type(exc).__name__)

    await asyncio.gather(*(renew(subscription) for subscription in subscriptions))


async def run_once(settings: WorkerSettings, *, product_defaults_only: bool = False) -> int:
    """Authenticated enrollment catch-up without starting a broker consumer."""
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    registry = EnrollmentRegistry(settings.source_subscriptions)
    try:
        await refresh_once(
            factory, settings, registry, strict=True, product_defaults_only=product_defaults_only
        )
        return len(registry.scopes)
    finally:
        await engine.dispose()


async def run(settings: WorkerSettings) -> None:
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine, guarded=True)
    registry = EnrollmentRegistry(settings.source_subscriptions)
    source = BrokerSource(
        ServiceKey(
            "identity",
            "catalog",
            frozenset({EVENT_TYPE}),
            settings.source_event_secret.get_secret_value().encode(),
        ),
        settings.source_broker_user,
    )

    async def handler(db: AsyncSession, envelope: MessageEnvelope) -> None:
        await handle_change(
            db,
            envelope,
            allowed_tenants=registry.tenants,
            ignore_unenrolled=settings.source_discovery,
        )

    try:
        while True:
            try:
                async with confirmed_channel(
                    settings.source_broker_url.get_secret_value()
                ) as channel:
                    queue = await declare_consumer_queue(
                        channel,
                        exchange_name=settings.source_exchange,
                        queue_name=settings.source_queue,
                        dead_letter_exchange=settings.source_dead_exchange,
                        routes=(EVENT_TYPE,),
                    )

                    async def consume(bound_queue: AbstractQueue = queue) -> None:
                        async with bound_queue.iterator() as messages:
                            async for message in messages:
                                await receive_one(
                                    factory,
                                    message,
                                    sources={settings.source_event_key_id: source},
                                    audience="catalog",
                                    consumer_name="catalog.identity_context.v1",
                                    handler=handler,
                                )

                    async def refresh() -> None:
                        while True:
                            await refresh_once(factory, settings, registry)
                            await asyncio.sleep(settings.source_refresh_seconds)

                    # The durable queue exists before any bootstrap request. Events
                    # can safely accumulate while the initial snapshot is obtained.
                    async with asyncio.TaskGroup() as tasks:
                        tasks.create_task(consume())
                        tasks.create_task(refresh())
            except Exception as exc:
                logger.warning("Catalog source worker retry: %s", type(exc).__name__)
                await asyncio.sleep(5)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--product-defaults-only", action="store_true")
    args = parser.parse_args()
    if args.product_defaults_only and not args.once:
        parser.error("--product-defaults-only requires --once")
    settings = WorkerSettings(_env_file=args.env_file)  # type: ignore[call-arg] # env file
    if args.once:
        count = asyncio.run(run_once(settings, product_defaults_only=args.product_defaults_only))
        logger.warning("Company default catch-up completed for %s enrolled companies", count)
    else:
        asyncio.run(run(settings))


__all__ = [
    "EVENT_TYPE",
    "Subscription",
    "WorkerSettings",
    "handle_change",
    "refresh_once",
    "run",
    "run_once",
]
