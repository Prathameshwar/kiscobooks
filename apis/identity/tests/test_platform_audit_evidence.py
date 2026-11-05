import uuid

from billing_platform.db import tenant_scope
from sqlalchemy import select

from identity.api.auth import Actor
from identity.events.audit_contract import AUDIT_EVENT_TYPES
from identity.models import Outbox
from identity.services.account_review import import_page
from identity.services.audit import record
from tests.test_account_review_domain import applicant


def test_setup_completion_is_selected_for_delivery():
    assert "platform.setup_completed" in AUDIT_EVENT_TYPES


async def test_platform_decision_keeps_safe_facts_without_personal_values(session, tenant_a):
    current = Actor(tenant_a, uuid.uuid4())
    command = uuid.uuid4()
    with tenant_scope(tenant_a):
        row = record(
            session,
            current,
            action="platform.account_decision_requested",
            entity="account_review",
            entity_id=uuid.uuid4(),
            reason="Private applicant details",
            changes={
                "action": "approve",
                "attested": True,
                "command_id": str(command),
                "email": "private@example.invalid",
            },
        )
    assert row.payload["changes"]["action"] == "approve"
    assert row.payload["changes"]["attested"] is True
    assert row.payload["changes"]["command_id"] == str(command)
    assert "private" not in str(row.payload).lower()


async def test_account_import_and_drift_emit_once_per_change(session, tenant_a):
    current = Actor(tenant_a, uuid.uuid4())
    observed = applicant()
    with tenant_scope(tenant_a):
        await import_page(session, current, [observed])
        await import_page(session, current, [observed])
        events = list(await session.scalars(select(Outbox)))
        assert len(events) == 1
        assert events[0].event_type == "platform.account_imported"
        from dataclasses import replace

        await import_page(session, current, [replace(observed, email="changed@example.invalid")])
        events = list(await session.scalars(select(Outbox)))
        assert [row.event_type for row in events] == [
            "platform.account_imported",
            "platform.account_drift_detected",
        ]
        assert "@" not in str([row.payload for row in events])
