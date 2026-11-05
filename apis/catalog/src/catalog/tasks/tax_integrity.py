"""Validate complete proposed schedules and the products affected by a tax change."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any, Literal, cast

from billing_platform.errors import ConflictError
from sqlalchemy import or_, select

from catalog.domain.tax import signature
from catalog.models import FamilyGroupAssignment, Item, ItemGroupParent, ProductFamily
from catalog.models.tax import (
    CatalogTaxBinding,
    CatalogTaxScope,
    TaxClassification,
    TaxRate,
    TaxRateComponent,
    TaxRateSeries,
    TaxRule,
)
from catalog.models.tax_governance import TaxRuleApplicability
from catalog.schemas.tax import ResolveInput
from catalog.schemas.tax_governance import ImpactItem, TaxImpact
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import business_date, protected, row
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.tax_history import live_rows, require_live, rows
from catalog.tasks.tax_validation import stored_components

if TYPE_CHECKING:
    from catalog.tasks.tax_commands import TaxWork

MAX_ITEMS = 256
MAX_DATES = 64
MAX_CHECKS = 2048


def dates_for(values: list[Any], start: dt.date) -> list[dt.date]:
    dates = {start}
    for value in values:
        if value.valid_from >= start:
            dates.add(value.valid_from)
        if value.valid_to is not None and start <= value.valid_to < dt.date.max:
            dates.add(value.valid_to + dt.timedelta(days=1))
    if len(dates) > MAX_DATES:
        raise ConflictError("tax review exceeds 64 effective date boundaries")
    return sorted(dates)


async def review_dates(
    access: ConfigurationAccess, items: list[Item], start: dt.date
) -> list[dt.date]:
    """Follow only the items' current/future owners, bindings and selected tax dependencies."""
    items = [item for item in items if item.sellable or item.purchasable]
    if not items:
        return [start]
    families = frozenset(item.family_id for item in items)
    assignments = await rows(access, FamilyGroupAssignment, since=start, family_id=families)
    groups = {entry.group_id for entry in assignments}
    pending = groups.copy()
    ancestry = []
    while pending:
        edges = await rows(access, ItemGroupParent, since=start, group_id=frozenset(pending))
        ancestry += edges
        pending = {
            entry.parent_group_id for entry in edges if entry.parent_group_id is not None
        } - groups
        groups |= pending
        if len(ancestry) > 8192:
            raise ConflictError("tax ancestry exceeds bounded review capacity")
    for value in [*assignments, *ancestry]:
        await access.require(value)
    owners = frozenset({access.company, *families, *groups, *(item.id for item in items)})
    scopes = await rows(access, CatalogTaxScope, owner_id=owners)
    bindings = await live_rows(
        access,
        CatalogTaxBinding,
        since=start,
        scope_id=frozenset(entry.id for entry in scopes),
        direction=frozenset(
            direction
            for item in items
            for direction, enabled in (("SALE", item.sellable), ("PURCHASE", item.purchasable))
            if enabled
        ),
    )
    series = await rows(
        access,
        TaxRateSeries,
        rule_id=frozenset(entry.rule_id for entry in bindings if entry.rule_id is not None),
    )
    rates = await live_rows(
        access, TaxRate, since=start, series_id=frozenset(entry.id for entry in series)
    )
    classifications = await live_rows(
        access,
        TaxClassification,
        since=start,
        id=frozenset(
            entry.classification_id for entry in bindings if entry.classification_id is not None
        ),
    )
    return dates_for([*assignments, *ancestry, *bindings, *rates, *classifications], start)


async def validate_schedules(
    access: ConfigurationAccess, rules: set[uuid.UUID], start: dt.date
) -> None:
    if not rules:
        return
    series = await rows(access, TaxRateSeries, rule_id=frozenset(rules))
    rates = await live_rows(
        access, TaxRate, since=start, series_id=frozenset(entry.id for entry in series)
    )
    components = await rows(
        access, TaxRateComponent, rate_id=frozenset(entry.id for entry in rates)
    )
    for rule_id in sorted(rules):
        rule = await row(access, TaxRule, rule_id)
        own_series = [entry for entry in series if entry.rule_id == rule_id]
        ids = {entry.id for entry in own_series}
        own_rates = [
            entry
            for entry in rates
            if entry.series_id in ids and (entry.valid_to is None or entry.valid_to >= start)
        ]
        definitions = {}
        for rate in own_rates:
            await access.require(rate)
            parent = next(entry for entry in own_series if entry.id == rate.series_id)
            await access.require(parent)
            entries = []
            for component in components:
                if component.rate_id != rate.id:
                    continue
                await access.require(component)
                entries.append(component)
            definitions[rate.id] = signature(
                stored_components(parent.applicability, rule.treatment, entries)
            )
        for date in dates_for(own_rates, start):
            effective = [
                entry
                for entry in own_rates
                if entry.valid_from <= date and (entry.valid_to is None or entry.valid_to >= date)
            ]
            if len({entry.series_id for entry in effective}) != len(effective):
                raise ConflictError("tax schedule contains overlapping live rates")
            signatures = {definitions[entry.id] for entry in effective}
            if len(signatures) > 1:
                raise ConflictError(
                    "effective GST or compensation cess disagrees across supply contexts"
                )


async def affected_items(
    access: ConfigurationAccess,
    scopes: set[uuid.UUID],
    start: dt.date,
    *,
    after: uuid.UUID | None = None,
    chunk: int | None = None,
) -> list[Item]:
    """Every affected product, or with ``chunk`` the next bounded page after ``after``.

    Synchronous previews stay capped; a background impact review pages through any size.
    """
    if not scopes:
        return []
    owners = await rows(access, CatalogTaxScope, id=frozenset(scopes))
    for owner in owners:
        await access.require(owner)
    await protected(access, Item)
    company = any(entry.owner_kind == "COMPANY" for entry in owners)
    families = {entry.family_id for entry in owners if entry.family_id is not None}
    items = {entry.item_id for entry in owners if entry.item_id is not None}
    groups = {entry.group_id for entry in owners if entry.group_id is not None}
    if groups:
        pending = groups.copy()
        while pending:
            edges = await rows(
                access, ItemGroupParent, since=start, parent_group_id=frozenset(pending)
            )
            for edge in edges:
                await access.require(edge)
            pending = {entry.group_id for entry in edges} - groups
            groups |= pending
            if len(groups) > 8192:
                raise ConflictError("tax descendants exceed bounded review capacity")
        for entry in await rows(
            access, FamilyGroupAssignment, since=start, group_id=frozenset(groups)
        ):
            if entry.group_id in groups and (entry.valid_to is None or entry.valid_to >= start):
                await access.require(entry)
                families.add(entry.family_id)
    statement = select(Item).where(Item.company_id == access.company, Item.status != "DISCONTINUED")
    if not company:
        statement = statement.where(or_(Item.id.in_(items), Item.family_id.in_(families)))
    if after is not None:
        statement = statement.where(Item.id > after)
    bound = MAX_ITEMS if chunk is None else chunk
    found = list(await access.db.scalars(statement.order_by(Item.id).limit(bound + 1)))
    if len(found) > bound:
        if chunk is None:
            raise ConflictError("tax impact exceeds 256 products; start a background impact review")
        found = found[:bound]
    for item in found:
        await access.require(item)
    return found


async def impact_for(
    access: ConfigurationAccess, scopes: set[uuid.UUID], start: dt.date, *, enforce: bool
) -> TaxImpact:
    return await evaluate(
        access, await affected_items(access, scopes, start), start, enforce=enforce
    )


async def evaluate(
    access: ConfigurationAccess, items: list[Item], start: dt.date, *, enforce: bool
) -> TaxImpact:
    from catalog.tasks.tax_resolution import resolve

    if not items:
        return TaxImpact(affected_item_ids=[], checked_dates=[], impact=[])
    boundaries = await review_dates(access, items, start)
    if (
        sum(int(item.sellable) + int(item.purchasable) for item in items) * len(boundaries)
        > MAX_CHECKS
    ):
        raise ConflictError("tax impact exceeds 2048 product/date/direction checks")
    impact = []
    for item in items:
        family = await access.reference(ProductFamily, item.family_id)
        work = ProductWork(access.db, access.actor, access.company, family, item, access)
        for date in boundaries:
            for direction, enabled in (("SALE", item.sellable), ("PURCHASE", item.purchasable)):
                if not enabled:
                    continue
                tax_direction = cast(Literal["SALE", "PURCHASE"], direction)
                try:
                    result = await resolve(
                        access,
                        ResolveInput(item_id=item.id, as_of=date, direction=tax_direction),
                        work=work,
                    )
                except ConflictError:
                    if enforce:
                        raise
                    impact.append(
                        ImpactItem(
                            item_id=item.id,
                            direction=tax_direction,
                            as_of=date,
                            status="INVALID",
                            missing=["invalid_configuration"],
                        )
                    )
                    continue
                if enforce and item.status == "ACTIVE" and result.status != "COMPLETE":
                    raise ConflictError(
                        "tax change leaves an active product without complete dated tax definitions"
                    )
                impact.append(
                    ImpactItem(
                        item_id=item.id,
                        direction=result.direction,
                        as_of=date,
                        status=result.status,
                        missing=result.missing,
                    )
                )
    return TaxImpact(
        affected_item_ids=[entry.id for entry in items], checked_dates=boundaries, impact=impact
    )


def blocking(item_status: str, entry: ImpactItem) -> bool:
    """The enforcement rule of ``impact_for``, applied to one stored review result."""
    return entry.status == "INVALID" or (item_status == "ACTIVE" and entry.status != "COMPLETE")


async def validate_changes(work: TaxWork) -> TaxImpact:
    scopes, today = await change_scopes(work)
    if work.impact_review is not None:
        # A COMPLETE background review of this exact input at this policy generation already
        # evaluated every affected product; nothing it read can have changed since.
        return TaxImpact(affected_item_ids=[], checked_dates=[], impact=[])
    return await impact_for(work.access, scopes, today, enforce=True)


async def change_scopes(work: TaxWork) -> tuple[set[uuid.UUID], dt.date]:
    """Validate schedules and dependent intervals; return the owner scopes whose products change."""
    access = work.access
    today = business_date((await access.context(TaxRule)).company.timezone)
    rules: set[uuid.UUID] = set()
    classification_ids = set()
    binding_ids = set()
    for (model, _), value in work.touched.items():
        if model is TaxRate:
            rules.add((await row(access, TaxRateSeries, value.series_id)).rule_id)
        elif model is TaxRuleApplicability:
            rules.add(value.rule_id)
        elif model is TaxClassification:
            classification_ids.add(value.id)
        elif model is CatalogTaxBinding:
            binding_ids.add(value.id)
    if not (rules or classification_ids or binding_ids):
        return set(), today
    await validate_schedules(access, rules, today)
    relevant = []
    for key, ids in (
        ("id", binding_ids),
        ("classification_id", classification_ids),
        ("rule_id", rules),
    ):
        if ids:
            filters: dict[str, Any] = {key: frozenset(ids)}
            relevant += await live_rows(access, CatalogTaxBinding, since=today, **filters)
    bindings = list({entry.id: entry for entry in relevant}.values())
    scopes = set()
    for binding in bindings:
        if (
            binding.id in binding_ids
            or binding.classification_id in classification_ids
            or binding.rule_id in rules
        ):
            await access.require(binding)
            scopes.add(binding.scope_id)
            if binding.classification_id is not None:
                classification = await row(access, TaxClassification, binding.classification_id)
                await require_live(access, classification)
                if classification.valid_from > binding.valid_from or (
                    classification.valid_to is not None
                    and (binding.valid_to is None or classification.valid_to < binding.valid_to)
                ):
                    raise ConflictError(
                        "classification change would invalidate a dependent binding interval"
                    )
    # Withdrawn bindings still affect the owner whose inherited behavior changes.
    scopes.update(
        value.scope_id for (model, _), value in work.touched.items() if model is CatalogTaxBinding
    )
    return scopes, today
