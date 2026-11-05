"""Stage Catalog GST publications on the outbox (docs/tax-accounting-plan.md Phase 5).

Called from ``TaxWork.published`` after the company generation bump, and by the backfill. It
only stages rows on the caller's session: the command's own transaction commits the tax change,
its audit events and these publications together, and a rollback leaves none of them.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from billing_platform.outbox import emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.events.tax_publication import (
    CLASSIFICATION_EVENT,
    RATE_EVENT,
    RULE_EVENT,
    classification_payload,
    rate_payload,
    rule_payload,
)
from catalog.models.classification import CatalogPolicyState
from catalog.models.tax import (
    TaxClassification,
    TaxRate,
    TaxRateComponent,
    TaxRateSeries,
    TaxRule,
)

#: Replica dependency order: a rate names its rule, so rules precede rates in one generation.
ORDER: tuple[type[Any], ...] = (TaxClassification, TaxRule, TaxRate)
EVENTS: Mapping[type[Any], str] = {
    TaxClassification: CLASSIFICATION_EVENT,
    TaxRule: RULE_EVENT,
    TaxRate: RATE_EVENT,
}


def aggregate_type(model: type[Any]) -> str:
    return "catalog." + str(model.__tablename__)


async def rate_parts(
    db: AsyncSession, rates: Iterable[TaxRate]
) -> tuple[dict[uuid.UUID, TaxRateSeries], dict[uuid.UUID, list[TaxRateComponent]]]:
    """Series and components of the given rates in two bounded reads."""
    values = list(rates)
    if not values:
        return {}, {}
    series = {
        entry.id: entry
        for entry in await db.scalars(
            select(TaxRateSeries).where(TaxRateSeries.id.in_({value.series_id for value in values}))
        )
    }
    components: dict[uuid.UUID, list[TaxRateComponent]] = {value.id: [] for value in values}
    for entry in await db.scalars(
        select(TaxRateComponent).where(TaxRateComponent.rate_id.in_(components))
    ):
        components[entry.rate_id].append(entry)
    return series, components


def payload(
    value: Any,
    generation: int,
    action: str,
    series: Mapping[uuid.UUID, TaxRateSeries],
    components: Mapping[uuid.UUID, list[TaxRateComponent]],
) -> dict[str, Any]:
    if isinstance(value, TaxClassification):
        return classification_payload(value, generation, action)
    if isinstance(value, TaxRule):
        return rule_payload(value, generation, action)
    if value.series_id not in series:
        raise ValueError("tax rate series is unavailable")
    return rate_payload(value, series[value.series_id], components[value.id], generation, action)


async def stage(db: AsyncSession, generation: int, changes: Iterable[tuple[Any, str]]) -> int:
    """Stage one event per ``(row, action)`` at ``generation``; returns how many."""
    entries = sorted(changes, key=lambda change: (ORDER.index(type(change[0])), str(change[0].id)))
    series, components = await rate_parts(
        db, [value for value, _ in entries if isinstance(value, TaxRate)]
    )
    for value, action in entries:
        emit(
            db,
            aggregate_type=aggregate_type(type(value)),
            aggregate_id=value.id,
            event_type=EVENTS[type(value)],
            payload=payload(value, generation, action, series, components),
            tenant_id=value.tenant_id,
        )
    return len(entries)


async def emit_publications(
    db: AsyncSession,
    state: CatalogPolicyState,
    publications: Mapping[tuple[type[Any], uuid.UUID], str],
) -> int:
    """Stage what one tax command changed, at the generation it just bumped to."""
    await db.flush()
    rows: list[tuple[Any, str]] = []
    for (model, ident), action in publications.items():
        value = await db.get(model, ident)
        if value is None or value.company_id != state.company_id:
            raise ValueError("published tax row left the command's company")
        rows.append((value, action))
    return await stage(db, state.generation, rows)


__all__ = ["EVENTS", "ORDER", "aggregate_type", "emit_publications", "payload", "stage"]
