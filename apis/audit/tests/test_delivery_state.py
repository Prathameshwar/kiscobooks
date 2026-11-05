import json
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select

from tools import delivery_state


async def test_recovery_preserves_evidence_and_historical_cutoff(
    factory, engine, tenant_a, tmp_path, monkeypatch
):
    event = "catalog.item.update"
    key = "catalog.current"
    secret = uuid.uuid4().hex
    cutoff = utcnow() - timedelta(days=1)
    (tmp_path / "catalog.env").write_text(
        "\n".join(
            [
                "CATALOG_DATABASE_URL=sqlite+aiosqlite:///:memory:",
                "CATALOG_AUDIT_BROKER_URL=amqp://test.invalid",
                "CATALOG_AUDIT_BROKER_USER=test",
                "CATALOG_AUDIT_EVENT_KEY_ID=" + key,
                "CATALOG_AUDIT_EVENT_SECRET=" + secret,
                "CATALOG_AUDIT_PUBLISH_AFTER=" + cutoff.isoformat(),
            ]
        )
    )
    (tmp_path / "audit.env").write_text(
        "AUDIT_BROKER_URL=amqp://test.invalid\nAUDIT_SOURCE_CREDENTIALS="
        + json.dumps(
            {
                key: {
                    "issuer": "catalog",
                    "secret": secret,
                    "broker_user": "test",
                    "event_types": [event],
                }
            }
        )
    )
    monkeypatch.setattr(delivery_state, "create_engine", lambda _: engine)
    monkeypatch.setattr(type(engine), "dispose", AsyncMock())
    ids = []
    async with factory() as db, db.begin():
        for occurred in (utcnow(), cutoff - timedelta(days=1)):
            row = emit(
                db,
                tenant_id=tenant_a,
                aggregate_type="catalog.item",
                aggregate_id=uuid.uuid4(),
                event_type=event,
                payload=audit_payload(
                    action=event,
                    category="admin",
                    entity_type="catalog.item",
                    entity_id=uuid.uuid4(),
                    actor_user_id=None,
                    changes={"status": {"from": "DRAFT", "to": "ACTIVE"}},
                ),
                occurred_at=occurred,
            )
            row.attempt_count = 12
            ids.append(row.message_id)
    preview = await delivery_state.inventory("catalog", [event], tmp_path, True, {ids[0]}, False)
    assert preview["historical_held"] == 1 and preview["invalid"] == {}
    async with factory() as db:
        before = (await db.scalar(select(Outbox).where(Outbox.message_id == ids[0]))).payload
    with pytest.raises(ValueError):
        await delivery_state.inventory("catalog", [event], tmp_path, False, set(ids), True)
    await delivery_state.inventory("catalog", [event], tmp_path, False, {ids[0]}, True)
    async with factory() as db:
        current = await db.scalar(select(Outbox).where(Outbox.message_id == ids[0]))
        held = await db.scalar(select(Outbox).where(Outbox.message_id == ids[1]))
        assert (
            current.attempt_count == 0
            and current.payload == before
            and current.message_id == ids[0]
        )
        assert held.attempt_count == 12


def test_preflight_rejects_retained_private_fields():
    row = Outbox(
        event_type="catalog.item.update",
        payload={"changes": {"name": {"from": None, "to": "private"}}},
    )
    with pytest.raises(ValueError):
        delivery_state.evidence_valid(row, "catalog")


@pytest.mark.parametrize("source", ["catalog_source", "voucher_source", "report_source"])
def test_identity_discovery_preflight_accepts_counts_but_rejects_private_values(source):
    row = Outbox(
        event_type=source + ".discovery_read",
        payload={"changes": {"scope_count": {"to": 2}}},
    )
    delivery_state.evidence_valid(row, "identity")
    row.payload = {"changes": {"scope_count": {"to": 2}, "name": {"to": "private"}}}
    with pytest.raises(ValueError):
        delivery_state.evidence_valid(row, "identity")
    row.event_type = "company.setup_requested"
    row.payload = {"changes": {"scope_count": {"to": 2}}}
    with pytest.raises(ValueError):
        delivery_state.evidence_valid(row, "identity")
