"""Public cutover declarations never post stock or silently enable trading."""

import uuid

from billing_platform.db import tenant_scope
from sqlalchemy import func, select

from accounting.models.stock import StockPosting
from accounting.models.stock_opening import StockOpeningControl
from tests.conftest import COMPANY, TENANT
from tests.test_ledger_api import LEDGER_PERMISSIONS, journal_setup, ledger_headers
from tests.test_stock_effects import configure

BASE = f"/v1/companies/{COMPANY}/stock/openings"


def auth(**changes):
    return ledger_headers(
        permissions=LEDGER_PERMISSIONS
        | {
            "accounting.stock.read",
            "accounting.stock.configure",
        },
        features={"inventory"},
        **changes,
    )


def manifest():
    return {
        "stock_date": "2026-04-01",
        "currency": "INR",
        "opening_mode": "COMBINED",
        "reason": "Reviewed empty stock at cutover",
        "lines": [],
    }


async def test_zero_stock_manifest_is_explicit_finalized_and_replayed(client, app):
    await journal_setup(client, app)
    await configure(app, finalize_zero=False)
    headers = auth()
    readiness = await client.get(BASE + "/readiness", headers=headers)
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["status"] == "NOT_STARTED"
    assert (await client.post(BASE, json=manifest())).status_code == 401
    created = await client.post(BASE, json=manifest(), headers=headers)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["status"] == "OPEN" and row["applied_cohorts"] == 0
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockPosting.id))) == 0
    body = {
        "expected_version": row["expected_version"],
        "manifest_hash": row["manifest_hash"],
        "reason": "Confirm no physical opening stock",
    }
    final_headers = auth()
    finished = await client.post(BASE + f"/{row['id']}/finalize", json=body, headers=final_headers)
    assert finished.status_code == 200, finished.text
    assert finished.json()["status"] == "FINALIZED"
    replay = await client.post(BASE + f"/{row['id']}/finalize", json=body, headers=final_headers)
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    assert (await client.post(BASE, json=manifest(), headers=auth())).status_code == 409


async def test_read_write_and_cost_field_permissions_are_independent(client, app):
    await journal_setup(client, app)
    await configure(app, finalize_zero=False)
    read = ledger_headers(permissions={"accounting.stock.read"}, features={"inventory"})
    assert (await client.get(BASE + "/readiness", headers=read)).status_code == 200
    assert (await client.post(BASE, json=manifest(), headers=read)).status_code == 403
    denied = auth(
        policies=[
            {
                "entity_type": "accounting.stock_movement",
                "field_key": "value",
                "access": "read",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )
    assert (await client.get(BASE + "/readiness", headers=denied)).status_code == 403
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockOpeningControl.id))) == 0


async def test_wrong_date_and_missing_cohorts_cannot_finalize(client, app):
    await journal_setup(client, app)
    await configure(app, finalize_zero=False)
    assert (
        await client.post(BASE, json=manifest() | {"stock_date": "2026-04-02"}, headers=auth())
    ).status_code == 409
    body = manifest()
    body["lines"] = [
        {
            "line_id": str(uuid.uuid4()),
            "item_id": str(uuid.uuid4()),
            "warehouse_id": str(uuid.uuid4()),
            "quantity": "2",
            "received_value": "10",
            "opening": {
                "source_key": "legacy-row-1",
                "entered_unit_id": str(uuid.uuid4()),
                "unit_revision_id": str(uuid.uuid4()),
                "entered_quantity": "2",
                "cost_mode": "VALUE",
                "history_known": False,
            },
        }
    ]
    created = await client.post(BASE, json=body, headers=auth())
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["missing_source_keys"] == ["legacy-row-1"]
    result = await client.post(
        BASE + f"/{row['id']}/finalize",
        json={
            "expected_version": row["expected_version"],
            "manifest_hash": row["manifest_hash"],
            "reason": "Attempt incomplete stock migration",
        },
        headers=auth(),
    )
    assert result.status_code == 409 and "OPENING_COHORTS_MISSING" in result.text


async def test_narrow_zero_permission_cannot_register_amounts_or_reopen(client, app):
    await journal_setup(client, app)
    await configure(app, finalize_zero=False)
    narrow = ledger_headers(
        permissions={"opening_balance.initialize_zero", "accounting.stock.read"},
        features={"inventory"},
    )
    ready = await client.get(BASE + "/readiness", headers=narrow)
    assert ready.status_code == 200, ready.text
    assert not ready.json()["can_start"]
    assert (await client.post(BASE, json=manifest(), headers=narrow)).status_code == 403
    zero = await client.post(
        BASE + "/confirm-zero",
        json={
            "expected_generation": ready.json()["expected_generation"],
            "reason": "Explicit company administrator no-stock declaration",
        },
        headers=narrow,
    )
    assert zero.status_code == 201, zero.text
    row = zero.json()
    assert row["status"] == "FINALIZED" and row["expected_value"] == "0.0000"
    assert (
        await client.post(
            BASE + f"/{row['id']}/reopen",
            json={
                "expected_version": row["expected_version"],
                "manifest_hash": row["manifest_hash"],
                "reason": "Attempt unauthorized opening correction",
            },
            headers=narrow,
        )
    ).status_code == 403


async def test_opening_revision_retains_replaced_manifest_and_current_scope(client, app):
    await journal_setup(client, app)
    await configure(app, finalize_zero=False)
    created = await client.post(BASE, json=manifest(), headers=auth())
    assert created.status_code == 201, created.text
    row = created.json()
    exporting = ledger_headers(
        permissions=LEDGER_PERMISSIONS | {"accounting.stock.read", "accounting.export.read"},
        features={"inventory"},
    )
    ticket = await client.get(BASE + f"/{row['id']}/export-ticket", headers=exporting)
    assert ticket.status_code == 200, ticket.text
    downloaded = await client.get(ticket.json()["download_path"], headers=exporting)
    assert downloaded.status_code == 200 and "carrying_value" in downloaded.text
    assert (
        await client.get(
            ticket.json()["download_path"],
            headers=ledger_headers(permissions={"accounting.stock.read"}, features={"inventory"}),
        )
    ).status_code == 403
    replacement = manifest() | {"reason": "Corrected migration source evidence"}
    changed = await client.post(
        BASE + f"/{row['id']}/replace",
        json={
            "expected_version": row["expected_version"],
            "manifest_hash": row["manifest_hash"],
            "reason": "Replace unused opening manifest",
            "manifest": replacement,
        },
        headers=auth(),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["manifest_hash"] != row["manifest_hash"]
    assert (await client.get(ticket.json()["download_path"], headers=exporting)).status_code == 422
    current = await client.get(BASE + f"/{row['id']}/manifest", headers=auth())
    assert current.status_code == 200 and current.json()["reason"] == replacement["reason"]
    with tenant_scope(TENANT):
        from accounting.models.stock_opening import StockOpeningRevision

        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockOpeningRevision.id))) == 2
    denied_capture = auth(
        policies=[
            {
                "entity_type": "accounting.stock_movement",
                "field_key": "opening",
                "effect": "deny",
                "access": "read",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ]
    )
    for suffix in ("", "/manifest", "/revisions", "/cohorts", "/reconciliation", "/export-ticket"):
        assert (
            await client.get(BASE + f"/{row['id']}" + suffix, headers=denied_capture)
        ).status_code == 403
