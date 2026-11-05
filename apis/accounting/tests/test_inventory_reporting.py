import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from pydantic import ValidationError
from sqlalchemy import func, select

from accounting.models.inventory_reporting import InventoryReportRecord
from accounting.tasks import reporting_feed as feed
from accounting.tasks.inventory_reporting import publish
from tests.conftest import COMPANY, TENANT
from tests.test_fiscal_api import fiscal_setup


def item(identity):
    return {
        "payload": {
            "kind": "ITEM",
            "item_id": str(identity),
            "code": "SKU",
            "name": "Stock item",
            "unit": "PCS",
            "active": True,
            "lot_tracked": False,
            "serial_tracked": False,
        }
    }


async def test_inventory_handoff_is_typed_scoped_replay_safe_and_commit_bound(app, client):
    await fiscal_setup(client)
    identity, item_id = uuid.uuid4(), uuid.uuid4()
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            await publish(db, tenant=TENANT, company=COMPANY, records=[(identity, item(item_id))])
            await db.flush()
            await db.rollback()
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(InventoryReportRecord.id))) == 0
        async with app.state.session_factory() as db, db.begin():
            await publish(db, tenant=TENANT, company=COMPANY, records=[(identity, item(item_id))])
        async with app.state.session_factory() as db, db.begin():
            prior = await db.run_sync(lambda sync: feed.head(sync, COMPANY))
            await publish(db, tenant=TENANT, company=COMPANY, records=[(identity, item(item_id))])
        async with app.state.session_factory() as db:
            latest = await db.run_sync(lambda sync: feed.head(sync, COMPANY))
            assert latest.sequence == prior.sequence
            rows = list(await db.scalars(select(InventoryReportRecord)))
            assert len(rows) == 1
            wire = feed.fact(rows[0], "inventory_report_record", identity)
            assert wire.data["payload"]["item_id"] == str(item_id)
            assert latest.manifest["control"]["counts"]["inventory_report_record"] == 1
        with pytest.raises(ConflictError):
            async with app.state.session_factory() as db, db.begin():
                await publish(
                    db, tenant=uuid.uuid4(), company=COMPANY, records=[(identity, item(item_id))]
                )
        with pytest.raises(ValidationError):
            async with app.state.session_factory() as db, db.begin():
                await publish(
                    db,
                    tenant=TENANT,
                    company=COMPANY,
                    records=[(identity, {"payload": {"kind": "UNKNOWN"}})],
                )
    with tenant_scope(uuid.uuid4()):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(InventoryReportRecord.id))) == 0


async def test_inventory_handoff_duplicate_identity_and_unbounded_pages_are_refused(app, client):
    await fiscal_setup(client)
    identity = uuid.uuid4()
    with tenant_scope(TENANT):
        for page in (
            [(identity, item(identity))] * 2,
            [(uuid.uuid4(), item(identity)) for _ in range(201)],
        ):
            with pytest.raises(ConflictError):
                async with app.state.session_factory() as db, db.begin():
                    await publish(db, tenant=TENANT, company=COMPANY, records=page)


def test_inventory_schema_is_additive_and_rejects_float_and_unsupported_coverage():
    from reporting_contract.contract import LEGACY_SCHEMA_HASH, SCHEMA_HASH, Manifest
    from reporting_contract.inventory import InventoryRecord

    assert SCHEMA_HASH != LEGACY_SCHEMA_HASH
    assert Manifest.model_fields["schema_hash"].default == SCHEMA_HASH
    assert dt.date(2026, 4, 30).isoformat() == "2026-04-30"
    with pytest.raises(ValidationError):
        InventoryRecord.model_validate({"payload": {"kind": "ITEM", "quantity": 1.5}})


async def test_committed_stock_movement_handoff_cannot_be_rewritten_or_deleted(app, client):
    await fiscal_setup(client)
    identity = uuid.uuid4()
    payload = {
        "payload": {
            "kind": "MOVEMENT",
            "movement_id": str(identity),
            "item_id": str(uuid.uuid4()),
            "location_id": str(uuid.uuid4()),
            "position_id": str(uuid.uuid4()),
            "effective_date": "2026-04-01",
            "sequence": 1,
            "action": "RECEIPT",
            "voucher_id": str(uuid.uuid4()),
            "voucher_number": "R-1",
            "quantity_delta": "1",
            "value_delta": None,
        }
    }
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await publish(db, tenant=TENANT, company=COMPANY, records=[(identity, payload)])
        for remove in (False, True):
            with pytest.raises(ConflictError, match="immutable"):
                async with app.state.session_factory() as db, db.begin():
                    row = await db.get(InventoryReportRecord, identity)
                    if remove:
                        await db.delete(row)
                    else:
                        row.payload = row.payload | {"quantity_delta": "2"}
        async with app.state.session_factory() as db:
            row = await db.get(InventoryReportRecord, identity)
            assert row.payload["quantity_delta"] == "1"


async def test_position_cost_evidence_survives_owner_publication_and_feed(app, client):
    await fiscal_setup(client)
    identity, layer = uuid.uuid4(), uuid.uuid4()
    payload = {
        "kind": "POSITION",
        "position_id": str(identity),
        "item_id": str(uuid.uuid4()),
        "location_id": str(uuid.uuid4()),
        "owner": "OWN",
        "custody": "LOCAL",
        "disposition": "GOOD",
        "quantity": "2",
        "opening_quantity": "2",
        "inward_quantity": "0",
        "outward_quantity": "0",
        "reserved": "0",
        "carrying_value": "30",
        "costing_method": "FIFO",
        "valuation_detail": {
            "layers": [
                {
                    "layer_id": str(layer),
                    "receipt_date": "2026-04-01",
                    "quantity": "2",
                    "carrying_value": "30",
                }
            ]
        },
    }
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            await publish(
                db, tenant=TENANT, company=COMPANY, records=[(identity, {"payload": payload})]
            )
        async with app.state.session_factory() as db:
            row = await db.get(InventoryReportRecord, identity)
            wire = feed.fact(row, "inventory_report_record", identity)
            assert wire.data["payload"]["valuation_detail"]["layers"][0]["layer_id"] == str(layer)
        invalid = payload | {
            "valuation_detail": {
                "layers": [payload["valuation_detail"]["layers"][0] | {"carrying_value": "31"}]
            }
        }
        with pytest.raises(ValidationError, match="cost layers do not reconcile"):
            async with app.state.session_factory() as db, db.begin():
                await publish(
                    db, tenant=TENANT, company=COMPANY, records=[(identity, {"payload": invalid})]
                )
        async with app.state.session_factory() as db:
            row = await db.get(InventoryReportRecord, identity)
            assert row.payload["carrying_value"] == "30"
