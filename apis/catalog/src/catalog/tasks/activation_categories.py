"""Check scheduled classification boundaries and pin their native evidence."""

import datetime as dt

from billing_platform.errors import ConflictError

from catalog.domain.categories import boundaries
from catalog.models.product_definitions import FamilyCategory
from catalog.tasks.category_membership import effective, rows
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_requirements import configuration
from catalog.tasks.tax_resolution import Pins


async def coverage(work: ProductWork, start: dt.date, pins: Pins) -> list[str]:
    history = await rows(work.access, FamilyCategory, FamilyCategory.family_id == work.family.id)
    dates = boundaries(((row.valid_from, row.valid_to) for row in history), start)
    if len(dates) > 128 or len(dates) * len(history) > 100000:
        raise ConflictError("scheduled category activation review exceeds its bounded capacity")
    missing: list[str] = []
    for point in dates:
        current, evidence, required = await effective(work.access, work.family.id, point)
        for value in evidence:
            pins.add(value)
        if point == start:
            # The complete requirements evaluator has already checked today's options.
            continue
        config = await configuration(work, point, proposed=True)
        if not current and config.options.category_mode == "REQUIRED":
            required.append("category")
        if current and config.options.category_mode == "DISABLED":
            required.append("forbidden_category")
        missing.extend("scheduled_" + value + ":" + str(point) for value in required)
    return missing
