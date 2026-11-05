"""Tax readiness across every known future effective-date boundary."""

import datetime as dt
from typing import Any, Literal, cast

from billing_platform.errors import ConflictError

from catalog.schemas.tax import ResolveInput
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.tax_integrity import review_dates
from catalog.tasks.tax_resolution import Pins, resolve


async def coverage(
    work: ProductWork, start: dt.date, pins: Pins
) -> tuple[list[dict[str, Any]], list[str]]:
    assert work.item is not None
    if not (work.item.sellable or work.item.purchasable):
        return [], []
    access = work.access
    from catalog.models.products import Item

    company = (await access.context(Item)).company
    if company.default_tax_system == "none":
        return [], []
    boundaries = await review_dates(access, [work.item], start)
    taxes: list[dict[str, Any]] = []
    missing = []
    for date in boundaries:
        for direction, enabled in (
            ("SALE", work.item.sellable),
            ("PURCHASE", work.item.purchasable),
        ):
            if not enabled:
                continue
            prefix = "tax:" + direction + ":" + (str(date) + ":" if date != start else "")
            try:
                result = await resolve(
                    access,
                    ResolveInput(
                        item_id=work.item.id,
                        as_of=date,
                        direction=cast(Literal["SALE", "PURCHASE"], direction),
                    ),
                    work=work,
                )
            except ConflictError:
                missing.append(prefix + "invalid_configuration")
                continue
            # Resolution values and their row/version pins are reviewed below.
            # A refreshed Identity transport watermark alone is not a tax change.
            taxes.append(result.model_dump(mode="json", exclude={"source_version"}))
            missing += [prefix + entry for entry in result.missing]
            for pin in result.sources:
                pins.rows[pin.entity_type, pin.entity_id] = pin
    return taxes, missing
