"""Dated tax selection with retained, explicitly withdrawn publication evidence."""

import datetime as dt
import uuid
from typing import Any, TypeVar

from billing_platform.errors import ConflictError
from sqlalchemy import or_, select

from catalog.models.pricing import PricingRow
from catalog.models.tax import CatalogTaxBinding, TaxClassification, TaxRate
from catalog.models.tax_governance import TaxHistoryAction
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.pricing_commands import effective as ordinary_effective
from catalog.tasks.pricing_commands import protected

T = TypeVar("T", bound=PricingRow)
DATED = (TaxClassification, TaxRate, CatalogTaxBinding)
MAX_ROWS = 8192


async def rows(
    access: ConfigurationAccess,
    model: type[Any],
    *,
    on: dt.date | None = None,
    since: dt.date | None = None,
    **filters: Any,
) -> list[Any]:
    await protected(access, model)
    key = (model, on, since, tuple(sorted(filters.items())))
    if key not in access.tax_rows:
        statement = select(model).where(model.company_id == access.company)
        for name, value in filters.items():
            column = getattr(model, name)
            statement = statement.where(
                column.in_(value) if isinstance(value, tuple | frozenset) else column == value
            )
        if on is not None:
            statement = statement.where(
                model.valid_from <= on, or_(model.valid_to.is_(None), model.valid_to >= on)
            )
        if since is not None:
            statement = statement.where(or_(model.valid_to.is_(None), model.valid_to >= since))
        found = list(await access.db.scalars(statement.limit(MAX_ROWS + 1)))
        if len(found) > MAX_ROWS:
            raise ConflictError("tax review exceeds its bounded history; narrow the change scope")
        access.tax_rows[key] = found
    return access.tax_rows[key]


async def withdrawn(access: ConfigurationAccess, **filters: Any) -> set[tuple[str, uuid.UUID]]:
    actions = await rows(access, TaxHistoryAction, action="WITHDRAW", **filters)
    for action in actions:
        await access.require(action)
    return {(entry.resource, entry.target_id) for entry in actions if entry.action == "WITHDRAW"}


async def live_rows(
    access: ConfigurationAccess,
    model: type[T],
    *,
    on: dt.date | None = None,
    since: dt.date | None = None,
    **filters: Any,
) -> list[T]:
    values = await rows(access, model, on=on, since=since, **filters)
    if not values:
        return []
    excluded = await withdrawn(
        access, resource=model.__tablename__, target_id=tuple(entry.id for entry in values)
    )
    return [entry for entry in values if (model.__tablename__, entry.id) not in excluded]


async def require_live(access: ConfigurationAccess, value: Any) -> None:
    if (value.__tablename__, value.id) in await withdrawn(
        access, resource=value.__tablename__, target_id=value.id
    ):
        raise ConflictError("selected tax definition has been withdrawn")


async def effective(
    access: ConfigurationAccess, model: type[Any], as_of: dt.date, **filters: Any
) -> Any:
    if model not in DATED:
        return await ordinary_effective(access, model, as_of, **filters)
    found = [
        entry
        for entry in await live_rows(access, model, on=as_of, **filters)
        if all(getattr(entry, key) == value for key, value in filters.items())
        and entry.valid_from <= as_of
        and (entry.valid_to is None or entry.valid_to >= as_of)
    ]
    if len(found) > 1:
        raise ConflictError("ambiguous effective tax history")
    if found:
        await access.require(found[0])
        return found[0]
    return None
