"""B39 calculation evidence; no stock, WIP, tax or journal effect."""

from dataclasses import replace
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from accounting.domain.manufacturing_cost import CostPool, OutputWeight, preview


def fixture():
    pool = CostPool(
        "INR",
        Decimal("80.0000"),
        Decimal("15.0000"),
        Decimal("4.0001"),
        Decimal("1.0000"),
        Decimal("7.0000"),
    )
    outputs = tuple(
        OutputWeight(uuid7(), uuid7(), weight)
        for weight in (Decimal(6), Decimal(3), Decimal(1))
    )
    return pool, outputs


def test_multiple_outputs_conserve_actual_pool_and_exclude_noncapitalizable_charge():
    pool, outputs = fixture()
    result = preview(pool, outputs)
    assert result.capitalizable_total == Decimal("100.0001")
    assert result.noncapitalizable_charge == Decimal("7.0000")
    assert sum(row.allocated_cost for row in result.outputs) == result.capitalizable_total
    assert [row.line_id for row in result.outputs] == [row.line_id for row in outputs]
    assert [row.allocated_cost for row in result.outputs] == [
        Decimal("60.0001"),
        Decimal("30.0000"),
        Decimal("10.0000"),
    ]


def test_unweighted_scrap_is_allowed_but_all_zero_weights_are_refused():
    pool, outputs = fixture()
    result = preview(pool, (outputs[0], replace(outputs[1], weight=Decimal(0))))
    assert result.outputs[1].allocated_cost == Decimal(0)
    with pytest.raises(ValidationFailedError, match="positive basis"):
        preview(pool, tuple(replace(row, weight=Decimal(0)) for row in outputs))


def test_negative_or_overprecise_cost_and_duplicate_sku_are_refused():
    pool, outputs = fixture()
    with pytest.raises(ValidationFailedError, match="negative"):
        preview(replace(pool, consumed_input=Decimal("-1")), outputs)
    with pytest.raises(ValidationFailedError, match="storage precision"):
        preview(replace(pool, consumed_input=Decimal("1.00001")), outputs)
    with pytest.raises(ValidationFailedError, match="SKUs must be distinct"):
        preview(pool, (outputs[0], replace(outputs[1], item_id=outputs[0].item_id)))
