"""Reviewed exact fixed/tier adjustments publish through normal price commands."""

from __future__ import annotations

import datetime as dt
import uuid
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Literal

from billing_platform.errors import ConflictError, ValidationFailedError
from pydantic import Field

from catalog.domain.pricing import RateGrid
from catalog.models.pricing import (
    ItemPrice,
    ItemPriceDraft,
    ItemPriceNumericRevision,
    ItemPriceSeries,
    PricePlan,
)
from catalog.schemas.pricing import ExactDecimal, PublicationInput, PublishInput
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import command, purpose_access, row
from catalog.tasks.pricing_publication import draft_input, publish, save_draft

if TYPE_CHECKING:
    from catalog.tasks.bulk_registry import Runtime


class PriceAdjustment(PublicationInput):
    expected_version: int = Field(strict=True, ge=1, lt=2**31)
    method: Literal["PERCENT", "DELTA", "SET"]
    value: ExactDecimal
    rounding_mode: Literal["UP", "DOWN", "HALF_UP"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_revision_id: uuid.UUID
    price_level_id: uuid.UUID | None
    price_basis_quantity: ExactDecimal = Field(gt=0)
    numeric_revision_id: uuid.UUID
    valid_from: dt.date = Field(ge=dt.date(1000, 1, 1))
    valid_to: dt.date | None = Field(default=None, ge=dt.date(1000, 1, 1))


async def adjust(
    runtime: Runtime, body: PriceAdjustment, target: uuid.UUID | None, key: str
) -> dict[str, Any]:
    assert target is not None
    access = ConfigurationAccess(runtime.db, runtime.actor, runtime.company)
    old = await row(access, ItemPrice, target)
    await purpose_access(access, old, write=True)
    series = await row(access, ItemPriceSeries, old.series_id)
    plan = await row(access, PricePlan, series.plan_id)
    numeric = await row(access, ItemPriceNumericRevision, body.numeric_revision_id)
    if old.row_version != body.expected_version:
        raise ConflictError("adjustment source changed; review again")
    if (old.currency, old.unit_revision_id, old.price_basis_quantity, plan.price_level_id) != (
        body.currency,
        body.unit_revision_id,
        body.price_basis_quantity,
        body.price_level_id,
    ):
        raise ValidationFailedError(
            "adjustment must retain the explicitly selected currency, unit, basis and level"
        )
    original = await draft_input(access, old)
    if original.price_method == "FORMULA" or original.purchase_term is not None:
        raise ValidationFailedError(
            "recipes and gross purchase terms require an explicit native draft revision"
        )
    grid = RateGrid(numeric.price_decimal_places, numeric.price_increment)

    def changed(amount: Any) -> str:
        source, value = Fraction(amount), Fraction(body.value)
        computed = (
            source * (1 + value / 100)
            if body.method == "PERCENT"
            else source + value
            if body.method == "DELTA"
            else value
        )
        return str(grid.rounded(computed, body.rounding_mode))

    values = original.model_dump(mode="json")
    values.update(
        numeric_revision_id=str(body.numeric_revision_id),
        valid_from=body.valid_from.isoformat(),
        valid_to=body.valid_to.isoformat() if body.valid_to else None,
    )
    if original.amount is not None:
        values["amount"] = changed(original.amount)
    for tier in values["tiers"]:
        tier["amount"] = changed(tier["amount"])
    draft = type(original).model_validate(values)
    saved = await command(
        runtime.factory,
        runtime.actor,
        runtime.company,
        ItemPriceDraft,
        draft,
        key + ":draft",
        save_draft,
    )
    state = await policy_state(runtime.db, runtime.actor, runtime.company)
    assert state is not None
    publication = PublishInput(
        expected_version=saved.value.row_version,
        expected_generation=state.generation,
        expected_source_version=saved.value.source_version,
        supersedes_id=old.id,
        expected_previous_version=body.expected_version,
    )
    result = await command(
        runtime.factory,
        runtime.actor,
        runtime.company,
        ItemPriceDraft,
        publication,
        key + ":publish",
        publish,
        object_id=saved.value.id,
        action="publish",
    )
    return result.value.model_dump(mode="json")
