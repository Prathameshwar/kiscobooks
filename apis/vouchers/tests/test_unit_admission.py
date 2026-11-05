"""Native unit admission rejects independently active but incompatible masters."""

import datetime as dt
from types import SimpleNamespace

import pytest
import pytest_asyncio
from billing_platform.db import create_engine, tenant_scope
from billing_platform.db.session import create_session_factory
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy import delete, select

from vouchers.domain.unit_admission import admit_quantity, admit_role
from vouchers.models.core import VoucherMasterEvidence
from vouchers.models.unit_sources import VoucherItemUnitProjection
from vouchers.schemas.documents import VoucherInput
from vouchers.schemas.sources import ItemUnitFacts, UnitMasterFacts
from vouchers.tasks.documents import validate_masters


@pytest_asyncio.fixture
async def admission():
    tenant, company, item, unit, mass = [uuid7() for _ in range(5)]
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (VoucherMasterEvidence.__table__, VoucherItemUnitProjection.__table__):
            await connection.run_sync(table.create)
    factory = create_session_factory(engine)
    current = SimpleNamespace(
        context=SimpleNamespace(
            company_id=company,
            base_currency="INR",
            features=frozenset(),
            allowed_currencies=frozenset(),
        )
    )
    with tenant_scope(tenant):
        async with factory.begin() as db:
            for entity, identity, data in [
                ("item", item, {"base_unit_id": str(unit)}),
                (
                    "unit",
                    unit,
                    {"dimension": "COUNT", "decimal_places": 0, "quantity_increment": "1"},
                ),
                (
                    "unit",
                    mass,
                    {"dimension": "MASS", "decimal_places": 3, "quantity_increment": "0.001"},
                ),
                (
                    "item_transaction_policy",
                    item,
                    {
                        "kind": "GOODS",
                        "item_version": 1,
                        "inventory_mode": "NON_STOCK",
                        "sellable": True,
                        "purchasable": True,
                    },
                ),
            ]:
                db.add(
                    VoucherMasterEvidence(
                        tenant_id=tenant,
                        company_id=company,
                        owner="catalog",
                        entity_type=entity,
                        source_id=identity,
                        source_version=1,
                        status="ACTIVE",
                        facts=data,
                        content_hash="a" * 64,
                    )
                )
            facts = {
                "version": 1,
                "item_id": str(item),
                "unit_id": str(unit),
                "binding_id": str(uuid7()),
                "usage_role": "BASE",
                "conversion_mode": "FIXED",
                "numerator": "1",
                "denominator": "1",
                "quantity_decimal_places": 0,
                "quantity_increment": "1",
                "fractional_entry": False,
                "valid_from": "2026-01-01",
                "valid_to": None,
            }
            db.add(
                VoucherItemUnitProjection(
                    tenant_id=tenant,
                    company_id=company,
                    source_id=uuid7(),
                    item_id=item,
                    unit_id=unit,
                    valid_from=dt.date(2026, 1, 1),
                    valid_to=None,
                    source_version=1,
                    facts=facts,
                    content_hash="b" * 64,
                )
            )
        yield factory, current, item, unit, mass
    await engine.dispose()


def payload(item, unit, quantity="1", **changes):
    return VoucherInput.model_validate(
        {
            "type_revision_id": str(uuid7()),
            "document_date": "2026-10-31",
            "currency": "INR",
            "mode": "ITEMS",
            "lines": [
                {
                    "line_key": str(uuid7()),
                    "item": {
                        "item_id": str(item),
                        "item_version": 1,
                        "unit_id": str(unit),
                        "actual_quantity": quantity,
                        "billed_quantity": quantity,
                        **changes,
                    },
                }
            ],
        }
    )


@pytest.mark.parametrize("field", ["actual_quantity", "billed_quantity", "planned_quantity"])
async def test_whole_count_rejects_fraction_in_every_quantity(admission, field):
    factory, current, item, unit, _ = admission
    async with factory.begin() as db:
        with pytest.raises(ValidationFailedError, match="quantity"):
            await validate_masters(
                db, current, payload(item, unit, **{field: "1.5"}), capture=False, kind="SALES"
            )


async def test_active_unbound_unit_is_rejected(admission):
    factory, current, item, _, mass = admission
    async with factory.begin() as db:
        with pytest.raises(ConflictError, match="unit"):
            await validate_masters(db, current, payload(item, mass), capture=False, kind="SALES")


async def test_bound_whole_count_is_accepted(admission):
    factory, current, item, unit, _ = admission
    async with factory.begin() as db:
        await validate_masters(db, current, payload(item, unit, "2"), capture=False, kind="SALES")


@pytest.mark.parametrize("capture", [True, False])
async def test_missing_signed_revision_is_fail_closed(admission, capture):
    factory, current, item, unit, _ = admission
    async with factory.begin() as db:
        await db.execute(delete(VoucherItemUnitProjection))
        with pytest.raises(ConflictError, match="unit binding"):
            await validate_masters(db, current, payload(item, unit), capture=capture, kind="SALES")


async def test_company_unit_facts_cannot_validate_another_company(admission):
    factory, current, item, unit, _ = admission
    async with factory.begin() as db:
        row = await db.scalar(select(VoucherItemUnitProjection))
        db.add(
            VoucherItemUnitProjection(
                tenant_id=row.tenant_id,
                company_id=uuid7(),
                source_id=row.source_id,
                item_id=row.item_id,
                unit_id=row.unit_id,
                valid_from=row.valid_from,
                valid_to=row.valid_to,
                source_version=1,
                facts=row.facts,
                content_hash=row.content_hash,
            )
        )
        await db.delete(row)
        await db.flush()
        with pytest.raises(ConflictError, match="unit binding"):
            await validate_masters(db, current, payload(item, unit), capture=False, kind="SALES")


async def test_another_tenants_matching_ids_cannot_supply_unit_evidence(admission):
    factory, current, item, unit, _ = admission
    async with factory.begin() as db:
        row = await db.scalar(select(VoucherItemUnitProjection))
        data = {
            key: getattr(row, key)
            for key in (
                "company_id",
                "source_id",
                "item_id",
                "unit_id",
                "valid_from",
                "valid_to",
                "source_version",
                "facts",
                "content_hash",
            )
        }
        await db.delete(row)
    foreign_tenant = uuid7()
    with tenant_scope(foreign_tenant):
        async with factory.begin() as db:
            db.add(VoucherItemUnitProjection(tenant_id=foreign_tenant, **data))
    async with factory.begin() as db:
        with pytest.raises(ConflictError, match="unit binding"):
            await validate_masters(db, current, payload(item, unit), capture=False, kind="SALES")


@pytest.mark.parametrize("date,accepted", [("2026-10-30", True), ("2026-10-31", False)])
async def test_effective_interval_uses_inclusive_end_date(admission, date, accepted):
    factory, current, item, unit, _ = admission
    async with factory.begin() as db:
        row = await db.scalar(select(VoucherItemUnitProjection))
        row.valid_to = dt.date(2026, 10, 30)
        row.facts = row.facts | {"valid_to": "2026-10-30"}
        await db.flush()
        body = payload(item, unit).model_copy(update={"document_date": dt.date.fromisoformat(date)})
        if accepted:
            await validate_masters(db, current, body, capture=False, kind="SALES")
        else:
            with pytest.raises(ConflictError, match="unit binding"):
                await validate_masters(db, current, body, capture=False, kind="SALES")


async def test_sku_increment_narrows_master_quantity_grid(admission):
    factory, current, item, unit, _ = admission
    async with factory.begin() as db:
        row = await db.scalar(select(VoucherItemUnitProjection))
        row.facts = row.facts | {"quantity_increment": "5"}
        await db.flush()
        with pytest.raises(ValidationFailedError, match="quantity"):
            await validate_masters(
                db, current, payload(item, unit, "2"), capture=False, kind="SALES"
            )
        await validate_masters(db, current, payload(item, unit, "10"), capture=False, kind="SALES")


def test_fixed_dimension_and_usage_role_are_native_admission_rules():
    from decimal import Decimal

    selected = ItemUnitFacts(
        item_id=uuid7(),
        unit_id=uuid7(),
        binding_id=uuid7(),
        usage_role="PURCHASE",
        conversion_mode="FIXED",
        numerator="1",
        denominator="1",
        quantity_decimal_places=0,
        quantity_increment="1",
        fractional_entry=False,
        valid_from=dt.date(2026, 1, 1),
        valid_to=None,
    )
    mass = UnitMasterFacts(dimension="MASS", decimal_places=0, quantity_increment="1")
    count = UnitMasterFacts(dimension="COUNT", decimal_places=0, quantity_increment="1")
    with pytest.raises(ConflictError, match="dimension"):
        admit_quantity(Decimal("1"), selected, mass, selected, count)
    with pytest.raises(ConflictError, match="sales"):
        admit_role(selected, "SALES")
