"""Counter cash accountability is optional, scoped and versioned."""

import uuid

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from conftest import COMPANY, TENANT, USER, headers
from test_foundation import create_type, draft
from test_money_capture import money, project

from vouchers.models import core as m


async def assign_cashier(client, prefix, counter_id):
    assigned = await client.post(
        prefix + f"/checkout-counters/{counter_id}/operators",
        headers=headers(), json={"user_id": str(USER)},
    )
    assert assigned.status_code == 201, assigned.text


async def test_two_counters_have_independent_sessions_and_reviewed_variance(client, prefix):
    outlet = await client.post(
        prefix + "/counter-outlets", headers=headers(),
        json={"code": "STORE_1", "name": "Main shop"},
    )
    assert outlet.status_code == 201, outlet.text
    outlet_id = outlet.json()["id"]
    counters = []
    for code in ("TILL_1", "TILL_2"):
        created = await client.post(
            prefix + "/checkout-counters", headers=headers(),
            json={"outlet_id": outlet_id, "code": code, "name": code},
        )
        assert created.status_code == 201, created.text
        counters.append(created.json()["id"])
        await assign_cashier(client, prefix, created.json()["id"])
    listed = await client.get(
        prefix + "/checkout-counters", headers=headers(), params={"outlet_id": outlet_id}
    )
    assert listed.status_code == 200, listed.text
    assert {row["id"] for row in listed.json()["items"]} == set(counters)
    sessions = []
    for counter_id in counters:
        opened = await client.post(
            prefix + "/counter-sessions", headers=headers(),
            json={"counter_id": counter_id, "currency": "INR", "opening_cash": "500.0000"},
        )
        assert opened.status_code == 201, opened.text
        sessions.append(opened.json())
    duplicate = await client.post(
        prefix + "/counter-sessions", headers=headers(),
        json={"counter_id": counters[0], "currency": "INR", "opening_cash": "100.0000"},
    )
    assert duplicate.status_code == 409
    active_counter = await client.put(
        prefix + f"/checkout-counters/{counters[0]}/status", headers=headers(),
        json={"expected_version": 1, "status": "INACTIVE", "reason": "Close till"},
    )
    assert active_counter.status_code == 409, active_counter.text
    assert sessions[0]["expected_cash"] == "500.0000"
    close = await client.post(
        prefix + f"/counter-sessions/{sessions[0]['id']}/close", headers=headers(),
        json={"expected_version": 1, "counted_cash": "500.0000"},
    )
    assert close.status_code == 200, close.text
    assert close.json()["variance"] == "0.0000"
    assert (
        await client.get(prefix + f"/counter-sessions/{sessions[1]['id']}", headers=headers())
    ).json()["status"] == "OPEN"
    variance_path = prefix + f"/counter-sessions/{sessions[1]['id']}/close"
    self_approved = await client.post(
        variance_path, headers=headers(),
        json={"expected_version": 1, "counted_cash": "499.0000",
              "reason": "Cashier found a one rupee shortage"},
    )
    assert self_approved.status_code == 403, self_approved.text
    reviewed = await client.post(
        variance_path, headers=headers(user=uuid7()),
        json={"expected_version": 1, "counted_cash": "499.0000",
              "reason": "Supervisor reviewed the one rupee shortage"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["variance"] == "-1.0000"
    inactive = await client.put(
        prefix + f"/checkout-counters/{counters[0]}/status", headers=headers(),
        json={"expected_version": 1, "status": "INACTIVE", "reason": "Till retired"},
    )
    assert inactive.status_code == 200, inactive.text
    unavailable = await client.post(
        prefix + "/counter-sessions", headers=headers(),
        json={"counter_id": counters[0], "currency": "INR", "opening_cash": "0"},
    )
    assert unavailable.status_code == 409, unavailable.text
    retired_outlet = await client.put(
        prefix + f"/counter-outlets/{outlet_id}/status", headers=headers(),
        json={"expected_version": 1, "status": "INACTIVE", "reason": "Shop closed"},
    )
    assert retired_outlet.status_code == 200, retired_outlet.text
    cannot_reactivate = await client.put(
        prefix + f"/checkout-counters/{counters[0]}/status", headers=headers(),
        json={"expected_version": 2, "status": "ACTIVE", "reason": "Reopen till"},
    )
    assert cannot_reactivate.status_code == 409, cannot_reactivate.text
    other_company = uuid7()
    cross = await client.get(
        f"/v1/companies/{other_company}/counter-sessions/{sessions[0]['id']}",
        headers=headers(company=other_company),
    )
    assert cross.status_code in {403, 404}


async def test_accounting_reversal_does_not_rewrite_drawer_cash(client, prefix, app):
    outlet = await client.post(
        prefix + "/counter-outlets", headers=headers(),
        json={"code": "REVERSAL_STORE", "name": "Reversal store"},
    )
    counter = await client.post(
        prefix + "/checkout-counters", headers=headers(),
        json={"outlet_id": outlet.json()["id"], "code": "TILL", "name": "Till"},
    )
    await assign_cashier(client, prefix, counter.json()["id"])
    opened = await client.post(
        prefix + "/counter-sessions", headers=headers(),
        json={"counter_id": counter.json()["id"], "currency": "INR",
              "opening_cash": "500.0000"},
    )
    shift_id = opened.json()["id"]
    kind = await create_type(
        client, prefix, kind="RECEIPT", code="COUNTER_RECEIPT",
        policy={"schema_version": 2, "counter": {"mode": "OPTIONAL", "session_required": True}},
    )
    financial = money() | {"purpose": "SETTLEMENT"}
    financial["tenders"] = [{
        "tender_key": str(uuid7()), "line_key": financial["accounts"][0]["line_key"],
        "mode": "CASH", "amount": "123.4500", "currency": "INR",
    }]
    await project(app, financial["accounts"])
    voucher, _ = await draft(
        client, prefix, kind["revision_id"], financial=financial,
        counter={"counter_id": counter.json()["id"], "session_id": shift_id},
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            for purpose in ("POST", "REVERSE"):
                db.add(m.VoucherOperation(
                    id=uuid7(), tenant_id=TENANT, company_id=COMPANY,
                    voucher_id=uuid.UUID(voucher["id"]),
                    revision_id=uuid.UUID(voucher["revision_id"]),
                    execution_id=uuid7(), purpose=purpose, status="COMMITTED",
                    content_hash="a" * 64, configuration_hash="a" * 64,
                    request_hash="a" * 64, command=None,
                ))
    # The physical collection remains until a separate refund or cash-out is posted.
    detail = await client.get(prefix + f"/counter-sessions/{shift_id}", headers=headers())
    assert detail.status_code == 200, detail.text
    assert detail.json()["expected_cash"] == "623.4500"


async def test_supervisor_can_approve_cashiers_counter_voucher(client, prefix):
    outlet = await client.post(
        prefix + "/counter-outlets", headers=headers(),
        json={"code": "SUPERVISED", "name": "Supervised store"},
    )
    counter = await client.post(
        prefix + "/checkout-counters", headers=headers(),
        json={"outlet_id": outlet.json()["id"], "code": "TILL", "name": "Till"},
    )
    await assign_cashier(client, prefix, counter.json()["id"])
    opened = await client.post(
        prefix + "/counter-sessions", headers=headers(),
        json={"counter_id": counter.json()["id"], "currency": "INR",
              "opening_cash": "0"},
    )
    configured = await create_type(
        client, prefix, kind="SALES", code="SUPERVISED_SALE",
        # A supervisor approves only where approval is required. A v2 type that omits the control
        # keeps the schema default (required, no self-approval), but this test says so explicitly.
        policy={
            "schema_version": 2,
            "approval_required": True,
            "counter": {"mode": "OPTIONAL", "session_required": True},
        },
    )
    voucher, _ = await draft(
        client, prefix, configured["revision_id"],
        counter={"counter_id": counter.json()["id"], "session_id": opened.json()["id"]},
    )
    filtered = await client.get(
        prefix + "/vouchers", headers=headers(),
        params={"counter_id": counter.json()["id"]},
    )
    assert filtered.status_code == 200, filtered.text
    assert [row["id"] for row in filtered.json()["items"]] == [voucher["id"]]
    path = prefix + f"/vouchers/{voucher['id']}"
    submitted = await client.post(
        path + "/submit", headers=headers(), json={"expected_version": 1},
    )
    assert submitted.status_code == 200, submitted.text
    approved = await client.post(
        path + "/approve", headers=headers(user=uuid7()),
        json={"expected_version": 2},
    )
    assert approved.status_code == 200, approved.text
