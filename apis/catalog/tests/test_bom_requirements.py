"""B37 baseline estimate quantities; no stock or WIP side effects."""

from dataclasses import replace
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from catalog.domain.bom_requirements import Component, Output, preview


def recipe() -> tuple[tuple[Component, ...], tuple[Output, ...]]:
    primary, co_product, material = (uuid7() for _ in range(3))
    outputs = (
        Output(uuid7(), primary, Decimal("100"), Decimal("0.95")),
        Output(uuid7(), co_product, Decimal("10"), role="CO_PRODUCT"),
    )
    components = (
        Component(
            uuid7(),
            material,
            Decimal("10"),
            basis="NET_REQUIRED",
            loss_fraction=Decimal("0.20"),
        ),
        Component(uuid7(), material, Decimal("0.5"), timing="PER_RUN"),
    )
    return components, outputs


def test_documented_yield_loss_fixed_setup_and_co_product_remain_separate() -> None:
    components, outputs = recipe()
    result = preview(Decimal("190"), components, outputs, run_count=2)
    assert result.nominal_run_quantity == Decimal("200.0000")
    assert [row.required_quantity for row in result.requirements] == [
        Decimal("25.0000"),
        Decimal("1.0000"),
    ]
    assert [row.expected_quantity for row in result.outputs] == [
        Decimal("190.0000"),
        Decimal("20.0000"),
    ]
    assert [row.line_key for row in result.requirements] == [row.line_key for row in components]
    assert result.requirements[0].item_id == result.requirements[1].item_id
    assert sum(row.required_quantity for row in result.requirements) == Decimal("26.0000")


def test_fixed_inputs_require_explicit_runs_and_unrepresentable_input_is_rejected() -> None:
    components, outputs = recipe()
    with pytest.raises(ValidationFailedError, match="run count"):
        preview(Decimal("190"), components, outputs)
    with pytest.raises(ValidationFailedError, match="four quantity places"):
        preview(Decimal("1"), (replace(components[0], quantity=Decimal("0.0001")),), outputs)


def test_bad_yield_loss_cycle_and_duplicate_output_are_rejected() -> None:
    components, outputs = recipe()
    with pytest.raises(ValidationFailedError, match="primary yield"):
        preview(
            Decimal("190"),
            components,
            (replace(outputs[0], yield_fraction=Decimal(0)),),
            run_count=2,
        )
    with pytest.raises(ValidationFailedError, match="component loss"):
        preview(
            Decimal("190"),
            (replace(components[0], loss_fraction=Decimal(1)),),
            outputs,
            run_count=2,
        )
    with pytest.raises(ValidationFailedError, match="distinct"):
        preview(
            Decimal("190"),
            (replace(components[0], item_id=outputs[0].item_id),),
            outputs,
        )
    with pytest.raises(ValidationFailedError, match="distinct"):
        preview(
            Decimal("190"),
            components,
            (outputs[0], replace(outputs[1], item_id=outputs[0].item_id)),
            run_count=2,
        )


def test_trailing_digits_and_implicit_gross_up_are_not_silently_rounded() -> None:
    components, outputs = recipe()
    with pytest.raises(ValidationFailedError, match="exactly representable"):
        preview(Decimal("190.00001"), components, outputs, run_count=2)
    with pytest.raises(ValidationFailedError, match="gross input"):
        preview(
            Decimal("190"),
            (replace(components[0], basis="GROSS_INPUT"),),
            outputs,
        )
