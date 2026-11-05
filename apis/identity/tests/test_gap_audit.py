from __future__ import annotations

import ast
import datetime as dt
import uuid
from pathlib import Path

import pytest
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.delivery import OutgoingMessage, publish_batch
from billing_platform.errors import ConflictError
from billing_platform.outbox import emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.events.audit_contract import AUDIT_EVENT_TYPES
from identity.tasks.audit_outbox import delivery_status, retry_event
from identity.tasks.audit_publisher import PublisherSettings, configuration


def settings() -> PublisherSettings:
    return PublisherSettings.model_validate(
        {
            "IDENTITY_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "broker_url": "amqp://localhost/",
            "broker_user": "identity.publisher",
            "event_secret": "test-identity-event-key-at-least-32",
            "publish_after": utcnow() - dt.timedelta(hours=1),
            "maximum_attempts": 1,
        }
    )


def test_all_existing_audit_routes_are_explicitly_allowed() -> None:
    root = Path(__file__).resolve().parents[1] / "src/identity/api"
    emitted: set[str] = set()
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.keyword) and node.arg == "event_type":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    emitted.add(node.value.value)
    assert emitted - {"user_notification_preference.changed"} <= AUDIT_EVENT_TYPES
    assert "identity.catalog_context.changed" not in AUDIT_EVENT_TYPES
    config = configuration(settings())
    assert config.key.audience == "audit" and config.key.operations == AUDIT_EVENT_TYPES
    assert config.maximum_attempts == 1 and config.occurred_after is not None


async def test_cutoff_exhaustion_diagnostics_and_explicit_retry(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    config = settings()
    async with factory() as db, db.begin():
        rows = [
            emit(
                db,
                tenant_id=tenant_a,
                aggregate_id=uuid.uuid4(),
                aggregate_type="user",
                event_type=event,
                payload={"private": "must not appear in diagnostics"},
            )
            for event in ("user.updated", "user.updated", "identity.catalog_context.changed")
        ]
        rows[0].occurred_at = config.publish_after - dt.timedelta(days=1)
        historical, current = rows[0].message_id, rows[1].message_id
    sent: list[uuid.UUID] = []

    async def unavailable(outgoing: OutgoingMessage) -> bool:
        sent.append(outgoing.message_id)
        return False

    for _ in range(2):
        await publish_batch(
            factory,
            unavailable,
            event_types=AUDIT_EVENT_TYPES,
            maximum_attempts=1,
            occurred_after=config.publish_after,
        )
    assert sent == [current]
    async with factory() as db, db.begin():
        state = await delivery_status(db, config)
        assert state["pending"] == 2 and state["historical_held"] == 1
        assert state["exhausted"] == 1 and "private" not in str(state)
        with pytest.raises(ConflictError):
            await retry_event(db, config, historical)
        await retry_event(db, config, current)

    async def recovered(outgoing: OutgoingMessage) -> bool:
        assert outgoing.message_id == current
        return True

    result = await publish_batch(
        factory,
        recovered,
        event_types=AUDIT_EVENT_TYPES,
        maximum_attempts=1,
        occurred_after=config.publish_after,
    )
    assert result.confirmed == 1
    async with factory() as db:
        stored = await db.scalar(select(Outbox).where(Outbox.message_id == historical))
        assert stored is not None and stored.published_at is None


async def test_rollback_never_reaches_publication(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    async with factory() as db:
        emit(
            db,
            tenant_id=tenant_a,
            aggregate_id=uuid.uuid4(),
            aggregate_type="user",
            event_type="user.updated",
            payload={},
        )
        await db.flush()
        await db.rollback()

    async def never(outgoing: OutgoingMessage) -> bool:
        raise AssertionError("rolled-back event was published")

    result = await publish_batch(factory, never, event_types=AUDIT_EVENT_TYPES)
    assert result.confirmed == result.deferred == 0
