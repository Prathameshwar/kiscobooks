"""Pure compound_factor() — multiplicative expansion of a compound unit."""

from decimal import Decimal
from fractions import Fraction

import pytest
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7

from catalog.domain.units import CompoundComponent, QuantityRule, UnitDefinition, compound_factor


def _unit(**changes: object) -> UnitDefinition:
    defaults: dict[str, object] = {
        "id": uuid7(),
        "company_id": uuid7(),
        "dimension": "COUNT",
        "quantity": QuantityRule(decimal_places=0, increment=Decimal("1")),
    }
    return UnitDefinition(**{**defaults, **changes})  # type: ignore[arg-type]


def test_single_component_returns_its_quantity() -> None:
    parent = _unit()
    bag = _unit(company_id=parent.company_id)
    result = compound_factor(parent, (CompoundComponent(1, bag, Decimal("12"), True),))
    assert result == Fraction(12)


def test_two_components_multiply() -> None:
    parent = _unit()
    bag = _unit(company_id=parent.company_id)
    kg = _unit(
        company_id=parent.company_id,
        dimension="MASS",
        quantity=QuantityRule(decimal_places=4, increment=Decimal("0.0001")),
    )
    result = compound_factor(
        parent,
        (
            CompoundComponent(1, bag, Decimal("12"), True),
            CompoundComponent(2, kg, Decimal("5"), True),
        ),
    )
    assert result == Fraction(60)


def test_inactive_child_refused() -> None:
    parent = _unit()
    bag = _unit(company_id=parent.company_id)
    with pytest.raises(ValidationFailedError, match="inactive child"):
        compound_factor(parent, (CompoundComponent(1, bag, Decimal("12"), False),))


def test_self_reference_refused() -> None:
    parent = _unit()
    with pytest.raises(ValidationFailedError, match="itself as a component"):
        compound_factor(parent, (CompoundComponent(1, parent, Decimal("2"), True),))


def test_cross_company_component_refused() -> None:
    parent = _unit()
    alien = _unit()
    with pytest.raises(ValidationFailedError, match="same company"):
        compound_factor(parent, (CompoundComponent(1, alien, Decimal("2"), True),))


def test_zero_and_negative_quantities_refused_at_construction() -> None:
    parent = _unit()
    bag = _unit(company_id=parent.company_id)
    for bad in (Decimal("0"), Decimal("-1")):
        with pytest.raises(ValidationFailedError, match="must be positive"):
            CompoundComponent(1, bag, bad, True)


def test_duplicate_ordinal_refused() -> None:
    parent = _unit()
    bag = _unit(company_id=parent.company_id)
    kg = _unit(company_id=parent.company_id)
    with pytest.raises(ValidationFailedError, match="share an ordinal"):
        compound_factor(
            parent,
            (
                CompoundComponent(1, bag, Decimal("12"), True),
                CompoundComponent(1, kg, Decimal("5"), True),
            ),
        )


def test_empty_components_refused() -> None:
    parent = _unit()
    with pytest.raises(ValidationFailedError, match="at least one component"):
        compound_factor(parent, ())


def test_ordinal_order_does_not_change_product() -> None:
    """Whether components come in (1,2) or (2,1) order, the product is the same."""
    parent = _unit()
    a = _unit(company_id=parent.company_id)
    b = _unit(company_id=parent.company_id)
    forward = compound_factor(
        parent,
        (
            CompoundComponent(1, a, Decimal("3"), True),
            CompoundComponent(2, b, Decimal("7"), True),
        ),
    )
    reverse = compound_factor(
        parent,
        (
            CompoundComponent(2, b, Decimal("7"), True),
            CompoundComponent(1, a, Decimal("3"), True),
        ),
    )
    assert forward == reverse == Fraction(21)
