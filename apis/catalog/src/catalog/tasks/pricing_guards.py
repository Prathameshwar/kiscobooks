"""Combine dated restrictions; return guard evidence, never approve a transaction."""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from billing_platform.errors import ConflictError
from sqlalchemy import or_, select

from catalog.domain.classification import MAX_DEPTH
from catalog.domain.pricing import RateGrid, recipe_rate
from catalog.models.classification import ItemGroup, ItemGroupParent
from catalog.models.pricing import (
    CommercialGuardRule,
    CommercialPolicyScope,
    DiscountCeiling,
    ItemMrp,
    ItemPriceScope,
    ItemReferenceCost,
)
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import effective, protected
from catalog.tasks.pricing_foundation import numeric, unit
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_requirements import group_on


@dataclass(frozen=True)
class GuardResult:
    minimum: Fraction | None = None
    maximum: Fraction | None = None
    blocking_minimum: Fraction | None = None
    blocking_maximum: Fraction | None = None
    max_discount_pct: Decimal | None = None
    guard_ids: tuple[uuid.UUID, ...] = ()
    source_ids: tuple[uuid.UUID, ...] = ()
    approval_ids: tuple[uuid.UUID, ...] = ()
    needs_tax: bool = False
    needs_measurement: bool = False
    comparable_minimum: Fraction | None = None
    comparable_maximum: Fraction | None = None

    def violations(self, rate: Fraction) -> tuple[str, ...]:
        """Evaluate known same-basis BLOCK limits even if another limit needs tax facts."""
        result = []
        if self.comparable_minimum is not None and rate < self.comparable_minimum:
            result.append("BELOW_MINIMUM")
        if self.comparable_maximum is not None and rate > self.comparable_maximum:
            result.append("ABOVE_MAXIMUM")
        return tuple(result)


async def discounts(
    access: ConfigurationAccess, work: ProductWork, as_of: dt.date
) -> tuple[Decimal | None, list[uuid.UUID]]:
    assert work.item is not None
    group = await group_on(work, as_of)
    owners = [access.company, work.family.id, work.item.id]
    group_id = group.group_id if group else None
    seen: set[uuid.UUID] = set()
    while group_id is not None:
        if group_id in seen or len(seen) >= MAX_DEPTH:
            raise ConflictError("commercial ancestry is cyclic or exceeds its bound")
        seen.add(group_id)
        await access.reference(ItemGroup, group_id)
        owners.append(group_id)
        edge = await effective(access, ItemGroupParent, as_of, group_id=group_id)
        if edge is None:
            raise ConflictError("commercial group ancestry is incomplete")
        group_id = edge.parent_group_id
    await protected(access, CommercialPolicyScope)
    scopes = list(
        await access.db.scalars(
            select(CommercialPolicyScope)
            .where(
                CommercialPolicyScope.company_id == access.company,
                CommercialPolicyScope.owner_id.in_(owners),
            )
            .limit(MAX_DEPTH + 4)
        )
    )
    ceiling = None
    ids = []
    for scope in scopes:
        await access.require(scope)
        value = await effective(access, DiscountCeiling, as_of, scope_id=scope.id)
        if value is not None:
            ceiling = (
                value.max_discount_pct if ceiling is None else min(ceiling, value.max_discount_pct)
            )
            ids.append(value.id)
    return ceiling, ids


async def restrictions(
    access: ConfigurationAccess,
    work: ProductWork,
    revision_id: uuid.UUID,
    currency: str,
    as_of: dt.date,
    tax_basis: str,
    jurisdiction: str | None,
    *,
    mrp_required: bool = False,
    defer_measurement: bool = False,
    batch_scope: ItemPriceScope | None = None,
) -> GuardResult:
    assert work.item is not None
    requested, requested_binding = await unit(access, work.item.id, revision_id, as_of)
    await protected(access, CommercialGuardRule)
    rules = list(
        await access.db.scalars(
            select(CommercialGuardRule)
            .where(
                CommercialGuardRule.company_id == access.company,
                CommercialGuardRule.item_id == work.item.id,
                CommercialGuardRule.currency == currency,
                CommercialGuardRule.valid_from <= as_of,
                or_(CommercialGuardRule.valid_to.is_(None), CommercialGuardRule.valid_to >= as_of),
            )
            .limit(257)
        )
    )
    if len(rules) > 256:
        raise ConflictError("active commercial guards exceed the bounded unit/rule set")
    floor = None
    ceiling = None
    blocking_floor = None
    blocking_ceiling = None
    guard_ids = []
    source_ids: list[uuid.UUID] = []
    approval_ids = []
    tax_context = False
    measured_context = False
    comparable_floor = None
    comparable_ceiling = None
    seen: set[tuple[uuid.UUID, str]] = set()
    for guard in rules:
        await access.require(guard)
        identity = (guard.unit_revision_id, guard.rule_kind)
        if identity in seen:
            raise ConflictError("commercial guard history is ambiguous")
        seen.add(identity)
        guard_ids.append(guard.id)
        if guard.severity == "REQUIRE_APPROVAL":
            approval_ids.append(guard.id)
        original, _ = await unit(access, work.item.id, guard.unit_revision_id)
        factor: Fraction | None
        if requested.id == original.id:
            factor = Fraction(1)
        elif requested.conversion_mode == original.conversion_mode == "FIXED":
            assert requested.numerator is not None and requested.denominator is not None
            assert original.numerator is not None and original.denominator is not None
            factor = Fraction(requested.numerator, requested.denominator) / Fraction(
                original.numerator, original.denominator
            )
        elif not defer_measurement:
            raise ConflictError("guard comparison requires authoritative measured allocation")
        else:
            factor = None
            measured_context = True
        precision = await numeric(
            access,
            guard.numeric_revision_id,
            work.item.id,
            guard.unit_revision_id,
            currency,
            as_of,
            entering=False,
        )
        grid = RateGrid(precision.price_decimal_places, precision.price_increment)
        source_ids.extend((guard.id, original.id, precision.id))
        if guard.rule_kind.startswith("FIXED_"):
            assert guard.amount is not None
            value = Fraction(guard.amount) / Fraction(guard.price_basis_quantity)
        else:
            source = await effective(
                access,
                ItemReferenceCost,
                as_of,
                item_id=work.item.id,
                unit_revision_id=guard.unit_revision_id,
                currency=currency,
                estimate_kind=guard.estimate_kind,
            )
            if source is None:
                raise ConflictError("commercial guard requires an effective estimate source")
            source_ids.append(source.id)
            assert guard.percentage is not None
            exact = recipe_rate(
                Fraction(source.amount) / Fraction(source.price_basis_quantity),
                guard.rule_kind,
                guard.percentage,
            )
            value = Fraction(
                grid.rounded(exact * Fraction(guard.price_basis_quantity), "UP")
            ) / Fraction(guard.price_basis_quantity)
        if tax_basis != "EXCLUSIVE":
            tax_context = True
        if factor is None:
            continue
        value *= factor
        if guard.rule_kind == "FIXED_MAX":
            ceiling = value if ceiling is None else min(ceiling, value)
            if guard.severity == "BLOCK":
                blocking_ceiling = (
                    value if blocking_ceiling is None else min(blocking_ceiling, value)
                )
                if tax_basis == "EXCLUSIVE":
                    comparable_ceiling = blocking_ceiling
        else:
            floor = value if floor is None else max(floor, value)
            if guard.severity == "BLOCK":
                blocking_floor = value if blocking_floor is None else max(blocking_floor, value)
                if tax_basis == "EXCLUSIVE":
                    comparable_floor = blocking_floor
    # Product declarations apply only to the same declared pack. No implicit pack-MRP conversion.
    if batch_scope is not None:
        if batch_scope.lot_mrp is None:
            if mrp_required:
                raise ConflictError("The batch's physical MRP declaration is required")
        else:
            if (batch_scope.item_id, batch_scope.lot_currency, batch_scope.lot_unit_id) != (
                work.item.id,
                currency,
                requested_binding.unit_id,
            ):
                raise ConflictError("Batch MRP applies only to its declared unit and currency")
            source_ids.append(batch_scope.id)
            value = Fraction(batch_scope.lot_mrp)
            if tax_basis == "INCLUSIVE":
                comparable_ceiling = (
                    value if comparable_ceiling is None else min(comparable_ceiling, value)
                )
            if tax_basis != "INCLUSIVE" or rules:
                tax_context = True
            else:
                ceiling = value if ceiling is None else min(ceiling, value)
                blocking_ceiling = (
                    value if blocking_ceiling is None else min(blocking_ceiling, value)
                )
    elif jurisdiction is not None:
        mrp = await effective(
            access,
            ItemMrp,
            as_of,
            item_id=work.item.id,
            unit_revision_id=revision_id,
            currency=currency,
            jurisdiction=jurisdiction,
        )
        if mrp is None and mrp_required:
            raise ConflictError(
                "required product MRP declaration is missing for this pack/jurisdiction"
            )
        if mrp is not None:
            source_ids.append(mrp.id)
            value = Fraction(mrp.amount) / Fraction(mrp.price_basis_quantity)
            if tax_basis == mrp.tax_basis:
                comparable_ceiling = (
                    value if comparable_ceiling is None else min(comparable_ceiling, value)
                )
            if tax_basis != mrp.tax_basis or rules:
                tax_context = True
            else:
                ceiling = value if ceiling is None else min(ceiling, value)
                blocking_ceiling = (
                    value if blocking_ceiling is None else min(blocking_ceiling, value)
                )
    if floor is not None and ceiling is not None and floor > ceiling:
        raise ConflictError("commercial minimum exceeds its maximum")
    discount, discount_ids = await discounts(access, work, as_of)
    guard_ids += discount_ids
    return GuardResult(
        minimum=floor,
        maximum=ceiling,
        blocking_minimum=blocking_floor,
        blocking_maximum=blocking_ceiling,
        max_discount_pct=discount,
        guard_ids=tuple(guard_ids),
        source_ids=tuple(source_ids),
        approval_ids=tuple(approval_ids),
        needs_tax=tax_context,
        needs_measurement=measured_context,
        comparable_minimum=comparable_floor,
        comparable_maximum=comparable_ceiling,
    )
