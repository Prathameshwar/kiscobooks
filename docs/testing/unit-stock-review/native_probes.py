"""Read-only review probes. All database work uses a disposable in-memory engine."""

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apis/vouchers/src"))

from billing_platform.db import create_engine, tenant_scope
from billing_platform.db.session import create_session_factory
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from catalog.schemas.product_authoring import BarcodeResolution
from catalog.schemas.effective_item import EffectiveUnit
from vouchers.models.core import VoucherMasterEvidence
from vouchers.models.unit_sources import VoucherItemUnitProjection
from vouchers.schemas.documents import VoucherInput
from vouchers.tasks.documents import validate_masters


async def main():
    tenant, company, item, count, mass = [uuid7() for _ in range(5)]
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(VoucherMasterEvidence.__table__.create)
        await connection.run_sync(VoucherItemUnitProjection.__table__.create)
    factory = create_session_factory(engine)
    current = SimpleNamespace(context=SimpleNamespace(
        company_id=company, base_currency="INR", features=frozenset(),
        allowed_currencies=frozenset(),
    ))
    result = {}
    with tenant_scope(tenant):
        async with factory.begin() as db:
            facts = [
                ("item", item, {"base_unit_id": str(count)}),
                ("unit", count, {"dimension": "COUNT", "decimal_places": 0,
                                 "quantity_increment": "1"}),
                ("unit", mass, {"dimension": "MASS", "decimal_places": 3,
                                "quantity_increment": "0.001"}),
                ("item_transaction_policy", item, {"kind": "GOODS", "item_version": 1,
                    "inventory_mode": "NON_STOCK", "sellable": True, "purchasable": True}),
            ]
            for entity, identity, data in facts:
                db.add(VoucherMasterEvidence(
                    tenant_id=tenant, company_id=company, owner="catalog",
                    entity_type=entity, source_id=identity, source_version=1,
                    status="ACTIVE", facts=data, content_hash="a" * 64,
                ))
            db.add(VoucherItemUnitProjection(
                tenant_id=tenant, company_id=company, source_id=uuid7(), source_version=1,
                item_id=item, unit_id=count,
                valid_from=dt.date(2020, 1, 1), valid_to=None, content_hash="b" * 64,
                facts={"version": 1, "binding_id": str(uuid7()), "item_id": str(item),
                       "unit_id": str(count), "usage_role": "BASE", "conversion_mode": "FIXED",
                       "valid_from": "2020-01-01", "valid_to": None,
                       "numerator": "1", "denominator": "1",
                       "quantity_decimal_places": 0, "quantity_increment": "1",
                       "fractional_entry": False},
            ))
        for label, selected, quantity in [
            ("whole_count_refuses_fraction", count, "1.5"),
            ("sku_refuses_unbound_mass_unit", mass, "1"),
        ]:
            body = VoucherInput.model_validate({
                "type_revision_id": str(uuid7()), "document_date": dt.date.today().isoformat(),
                "currency": "INR", "mode": "ITEMS", "lines": [{
                    "line_key": str(uuid7()), "item": {"item_id": str(item),
                        "item_version": 1, "unit_id": str(selected),
                        "actual_quantity": quantity, "billed_quantity": quantity},
                }],
            })
            try:
                async with factory.begin() as db:
                    await validate_masters(db, current, body, capture=False, kind="SALES")
            except (ConflictError, ValidationFailedError):
                result[label] = "PASS: refused by native pre-approval validation"
            else:
                raise AssertionError(label + " was accepted")
    await engine.dispose()
    barcode = BarcodeResolution(
        barcode_id=uuid7(), matched_value="REVIEW-PACK", item_id=item, item_version=1,
        sku="REVIEW", name="Review pack", unit_id=count, binding_id=uuid7(),
        unit_revision_id=uuid7(), usage_role="PACK", numerator=9007199254740993,
        denominator=9007199254740995,
    )
    wire = barcode.model_dump_json()
    (ROOT / ".test_artifacts/unit-stock-review-barcode-wire.json").write_text(wire, encoding="utf-8")
    result["barcode_ratio_wire_type"] = type(json.loads(wire)["numerator"]).__name__
    assert json.loads(wire)["numerator"] == "9007199254740993"
    effective = EffectiveUnit(
        binding_id=barcode.binding_id, revision_id=barcode.unit_revision_id,
        revision=1, unit_id=count, usage_role="PACK", valid_from=dt.date.today(),
        valid_to=None, conversion_mode="FIXED", numerator=barcode.numerator,
        denominator=barcode.denominator, nominal_ratio=None,
        quantity_decimal_places=0, quantity_increment="1", fractional_entry=False,
    )
    result["effective_unit_ratio_wire_type"] = type(
        json.loads(effective.model_dump_json())["numerator"]
    ).__name__
    assert json.loads(effective.model_dump_json())["denominator"] == "9007199254740995"
    (ROOT / ".test_artifacts/unit-stock-review-native-probes.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


asyncio.run(main())
