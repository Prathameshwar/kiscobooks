"""Opening cohorts share positions while preserving exact origins and warehouse costs."""

import datetime as dt
import hashlib
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from voucher_execution.opening import OpeningCapture, OpeningUnitFact
from voucher_execution.stock import StockInput
from voucher_execution.transport import command_digest

from accounting.api.auth import delegated_access
from accounting.models.stock import StockCostPool, StockPosition, StockReceiptOrigin
from accounting.models.stock_opening import StockOpeningClaim
from accounting.tasks.stock_effects import apply
from accounting.tasks.stock_quote import simulate
from tests.conftest import COMPANY, SECRET, TENANT
from tests.test_ledger_api import journal_setup
from tests.test_stock_effects import captured, configure, intent, source
from tests.test_stock_ledger import item, line, warehouse
from tests.test_stock_opening_api import BASE, auth


async def settle_posting_delivery(app, owner):
    from accounting.tasks.posting_delivery import deliver

    class Terminal:
        async def terminal(self, tenant, company, operation_id, outcome, body):
            return await owner.terminal(
                tenant,
                company,
                operation_id=operation_id,
                outcome=outcome,
                reference=body.terminal_reference,
                posted_at=body.posted_at,
            )

    result = await deliver(app.state.session_factory, owner, stock_client=Terminal())
    assert result.deferred == 0


async def opening_fixture(
    client,
    app,
    method="FIFO",
    *,
    mode="COMBINED",
    existing_gl=False,
    tracking="NONE",
    expired=False,
):
    journal_body, period, owner = await journal_setup(client, app, zero_opening=not existing_gl)
    accounts = await configure(app, finalize_zero=False)
    journal_line_id = None
    if existing_gl:
        from accounting.models.ledger import JournalLine
        from tests.test_ledger_api import BASE as FINANCE
        from tests.test_ledger_api import ledger_headers
        from tests.test_openings_sources import post_source

        journal_body["lines"][0].update(
            account_id=str(accounts["inventory_account_id"]), amount="80.00"
        )
        journal_body["lines"][1].update(
            account_id=str(accounts["opening_offset_account_id"]), amount="80.00"
        )
        created_gl = await client.post(
            FINANCE + "/opening-batches",
            json={
                "posting_date": "2026-04-01",
                "description": "Imported inventory trial balance",
                "lines": journal_body["lines"],
            },
            headers=ledger_headers(),
        )
        assert created_gl.status_code == 201, created_gl.text
        posted_gl = await post_source(client, created_gl.json())
        assert posted_gl.status_code == 200, posted_gl.text
        await settle_posting_delivery(app, owner)
        with tenant_scope(TENANT):
            async with app.state.session_factory() as db:
                journal_line_id = await db.scalar(
                    select(JournalLine.id).where(
                        JournalLine.account_id == accounts["inventory_account_id"]
                    )
                )
    product, location = item(method=method), warehouse()
    batch = tracking in {"BATCH", "BATCH_SERIAL"}
    serial = tracking in {"SERIAL", "BATCH_SERIAL"}
    product = product.model_copy(
        update={
            "lot_tracking": batch,
            "serial_tracking": serial,
            "expiry_required": batch,
            "manufacture_date_required": batch,
        }
    )
    lot_id = uuid7() if batch else None
    serial_ids = [uuid7() for _ in range(5)] if serial else []
    if batch or serial:
        from accounting.models.stock import StockUnitPosition
        from accounting.models.stock_tracking import StockLot
        from tests.test_stock_ledger import preparation_source, prepare_serial, values

        with tenant_scope(TENANT):
            async with app.state.session_factory.begin() as db:
                if batch:
                    db.add(
                        StockLot(
                            **(values() | {"id": lot_id}),
                            item_id=product.item_id,
                            code="OPENING-BATCH",
                            normalized_code="opening-batch",
                            namespace_key="COMPANY",
                            manufactured_on=dt.date(2025, 11, 1),
                            expires_on=dt.date(2026, 3, 31) if expired else dt.date(2027, 12, 31),
                            status="ACTIVE",
                            is_held=False,
                            source_facts=preparation_source(product),
                        )
                    )
                    await db.flush()
                for identity in serial_ids:
                    await prepare_serial(db, product, identity, lot_id=lot_id)
                assert await db.scalar(select(func.count(StockUnitPosition.id))) == 0
    unit_revision = uuid7()
    unit = OpeningUnitFact(
        item_id=product.item_id,
        unit_id=product.base_unit_id,
        revision_id=unit_revision,
        numerator=1,
        denominator=1,
        quantity_increment=Decimal("1"),
        quantity_decimal_places=0,
    )
    product = product.model_copy(update={"opening_units": (unit,)})
    lines = tuple(
        line(
            product,
            location,
            quantity,
            received_value=str(amount),
            opening_journal_line_id=journal_line_id if mode == "LINKED_GL" else None,
            opening=OpeningCapture(
                source_key=key,
                entered_unit_id=product.base_unit_id,
                unit_revision_id=unit_revision,
                entered_quantity=Decimal(quantity),
                cost_mode="VALUE",
                history_known=known,
                received_on=dt.date(2025, 12, 1) if known else None,
            ),
        )
        for quantity, amount, key, known in ((2, 20, "older", True), (3, 60, "unknown", False))
    )
    if batch or serial:
        lines = tuple(
            entry.model_copy(
                update={
                    "lot_id": lot_id,
                    "unit_ids": tuple(serial_ids[:2] if index == 0 else serial_ids[2:]),
                }
            )
            for index, entry in enumerate(lines)
        )
    manifest = {
        "stock_date": "2026-04-01",
        "currency": "INR",
        "opening_mode": mode,
        "reason": "Reviewed migration cost cohorts",
        "lines": [entry.model_dump(mode="json") for entry in lines],
    }
    created = await client.post(BASE, json=manifest, headers=auth())
    assert created.status_code == 201, created.text
    control_id = created.json()["id"]
    body = StockInput(
        action="OPENING",
        stock_date=dt.date(2026, 4, 1),
        currency="INR",
        opening_mode=mode,
        opening_control_id=control_id,
        lines=lines,
        reason=manifest["reason"],
    )
    request = captured(period, product, location)
    payload = request.source_payload | {
        "stock": body.model_dump(mode="json"),
        "posting_date": "2026-04-01",
        "stock_date": "2026-04-01",
        "document_date": "2026-04-01",
        "lines": [
            {
                "line_key": str(entry.line_id),
                "item": {
                    "item_id": str(product.item_id),
                    "item_version": product.item_version,
                    "unit_id": str(product.base_unit_id),
                    "actual_quantity": format(entry.quantity, ".4f"),
                    "billed_quantity": "0",
                },
            }
            for entry in lines
        ],
    }
    evidence = {
        "kind": "STOCK_JOURNAL",
        "profile": "OPENING",
        "company_configuration_hash": request.company_configuration_hash,
        "policy": {"stock": {}},
    }
    digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    request = request.model_copy(
        update={
            "kind": "STOCK_JOURNAL",
            "profile": "OPENING",
            "stock_date": body.stock_date,
            "posting_date": body.stock_date,
            "source_payload": payload,
            "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
            "configuration_hash": digest,
            "configuration_evidence": evidence | {"digest": digest},
        }
    )
    if batch or serial:
        from tests.test_stock_effects import authority

        request = request.model_copy(
            update={
                "authority": authority(
                    features={"inventory"}
                    | ({"batch_tracking", "expiry_tracking"} if batch else set())
                    | ({"serial_tracking"} if serial else set())
                )
            }
        )
    request = request.model_copy(update={"request_hash": command_digest(request)})
    preview = await client.get(BASE + f"/{control_id}/accounting-preview", headers=auth())
    assert preview.status_code == 200, preview.text
    assert preview.json()["remaining_value"] == "80.0000"
    assert preview.json()["additional_gl_value"] == ("80.0000" if mode == "COMBINED" else "0.0000")
    assert len(preview.json()["entries"]) == (2 if mode == "COMBINED" else 0)
    return request, product, location, control_id, owner


@pytest.mark.parametrize("method", ["FIFO", "MOVING_AVERAGE"])
async def test_opening_quote_multiple_cohorts_preserves_dates_and_exact_native_claims(
    client, app, method
):
    request, product, location, control_id, _ = await opening_fixture(client, app, method)
    current = delegated_access(
        request.authority,
        SECRET.encode(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=request.actor_user_id,
    )
    facts = source(request, product, location)
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:

            async def quote():
                return await apply(db, current, request, await intent(db, request), facts)

            preview = await simulate(db, quote)
            assert await db.scalar(select(func.count(StockOpeningClaim.id))) == 0
            posted = await apply(db, current, request, await intent(db, request), facts)
            assert preview.semantic_hash == posted.semantic_hash
            assert await db.scalar(select(func.count(StockPosition.id))) == 1
            assert await db.scalar(select(func.count(StockOpeningClaim.id))) == 2
            origins = list(
                await db.scalars(
                    select(StockReceiptOrigin).order_by(StockReceiptOrigin.received_on)
                )
            )
            assert [(row.received_on, row.history_known) for row in origins] == [
                (dt.date(2025, 12, 1), True),
                (dt.date(2026, 4, 1), False),
            ]
            pool = await db.scalar(select(StockCostPool))
            assert pool.quantity == 5 and pool.value == 80
        with pytest.raises(ConflictError, match="absent or already posted"):
            async with app.state.session_factory.begin() as db:
                duplicate = request.model_copy(
                    update={
                        "execution_id": uuid7(),
                        "operation_id": uuid7(),
                        "voucher_id": uuid7(),
                        "revision_id": uuid7(),
                    }
                )
                duplicate = duplicate.model_copy(update={"request_hash": command_digest(duplicate)})
                await apply(
                    db,
                    current,
                    duplicate,
                    await intent(db, duplicate),
                    source(duplicate, product, location),
                )
    cohorts = await client.get(BASE + f"/{control_id}/cohorts", headers=auth())
    assert cohorts.status_code == 200, cohorts.text
    values = {row["source_key"]: row for row in cohorts.json()["items"]}
    assert values["older"]["received_on"] == "2025-12-01"
    assert values["unknown"]["received_on"] is None and not values["unknown"]["history_known"]


@pytest.mark.parametrize("method", ["FIFO", "MOVING_AVERAGE"])
async def test_native_opening_gl_finalize_replay_reopen_reverse_and_replace(client, app, method):
    from billing_platform.db.types import utcnow

    from accounting.models.ledger import Journal
    from accounting.tasks.stock_execution import _dispatch, dispatch
    from tests.test_stock_effects import Source, authority

    request, product, location, control_id, owner = await opening_fixture(client, app, method)
    location = location.model_copy(
        update={"allowed_operations": (*location.allowed_operations, "ADJUSTMENT")}
    )
    result, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    assert (
        await dispatch(
            app.state.session_factory,
            request,
            secret=SECRET.encode(),
            client=None,
            source_client=None,
            enabled=False,
        )
        == result
    )
    review = (await client.get(BASE + f"/{control_id}/reconciliation", headers=auth())).json()
    assert review["applied_cohorts"] == 2 and review["applied_value"] == "80.0000"
    assert "EXECUTION_UNCONFIRMED" in review["blockers"]
    await settle_posting_delivery(app, owner)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            journal = await db.scalar(select(Journal).where(Journal.status == "POSTED"))
            assert journal.total_debit == journal.total_credit == Decimal("80")

    async def transition(action, current, **extra):
        return await client.post(
            BASE + f"/{control_id}/{action}",
            json={
                "expected_version": current["expected_version"],
                "manifest_hash": current["manifest_hash"],
                "reason": "Reviewed native stock migration correction",
                **extra,
            },
            headers=auth(),
        )

    finalized = await transition("finalize", review)
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["status"] == "FINALIZED"
    stale = await transition("reopen", review)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "review_stale"
    reopened = await transition("reopen", finalized.json())
    assert reopened.status_code == 200, reopened.text
    assert (
        await transition(
            "replace",
            reopened.json(),
            manifest={
                "stock_date": "2026-04-01",
                "currency": "INR",
                "opening_mode": "COMBINED",
                "reason": "Cannot replace live opening claims",
                "lines": [],
            },
        )
    ).status_code == 409
    reverse = request.model_copy(
        update={
            "purpose": "REVERSE",
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "reversal_of_execution_id": request.execution_id,
            "correction_reason": "Audited reversal before replacement",
            "authority": authority(),
            "authority_expires_at": utcnow() + dt.timedelta(seconds=60),
        }
    )
    reverse = reverse.model_copy(update={"request_hash": command_digest(reverse)})
    reversed_result, _ = await _dispatch(
        app.state.session_factory,
        reverse,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(
            source(reverse, product, location).model_copy(update={"action": "REVERSE"})
        ),
        enabled=True,
    )
    assert reversed_result.outcome == "COMMITTED"
    await settle_posting_delivery(app, owner)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            pool = await db.scalar(select(StockCostPool))
            assert pool.quantity == pool.value == 0
    review = (await client.get(BASE + f"/{control_id}", headers=auth())).json()
    replaced = await transition(
        "replace",
        review,
        manifest={
            "stock_date": "2026-04-01",
            "currency": "INR",
            "opening_mode": "COMBINED",
            "reason": "Audited zero replacement",
            "lines": [],
        },
    )
    assert replaced.status_code == 200, replaced.text
    revisions = await client.get(BASE + f"/{control_id}/revisions?limit=1", headers=auth())
    assert revisions.status_code == 200 and revisions.json()["page"]["has_more"]
    revision = revisions.json()["items"][0]
    previous = await client.get(BASE + f"/{control_id}/revisions/{revision['id']}", headers=auth())
    assert previous.status_code == 200 and len(previous.json()["lines"]) == 2
    assert (await transition("finalize", replaced.json())).status_code == 200


async def test_linked_opening_consumes_imported_gl_without_second_asset_journal(client, app):
    from accounting.models.ledger import Journal
    from accounting.models.stock import StockOpeningBridge
    from accounting.tasks.stock_execution import _dispatch
    from tests.test_stock_effects import Source

    request, product, location, control_id, owner = await opening_fixture(
        client, app, mode="LINKED_GL", existing_gl=True
    )
    result, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert (
                await db.scalar(select(func.count(Journal.id)).where(Journal.status == "POSTED"))
                == 1
            )
            assert await db.scalar(select(func.sum(StockOpeningBridge.amount))) == Decimal("80")
    review = await client.get(BASE + f"/{control_id}/reconciliation", headers=auth())
    assert review.status_code == 200 and "GL_RECONCILIATION_FAILED" not in review.json()["blockers"]


async def test_combined_opening_refuses_existing_unclaimed_gl_and_rolls_back(client, app):
    from accounting.tasks.stock_execution import _dispatch
    from tests.test_stock_effects import Source

    request, product, location, _, owner = await opening_fixture(client, app, existing_gl=True)
    with pytest.raises(ConflictError, match="opening"):
        await _dispatch(
            app.state.session_factory,
            request,
            secret=SECRET.encode(),
            client=owner,
            source_client=Source(source(request, product, location)),
            enabled=True,
        )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockOpeningClaim.id))) == 0
            assert await db.scalar(select(func.count(StockPosition.id))) == 0


@pytest.mark.parametrize("tracking", ["BATCH", "SERIAL", "BATCH_SERIAL"])
async def test_prepared_identities_gain_stock_only_from_native_opening(client, app, tracking):
    from accounting.models.stock import StockUnitPosition
    from accounting.tasks.stock_execution import _dispatch
    from tests.test_stock_effects import Source

    request, product, location, _, owner = await opening_fixture(client, app, tracking=tracking)
    result, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockUnitPosition.id))) == (
                5 if product.serial_tracking else 0
            )
            pool = await db.scalar(select(StockCostPool))
            assert pool.quantity == 5 and pool.value == 80


async def test_expired_opening_batch_has_no_native_stock_or_cost_effect(client, app):
    from accounting.tasks.stock_execution import _dispatch
    from tests.test_stock_effects import Source

    request, product, location, _, owner = await opening_fixture(
        client, app, tracking="BATCH", expired=True
    )
    with pytest.raises(ConflictError, match="expired opening"):
        await _dispatch(
            app.state.session_factory,
            request,
            secret=SECRET.encode(),
            client=owner,
            source_client=Source(source(request, product, location)),
            enabled=True,
        )
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(StockOpeningClaim.id))) == 0
            assert await db.scalar(select(func.count(StockPosition.id))) == 0


@pytest.mark.parametrize("method,remaining_value", [("FIFO", 70), ("MOVING_AVERAGE", 64)])
async def test_normal_issue_consumes_imported_warehouse_cost_and_blocks_reopening(
    client, app, method, remaining_value
):
    from accounting.tasks.stock_execution import _dispatch
    from tests.test_stock_effects import Source

    request, product, location, control_id, owner = await opening_fixture(client, app, method)
    result, _ = await _dispatch(
        app.state.session_factory,
        request,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(request, product, location)),
        enabled=True,
    )
    assert result.outcome == "COMMITTED"
    await settle_posting_delivery(app, owner)
    review = (await client.get(BASE + f"/{control_id}", headers=auth())).json()
    finalized = await client.post(
        BASE + f"/{control_id}/finalize",
        json={
            "expected_version": review["expected_version"],
            "manifest_hash": review["manifest_hash"],
            "reason": "Finalize before ordinary physical trading",
        },
        headers=auth(),
    )
    assert finalized.status_code == 200, finalized.text
    stock = StockInput(
        action="DISPATCH",
        stock_date=dt.date(2026, 4, 2),
        currency="INR",
        lines=(line(product, location, 1),),
        reason="Issue imported opening stock",
    )
    payload = request.source_payload | {
        "stock": stock.model_dump(mode="json"),
        "document_date": "2026-04-02",
        "posting_date": "2026-04-02",
        "stock_date": "2026-04-02",
        "lines": [
            {
                "line_key": str(stock.lines[0].line_id),
                "item": {
                    "item_id": str(product.item_id),
                    "item_version": product.item_version,
                    "unit_id": str(product.base_unit_id),
                    "actual_quantity": "1",
                    "billed_quantity": "0",
                },
            }
        ],
    }
    evidence = {
        "kind": "DELIVERY_NOTE",
        "profile": "STANDARD",
        "company_configuration_hash": request.company_configuration_hash,
        "policy": {"stock": {}},
    }
    digest = hashlib.sha256(canonical_json(evidence)).hexdigest()
    issue = request.model_copy(
        update={
            "voucher_id": uuid7(),
            "revision_id": uuid7(),
            "operation_id": uuid7(),
            "execution_id": uuid7(),
            "kind": "DELIVERY_NOTE",
            "profile": "STANDARD",
            "stock_date": stock.stock_date,
            "posting_date": stock.stock_date,
            "source_payload": payload,
            "content_hash": hashlib.sha256(canonical_json(payload)).hexdigest(),
            "configuration_hash": digest,
            "configuration_evidence": evidence | {"digest": digest},
        }
    )
    issue = issue.model_copy(update={"request_hash": command_digest(issue)})
    posted, _ = await _dispatch(
        app.state.session_factory,
        issue,
        secret=SECRET.encode(),
        client=owner,
        source_client=Source(source(issue, product, location)),
        enabled=True,
    )
    assert posted.outcome == "COMMITTED"
    await settle_posting_delivery(app, owner)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            pool = await db.scalar(select(StockCostPool))
            assert pool.quantity == 4 and pool.value == remaining_value
    blocked = await client.post(
        BASE + f"/{control_id}/reopen",
        json={
            "expected_version": finalized.json()["expected_version"],
            "manifest_hash": finalized.json()["manifest_hash"],
            "reason": "Attempt to invalidate later issue costs",
        },
        headers=auth(),
    )
    assert (
        blocked.status_code == 409
        and blocked.json()["error"]["code"] == "correction_has_dependencies"
    )
