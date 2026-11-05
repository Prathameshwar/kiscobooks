"""A new product's first opening is independent of other products' trading."""

import hashlib
import uuid
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import select
from voucher_execution.opening import OpeningCapture, OpeningUnitFact
from voucher_execution.stock import StockInput
from voucher_execution.transport import command_digest

from accounting.models.stock import StockCostPool
from accounting.models.stock_opening import StockOpeningControl
from accounting.tasks.stock_execution import _dispatch
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_stock_effects import Source, captured, source
from tests.test_stock_ledger import item, line
from tests.test_stock_opening_api import BASE, auth
from tests.test_stock_opening_cohorts import opening_fixture, settle_posting_delivery


async def test_capture_fields_follow_posting_authority_and_native_field_denies(client):
    from tests.test_ledger_api import LEDGER_PERMISSIONS, ledger_headers

    permissions = LEDGER_PERMISSIONS | {
        "accounting.stock.read",
        "accounting.stock.configure",
        "accounting.stock.post",
    }

    async def metadata(allowed, policies=()):
        response = await client.get(
            BASE + "/capture-fields",
            headers=ledger_headers(
                permissions=allowed,
                features={"inventory"},
                policies=list(policies),
            ),
        )
        assert response.status_code == 200, response.text
        return {field["key"]: field for field in response.json()["fields"]}

    full = await metadata(permissions)
    assert full["quantity"]["writable"]
    read = await metadata({"accounting.stock.read"})
    assert not read["quantity"]["writable"]
    denied = await metadata(
        permissions,
        [
            {
                "entity_type": "accounting.stock_movement",
                "field_key": "quantity",
                "access": "write",
                "effect": "deny",
                "scope_type": "company",
                "scope_id": str(COMPANY),
            }
        ],
    )
    assert not denied["quantity"]["writable"]


@pytest.mark.parametrize("serialized", [False, True])
@pytest.mark.parametrize("batched", [False, True])
async def test_first_product_opening_after_other_product_trades(client, app, batched, serialized):
    original, first, location, baseline_id, owner = await opening_fixture(client, app)

    async def post(request, product):
        result, _ = await _dispatch(
            app.state.session_factory,
            request,
            secret=SECRET.encode(),
            client=owner,
            source_client=Source(source(request, product, location)),
            enabled=True,
        )
        assert result.outcome == "COMMITTED", result
        await settle_posting_delivery(app, owner)
        return result

    async def finish(control_id):
        review = await client.get(BASE + f"/{control_id}/reconciliation", headers=auth())
        assert review.status_code == 200, review.text
        row = review.json()
        finalized = await client.post(
            BASE + f"/{control_id}/finalize",
            headers=auth(),
            json={
                "expected_version": row["expected_version"],
                "manifest_hash": row["manifest_hash"],
                "reason": "Finish automatically after the native opening completes",
            },
        )
        assert finalized.status_code == 200, finalized.text
        return finalized.json()

    await post(original, first)
    await finish(baseline_id)
    period_id, period_version = next(iter(original.period_versions.items()))
    trading = captured({"id": str(period_id), "row_version": period_version}, first, location)
    await post(trading, first)
    second = item()
    revision_id = uuid7()
    second = second.model_copy(
        update={
            "opening_units": (
                OpeningUnitFact(
                    item_id=second.item_id,
                    unit_id=second.base_unit_id,
                    revision_id=revision_id,
                    numerator=1,
                    denominator=1,
                    quantity_decimal_places=0,
                    quantity_increment="1",
                ),
            )
        }
    )
    entry = line(second, location, 25, received_value="2500").model_copy(
        update={
            "opening": OpeningCapture(
                source_key="simple-product-" + second.item_id.hex,
                entered_unit_id=second.base_unit_id,
                unit_revision_id=revision_id,
                entered_quantity="25",
                cost_mode="RATE",
                unit_cost="100",
                history_known=False,
            )
        }
    )
    second = second.model_copy(update={"serial_tracking": serialized})
    entries = [entry]
    if batched:
        from accounting.models.stock_tracking import StockLot
        from tests.test_stock_ledger import preparation_source, values

        second = second.model_copy(update={"lot_tracking": True})
        lots = [uuid7(), uuid7()]
        with tenant_scope(TENANT):
            async with app.state.session_factory.begin() as db:
                for index, identity in enumerate(lots):
                    db.add(
                        StockLot(
                            **(values() | {"id": identity}),
                            item_id=second.item_id,
                            code=f"BATCH-{index}",
                            normalized_code=f"batch-{index}",
                            namespace_key="COMPANY",
                            status="ACTIVE",
                            is_held=False,
                            source_facts=preparation_source(second),
                        )
                    )
        entries = [
            entry.model_copy(update={"lot_id": lots[0]}),
            entry.model_copy(
                update={
                    "line_id": uuid7(),
                    "lot_id": lots[1],
                    "quantity": Decimal("5"),
                    "received_value": Decimal("1000"),
                    "opening": entry.opening.model_copy(
                        update={
                            "source_key": "second-batch",
                            "entered_quantity": Decimal("5"),
                            "unit_cost": Decimal("200"),
                        }
                    ),
                }
            ),
        ]
    if serialized:
        from tests.test_stock_ledger import prepare_serial

        serial_entries = []
        with tenant_scope(TENANT):
            async with app.state.session_factory.begin() as db:
                for index, entry in enumerate(entries):
                    count = 2 if index == 0 else 1
                    unit_ids = tuple(uuid7() for _ in range(count))
                    for identity in unit_ids:
                        await prepare_serial(db, second, identity, entry.lot_id)
                    serial_entries.append(
                        entry.model_copy(
                            update={
                                "unit_ids": unit_ids,
                                "quantity": Decimal(count),
                                "received_value": Decimal(count) * entry.opening.unit_cost,
                                "opening": entry.opening.model_copy(
                                    update={"entered_quantity": Decimal(count)}
                                ),
                            }
                        )
                    )
        entries = serial_entries
    manifest = {
        "stock_date": "2026-04-01",
        "currency": "INR",
        "opening_mode": "COMBINED",
        "reason": "First opening entered with this product",
        "lines": [entry.model_dump(mode="json") for entry in entries],
    }
    headers = auth()
    created = await client.post(
        BASE + f"/products/{second.item_id}", headers=headers, json=manifest
    )
    assert created.status_code == 201, created.text
    replay = await client.post(BASE + f"/products/{second.item_id}", headers=headers, json=manifest)
    assert replay.status_code == 201 and replay.json()["id"] == created.json()["id"]
    assert replay.headers["Idempotency-Replayed"] == "true"
    control_id = created.json()["id"]
    stock = StockInput(
        action="OPENING",
        stock_date=manifest["stock_date"],
        currency="INR",
        opening_control_id=control_id,
        opening_mode="COMBINED",
        lines=tuple(entries),
        reason=manifest["reason"],
    )
    payload = original.source_payload | {
        "stock": stock.model_dump(mode="json"),
        "lines": [
            {
                "line_key": str(entry.line_id),
                "item": {
                    "item_id": str(second.item_id),
                    "item_version": second.item_version,
                    "unit_id": str(second.base_unit_id),
                    "actual_quantity": str(entry.quantity),
                    "billed_quantity": "0",
                },
            }
            for entry in entries
        ],
    }
    request = original.model_copy(
        update={
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "voucher_id": uuid7(),
            "revision_id": uuid7(),
            "source_payload": payload,
            "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
        }
    )
    if batched or serialized:
        from tests.test_stock_effects import authority

        request = request.model_copy(
            update={
                "authority": authority(
                    features=frozenset(
                        {"inventory"}
                        | ({"batch_tracking"} if batched else set())
                        | ({"serial_tracking"} if serialized else set())
                    )
                )
            }
        )
    request = request.model_copy(update={"request_hash": command_digest(request)})
    await post(request, second)
    assert (await finish(control_id))["status"] == "FINALIZED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            baseline = await db.get(StockOpeningControl, uuid.UUID(baseline_id))
            assert baseline.status == "FINALIZED" and baseline.item_id is None
            own = await db.get(StockOpeningControl, uuid.UUID(control_id))
            assert own.item_id == second.item_id and own.company_slot is None
            pool = (
                await db.scalars(
                    select(StockCostPool).where(
                        StockCostPool.company_id == COMPANY,
                        StockCostPool.item_id == second.item_id,
                    )
                )
            ).one()
            assert isinstance(pool.quantity, Decimal) and isinstance(pool.value, Decimal)
            assert pool.quantity == Decimal(
                ("3" if batched else "2") if serialized else ("30" if batched else "25")
            )
            assert pool.value == Decimal(
                ("400" if batched else "200") if serialized else ("3500" if batched else "2500")
            )
            if batched:
                from accounting.models.stock import StockBalance, StockPosition

                rows = (
                    await db.execute(
                        select(StockPosition.lot_id, StockBalance.quantity)
                        .join(StockBalance, StockBalance.position_id == StockPosition.id)
                        .where(StockPosition.item_id == second.item_id)
                    )
                ).all()
                assert dict(rows) == {
                    lots[0]: Decimal("2" if serialized else "25"),
                    lots[1]: Decimal("1" if serialized else "5"),
                }
    assert (
        await client.post(BASE + f"/products/{second.item_id}", headers=auth(), json=manifest)
    ).status_code == 409
    from billing_platform.db.platform_models import Outbox
    from sqlalchemy import func

    from accounting.models.fiscal import FiscalPeriod

    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            period = await db.scalar(
                select(FiscalPeriod).where(
                    FiscalPeriod.company_id == COMPANY,
                    FiscalPeriod.start_date <= own.books_begin_date,
                    FiscalPeriod.end_date >= own.books_begin_date,
                )
            )
            period.status = "CLOSED"
        async with app.state.session_factory() as db:
            before = {
                model: await db.scalar(select(func.count(model.id)))
                for model in (StockOpeningControl, Outbox)
            }
    third = uuid7()
    closed = await client.post(
        BASE + f"/products/{third}",
        headers=auth(),
        json=manifest
        | {
            "lines": [manifest["lines"][0] | {"item_id": str(third)}],
        },
    )
    assert closed.status_code == 409 and "period" in closed.text.lower(), closed.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            for model, count in before.items():
                assert await db.scalar(select(func.count(model.id))) == count
