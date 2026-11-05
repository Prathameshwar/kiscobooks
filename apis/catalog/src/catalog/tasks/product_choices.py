"""Apply explicit option prohibitions while a product draft is being authored."""

import datetime as dt
from collections.abc import Mapping
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError

from catalog.models.products import ProductFamily
from catalog.schemas.configuration import EffectiveQuery
from catalog.tasks.configuration_resolution import resolve
from catalog.tasks.product_commands import ProductWork

ASSIGNMENT_OPTIONS = {"brand_id": "brand", "series_id": "brand", "model_code": "model"}


async def require_assignments(
    work: ProductWork,
    before: Mapping[str, Any],
    *,
    as_of: dt.date | None = None,
) -> None:
    """Permit clearing or retaining old data; check every new descriptive assignment."""
    changed = {
        option
        for field, option in ASSIGNMENT_OPTIONS.items()
        if (value := getattr(work.family, field)) and str(value) != str(before.get(field))
    }
    if changed:
        # Reference resolution refreshes ORM identities from the database. The
        # caller has already checked field writes and references; retain those
        # edits inside this transaction before resolving the applicable policy.
        # A prohibition still rolls back the complete command and its audit.
        await work.db.flush()
    for option in sorted(changed):
        await require_choice(work, option, as_of=as_of)


async def require_choice(work: ProductWork, option: str, *, as_of: dt.date | None = None) -> None:
    if option == "variants":
        from catalog.tasks.product_mode import require_advanced

        await require_advanced(work.db, work.company)
    # Local imports avoid the command/requirements cycle. For SKU edits, retain the
    # adopted configuration; family structure uses company/type/group/family controls.
    from catalog.tasks.product_requirements import configuration, group_on

    if as_of is None:
        context = await work.access.context(ProductFamily)
        as_of = utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
    if work.item is not None:
        effective = await configuration(work, as_of)
    else:
        group = await group_on(work, as_of)
        effective = await resolve(
            work.db,
            work.actor,
            work.company,
            EffectiveQuery(
                as_of=as_of,
                kind=cast(Literal["GOODS", "SERVICE"], work.family.kind),
                family_id=work.family.id,
                group_id=group.group_id if group else None,
            ),
        )
    if getattr(effective.options, option + "_mode") == "DISABLED":
        raise ValidationFailedError("product configuration disables this native choice")
