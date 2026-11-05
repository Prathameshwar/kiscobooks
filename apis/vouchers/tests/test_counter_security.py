"""Drawer authority is separate from document authority and bound to a counter."""

import uuid

from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, headers
from sqlalchemy import select

from vouchers.events.audit_contract import AUDIT_EVENTS
from vouchers.models.counter import CounterOperator


async def test_counter_operator_assignment_and_private_drawer(client, prefix, app):
    cashier, stranger = uuid7(), uuid7()
    outlet = await client.post(
        prefix + "/counter-outlets", headers=headers(),
        json={"code": "SECURITY_OUTLET", "name": "Security outlet"},
    )
    assert outlet.status_code == 201, outlet.text
    counter = await client.post(
        prefix + "/checkout-counters", headers=headers(),
        json={"outlet_id": outlet.json()["id"], "code": "DRAWER", "name": "Drawer"},
    )
    assert counter.status_code == 201, counter.text
    counter_id = counter.json()["id"]
    operator = frozenset({"vouchers.counter.operate", "vouchers.counter.close"})
    opening = {"counter_id": counter_id, "currency": "INR", "opening_cash": "100.0000"}
    assert (
        await client.post(
            prefix + "/counter-sessions", json=opening,
            headers=headers(user=cashier, permissions=operator),
        )
    ).status_code == 403
    assigned = await client.post(
        prefix + f"/checkout-counters/{counter_id}/operators", headers=headers(),
        json={"user_id": str(cashier)},
    )
    assert assigned.status_code == 201, assigned.text
    second = await client.post(
        prefix + "/checkout-counters", headers=headers(),
        json={"outlet_id": outlet.json()["id"], "code": "OTHER", "name": "Other drawer"},
    )
    assert second.status_code == 201, second.text
    assert (
        await client.post(
            prefix + "/counter-sessions",
            json=opening | {"counter_id": second.json()["id"]},
            headers=headers(user=cashier, permissions=operator),
        )
    ).status_code == 403
    assert (
        await client.post(
            prefix + "/counter-sessions", json=opening,
            headers=headers(user=cashier, permissions=frozenset({"vouchers.create"})),
        )
    ).status_code == 403
    opened = await client.post(
        prefix + "/counter-sessions", json=opening,
        headers=headers(user=cashier, permissions=operator),
    )
    assert opened.status_code == 201, opened.text
    path = prefix + f"/counter-sessions/{opened.json()['id']}"
    assert (
        await client.get(path, headers=headers(user=stranger, permissions=operator))
    ).status_code == 403
    assert (
        await client.get(path, headers=headers(user=cashier, permissions=operator))
    ).status_code == 200
    assert (
        await client.get(
            path, headers=headers(user=stranger, permissions=frozenset({"vouchers.read"}))
        )
    ).status_code == 403
    assert (
        await client.get(
            path, headers=headers(user=stranger, permissions=frozenset({"vouchers.counter.read"}))
        )
    ).status_code == 200
    another_operator = uuid7()
    assert (
        await client.post(
            prefix + f"/checkout-counters/{counter_id}/operators", headers=headers(),
            json={"user_id": str(another_operator)},
        )
    ).status_code == 201
    shared_key = str(uuid7())
    revoked = await client.put(
        prefix + f"/checkout-counters/{counter_id}/operators/{cashier}/status",
        headers=headers(key=shared_key),
        json={"expected_version": 1, "status": "INACTIVE", "reason": "Shift reassigned"},
    )
    assert revoked.status_code == 200, revoked.text
    wrong_replay = await client.put(
        prefix + f"/checkout-counters/{counter_id}/operators/{another_operator}/status",
        headers=headers(key=shared_key),
        json={"expected_version": 1, "status": "INACTIVE", "reason": "Shift reassigned"},
    )
    assert wrong_replay.status_code == 422
    assert wrong_replay.json()["error"]["code"] == "idempotency_key_reused"
    assert (
        await client.post(
            path + "/close", headers=headers(user=cashier, permissions=operator),
            json={"expected_version": 1, "counted_cash": "100.0000"},
        )
    ).status_code == 403
    supervisor = frozenset({"vouchers.counter.supervise", "vouchers.counter.close"})
    closed = await client.post(
        path + "/close", headers=headers(user=stranger, permissions=supervisor),
        json={"expected_version": 1, "counted_cash": "100.0000", "reason": "Operator revoked"},
    )
    assert closed.status_code == 200, closed.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            events = list(await db.scalars(select(Outbox)))
            second_assignment = await db.scalar(
                select(CounterOperator.status).where(
                    CounterOperator.company_id == COMPANY,
                    CounterOperator.counter_id == uuid.UUID(counter_id),
                    CounterOperator.user_id == another_operator,
                )
            )
    assert second_assignment == "ACTIVE"
    counter_events = [row for row in events if "counter" in row.event_type]
    assert counter_events
    assert all(row.event_type in AUDIT_EVENTS for row in counter_events)
    revoked_event = next(
        row for row in counter_events if row.event_type.endswith("operator.status")
    )
    assert revoked_event.payload["category"] == "security"
    assert revoked_event.payload["reason"] == "Shift reassigned"
    assert {
        row.payload["category"]
        for row in counter_events
        if row.event_type.startswith("vouchers.counter_session.")
    } == {"money"}
