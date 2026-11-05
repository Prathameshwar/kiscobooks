"""Read-only candidates require current native facts and all contributing fields."""

import datetime as dt
from decimal import Decimal

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.ids import uuid7

from accounting.api.auth import Access, delegated_access
from accounting.models.stock_tracking import StockUnit
from accounting.schemas.stock import StockAvailableUnitQuery, StockSelectionInput
from accounting.schemas.stock_tracking import SerialQuery
from accounting.stock_resources import SERIAL
from accounting.tasks.stock_candidates import available_units, selection
from accounting.tasks.stock_tracking import listing
from tests.conftest import COMPANY, SECRET, TENANT, USER
from tests.test_stock_effects import authority, source
from tests.test_stock_ledger import DAY, item, ledger, line, prepare_serial, warehouse


async def test_selection_is_scoped_non_reserving_and_fail_closed_on_field_denies(app):
    product, location = item(), warehouse()
    proof = authority()
    current = delegated_access(
        proof,
        SECRET.encode(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=USER,
    )

    class Source:
        calls = 0

        async def acquire(self, request):
            self.calls += 1
            assert request.purpose == "PREVIEW"
            return source(request, product, location).model_copy(update={"purpose": "PREVIEW"})

    owner = Source()
    body = StockSelectionInput(
        item_id=product.item_id,
        warehouse_id=location.warehouse_id,
        stock_date=DAY,
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            stock = await ledger(db)
            received = await stock.receive(
                line(product, location, 2),
                product,
                location,
                value=Decimal("10"),
            )
        result = await selection(app.state.session_factory, current, body, proof, owner)
        assert result.company_id == COMPANY and result.has_more is False
        assert len(result.items) == 1
        assert result.items[0].quantity == Decimal("2")
        assert result.items[0].position_id == received.position_id
        assert "value" not in result.items[0].model_dump()
        hidden = Access(
            current.actor,
            current.context.model_copy(
                update={
                    "policies": [
                        {
                            "entity_type": "accounting.stock_position",
                            "field_key": "quantity",
                            "access": "read",
                            "effect": "deny",
                            "scope_type": "company",
                            "scope_id": str(COMPANY),
                        }
                    ]
                }
            ),
        )
        with pytest.raises(PermissionDeniedError):
            await selection(app.state.session_factory, hidden, body, proof, owner)
        assert owner.calls == 1


async def test_available_serial_lookup_excludes_held_and_prepared_only_units_and_pages(app):
    product = item().model_copy(update={"serial_tracking": True})
    location = warehouse()
    proof = authority(extra_permissions={"accounting.serial.read"})
    current = delegated_access(
        proof,
        SECRET.encode(),
        tenant_id=TENANT,
        company_id=COMPANY,
        actor_user_id=USER,
    )

    class Source:
        async def acquire(self, request):
            return source(request, product, location).model_copy(update={"purpose": "PREVIEW"})

    first, second, held, prepared = [uuid7() for _ in range(4)]
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            for identity in (first, second, held, prepared):
                await prepare_serial(db, product, identity)
            owner = await ledger(db)
            receipt = await owner.receive(
                line(product, location, 3, unit_ids=(first, second, held)),
                product,
                location,
                value=Decimal("30"),
            )
            unit = await db.get(StockUnit, held)
            unit.is_held = True
        query = StockAvailableUnitQuery(position_id=receipt.position_id, stock_date=DAY, limit=1)
        page = await available_units(
            app.state.session_factory,
            current,
            query,
            proof,
            Source(),
            SECRET.encode(),
        )
        assert [row.id for row in page.items] == [first]
        assert page.items[0].identifiers[0].value == str(first)
        assert page.page.has_more and page.page.next_cursor
        following = await available_units(
            app.state.session_factory,
            current,
            query.model_copy(update={"cursor": page.page.next_cursor}),
            proof,
            Source(),
            SECRET.encode(),
        )
        assert [row.id for row in following.items] == [second]
        assert following.page.has_more is False
        denied = Access(
            current.actor,
            current.context.model_copy(
                update={
                    "policies": [
                        {
                            "entity_type": "accounting.stock_unit",
                            "field_key": "identifiers",
                            "access": "read",
                            "effect": "deny",
                            "scope_type": "company",
                            "scope_id": str(COMPANY),
                        }
                    ]
                }
            ),
        )
        with pytest.raises(PermissionDeniedError):
            await available_units(
                app.state.session_factory,
                denied,
                query,
                proof,
                Source(),
                SECRET.encode(),
            )


async def test_receipt_serial_choices_exclude_ever_received_units_and_held_records(app):
    product = item().model_copy(update={"serial_tracking": True})
    location = warehouse()
    proof = authority(extra_permissions={"accounting.serial.read"})
    current = delegated_access(
        proof, SECRET.encode(), tenant_id=TENANT, company_id=COMPANY, actor_user_id=USER
    )
    received, prepared, held = [uuid7() for _ in range(3)]
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            for identity in (received, prepared, held):
                await prepare_serial(db, product, identity)
            owner = await ledger(db)
            receipt = await owner.receive(
                line(product, location, 1, unit_ids=(received,)),
                product,
                location,
                value=Decimal("10"),
            )
            unit = await db.get(StockUnit, held)
            unit.is_held = True
        async with app.state.session_factory.begin() as db:
            page = await listing(
                db,
                current,
                SERIAL,
                SerialQuery(
                    item_id=product.item_id, status="ACTIVE", is_held=False, never_received=True
                ),
                SECRET.encode(),
            )
            assert [row.id for row in page.items] == [prepared]
            original = await listing(
                db,
                current,
                SERIAL,
                SerialQuery(item_id=product.item_id, source_movement_id=receipt.movement_id),
                SECRET.encode(),
            )
            assert [row.id for row in original.items] == [received]


async def test_selection_does_not_present_current_balances_as_backdated_availability(app):
    product, location = item(), warehouse()
    proof = authority()
    current = delegated_access(
        proof, SECRET.encode(), tenant_id=TENANT, company_id=COMPANY, actor_user_id=USER
    )

    class Source:
        async def acquire(self, request):
            return source(request, product, location).model_copy(update={"purpose": "PREVIEW"})

    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, day=DAY - dt.timedelta(days=1))
            await owner.receive(line(product, location, 2), product, location, value=Decimal("20"))
            owner = await ledger(db, "DISPATCH", day=DAY)
            await owner.issue(line(product, location, 1), product, location)
        with pytest.raises(ConflictError, match="later warehouse movements"):
            await selection(
                app.state.session_factory,
                current,
                StockSelectionInput(
                    item_id=product.item_id,
                    warehouse_id=location.warehouse_id,
                    stock_date=DAY - dt.timedelta(days=1),
                ),
                proof,
                Source(),
            )


async def test_receipt_selector_restores_fully_reversed_serial_without_allowing_issued_units(app):
    from accounting.models.stock import StockPosting
    from accounting.tasks.stock_reversal import guard, reverse_leg

    product = item().model_copy(update={"serial_tracking": True})
    location, corrected, issued = warehouse(), uuid7(), uuid7()
    proof = authority(extra_permissions={"accounting.serial.read"})
    current = delegated_access(
        proof, SECRET.encode(), tenant_id=TENANT, company_id=COMPANY, actor_user_id=USER
    )
    with tenant_scope(TENANT):
        async with app.state.session_factory.begin() as db:
            for identity in (issued, corrected):
                await prepare_serial(db, product, identity)
                owner = await ledger(db)
                await owner.receive(
                    line(product, location, 1, unit_ids=(identity,)),
                    product,
                    location,
                    value=Decimal("10"),
                )
                if identity == corrected:
                    original = owner.posting.id
        async with app.state.session_factory.begin() as db:
            owner = await ledger(db, "REVERSAL", reverses_id=original)
            for movement in await guard(owner, await db.get(StockPosting, original)):
                await reverse_leg(owner, movement, product, location)
            owner = await ledger(db, "DISPATCH")
            await owner.issue(line(product, location, 1, unit_ids=(issued,)), product, location)
        async with app.state.session_factory.begin() as db:
            choices = await listing(
                db,
                current,
                SERIAL,
                SerialQuery(item_id=product.item_id, receipt_eligible=True),
                SECRET.encode(),
            )
            assert [row.id for row in choices.items] == [corrected]
