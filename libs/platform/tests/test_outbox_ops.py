import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.outbox import emit
from billing_platform.outbox_ops import inventory, retry_selected

EVENTS = frozenset({"example.changed"})


async def test_health_inventory_excludes_held_history_and_never_loads_samples(factory, tenant_a):
    cutoff = utcnow() - timedelta(days=1)
    async with factory() as db, db.begin():
        row = emit(
            db,
            aggregate_type="example",
            aggregate_id=uuid.uuid4(),
            event_type="example.changed",
            tenant_id=tenant_a,
            payload={"private": "value"},
            occurred_at=cutoff - timedelta(days=1),
        )
        row.attempt_count = 12
    health = await inventory(factory, EVENTS, occurred_after=cutoff, sample_limit=0)
    assert health["pending"] == health["exhausted"] == 0
    assert health["sample"] == [] and health["oldest_age_seconds"] == 0


async def test_inventory_and_explicit_retry_preserve_evidence(factory, tenant_a):
    async with factory() as db, db.begin():
        row = emit(
            db,
            aggregate_type="example",
            aggregate_id=uuid.uuid4(),
            event_type="example.changed",
            tenant_id=tenant_a,
            payload={"original": True},
        )
        row.attempt_count = 12
        mid = row.message_id
    status = await inventory(factory, EVENTS)
    assert status["pending"] == status["exhausted"] == 1
    await retry_selected(factory, EVENTS, [mid])
    async with factory() as db:
        assert (await db.scalar(select(Outbox))).attempt_count == 12
    await retry_selected(factory, EVENTS, [mid], apply=True)
    async with factory() as db:
        restored = await db.scalar(select(Outbox))
        assert restored.attempt_count == 0
        assert restored.message_id == mid and restored.payload == {"original": True}
    with pytest.raises(ValueError):
        await retry_selected(factory, EVENTS, [mid, mid], apply=True)
    with pytest.raises(ValueError):
        await retry_selected(factory, frozenset({"other"}), [mid], apply=True)
