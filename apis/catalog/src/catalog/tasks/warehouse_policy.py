"""Location lifecycle rules that hold whoever wrote the row.

Deliberately free of the command framework: ``tasks/classification.py`` imports this at
module level, the same shape as the handling and inventory-template master validators.
"""

import datetime as dt
import uuid
from collections.abc import Collection, Mapping
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from billing_platform.gateway import Actor
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.warehouses import TRANSIT_CODE, assert_additional_locations
from catalog.models.classification import ClassificationMaster
from catalog.models.warehouse_groups import WarehouseGroupAssignment
from catalog.models.warehouse_policies import (
    ItemReplenishmentPolicy,
    ItemWarehousePermission,
    ItemWarehousePolicy,
)
from catalog.models.warehouses import (
    DEFAULT_POINTERS,
    CompanyWarehouseConfiguration,
    Warehouse,
    WarehouseBin,
)
from catalog.tasks.acknowledgements import assert_retirable
from catalog.tasks.reference_locations import LOCATION_CODES, assert_reference_location

#: What no actor may change on a built-in location: the codes are referenced by id from
#: the company configuration row and the reserved-code check ties them to ``is_system``,
#: so a rename or retirement would strand the fallback. The label stays editable
#: (docs/catalog-warehouses.md §1).
RESERVED_FIELDS = frozenset({"code", "kind", "is_system", "is_active"})
#: Product-owned tables that point at a location and so gate its retirement (§5).
POLICY_DEPENDENTS: tuple[Any, ...] = (ItemWarehousePermission, ItemReplenishmentPolicy)


async def default_pointer(
    db: AsyncSession, model: Any, company: uuid.UUID, warehouse: uuid.UUID
) -> bool:
    """Is this location a current activity default at the company or the product level?

    One query shape for both, because the four columns *are* the same four by name: the same
    operations resolve through both levels, and a fence that read only one list of names would
    let a retirement strand the other (docs/catalog-warehouses.md §3).

    The product level is checked in its own right rather than inferred from the membership rows
    below. The write path keeps every pointer inside the product's membership, but that is
    application logic: if a pointer ever outlived its membership, "reassign the default" is a
    far better answer than a resolution failure on a document weeks later.
    """
    return (
        await db.scalar(
            select(model.id)
            .where(
                model.company_id == company,
                or_(*(getattr(model, key) == warehouse for key in DEFAULT_POINTERS)),
            )
            .limit(1)
        )
        is not None
    )


async def product_dependency(db: AsyncSession, company: uuid.UUID, warehouse: uuid.UUID) -> bool:
    """Does any product still name this location in a live policy or replenishment band?

    Both tables are indexed on ``(tenant, company, warehouse_id, is_active)`` precisely so
    this stays two bounded lookups rather than a scan. Retired rows are ignored: they are
    history, and history is what makes retirement safe rather than what blocks it.
    """
    for model in POLICY_DEPENDENTS:
        found = await db.scalar(
            select(model.id)
            .where(
                model.company_id == company,
                model.warehouse_id == warehouse,
                model.is_active.is_(True),
            )
            .limit(1)
        )
        if found is not None:
            return True
    return False


async def group_dependency(
    db: AsyncSession, company: uuid.UUID, warehouse: uuid.UUID, *, today: dt.date
) -> bool:
    """Does this location still report to a group?

    An open membership interval is a live reporting relationship: every rollup over that group
    includes this location, and retiring it underneath one would silently change what last
    month's group total means. Closing the membership first is the reviewed action, and the
    closed interval is what keeps the old rollup explicable (docs/catalog-warehouses.md §3).
    """
    return (
        await db.scalar(
            select(WarehouseGroupAssignment.id)
            .where(
                WarehouseGroupAssignment.company_id == company,
                WarehouseGroupAssignment.warehouse_id == warehouse,
                (WarehouseGroupAssignment.valid_to.is_(None))
                | (WarehouseGroupAssignment.valid_to >= today),
            )
            .limit(1)
        )
        is not None
    )


async def assert_location_retirable(
    db: AsyncSession, row: Warehouse, *, actor: Actor, today: dt.date
) -> None:
    """The two halves of the retirement fence: Catalog's own, then the consumers' (§5).

    Catalog's half runs first and every failure in it is a 409 the caller can act on — a
    pointer to reassign, a bin to retire, a product policy to restate. Only then does the
    coordinated half run, because a caller told "no consumer has cleared this" would otherwise
    go asking Billing about a retirement Catalog was going to refuse anyway.

    ``warehouse.deactivate`` is demanded here rather than at the route: the classification
    pipeline authorizes ``warehouse.manage`` for every write, and retirement is the one location
    action that can strand stock, so it carries its own key
    (libs/platform ``permissions.py``, docs/roles-permissions.md).
    """
    actor.require_scope("warehouse.deactivate", target=ScopePath(company_id=row.company_id))
    if await default_pointer(db, CompanyWarehouseConfiguration, row.company_id, row.id):
        raise ConflictError("reassign the company activity default before retiring a location")
    active_bin = (
        select(WarehouseBin.id)
        .where(
            WarehouseBin.company_id == row.company_id,
            WarehouseBin.warehouse_id == row.id,
            WarehouseBin.is_active.is_(True),
        )
        .limit(1)
    )
    if await db.scalar(active_bin) is not None:
        raise ConflictError("retire the location's bins before retiring the location")
    if await default_pointer(db, ItemWarehousePolicy, row.company_id, row.id):
        raise ConflictError("reassign the product activity default before retiring a location")
    if await product_dependency(db, row.company_id, row.id):
        raise ConflictError("restate the products stocked here before retiring a location")
    if await group_dependency(db, row.company_id, row.id, today=today):
        raise ConflictError("close the location's group membership before retiring it")
    # Deferred: both modules reach the classification pipeline that imports this one. The
    # alternative is restating "which release is in force" and "which policy revision is open"
    # here, and a second copy of either rule is exactly the drift this fence cannot afford.
    from catalog.tasks.releases import release_in_force
    from catalog.tasks.warehouse_operations import open_revision

    release = await release_in_force(db, row.company_id, today)
    if release is None:
        raise ConflictError("publish a stock-location policy release before retiring a location")
    revision = await open_revision(db, row.company_id, row.id)
    if revision is None:
        raise ConflictError("this location has no reviewed operation policy to clear")
    from catalog.domain.policy_release import RETIREMENT_AGGREGATE
    from catalog.schemas.acknowledgements import AcknowledgementEvent
    from catalog.tasks.acknowledgements import ingest
    from catalog.tasks.stock_retirement import check

    clearance = await check(db, actor, row)
    await ingest(
        db,
        message_id=clearance.check_id,
        consumer="billing",
        companies={actor.tenant_id: frozenset({row.company_id})},
        event=AcknowledgementEvent(
            tenant_id=actor.tenant_id,
            company_id=row.company_id,
            release_id=release.id,
            release_revision=release.revision,
            aggregate=RETIREMENT_AGGREGATE,
            aggregate_id=row.id,
            enforced_revision=revision.revision,
            result="APPLIED",
            acknowledged_at=clearance.checked_at,
        ),
    )
    await assert_retirable(
        db,
        row.company_id,
        warehouse_id=row.id,
        in_force_release=release.revision,
        policy_revision=revision.revision,
    )


async def validate_bin(db: AsyncSession, row: WarehouseBin, before: Mapping[str, Any]) -> None:
    """A bin is a subdivision of one real location, on create and for the rest of its life.

    The location is part of the bin's identity, so it never moves: ``A1`` in one godown and
    ``A1`` in another are two bins, and rewriting the parent would silently relabel stock
    history that was recorded against the first (docs/catalog-warehouses.md §4).
    """
    creating = not before
    if not creating and row.warehouse_id != before["warehouse_id"]:
        raise ConflictError("a bin belongs to one location; create a bin in the other instead")
    if not (creating or (row.is_active and not before["is_active"])):
        return
    parent = await company_object(db, Warehouse, row.warehouse_id, company_id=row.company_id)
    if not parent.is_active:
        raise ConflictError("bin location is inactive")
    if parent.kind == "INTERNAL_TRANSIT":
        raise ConflictError("internal transit custody records no physical location facts")


def assert_groupable(row: ClassificationMaster) -> None:
    """Internal transit is custody, not a place: it belongs to no reporting dimension.

    A membership change alters no column on the location, so ``validate_location`` sees an
    empty changed set and the reserved-row rule never fires. The rule still holds, so it is
    asserted here instead (docs/catalog-warehouses.md §1, §3).
    """
    if isinstance(row, Warehouse) and row.kind == "INTERNAL_TRANSIT":
        raise ConflictError("internal transit custody records no physical location facts")


async def validate_location(
    db: AsyncSession,
    row: ClassificationMaster,
    before: Mapping[str, Any],
    *,
    features: Collection[str],
    actor: Actor,
    today: dt.date,
) -> None:
    """Lifecycle rules for a location and its bins. ``before`` is empty on create."""
    if isinstance(row, WarehouseBin):
        if before and before["is_active"] and not row.is_active:
            from catalog.tasks.stock_retirement import check

            await check(db, actor, row)
        await validate_bin(db, row, before)
        return
    if not isinstance(row, Warehouse):
        return
    changed = frozenset(key for key, value in before.items() if getattr(row, key) != value)
    reactivating = bool(before) and row.is_active and not before["is_active"]
    if before:
        if before["is_system"]:
            if changed & RESERVED_FIELDS:
                raise ConflictError("the built-in location's identity and lifecycle are reserved")
            if before["code"] == TRANSIT_CODE and changed - {"name"}:
                raise ConflictError("internal transit custody records no physical location facts")
        elif reactivating:
            # Reactivation is a second usable location just as much as a create is.
            assert_additional_locations(features)
    if row.tax_registration_id is not None and (
        not before
        or any(
            getattr(row, key) != before.get(key)
            for key in ("tax_registration_id", "country_code", "state_code", "is_active")
        )
    ):
        from catalog.tasks.warehouse_tax import validate_registration

        validate_registration(row, actor, today=today)
    # Runs after the reserved-row rules, so a built-in still refuses the edit for the reason
    # that matters. On create ``before`` is empty and ``.get`` reads as "nothing named yet", so
    # any code present is a fresh selection; reactivation re-selects the stored pair as it now
    # stands, which is where a code withdrawn from ISO since is caught.
    if reactivating or any(getattr(row, key) != before.get(key) for key in LOCATION_CODES):
        await assert_reference_location(
            db, subject="location", country_code=row.country_code, state_code=row.state_code
        )
    if "is_active" in changed and not row.is_active:
        await assert_location_retirable(db, row, actor=actor, today=today)
