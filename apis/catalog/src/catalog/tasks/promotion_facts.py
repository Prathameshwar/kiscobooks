"""Reconstruct dormant same-item promotion facts for publication review.

This reader confers no redemption authority. A later release must bind its source
manifest and Accounting acknowledgement before these facts may affect a voucher.
"""

import uuid
from dataclasses import dataclass
from typing import TypeVar

from billing_platform.errors import ValidationFailedError
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.promotion_deals import SameItemDealTerms, same_item_deal_profile
from catalog.models.promotions import (
    PromotionBenefit,
    PromotionPriceLevelTarget,
    PromotionRevision,
    PromotionSkuTarget,
    PromotionStackGroup,
    PromotionStackPermission,
    PromotionStackPolicy,
)
from catalog.schemas.promotions import PromotionTerms, StackPolicyTerms

T = TypeVar("T", bound=BaseModel)


def _typed(model: type[T], values: dict[str, object]) -> T:
    try:
        return model.model_validate(values)
    except ValidationError as exc:
        raise ValidationFailedError("stored promotion facts are inconsistent") from exc


@dataclass(frozen=True)
class StoredSameItemDeal:
    promotion_id: uuid.UUID
    revision_id: uuid.UUID
    revision_version: int
    source_sha256: str
    stack_source_sha256: str
    policy_generation: int
    source_version: int
    terms: SameItemDealTerms


async def read_stored_same_item_deal(
    db: AsyncSession, company_id: uuid.UUID, revision_id: uuid.UUID
) -> StoredSameItemDeal:
    """Fail closed if any persisted part is missing or outside the bounded mechanic."""
    revision = await db.scalar(
        select(PromotionRevision).where(
            PromotionRevision.company_id == company_id,
            PromotionRevision.id == revision_id,
        )
    )
    if revision is None:
        raise ValidationFailedError("promotion revision is unavailable")
    policy = await db.scalar(
        select(PromotionStackPolicy).where(
            PromotionStackPolicy.company_id == company_id,
            PromotionStackPolicy.id == revision.stack_policy_revision_id,
        )
    )
    if policy is None:
        raise ValidationFailedError("promotion stack policy is unavailable")
    groups = list(
        await db.scalars(
            select(PromotionStackGroup)
            .where(
                PromotionStackGroup.company_id == company_id,
                PromotionStackGroup.policy_revision_id == policy.id,
            )
            .order_by(PromotionStackGroup.position, PromotionStackGroup.id)
        )
    )
    permissions = list(
        await db.scalars(
            select(PromotionStackPermission).where(
                PromotionStackPermission.company_id == company_id,
                PromotionStackPermission.policy_revision_id == policy.id,
            )
        )
    )
    stack = _typed(
        StackPolicyTerms,
        {
            "groups": [
                {
                    "group_id": row.id,
                    "stage": row.stage,
                    "selection": row.selection,
                    "changes_basket": row.changes_basket,
                }
                for row in groups
            ],
            "permissions": [
                {
                    "earlier_group_id": row.earlier_group_id,
                    "later_group_id": row.later_group_id,
                    "include_reward_units": row.include_reward_units,
                }
                for row in permissions
            ],
            "maximum_applied": policy.maximum_applied,
        },
    )
    benefits = list(
        await db.scalars(
            select(PromotionBenefit).where(
                PromotionBenefit.company_id == company_id,
                PromotionBenefit.revision_id == revision.id,
            )
        )
    )
    sku_ids = list(
        await db.scalars(
            select(PromotionSkuTarget.item_id).where(
                PromotionSkuTarget.company_id == company_id,
                PromotionSkuTarget.revision_id == revision.id,
            )
        )
    )
    level_ids = list(
        await db.scalars(
            select(PromotionPriceLevelTarget.price_level_id).where(
                PromotionPriceLevelTarget.company_id == company_id,
                PromotionPriceLevelTarget.revision_id == revision.id,
            )
        )
    )
    if len(benefits) != 1 or not sku_ids or not level_ids:
        raise ValidationFailedError("published promotion facts are incomplete")
    benefit = benefits[0]
    terms = _typed(
        PromotionTerms,
        {
            "currency": revision.currency,
            "eligible_price_level_ids": sorted(level_ids),
            "selection_mode": revision.selection_mode,
            "condition_groups": [
                {
                    "selectors": [{"dimension": "SKU", "mode": "INCLUDE", "ids": sorted(sku_ids)}],
                    "item_kinds": ["GOODS"],
                }
            ],
            "benefit": {
                "kind": benefit.kind,
                "qualifying": {
                    "quantity": benefit.qualifying_quantity,
                    "unit_revision_id": benefit.unit_revision_id,
                },
                "reward": {
                    "quantity": benefit.reward_quantity,
                    "unit_revision_id": benefit.unit_revision_id,
                },
                "reward_percent": benefit.reward_percent,
                "pool": benefit.pool,
                "reward_item_ids": sorted(sku_ids),
                "selection": "LOWEST_REGULAR_UNIT_PRICE",
                "maximum_repeats": benefit.maximum_repeats,
            },
            "trigger": revision.trigger_mode,
            "starts_at": revision.starts_at,
            "ends_at": revision.ends_at,
            "timezone": revision.timezone,
            "stack_policy_revision_id": revision.stack_policy_revision_id,
            "stack_group_id": revision.stack_group_id,
            "return_policy_revision_id": revision.return_policy_revision_id,
            "priority": revision.priority,
        },
    )
    return StoredSameItemDeal(
        revision.promotion_id,
        revision.id,
        revision.version,
        revision.source_sha256,
        policy.source_sha256,
        revision.policy_generation,
        revision.source_version,
        same_item_deal_profile(terms, stack),
    )
