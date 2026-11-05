"""Bounded declared price coverage and read-only publication history review."""

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy import or_, select

from catalog.models import ItemUnitRevision
from catalog.models.pricing import (
    CommercialGuardRule,
    ItemCommercialPolicy,
    ItemMrp,
    ItemPrice,
    ItemPriceDraft,
    ItemPriceSeries,
    ItemReferenceCost,
)
from catalog.schemas.pricing import DraftInput, PricingIssue
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import business_date, protected, row

MAX_HISTORY_ROWS = 1024
MAX_REVIEW_DATES = 64


def day_after(value: dt.date) -> dt.date | None:
    return value + dt.timedelta(days=1) if value < dt.date.max else None


def first_gap(
    intervals: list[tuple[dt.date, dt.date | None]], start: dt.date, end: dt.date | None
) -> dt.date | None:
    cursor = start
    for lower, upper in sorted(intervals, key=lambda entry: entry[0]):
        if upper is not None and upper < start:
            continue
        if lower > (end or dt.date.max):
            break
        if lower > cursor:
            return cursor
        if lower < cursor and cursor != start:
            raise ConflictError("price dependency history is ambiguous")
        if upper is None or upper >= (end or dt.date.max):
            return None
        following = day_after(upper)
        if following is None:
            return None
        cursor = following
    return cursor


@dataclass
class ScheduleReview:
    valid_to: dt.date | None
    issues: list[PricingIssue] = field(default_factory=list)
    source_ids: set[uuid.UUID] = field(default_factory=set)
    dates: set[dt.date] = field(default_factory=set)

    def gap(self, date: dt.date, code: str, message: str) -> None:
        self.issues.append(PricingIssue(code=code, as_of=date, message=message))
        end = date - dt.timedelta(days=1)
        self.valid_to = end if self.valid_to is None else min(self.valid_to, end)


async def history(
    access: ConfigurationAccess,
    model: type[Any],
    start: dt.date,
    end: dt.date | None,
    review: ScheduleReview,
    **filters: Any,
) -> list[Any]:
    await protected(access, model)
    entries = list(
        await access.db.scalars(
            select(model)
            .where(
                model.company_id == access.company,
                *(getattr(model, key) == value for key, value in filters.items()),
                model.valid_from <= (end or dt.date.max),
                or_(model.valid_to.is_(None), model.valid_to >= start),
            )
            .order_by(model.valid_from, model.id)
            .limit(MAX_HISTORY_ROWS + 1)
        )
    )
    if len(entries) > MAX_HISTORY_ROWS:
        raise ConflictError("price dependency history exceeds the review bound")
    previous_end: dt.date | None = start
    for index, entry in enumerate(entries):
        await access.require(entry)
        if index and (previous_end is None or entry.valid_from <= previous_end):
            # Callers query one temporal identity, except the multi-unit guard collection.
            if model is not CommercialGuardRule:
                raise ConflictError("price dependency history is ambiguous")
        previous_end = entry.valid_to
        review.source_ids.add(entry.id)
        review.dates.add(max(start, entry.valid_from))
        if entry.valid_to is not None and (following := day_after(entry.valid_to)) is not None:
            if following <= (end or dt.date.max):
                review.dates.add(following)
    return entries


async def reference_coverage(
    access: ConfigurationAccess,
    model: type[Any],
    start: dt.date,
    end: dt.date | None,
    review: ScheduleReview,
    **filters: Any,
) -> None:
    entries = await history(access, model, start, end, review, **filters)
    gap = first_gap([(entry.valid_from, entry.valid_to) for entry in entries], start, end)
    if gap is not None:
        review.gap(
            gap,
            "SOURCE_COVERAGE_GAP",
            "price reference coverage ends before the requested price interval",
        )


async def coverage(
    access: ConfigurationAccess,
    body: DraftInput,
    series: ItemPriceSeries,
    *,
    sale: bool,
    mrp_required: bool,
    mrp_revision_id: uuid.UUID,
    jurisdiction: str,
    batch_scope: bool = False,
) -> ScheduleReview:
    review = ScheduleReview(valid_to=body.valid_to)
    revision = await row(access, ItemUnitRevision, series.unit_revision_id)
    if revision.valid_to is not None and revision.valid_to < (body.valid_to or dt.date.max):
        following = day_after(revision.valid_to)
        assert following is not None
        review.gap(
            following, "UNIT_COVERAGE_GAP", "price interval extends beyond its unit revision"
        )
    common = {"item_id": series.item_id, "currency": series.currency}
    start, end = body.valid_from, review.valid_to
    if body.formula is not None:
        if body.formula.recipe == "MRP_LESS_PERCENT" and not batch_scope:
            await reference_coverage(
                access,
                ItemMrp,
                start,
                end,
                review,
                **common,
                unit_revision_id=series.unit_revision_id,
                jurisdiction=body.formula.jurisdiction,
            )
        elif body.formula.recipe != "MRP_LESS_PERCENT":
            await reference_coverage(
                access,
                ItemReferenceCost,
                start,
                end,
                review,
                **common,
                unit_revision_id=series.unit_revision_id,
                estimate_kind=body.formula.estimate_kind,
            )
    if sale:
        guards = await history(access, CommercialGuardRule, start, end, review, **common)
        for guard in guards:
            if guard.estimate_kind is not None:
                guard_end = min(end or dt.date.max, guard.valid_to or dt.date.max)
                await reference_coverage(
                    access,
                    ItemReferenceCost,
                    max(start, guard.valid_from),
                    None if guard_end == dt.date.max else guard_end,
                    review,
                    **common,
                    unit_revision_id=guard.unit_revision_id,
                    estimate_kind=guard.estimate_kind,
                )
        mrps = (
            []
            if batch_scope
            else await history(
                access,
                ItemMrp,
                start,
                end,
                review,
                **common,
                unit_revision_id=mrp_revision_id,
                jurisdiction=jurisdiction,
            )
        )
        if mrp_required:
            gap = first_gap([(entry.valid_from, entry.valid_to) for entry in mrps], start, end)
            if gap is not None:
                review.gap(
                    gap,
                    "SOURCE_COVERAGE_GAP",
                    "required MRP coverage ends before the requested price interval",
                )
        await history(access, ItemCommercialPolicy, start, end, review, item_id=series.item_id)
    review.dates = {
        date for date in review.dates if start < date <= (review.valid_to or dt.date.max)
    }
    if len(review.dates) > MAX_REVIEW_DATES:
        raise ConflictError(
            "price schedule exceeds 64 review dates; use shorter dated price revisions"
        )
    return review


@dataclass
class PublicationReview:
    issues: list[PricingIssue]
    predecessor: ItemPrice | None = None


async def publication(access: ConfigurationAccess, draft: ItemPriceDraft) -> PublicationReview:
    if draft.status != "DRAFT":
        return PublicationReview(
            [
                PricingIssue(
                    code="ALREADY_PUBLISHED",
                    as_of=draft.valid_from,
                    message="published drafts cannot be published again",
                )
            ]
        )
    company = (await access.context(ItemPriceDraft)).company
    if draft.valid_from < business_date(company.timezone):
        return PublicationReview(
            [
                PricingIssue(
                    code="PAST_PUBLICATION",
                    as_of=draft.valid_from,
                    message="new pricing history cannot rewrite past dates",
                )
            ]
        )
    await protected(access, ItemPrice)
    overlaps = list(
        await access.db.scalars(
            select(ItemPrice)
            .where(
                ItemPrice.company_id == access.company,
                ItemPrice.series_id == draft.series_id,
                ItemPrice.valid_from <= (draft.valid_to or dt.date.max),
                or_(ItemPrice.valid_to.is_(None), ItemPrice.valid_to >= draft.valid_from),
            )
            .limit(2)
        )
    )
    for price in overlaps:
        await access.require(price)
    if not overlaps:
        return PublicationReview([])
    if len(overlaps) == 1 and overlaps[0].valid_from < draft.valid_from:
        return PublicationReview([], overlaps[0])
    return PublicationReview(
        [
            PricingIssue(
                code="HISTORY_CONFLICT",
                as_of=draft.valid_from,
                message="price overlaps history that cannot be superseded on this effective date",
            )
        ]
    )
