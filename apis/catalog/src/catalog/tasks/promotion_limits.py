"""Stable limit measure validation and immutable proposed cap definitions."""

from collections.abc import Mapping
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.money import MoneyError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.promotion_limits import LimitIdentity, validate_cap
from catalog.domain.units import QuantityRule
from catalog.models.classification import ClassificationMaster
from catalog.models.promotion_limits import PromotionLimitDefinition, PromotionLimitRevision
from catalog.models.units import UnitOfMeasure
from catalog.schemas.promotion_limits import (
    LimitRevisionDetail,
    LimitRevisionInput,
    LimitRevisionListItem,
)
from catalog.tasks.aggregate_work import AggregateWork
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.definition_revisions import DefinitionRevision
from catalog.tasks.pricing_foundation import currency

IDENTITY_FIELDS = frozenset(
    {"code", "scope_kind", "metric", "period_basis", "timezone", "currency", "unit_id"}
)


def identity(parent: PromotionLimitDefinition) -> LimitIdentity:
    return LimitIdentity(
        parent.scope_kind,
        parent.metric,
        parent.period_basis,
        parent.timezone,
        parent.currency,
        parent.unit_id,
    )


async def validate_header(
    db: AsyncSession, actor: Actor, row: ClassificationMaster, before: Mapping[str, Any]
) -> None:
    assert isinstance(row, PromotionLimitDefinition)
    identity(row)
    if before and any(getattr(row, key) != before[key] for key in IDENTITY_FIELDS):
        existing = await db.scalar(
            select(PromotionLimitRevision.id)
            .where(
                PromotionLimitRevision.company_id == row.company_id,
                PromotionLimitRevision.definition_id == row.id,
            )
            .limit(1)
        )
        if existing is not None:
            raise ConflictError(
                "limit identity and quota measure cannot change after its first revision"
            )
    if not row.is_active or (before and before.get("is_active") == row.is_active and all(getattr(row, key) == before[key] for key in IDENTITY_FIELDS)):
        return
    access = ConfigurationAccess(db, actor, row.company_id)
    if row.currency is not None:
        await currency(access, row.currency, owner=PromotionLimitDefinition)
    if row.unit_id is not None:
        unit = await access.reference(UnitOfMeasure, row.unit_id)
        if unit.dimension != "COUNT":
            raise ConflictError("reward-unit limits require a declared physical count unit")


async def validate_revision(
    work: AggregateWork, parent: Any, values: Mapping[str, Any], publishing: bool
) -> None:
    assert isinstance(parent, PromotionLimitDefinition)
    value = validate_cap(
        identity(parent),
        **{key: values[key] for key in ("maximum_count", "maximum_quantity", "maximum_amount")},
    )
    await validate_header(work.db, work.actor, parent, {})
    if parent.unit_id is not None:
        unit = await work.access.reference(UnitOfMeasure, parent.unit_id)
        try:
            QuantityRule(unit.decimal_places, unit.quantity_increment).validate(value)
        except MoneyError as exc:
            raise ValidationFailedError(
                "reward cap must fit its declared native unit grid"
            ) from exc


LIMIT_REVISION = DefinitionRevision(
    PromotionLimitRevision,
    PromotionLimitDefinition,
    "definition_id",
    "promotion_limit",
    LimitRevisionInput,
    LimitRevisionListItem,
    LimitRevisionDetail,
    validate_revision,
)
