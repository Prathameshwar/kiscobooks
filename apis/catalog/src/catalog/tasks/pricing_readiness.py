"""Shared static commercial assessment; transaction facts remain with Billing."""

import datetime as dt
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal
from fractions import Fraction

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.money import MoneyError

from catalog.models.pricing import ItemPriceScope, PricePlan
from catalog.schemas.pricing import DraftInput, PricingIssue, TransactionRequirement
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import row
from catalog.tasks.pricing_guards import GuardResult, restrictions
from catalog.tasks.pricing_schedule import coverage
from catalog.tasks.pricing_validation import settings, validate
from catalog.tasks.product_commands import ProductWork

MESSAGES = {
    "BELOW_MINIMUM": "regular price is below an applicable minimum",
    "ABOVE_MAXIMUM": "regular price exceeds an applicable maximum",
}


@dataclass
class PriceAssessment:
    plan: PricePlan
    amount: Decimal | None
    source_ids: list[uuid.UUID]
    guards: GuardResult
    issues: list[PricingIssue]
    coverage_valid_to: dt.date | None = None

    @property
    def transaction_requirements(self) -> list[TransactionRequirement]:
        result: list[TransactionRequirement] = []
        if self.guards.needs_tax:
            result.append("TAX_CONTEXT")
        if self.guards.needs_measurement:
            result.append("MEASURED_QUANTITY")
        return result

    def require_valid(self) -> None:
        if self.issues:
            raise ConflictError(self.issues[0].message)


async def assess(
    access: ConfigurationAccess,
    body: DraftInput,
    *,
    entering: bool = True,
    requested_revision: uuid.UUID | None = None,
    unit_factor: Fraction = Fraction(1),
    check_schedule: bool = False,
) -> PriceAssessment:
    series, plan, _, amount, sources = await validate(access, body, entering=entering)
    scope = await row(access, ItemPriceScope, series.price_scope_id)
    guards = GuardResult()
    mrp_required = False
    context = await access.context(PricePlan)
    if plan.purpose == "SALE":
        item, family, config = await settings(access, series.item_id, body.valid_from)
        mrp_required = config.pricing.mrp_mode == "REQUIRED"
        guards = await restrictions(
            access,
            ProductWork(access.db, access.actor, access.company, family, item, access),
            requested_revision or series.unit_revision_id,
            series.currency,
            body.valid_from,
            plan.tax_basis,
            context.company.country_code,
            mrp_required=mrp_required,
            defer_measurement=True,
            batch_scope=scope if scope.lot_id is not None else None,
        )
    amounts = [tier.amount for tier in body.tiers] if body.price_method == "TIERS" else [amount]
    codes: set[str] = set()
    for value in amounts:
        assert value is not None
        codes.update(
            guards.violations(Fraction(value) / Fraction(body.price_basis_quantity) * unit_factor)
        )
    result = PriceAssessment(
        plan=plan,
        amount=amount,
        source_ids=list(dict.fromkeys([*sources, *guards.source_ids, *guards.guard_ids])),
        guards=guards,
        issues=[
            PricingIssue(code=code, as_of=body.valid_from, message=MESSAGES[code])
            for code in sorted(codes)
        ],
        coverage_valid_to=body.valid_to,
    )
    if not check_schedule:
        return result
    schedule = await coverage(
        access,
        body,
        series,
        sale=plan.purpose == "SALE",
        mrp_required=mrp_required and scope.lot_id is None,
        mrp_revision_id=requested_revision or series.unit_revision_id,
        jurisdiction=context.company.country_code,
        batch_scope=scope.lot_id is not None,
    )
    result.coverage_valid_to = schedule.valid_to
    result.issues.extend(schedule.issues)
    result.source_ids = list(dict.fromkeys([*result.source_ids, *sorted(schedule.source_ids)]))
    for date in sorted(schedule.dates):
        try:
            future = await assess(
                access,
                body.model_copy(update={"valid_from": date}),
                entering=False,
                requested_revision=requested_revision,
                unit_factor=unit_factor,
            )
        except (ConflictError, ValidationFailedError, MoneyError):
            result.issues.append(
                PricingIssue(
                    code="FUTURE_DEFINITION_INVALID",
                    as_of=date,
                    message="price definition is unusable at a declared dependency change",
                )
            )
            continue
        result.issues.extend(future.issues)
        result.source_ids = list(dict.fromkeys([*result.source_ids, *future.source_ids]))
        result.guards = replace(
            result.guards,
            guard_ids=tuple(dict.fromkeys([*result.guards.guard_ids, *future.guards.guard_ids])),
            approval_ids=tuple(
                dict.fromkeys([*result.guards.approval_ids, *future.guards.approval_ids])
            ),
            needs_tax=result.guards.needs_tax or future.guards.needs_tax,
            needs_measurement=result.guards.needs_measurement or future.guards.needs_measurement,
        )
    return result
