"""Repeated source returns preserve original components, signs and the last minor units."""

from decimal import Decimal, localcontext
from fractions import Fraction

import pytest
from billing_platform.errors import ValidationFailedError

from accounting.domain.invoice_returns import Entitlement, ReturnClaim, allocate


def claim(source, previous=(), requested="1", basis="5"):
    return allocate(
        Decimal(basis), source, previous, Decimal(requested), precision=2, rounding_mode="HALF_UP"
    )


def test_five_returns_receive_original_tax_residual_without_repricing():
    # CAL10: A retains its original 814.00 base and two 73.26 tax components.
    source = (
        Entitlement("commercial", Decimal("814.00")),
        Entitlement("cgst", Decimal("73.26")),
        Entitlement("sgst", Decimal("73.26")),
    )
    claims = ()
    with localcontext() as context:
        context.prec = 3
        for index in range(5):
            value = claim(source, claims)
            # Keep the assertion exact under the deliberately hostile Decimal context.
            assert sum(int(Fraction(amount) * 100) for _, amount in value.amounts) == (
                19212 if index == 4 else 19210
            )
            claims = (*claims, value)
    for key in ("commercial", "cgst", "sgst"):
        assert sum(dict(row.amounts)[key] for row in claims) == next(
            row.amount for row in source if row.key == key
        )
    with pytest.raises(ValidationFailedError, match="unclaimed"):
        claim(source, claims)


def test_nonreturnable_freight_and_original_discounts_are_retained():
    source = (
        Entitlement("supply", Decimal("100")),
        Entitlement("discount", Decimal("-10")),
        Entitlement("freight", Decimal("7"), "NONRETURNABLE"),
    )
    first = claim(source, requested="2")
    assert dict(first.amounts) == {"supply": Decimal("40"), "discount": Decimal("-4"), "freight": 0}
    final = claim(source, (first,), requested="3")
    assert dict(final.amounts) == {"supply": Decimal("60"), "discount": Decimal("-6"), "freight": 0}


@pytest.mark.parametrize(
    "source,previous,requested,basis",
    [
        ((), (), "1", "5"),
        ((Entitlement("a", Decimal("1")), Entitlement("a", Decimal("2"))), (), "1", "5"),
        ((Entitlement("a", Decimal("1"), "UNKNOWN"),), (), "1", "5"),
        ((Entitlement("a", Decimal("1.001")),), (), "1", "5"),
        ((Entitlement("", Decimal("1")),), (), "1", "5"),
        ((Entitlement("a", Decimal("1")),), (), "0", "5"),
        ((Entitlement("a", Decimal("1")),), (), "6", "5"),
        ((Entitlement("a", Decimal("1")),), (), "1", "0"),
        ((Entitlement("a", Decimal("1")),), (ReturnClaim(Decimal("1"), ()),), "1", "5"),
        (
            (Entitlement("a", Decimal("1")),),
            (ReturnClaim(Decimal("1"), (("a", Decimal("-1")),)),),
            "1",
            "5",
        ),
        (
            (Entitlement("a", Decimal("-1")),),
            (ReturnClaim(Decimal("1"), (("a", Decimal("1")),)),),
            "1",
            "5",
        ),
        (
            (Entitlement("a", Decimal("0")),),
            (ReturnClaim(Decimal("1"), (("a", Decimal("1")),)),),
            "1",
            "5",
        ),
        (
            (Entitlement("a", Decimal("1"), "NONRETURNABLE"),),
            (ReturnClaim(Decimal("1"), (("a", Decimal("1")),)),),
            "1",
            "5",
        ),
        (
            (Entitlement("a", Decimal("1")),),
            (ReturnClaim(Decimal("1"), (("a", Decimal("2")),)),),
            "1",
            "5",
        ),
        (
            (Entitlement("a", Decimal(".01")),),
            (ReturnClaim(Decimal("1"), (("a", Decimal(".01")),)),),
            "3",
            "5",
        ),
    ],
)
def test_invalid_source_caps_signs_profiles_and_history(source, previous, requested, basis):
    with pytest.raises(ValidationFailedError):
        claim(source, previous, requested, basis)
