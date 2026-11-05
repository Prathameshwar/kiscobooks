"""Voucher events must reach Audit with the correct retention class."""

from pathlib import Path

from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.messages import MessageEnvelope
from conftest import TENANT, headers
from sqlalchemy import select
from test_foundation import create_type, draft

from vouchers.events.audit_contract import AUDIT_EVENTS


async def test_voucher_audit_routes_and_financial_retention(client, prefix, app, monkeypatch):
    kind = await create_type(client, prefix)
    voucher, _ = await draft(client, prefix, kind["revision_id"])
    submitted = await client.post(
        prefix + f'/vouchers/{voucher["id"]}/submit',
        json={"expected_version": 1},
        headers=headers(),
    )
    assert submitted.status_code == 200, submitted.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list(await db.scalars(select(Outbox)))
    assert rows
    assert all(row.event_type in AUDIT_EVENTS for row in rows)
    assert {
        row.payload["category"]
        for row in rows
        if row.event_type.startswith("vouchers.voucher.")
    } == {"money"}
    assert {
        row.payload["category"] for row in rows if row.event_type.startswith("vouchers.type.")
    } == {"admin"}
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "audit/src"))
    from audit.domain.source_contract import validate_source
    from audit.metadata import service_metadata
    from audit.models import AuditEvent
    from audit.tasks.consume import handle_event

    engine = create_engine("sqlite+aiosqlite:///:memory:")
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(service_metadata().create_all)
        with tenant_scope(TENANT):
            async with factory() as db, db.begin():
                for row in rows:
                    envelope = MessageEnvelope(
                        message_id=row.message_id,
                        tenant_id=row.tenant_id,
                        event_type=row.event_type,
                        schema_version=row.schema_version,
                        occurred_at=row.occurred_at,
                        payload=row.payload,
                    )
                    validate_source(envelope, "vouchers")
                    await handle_event(db, envelope, consumer_name="voucher-audit-contract")
            async with factory() as db:
                received = list(await db.scalars(select(AuditEvent)))
        assert len(received) == len(rows)
        assert {event.message_id for event in received} == {row.message_id for row in rows}
        assert all(event.company_id is not None for event in received)
        assert {
            event.category
            for event in received
            if event.entity_type == "vouchers.voucher"
        } == {"money"}
    finally:
        await engine.dispose()


def test_posting_operation_route_is_published():
    assert "vouchers.operation.create" in AUDIT_EVENTS
    assert "vouchers.operation.result" in AUDIT_EVENTS
