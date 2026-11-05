"""Static profile for the bounded same-item deal evaluator.

This is a publication preflight, not authority to redeem. Native references, source
generations, limits, and complete release acknowledgement are checked by publication
and the eventual Accounting projection before a rule can become executable.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from billing_platform.errors import ValidationFailedError

from catalog.schemas.promotions import BuyGetBenefit, PromotionTerms, StackPolicyTerms


@dataclass(frozen=True)
class SameItemDealTerms:
    item_ids: frozenset[uuid.UUID]
    unit_revision_id: uuid.UUID
    currency: str
    qualifying: Decimal
    reward: Decimal
    maximum_repeats: int
    starts_at: dt.datetime
    ends_at: dt.datetime
    price_level_ids: frozenset[uuid.UUID]
    manual_stacking: bool


def same_item_deal_profile(terms: PromotionTerms, stack: StackPolicyTerms) -> SameItemDealTerms:
    """Reject definitions that the current one-rule evaluator cannot safely interpret."""
    benefit = terms.benefit
    if (
        not isinstance(benefit, BuyGetBenefit)
        or benefit.pool != "SAME_ITEM"
        or benefit.reward_percent != 100
        or benefit.selection != "LOWEST_REGULAR_UNIT_PRICE"
        or benefit.qualifying.unit_revision_id != benefit.reward.unit_revision_id
        or terms.trigger != "AUTOMATIC"
        or terms.selection_mode != "SNAPSHOT_ON_PUBLISH"
        or len(terms.condition_groups) != 1
    ):
        raise ValidationFailedError("same-item deal requires a supported published mechanic")
    condition = terms.condition_groups[0]
    if (
        len(condition.selectors) != 1
        or condition.selectors[0].dimension != "SKU"
        or condition.selectors[0].mode != "INCLUDE"
        or set(condition.selectors[0].ids) != set(benefit.reward_item_ids)
        or condition.attributes
        or condition.minimum_spend is not None
        or condition.minimum_quantity is not None
        or condition.item_kinds not in {(), ("GOODS",)}
    ):
        raise ValidationFailedError("same-item deal requires identical eligible and reward SKUs")
    group = next((row for row in stack.groups if row.group_id == terms.stack_group_id), None)
    if (
        group is None
        or group.stage != "PRODUCT_SCHEME"
        or group.selection != "PRIORITY"
        or not group.changes_basket
    ):
        raise ValidationFailedError("same-item deal requires a supported product stack group")
    manual_ids = {row.group_id for row in stack.groups if row.stage == "MANUAL"}
    manual_stacking = stack.maximum_applied >= 2 and any(
        row.earlier_group_id == group.group_id and row.later_group_id in manual_ids
        for row in stack.permissions
    )
    return SameItemDealTerms(
        frozenset(benefit.reward_item_ids),
        benefit.qualifying.unit_revision_id,
        terms.currency,
        benefit.qualifying.quantity,
        benefit.reward.quantity,
        benefit.maximum_repeats,
        terms.starts_at,
        terms.ends_at,
        frozenset(terms.eligible_price_level_ids),
        manual_stacking,
    )
