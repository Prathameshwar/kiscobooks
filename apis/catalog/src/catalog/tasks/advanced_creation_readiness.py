"""Translate native SKU activation evidence into wizard step and field paths."""

import datetime as dt
import uuid

from billing_platform.gateway import Actor
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.schemas.advanced_product_creation import (
    AdvancedReadinessBlocker,
    AdvancedSkuReadiness,
)
from catalog.tasks.activation import prepare
from catalog.tasks.advanced_creation_steps import native_rows
from catalog.tasks.advanced_product_creation import owned
from catalog.tasks.product_requirements import product_work


def blocker(code: str, index: int) -> AdvancedReadinessBlocker:
    if code == "primary_group":
        return AdvancedReadinessBlocker(code=code, step="profile", path="profile.group_id")
    if code.startswith("categor"):
        return AdvancedReadinessBlocker(code=code, step="profile", path="profile.categories")
    if code in {"brand", "model", "manufacturer"}:
        return AdvancedReadinessBlocker(code=code, step="profile", path="profile." + code)
    if code.startswith(("variant", "attribute:")):
        return AdvancedReadinessBlocker(code=code, step="skus", path=f"skus.{index}.attributes")
    if code.startswith(("base_unit", "alternate_units", "compound_units", "measured_units")):
        return AdvancedReadinessBlocker(code=code, step="skus", path=f"skus.{index}.units")
    if "tax" in code or code.startswith(("hsn", "sac")):
        return AdvancedReadinessBlocker(
            code=code, step="business", path=f"business.skus.{index}.tax"
        )
    if code.startswith(("price", "mrp", "purchase", "required_sale", "sale_book")):
        return AdvancedReadinessBlocker(
            code=code, step="business", path=f"business.skus.{index}.prices"
        )
    if "profile" in code or code.startswith("inventory"):
        return AdvancedReadinessBlocker(
            code=code, step="business", path=f"business.skus.{index}.inventory_profile"
        )
    return AdvancedReadinessBlocker(code=code, step="business", path=f"business.skus.{index}")


async def read(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    as_of: dt.date,
    secret: bytes,
) -> AdvancedSkuReadiness:
    creation = await owned(db, actor, company, creation_id)
    family, item = await native_rows(db, creation, company, item_id, lock=False)
    index = creation.sku_ids.index(str(item_id))
    if item.status == "ACTIVE":
        from catalog.tasks.policy_state import policy_state

        state = await policy_state(db, actor, company)
        return AdvancedSkuReadiness(
            item_id=item_id,
            eligible=True,
            blockers=[],
            item_version=item.row_version,
            family_version=family.row_version,
            policy_generation=state.generation if state else 1,
            source_version=None,
        )
    preview, _ = await prepare(await product_work(db, actor, company, item_id), as_of, secret)
    return AdvancedSkuReadiness(
        item_id=item_id,
        eligible=preview.eligible,
        blockers=[blocker(code, index) for code in preview.missing],
        item_version=preview.expected_version,
        family_version=preview.expected_family_version,
        policy_generation=preview.policy_generation,
        source_version=preview.source_version,
    )
