"""Paid/reward partition and policy guards, independent of physical fulfillment."""

import datetime as dt
from dataclasses import replace
from decimal import Decimal

import pytest
from billing_platform.errors import ValidationFailedError

from accounting.domain.invoice_calculation import Component, Quantity, Supply, Tax, calculate
from accounting.domain.invoice_deals import SameItemDeal, evaluate, evaluate_paid, priced_amount

RULE = SameItemDeal(
    "published-revision",
    3,
    frozenset({"item"}),
    "pieces",
    "INR",
    Decimal(10),
    Decimal(1),
    10,
    dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
    dt.datetime(2027, 1, 1, tzinfo=dt.UTC),
    frozenset({"retail"}),
    True,
)
FACTS = {
    "kind": "SALES",
    "item_id": "item",
    "unit_id": "pieces",
    "currency": "INR",
    "price_level_id": "retail",
    "at": dt.datetime(2026, 10, 10, tzinfo=dt.UTC),
    "actual": Decimal(11),
    "regular_unit_price": Decimal(100),
}


def test_same_item_ten_plus_one_with_configured_stacking() -> None:
    award = evaluate(RULE, **FACTS, manual_discount=True, policy_stacking=True)
    assert (award.actual, award.billed, award.reward, award.regular_comparison) == (11, 10, 1, 100)
    amount = priced_amount(
        Decimal(100), award.billed, Decimal(1), precision=2, rounding_mode="HALF_UP"
    )
    line = Supply(
        "item",
        amount,
        quantities=(
            Quantity("ACTUAL", award.actual, "pieces"),
            Quantity("BILLED", award.billed, "pieces"),
        ),
        taxes=(Tax("c", "CGST", Decimal(9)), Tax("s", "SGST", Decimal(9))),
    )
    result = calculate(
        (line,),
        (
            Component("trade", ("item",), Decimal(10)),
            Component("bill", ("item",), Decimal(5), dependencies=("trade",)),
            Component("packing", ("item",), Decimal(20), effect="ADD", kind="FIXED"),
        ),
    )
    assert result.payable == Decimal("1032.50")
    assert result.commercial_total == 875
    assert award.regular_comparison == 100  # explanation only, never another deduction


@pytest.mark.parametrize(
    "actual,billed,free", [(10, 10, 0), (21, 20, 1), (22, 20, 2), (120, 110, 10)]
)
def test_disjoint_units_and_repeat_cap(actual: int, billed: int, free: int) -> None:
    award = evaluate(RULE, **(FACTS | {"actual": Decimal(actual)}))
    assert award.billed == billed
    assert award.reward == free
    assert award.actual == award.billed + award.reward


@pytest.mark.parametrize(
    "paid,physical,reward_units",
    [(9, 9, 0), (10, 11, 1), (19, 20, 1), (20, 22, 2), (110, 120, 10)],
)
def test_paid_entry_adds_only_earned_reward_units(
    paid: int, physical: int, reward_units: int
) -> None:
    award = evaluate_paid(
        RULE,
        **{key: value for key, value in FACTS.items() if key != "actual"},
        billed=Decimal(paid),
    )
    assert (award.billed, award.actual, award.reward) == (paid, physical, reward_units)


def test_paid_entry_rejects_unrepresentable_quantity() -> None:
    with pytest.raises(ValidationFailedError):
        evaluate_paid(
            RULE,
            **{key: value for key, value in FACTS.items() if key != "actual"},
            billed=Decimal("10.00001"),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "PURCHASE"),
        ("item_id", "other"),
        ("unit_id", "kg"),
        ("currency", "USD"),
        ("price_level_id", "wholesale"),
        ("at", dt.datetime(2027, 1, 1, tzinfo=dt.UTC)),
        ("at", dt.datetime(2026, 10, 10)),
        ("actual", Decimal(-1)),
        ("price_denominator", Decimal(0)),
    ],
)
def test_deal_eligibility_cannot_be_inferred_from_label(field: str, value: object) -> None:
    with pytest.raises(ValidationFailedError):
        evaluate(RULE, **(FACTS | {field: value}))


def test_both_published_stack_and_voucher_policy_are_required() -> None:
    with pytest.raises(ValidationFailedError, match="stack"):
        evaluate(RULE, **FACTS, manual_discount=True)
    with pytest.raises(ValidationFailedError, match="stack"):
        evaluate(
            replace(RULE, manual_stacking=False),
            **FACTS,
            manual_discount=True,
            policy_stacking=True,
        )


def test_pack_price_uses_explicit_denominator() -> None:
    assert (
        priced_amount(Decimal(50), Decimal(250), Decimal(100), precision=2, rounding_mode="HALF_UP")
        == 125
    )
    with pytest.raises(ValidationFailedError):
        priced_amount(Decimal(-1), Decimal(1), Decimal(1), precision=2, rounding_mode="HALF_UP")
