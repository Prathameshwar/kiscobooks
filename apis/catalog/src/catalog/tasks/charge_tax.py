"""Produce signed version-two charge-tax evidence for Accounting (Phase 5, no route yet).

Accounting's ``POST /charge-tax-snapshots`` accepts a Catalog statement signed for operation
``catalog.accounting_tax.assessed``. This module is Catalog's producer: it resolves the GST
rule's rate effective on ``posting_date`` for the supply context ``place_of_supply`` decides,
computes amounts with ``billing_platform.tax_calc`` and signs the statement. Who calls it, and
when, is not decided by the docs (open item in docs/tax-accounting-plan.md Phase 5), so it is
exposed as a task function only — never a route.

Authority: the caller's own ``tax_rule.read`` and field context, through the same
``ConfigurationAccess`` reads every tax route uses. A rule, series, rate or component the actor
cannot read refuses the statement rather than computing from it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.money import RoundingMode
from billing_platform.service_auth import ServiceKey
from billing_platform.tax_calc import (
    BuyerType,
    ComponentCode,
    ComponentKind,
    ComponentRounding,
    SupplyKind,
    TaxComponent,
    Treatment,
)
from sqlalchemy import select

from catalog.domain.charge_tax import (
    OPERATION,
    ChargeTaxInput,
    CompanyFacts,
    determine,
    sign,
    statement,
)
from catalog.models.tax import TaxRate, TaxRateComponent, TaxRateSeries, TaxRule
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import protected, row
from catalog.tasks.tax_history import effective

#: Treatments whose rules carry a dated rate; the others are untaxed by definition.
RATED = frozenset({"TAXABLE", "NIL_RATED"})


def tax_component(value: TaxRateComponent) -> TaxComponent:
    return TaxComponent(
        component=ComponentCode(value.component),
        kind=ComponentKind(value.kind),
        rounding_mode=ComponentRounding(value.rounding_mode),
        position=int(value.position),
        percentage=value.percentage,
        amount=value.amount,
        currency=value.currency,
        unit_id=value.unit_id,
        basis_quantity=value.basis_quantity,
    )


async def rate_components(
    access: ConfigurationAccess, rule: TaxRule, applicability: str, posting_date: dt.date
) -> tuple[TaxComponent, ...]:
    """The live rate of the rule's series for this supply context on ``posting_date``."""
    await protected(access, TaxRateSeries)
    series = list(
        await access.db.scalars(
            select(TaxRateSeries)
            .where(
                TaxRateSeries.company_id == access.company,
                TaxRateSeries.rule_id == rule.id,
                TaxRateSeries.applicability == applicability,
            )
            .limit(2)
        )
    )
    if len(series) != 1:
        raise ConflictError("the tax rule has no single rate series for this supply context")
    await access.require(series[0])
    rate = await effective(access, TaxRate, posting_date, series_id=series[0].id)
    if rate is None:
        # Never a silent zero: a taxable rule without a rate on the date is a gap to fix.
        raise ConflictError("no tax rate is effective on the posting date")
    await protected(access, TaxRateComponent)
    components = list(
        await access.db.scalars(
            select(TaxRateComponent)
            .where(
                TaxRateComponent.company_id == access.company,
                TaxRateComponent.rate_id == rate.id,
            )
            .limit(17)
        )
    )
    if not 1 <= len(components) <= 16:
        raise ConflictError("the effective tax rate has no valid component set")
    for entry in components:
        await access.require(entry)
    return tuple(tax_component(entry) for entry in components)


async def assess_charge_tax(
    access: ConfigurationAccess,
    *,
    assessment_id: uuid.UUID,
    input_hash: str,
    posting_date: dt.date,
    currency: str,
    net_amount: Decimal,
    rule_id: uuid.UUID,
    place_of_supply_state: str | None,
    buyer_type: BuyerType | str,
    registrations: Iterable[Mapping[str, Any]],
    utgst_states: frozenset[str],
    quantity: Decimal | None = None,
    unit_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """The version-two computation for one Accounting charge assessment.

    ``registrations`` are Identity's company registration rows (the shape Identity sends
    Accounting); ``utgst_states`` is the configured set of UTGST-levying state codes. Both are
    explicit inputs because Catalog's own Identity context carries neither (open items).
    """
    if not isinstance(net_amount, Decimal):
        raise ValidationFailedError("charge-tax net amount must be a Decimal")
    if quantity is not None and not isinstance(quantity, Decimal):
        raise ValidationFailedError("charge-tax quantity must be a Decimal")
    rule = await row(access, TaxRule, rule_id)
    if not rule.is_active:
        raise ConflictError("the tax rule is inactive")
    company = (await access.context(TaxRule)).company
    if company.country_code != "IN":
        raise ConflictError("this tax adapter supports Indian companies only")
    facts = CompanyFacts(
        country_code=company.country_code,
        state_code=company.state_code,
        base_currency=company.base_currency,
        amount_precision=company.amount_precision,
        rounding_mode=RoundingMode(company.rounding_mode),
    )
    request = ChargeTaxInput(
        tenant_id=access.actor.tenant_id,
        company_id=access.company,
        assessment_id=assessment_id,
        input_hash=input_hash,
        posting_date=posting_date,
        currency=currency,
        net_amount=net_amount,
        supply_kind=SupplyKind(rule.item_kind),
        treatment=Treatment(rule.treatment),
        place_of_supply_state=place_of_supply_state,
        buyer_type=BuyerType(buyer_type),
        quantity=quantity,
        unit_id=unit_id,
    )
    determination = determine(request, facts, utgst_states=utgst_states)
    components = (
        await rate_components(access, rule, determination.context.value, posting_date)
        if rule.treatment in RATED
        else ()
    )
    return statement(request, facts, determination, components, registrations)


def evidence(
    computation: Mapping[str, Any],
    *,
    secret: bytes,
    key_id: str,
    timestamp: int,
) -> dict[str, Any]:
    """Signed evidence for Accounting; the caller adds Accounting-owned ``accounts``."""
    key = ServiceKey("catalog", "accounting", frozenset({OPERATION}), secret)
    return {
        "key_id": key_id,
        "timestamp": timestamp,
        "computation": dict(computation),
        "signature": sign(key, key_id, computation, timestamp),
    }


__all__ = ["RATED", "assess_charge_tax", "evidence", "rate_components", "tax_component"]
