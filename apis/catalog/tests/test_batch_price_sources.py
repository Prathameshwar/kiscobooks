"""Batch prices must never inherit a different pack's product MRP."""

import datetime as dt
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7

from catalog.models.pricing import ItemMrp
from catalog.schemas.pricing import FormulaInput
from catalog.schemas.simple_product_creation import SimpleBatchInput
from catalog.tasks import pricing_schedule, pricing_validation


async def test_batch_schedule_does_not_consult_product_mrp(monkeypatch):
    seen = []

    async def history(access, model, *args, **kwargs):
        seen.append(model)
        return []

    monkeypatch.setattr(pricing_schedule, "history", history)
    monkeypatch.setattr(
        pricing_schedule, "row", AsyncMock(return_value=SimpleNamespace(valid_to=None))
    )
    body = SimpleNamespace(valid_from=dt.date.today(), valid_to=None, formula=None)
    series = SimpleNamespace(item_id=uuid7(), unit_revision_id=uuid7(), currency="INR")
    await pricing_schedule.coverage(
        None,
        body,
        series,
        sale=True,
        mrp_required=False,
        mrp_revision_id=series.unit_revision_id,
        jurisdiction="IN",
        batch_scope=True,
    )
    assert ItemMrp not in seen


async def test_batch_mrp_formula_uses_its_physical_declaration(monkeypatch):
    unit_id = uuid7()
    scope = SimpleNamespace(
        id=uuid7(),
        item_id=uuid7(),
        lot_mrp=Decimal("30"),
        lot_currency="INR",
        lot_unit_id=unit_id,
    )
    monkeypatch.setattr(
        pricing_validation,
        "unit",
        AsyncMock(return_value=(None, SimpleNamespace(unit_id=unit_id))),
    )
    product_reference = AsyncMock(side_effect=AssertionError("Product MRP was read"))
    monkeypatch.setattr(pricing_validation, "effective", product_reference)
    formula = FormulaInput(
        recipe="MRP_LESS_PERCENT", percentage="10", jurisdiction="IN", rounding_mode="HALF_UP"
    )
    access = SimpleNamespace(
        context=AsyncMock(return_value=SimpleNamespace(company=SimpleNamespace(country_code="IN")))
    )
    result, source = await pricing_validation.source_rate(
        access,
        formula,
        scope.item_id,
        uuid7(),
        "INR",
        dt.date.today(),
        "INCLUSIVE",
        batch_scope=scope,
    )
    assert result == Fraction(27) and source == scope.id
    with pytest.raises(ConflictError, match="tax-basis context"):
        await pricing_validation.source_rate(
            access,
            formula,
            scope.item_id,
            uuid7(),
            "INR",
            dt.date.today(),
            "EXCLUSIVE",
            batch_scope=scope,
        )
    product_reference.assert_not_awaited()
    with pytest.raises(ConflictError, match="jurisdiction"):
        await pricing_validation.source_rate(
            access,
            formula.model_copy(update={"jurisdiction": "US"}),
            scope.item_id,
            uuid7(),
            "INR",
            dt.date.today(),
            "INCLUSIVE",
            batch_scope=scope,
        )


def test_batch_code_rejects_normalization_overflow():
    with pytest.raises(ValueError, match="normalized"):
        SimpleBatchInput(code="\ufb03" * 40)
