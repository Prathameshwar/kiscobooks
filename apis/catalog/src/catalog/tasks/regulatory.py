"""Date-resolved Catalog regulatory evidence; no stock or voucher effects."""

import datetime as dt
import uuid
from typing import Literal, cast

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from sqlalchemy import or_, select

from catalog.models.pricing import PricingRow
from catalog.models.regulatory import ItemRegulatoryClassification
from catalog.schemas.regulatory import (
    EffectiveRegulatoryClassification,
    LicenceClass,
    PrescriptionSchedule,
    RegulatoryClassificationInput,
)
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import PricingWork, product


class RegulatoryWork(PricingWork):
    entity_model: type[PricingRow] = ItemRegulatoryClassification
    policy_subject = "item regulatory classification"


async def classify(
    work: PricingWork, body: RegulatoryClassificationInput, item_id: uuid.UUID | None
) -> ItemRegulatoryClassification:
    assert item_id is not None
    item, family = await product(work.access, item_id)
    if family.kind != "GOODS":
        raise ConflictError("a service cannot be classified as regulated goods")
    if item.status == "DISCONTINUED":
        raise ConflictError("discontinued items cannot receive new regulatory history")
    await work.history(ItemRegulatoryClassification, body, {"item_id": item_id})
    return await work.new(
        ItemRegulatoryClassification,
        item_id=item_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        product_kind=body.product_kind,
        licence_class=body.licence_class,
        prescription_schedule=body.prescription_schedule,
        food_category_code=body.food_category_code,
        source_reference=body.source_reference,
        source_url=body.source_url,
        source_sha256=body.source_sha256,
        review_reason=body.review_reason,
        reviewed_at=utcnow(),
        reviewed_by=work.actor.user_id,
    )


async def effective(
    access: ConfigurationAccess, item_id: uuid.UUID, as_of: dt.date
) -> EffectiveRegulatoryClassification | None:
    """Missing evidence is unknown, never implicit non-drug or legal eligibility."""
    context = await access.context(ItemRegulatoryClassification)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("regulatory classification evidence is protected")
    rows = list(
        await access.db.scalars(
            select(ItemRegulatoryClassification)
            .where(
                ItemRegulatoryClassification.company_id == access.company,
                ItemRegulatoryClassification.item_id == item_id,
                ItemRegulatoryClassification.valid_from <= as_of,
                or_(
                    ItemRegulatoryClassification.valid_to.is_(None),
                    ItemRegulatoryClassification.valid_to >= as_of,
                ),
            )
            .order_by(ItemRegulatoryClassification.valid_from.desc())
            .limit(2)
        )
    )
    if len(rows) > 1:
        raise ConflictError("ambiguous effective regulatory classification")
    if not rows:
        return None
    row = rows[0]
    await access.require(row)
    return EffectiveRegulatoryClassification(
        id=row.id,
        row_version=row.row_version,
        item_id=row.item_id,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        product_kind=cast(Literal["NON_DRUG", "MEDICINE", "FOOD"], row.product_kind),
        licence_class=cast(LicenceClass | None, row.licence_class),
        prescription_schedule=cast(PrescriptionSchedule | None, row.prescription_schedule),
        food_category_code=row.food_category_code,
        source_reference=row.source_reference,
        source_url=row.source_url,
        source_sha256=row.source_sha256,
        review_reason=row.review_reason,
        reviewed_at=row.reviewed_at,
        reviewed_by=row.reviewed_by,
    )
