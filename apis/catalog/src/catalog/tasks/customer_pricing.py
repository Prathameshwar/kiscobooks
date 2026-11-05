"""Assemble the customer-pricing resolver's inputs from the database.

The resolver in ``catalog.domain.customer_pricing_resolution`` is pure; this
module reads what it needs and calls it. Every read is company- and
tenant-scoped through the session filter (docs/CLAUDE.md §6.3), so the caller
never has to state the scope in a WHERE clause.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from billing_platform.authz import ScopePath
from billing_platform.errors import ValidationFailedError
from billing_platform.gateway import Actor
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.customer_pricing_resolution import (
    Assignment,
    CustomerPricingUnavailableError,
    PartyMembership,
    resolve,
)
from catalog.models import (
    CompanyPricingPolicy,
    CustomerPricingProjection,
    CustomerTypeProjection,
    PriceLevel,
    PriceLevelAssignment,
    PriceLevelAssignmentScope,
)
from catalog.schemas.customer_pricing import CustomerPricingChain, CustomerPricingEffective


@dataclass(frozen=True)
class CustomerPricingChoice:
    price_level_id: uuid.UUID
    chain: tuple[CustomerPricingChain, ...]
    source_ids: tuple[uuid.UUID, ...]


async def customer_pricing_choice(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    party_id: uuid.UUID,
    as_of: dt.date,
    default_level_id: uuid.UUID,
) -> CustomerPricingChoice:
    """Resolve a buyer using bounded, dated local source facts."""
    membership_rows = list(
        await db.scalars(
            select(CustomerPricingProjection)
            .where(
                CustomerPricingProjection.company_id == company_id,
                CustomerPricingProjection.party_id == party_id,
                CustomerPricingProjection.is_active.is_(True),
                CustomerPricingProjection.valid_from <= as_of,
                or_(
                    CustomerPricingProjection.valid_to.is_(None),
                    CustomerPricingProjection.valid_to >= as_of,
                ),
            )
            .limit(2)
        )
    )
    if not membership_rows:
        raise ValidationFailedError("customer pricing membership is missing or inactive")
    if len(membership_rows) != 1:
        raise ValidationFailedError("party has more than one active customer-type membership")
    membership = membership_rows[0]
    type_source_id = None
    if membership.customer_type_code is not None:
        types = list(
            await db.scalars(
                select(CustomerTypeProjection)
                .where(
                    CustomerTypeProjection.company_id == company_id,
                    CustomerTypeProjection.code == membership.customer_type_code,
                    CustomerTypeProjection.is_active.is_(True),
                )
                .limit(2)
            )
        )
        if len(types) != 1:
            raise ValidationFailedError("customer pricing type is missing or ambiguous")
        type_source_id = types[0].source_id
    assignments = tuple(
        Assignment(
            subject_kind=row.PriceLevelAssignmentScope.subject_kind,
            customer_ref=row.PriceLevelAssignmentScope.customer_ref,
            pricing_type_ref=row.PriceLevelAssignmentScope.pricing_type_ref,
            price_level_id=row.PriceLevelAssignment.price_level_id,
            valid_from=row.PriceLevelAssignment.valid_from,
            valid_to=row.PriceLevelAssignment.valid_to,
            assignment_id=row.PriceLevelAssignment.id,
        )
        for row in (
            await db.execute(
                select(PriceLevelAssignment, PriceLevelAssignmentScope)
                .join(
                    PriceLevelAssignmentScope,
                    (PriceLevelAssignment.tenant_id == PriceLevelAssignmentScope.tenant_id)
                    & (PriceLevelAssignment.company_id == PriceLevelAssignmentScope.company_id)
                    & (PriceLevelAssignment.scope_id == PriceLevelAssignmentScope.id),
                )
                .where(
                    PriceLevelAssignment.company_id == company_id,
                    PriceLevelAssignment.valid_from <= as_of,
                    or_(
                        PriceLevelAssignment.valid_to.is_(None),
                        PriceLevelAssignment.valid_to >= as_of,
                    ),
                    or_(
                        (PriceLevelAssignmentScope.subject_kind == "CUSTOMER")
                        & (PriceLevelAssignmentScope.customer_ref == party_id),
                        (PriceLevelAssignmentScope.subject_kind == "PRICING_TYPE")
                        & (
                            PriceLevelAssignmentScope.pricing_type_ref
                            == membership.customer_type_code
                        ),
                    ),
                )
                .limit(3)
            )
        ).all()
    )
    if len(assignments) == 3:
        raise ValidationFailedError("customer pricing assignments overlap")
    try:
        resolution = resolve(
            party_id=party_id,
            posting_date=as_of,
            memberships=(
                PartyMembership(
                    party_id=membership.party_id,
                    customer_type_code=membership.customer_type_code,
                    valid_from=membership.valid_from,
                    valid_to=membership.valid_to,
                    is_active=membership.is_active,
                    source_id=membership.source_id,
                ),
            ),
            assignments=assignments,
            company_default_price_level_id=default_level_id,
        )
    except CustomerPricingUnavailableError as exc:
        raise ValidationFailedError(str(exc)) from exc
    selected = await db.scalar(
        select(PriceLevel).where(
            PriceLevel.company_id == company_id, PriceLevel.id == resolution.price_level_id
        )
    )
    if selected is None or not selected.is_active:
        raise ValidationFailedError("resolved customer price level is unavailable")
    return CustomerPricingChoice(
        price_level_id=resolution.price_level_id,
        chain=tuple(
            CustomerPricingChain(kind=resolution.chain[i], ref=resolution.chain[i + 1])
            for i in range(0, len(resolution.chain), 2)
        ),
        source_ids=tuple(
            dict.fromkeys(
                (
                    *resolution.source_ids,
                    *((type_source_id,) if type_source_id else ()),
                    selected.id,
                )
            )
        ),
    )


async def effective_customer_pricing(
    db: AsyncSession,
    current: Actor,
    company_id: uuid.UUID,
    *,
    party_id: uuid.UUID,
    as_of: dt.date,
) -> CustomerPricingEffective:
    """Return the price level that resolves for ``party`` on ``as_of``.

    Enforces the object-level scope: the actor must hold
    ``customer_pricing.read`` for this specific company (CLAUDE.md §5.2). The
    Missing or ambiguous local source facts surface as ``ValidationFailedError``
    until an authenticated Accounting projection feed is available.
    """
    current.require("customer_pricing.read")
    current.require_scope("customer_pricing.read", target=ScopePath(company_id=company_id))

    policies = list(await db.scalars(
        select(CompanyPricingPolicy)
        .where(
            CompanyPricingPolicy.company_id == company_id,
            CompanyPricingPolicy.valid_from <= as_of,
            or_(CompanyPricingPolicy.valid_to.is_(None), CompanyPricingPolicy.valid_to >= as_of),
        )
        .order_by(CompanyPricingPolicy.valid_from.desc())
        .limit(2)
    ))
    if not policies:
        raise ValidationFailedError(
            "no company default price level; configure company_pricing_policy first"
        )
    if len(policies) > 1:
        raise ValidationFailedError("company pricing policies overlap on this date")
    choice = await customer_pricing_choice(
        db, company_id, party_id=party_id, as_of=as_of,
        default_level_id=policies[0].default_level_id,
    )
    return CustomerPricingEffective(
        party_id=party_id,
        as_of=as_of,
        price_level_id=choice.price_level_id,
        chain=choice.chain,
    )
