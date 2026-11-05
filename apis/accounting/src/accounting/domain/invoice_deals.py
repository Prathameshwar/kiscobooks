"""One same-item paid-bundle evaluator, used by preview and later goods execution.

Catalog owns published definitions; callers must obtain these resolved facts from the
authenticated local projection. A reward comparison value never reduces payable twice.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from accounting.domain.invoice_calculation import exact, money, refuse


@dataclass(frozen=True)
class SameItemDeal:
    revision_id: str
    source_version: int
    item_ids: frozenset[str]
    unit_id: str
    currency: str
    qualifying: Decimal
    reward: Decimal
    maximum_repeats: int
    starts_at: dt.datetime
    ends_at: dt.datetime
    price_level_ids: frozenset[str]
    manual_stacking: bool


@dataclass(frozen=True)
class Award:
    revision_id: str
    source_version: int
    repeats: int
    actual: Decimal
    billed: Decimal
    reward: Decimal
    regular_comparison: Decimal


def evaluate(
    rule: SameItemDeal,
    *,
    kind: str,
    item_id: str,
    unit_id: str,
    currency: str,
    price_level_id: str,
    at: dt.datetime,
    actual: Decimal,
    regular_unit_price: Decimal,
    price_denominator: Decimal = Decimal(1),
    precision: int = 2,
    manual_discount: bool = False,
    policy_stacking: bool = False,
) -> Award:
    qualifying, reward, quantity = exact(rule.qualifying), exact(rule.reward), exact(actual)
    price, denominator = exact(regular_unit_price), exact(price_denominator)
    if (
        kind != "SALES"
        or item_id not in rule.item_ids
        or unit_id != rule.unit_id
        or currency != rule.currency
        or price_level_id not in rule.price_level_ids
        or rule.source_version < 1
        or not rule.revision_id
    ):
        refuse("published deal does not cover these invoice facts")
    if (
        at.tzinfo is None
        or rule.starts_at.tzinfo is None
        or rule.ends_at.tzinfo is None
        or not rule.starts_at <= at < rule.ends_at
    ):
        refuse("deal is outside its published time window")
    if (
        qualifying <= 0
        or reward <= 0
        or quantity <= 0
        or price < 0
        or denominator <= 0
        or not 1 <= rule.maximum_repeats <= 1000
    ):
        refuse("invalid published deal quantity or regular price")
    if manual_discount and not (rule.manual_stacking and policy_stacking):
        refuse("deal and manual discounts are not permitted to stack")
    # Actual units are partitioned. Qualifying and reward units cannot overlap,
    # and repeated physical allocations cannot reevaluate this source award.
    repeats = min(int(quantity // (qualifying + reward)), rule.maximum_repeats)
    free = repeats * reward
    billed = quantity - free
    return Award(
        rule.revision_id,
        rule.source_version,
        repeats,
        money(quantity, 4),
        money(billed, 4),
        money(free, 4),
        money(free * price / denominator, precision),
    )


def evaluate_paid(
    rule: SameItemDeal,
    *,
    billed: Decimal,
    kind: str,
    item_id: str,
    unit_id: str,
    currency: str,
    price_level_id: str,
    at: dt.datetime,
    regular_unit_price: Decimal,
    price_denominator: Decimal = Decimal(1),
    precision: int = 2,
    manual_discount: bool = False,
    policy_stacking: bool = False,
) -> Award:
    """Add bounded reward units to paid units using the same physical partition evaluator."""
    paid, qualifying, reward = exact(billed), exact(rule.qualifying), exact(rule.reward)
    if paid <= 0 or paid != money(paid, 4) or qualifying <= 0 or reward <= 0:
        refuse("invalid paid or published deal quantity")
    repeats = min(int(paid // qualifying), rule.maximum_repeats)
    physical = paid + repeats * reward
    result = evaluate(
        rule,
        kind=kind,
        item_id=item_id,
        unit_id=unit_id,
        currency=currency,
        price_level_id=price_level_id,
        at=at,
        actual=Decimal(physical.numerator) / Decimal(physical.denominator),
        regular_unit_price=regular_unit_price,
        price_denominator=price_denominator,
        precision=precision,
        manual_discount=manual_discount,
        policy_stacking=policy_stacking,
    )
    if result.billed != paid or result.reward != repeats * reward:
        refuse("paid and reward units could not be partitioned exactly")
    return result


def priced_amount(
    rate: Decimal, billed: Decimal, denominator: Decimal, *, precision: int, rounding_mode: str
) -> Decimal:
    value, quantity, units = exact(rate), exact(billed), exact(denominator)
    if value < 0 or quantity < 0 or units <= 0:
        refuse("unit price requires nonnegative quantity and a positive denominator")
    return money(Fraction(value * quantity, units), precision, rounding_mode)
