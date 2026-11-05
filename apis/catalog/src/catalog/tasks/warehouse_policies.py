"""Per-product stock-location policies and replenishment bands.

docs/catalog-warehouses.md §2, §3. Both endpoints state the **whole** policy, the same way
the location's own operation policy does: an omitted location or an omitted band could
neither quietly keep nor quietly drop what it replaces, and the reviewer approving the
change sees exactly what the resolver will read.

What this module writes, ``domain/warehouse_policy_composition`` decides the shape of, and
nothing here re-decides:

* A product restriction **narrows, never widens**. The location's reviewed revision is the
  ceiling; a write naming an operation the location does not allow is refused rather than
  trimmed, so the stored flags mean what was approved.
* A **missing row is the documented baseline**, not a guess and not a caller-supplied
  claim. Adding these tables changed no existing product's reach.
* A **stock location is for stock**. A service, or goods a type calls non-stock, is
  rejected outright.

Writing needs ``item_warehouse_policy.manage``; reading needs ``item_warehouse_policy.read``
*and* ``warehouse.read``, because these projections answer with location identities and
composed operations. A reader who may not see the company's locations must not be able to
enumerate them through one of its products.

There is no publish key here by design: none of these rows posts, moves money or allocates
a number, and the location's own reviewed policy is still the ceiling. The command boundary
still demands ``manage`` for the publication gate, since the bodies carry expectations.
"""

import uuid
from collections.abc import Collection, Mapping, Sequence
from decimal import Decimal
from typing import Any, TypeVar

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.money import MoneyError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.units import QuantityRule
from catalog.domain.warehouse_policy_composition import (
    ALLOW_ALL_ACTIVE,
    ProductPermission,
    ProductPolicy,
    Replenishment,
    assert_narrows,
    assert_stock_allocatable,
)
from catalog.domain.warehouse_resolution import (
    ACTIVITY_DEFAULTS,
    OPERATIONS,
    SKU_DEFAULT,
    Location,
    allowed_flags,
    assert_can_serve,
)
from catalog.domain.warehouses import OPERATION_FLAGS, assert_selectable
from catalog.models.commercial import ProductTypeRevision
from catalog.models.pricing import PricingRow
from catalog.models.product_definitions import ItemUnitRevision
from catalog.models.products import Item, ProductFamily
from catalog.models.tax import ItemInventoryProfile
from catalog.models.warehouse_policies import (
    ITEM_WIDE_SCOPE,
    WAREHOUSE_POLICY_MODELS,
    ItemReplenishmentPolicy,
    ItemWarehousePermission,
    ItemWarehousePolicy,
)
from catalog.models.warehouses import (
    CompanyWarehouseConfiguration,
    Warehouse,
    WarehouseOperationPolicyRevision,
)
from catalog.schemas.warehouse_policies import (
    ItemReplenishmentPolicyInput,
    ItemReplenishmentPolicyView,
    ItemWarehousePolicyInput,
    ItemWarehousePolicyView,
    LocationPermissionDetail,
    ReplenishmentScopeDetail,
    ReplenishmentScopeInput,
)
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import PricingWork, business_date, product, row
from catalog.tasks.product_unit_rules import unit_revisions
from catalog.tasks.warehouse_operations import flag_values, location_state, open_revisions

RowT = TypeVar("RowT", bound=PricingRow)

#: The command framework resolves a receipt's row against this tuple. All three are listed
#: because all three are written under one manage key; only the two parents are returned.
POLICY_MODELS: tuple[type[PricingRow], ...] = WAREHOUSE_POLICY_MODELS

#: Flag column -> the operation kind it governs, for the composed projection. The inverse of
#: ``OPERATIONS``: the wire speaks in operation kinds, the columns in permissions.
OPERATION_KINDS: Mapping[str, str] = {flag: kind for kind, flag in OPERATIONS.items()}

#: How many stored rows one product's policy may accumulate before the projection refuses to
#: answer. Retired rows persist, so this is above the per-request authoring bounds: it is the
#: loud failure that keeps a read from becoming an unbounded query
#: (docs/api-conventions.md).
STORED_LIMIT = 512


class ItemPolicyWork(PricingWork):
    """``PricingWork`` with the publication check moved off ``PricePlan``.

    The base class would resolve the expectation check through pricing's field context, which
    demands ``price_plan.read`` from a stock administrator. Only the entity whose context is
    consulted changes: the generation is the company's and ``source_version`` is the Identity
    checkpoint, so both expectations mean what they mean everywhere else. The command boundary
    has already loaded this entity's context, so consulting it adds no permission demand of
    its own.
    """

    entity_model: type[PricingRow] = ItemWarehousePolicy
    policy_subject = "product location policy"


class ItemReplenishmentWork(ItemPolicyWork):
    """The same, for the band endpoint's own entity."""

    entity_model: type[PricingRow] = ItemReplenishmentPolicy


async def assert_stocked(access: ConfigurationAccess, item: Item, family: ProductFamily) -> None:
    """A stock location is for stock, including at the individual SKU level (§2).

    The type revision is read directly rather than through ``access.reference``: this is a
    domain invariant and none of its fields is projected, so demanding ``product_type.read``
    from a stock administrator would be an unrelated permission for an answer the caller
    never sees.
    """
    revision = await company_object(
        access.db,
        ProductTypeRevision,
        family.product_type_revision_id,
        company_id=access.company,
    )
    assert_stock_allocatable(kind=family.kind, inventory_modes=revision.inventory_modes)
    # Drafts may stage location policy before their inventory profile is selected. An
    # activated mixed-mode SKU, however, is stock only if activation instantiated one.
    if item.status != "DRAFT":
        profile_id = await access.db.scalar(
            select(ItemInventoryProfile.id).where(
                ItemInventoryProfile.company_id == access.company,
                ItemInventoryProfile.item_id == item.id,
            )
        )
        if profile_id is None:
            raise ConflictError("a non-stock product is never stocked at a location")


async def location_configuration(
    access: ConfigurationAccess,
) -> CompanyWarehouseConfiguration:
    """The company's location configuration, read and never provisioned from here.

    Naming a location in a product policy means the location already exists, and
    provisioning is ``warehouse.manage``'s job — a product-policy administrator does not
    hold it. Only ``main_warehouse_id`` is required to be readable: that is the one fact
    this module needs, and the rest of the singleton is another endpoint's projection.

    The permission is resolved before the existence lookup, so an unprovisioned company
    cannot be discovered by an actor without ``warehouse.read``.
    """
    await access.context(CompanyWarehouseConfiguration)
    config = await access.db.scalar(
        select(CompanyWarehouseConfiguration).where(
            CompanyWarehouseConfiguration.company_id == access.company
        )
    )
    if config is None:
        raise NotFoundError("company location configuration is not provisioned")
    await access.require(config, {"main_warehouse_id"})
    return config


async def stored_policy(
    access: ConfigurationAccess, item_id: uuid.UUID
) -> ItemWarehousePolicy | None:
    """This product's stored policy row, or ``None`` — which is the baseline, not a deny."""
    await access.context(ItemWarehousePolicy)
    stored: ItemWarehousePolicy | None = await access.db.scalar(
        select(ItemWarehousePolicy).where(
            ItemWarehousePolicy.company_id == access.company,
            ItemWarehousePolicy.item_id == item_id,
        )
    )
    return stored


async def stored_rows(
    access: ConfigurationAccess, model: type[RowT], item_id: uuid.UUID, *, active_only: bool
) -> list[RowT]:
    """One product's child rows, bounded and ordered so a read is never a scan."""
    table: Any = model
    statement = select(model).where(table.company_id == access.company, table.item_id == item_id)
    if active_only:
        statement = statement.where(table.is_active.is_(True))
    rows = list(await access.db.scalars(statement.order_by(table.id).limit(STORED_LIMIT + 1)))
    if len(rows) > STORED_LIMIT:
        raise ConflictError("this product's stored location policy exceeds the authoring bound")
    return rows


def entry_flags(entry: ItemWarehousePermission) -> frozenset[str]:
    """The set form of one membership row's eight booleans."""
    return allowed_flags({flag: bool(getattr(entry, flag)) for flag in OPERATION_FLAGS})


async def effective_policy(access: ConfigurationAccess, item_id: uuid.UUID) -> ProductPolicy:
    """The product's stored policy as the resolver needs it, or the documented baseline.

    Only active memberships take part. A retired row is history — it is what the location
    deactivation fence and the audit trail read, not a permission that still holds.
    """
    stored = await stored_policy(access, item_id)
    if stored is None:
        return ProductPolicy.baseline()
    await access.require(stored, {"selection_mode"})
    entries = await stored_rows(access, ItemWarehousePermission, item_id, active_only=True)
    return ProductPolicy(
        stored.selection_mode,
        tuple(ProductPermission(entry.warehouse_id, entry_flags(entry)) for entry in entries),
    )


async def selectable_location(
    access: ConfigurationAccess,
    config: CompanyWarehouseConfiguration,
    warehouse_id: uuid.UUID,
    features: Collection[str],
) -> Warehouse:
    """One location this product may name: in scope, selectable and still in service.

    ``row`` resolves the actor's object-level scope first, so a location in another company
    is a 404 and one out of this actor's scope is a 403 before anything else is checked.
    A retired location is refused because the deactivation fence works the other way round
    too: an active policy row is what blocks a retirement (§5).
    """
    warehouse = await row(access, Warehouse, warehouse_id)
    assert_selectable(
        features, is_main=warehouse.id == config.main_warehouse_id, kind=warehouse.kind
    )
    if not warehouse.is_active:
        raise ConflictError("a retired stock location cannot be a product's stock location")
    return warehouse


async def ordering_grid(access: ConfigurationAccess, item_id: uuid.UUID) -> list[ItemUnitRevision]:
    """Every current-or-scheduled unit revision of one product, base units and packs alike.

    Read once per command rather than once per band: the set depends on the product and on
    today's business date, neither of which a band can change, and one body may carry dozens
    of bands. The two reads are separate because the query distinguishes base from derived.
    """
    context = await access.context(ItemUnitRevision)
    today = business_date(context.company.timezone)
    return [
        revision
        for base in (True, False)
        for revision in await unit_revisions(access, item_id, today, base=base)
    ]


def validate_band(
    grid: Sequence[ItemUnitRevision], binding_id: uuid.UUID, band: Replenishment
) -> None:
    """Every quantity must land on the ordering unit's own grid, now and later.

    Current *and* scheduled revisions, like every other quantity in Catalog: a band that
    fits today's grid but not next month's would fail on the purchase order built from it,
    long after the reviewer approved it.

    A binding with no current or scheduled revision is a conflict rather than a validation
    error: the request is well formed, and the product's unit definitions are what is
    missing. The grid holds only *this* product's revisions, so a band cannot be expressed
    in another product's carton.
    """
    revisions = [revision for revision in grid if revision.binding_id == binding_id]
    if not revisions:
        raise ConflictError("the ordering unit has no current or scheduled revision here")
    quantities: tuple[Decimal, ...] = (
        band.safety_quantity,
        band.reorder_quantity,
        band.target_quantity,
        band.min_order_quantity,
        band.order_multiple,
    )
    if band.max_order_quantity is not None:
        quantities += (band.max_order_quantity,)
    for revision in revisions:
        rule = QuantityRule(revision.quantity_decimal_places, revision.quantity_increment)
        for value in quantities:
            try:
                rule.validate(value)
            except MoneyError as exc:
                raise ValidationFailedError(
                    "a replenishment quantity does not fit the ordering unit's quantity grid"
                ) from exc


async def set_policy(
    work: PricingWork, body: ItemWarehousePolicyInput, object_id: uuid.UUID | None
) -> PricingRow:
    """Command handler: state one product's whole location policy.

    The order is deliberate. Every named location is validated against the location's own
    reviewed revision *before* anything is written, and each activity default is validated
    against the **composed** policy — the intersection of the location's flags and the ones
    this policy is about to store. A default that could not serve its own operation would
    otherwise fail weeks later, on a document, with nothing recording why.

    Concurrency is the generation check in ``publication`` plus the company policy lock, not
    a row version per child: the caller stated the policy as a whole, and any competing
    write to it bumps that generation.
    """
    assert object_id is not None
    await work.publication(body)
    item, family = await product(work.access, object_id)
    await assert_stocked(work.access, item, family)
    context = await work.access.context(ItemWarehousePolicy)
    proposals: dict[uuid.UUID, frozenset[str]] = {}
    candidates: dict[uuid.UUID, Location] = {}
    if body.locations:
        config = await location_configuration(work.access)
        revisions = await open_revisions(
            work.db, work.company, [entry.warehouse_id for entry in body.locations]
        )
        for entry in body.locations:
            warehouse = await selectable_location(
                work.access, config, entry.warehouse_id, context.features
            )
            location = location_state(warehouse, config, revisions.get(warehouse.id))
            requested = allowed_flags(
                {flag: bool(getattr(entry, flag)) for flag in OPERATION_FLAGS}
            )
            assert_narrows(location.flags, requested)
            proposals[warehouse.id] = requested
            candidates[warehouse.id] = location
    policy = ProductPolicy(
        body.selection_mode,
        tuple(ProductPermission(key, flags) for key, flags in proposals.items()),
    )
    for column, operation in ACTIVITY_DEFAULTS.items():
        target: uuid.UUID | None = getattr(body, column)
        if target is not None:
            assert_can_serve(
                policy.restrict(candidates[target]),
                operation=operation,
                features=context.features,
                origin=SKU_DEFAULT,
            )
    return await write_policy(work, object_id, body, proposals)


async def write_policy(
    work: PricingWork,
    item_id: uuid.UUID,
    body: ItemWarehousePolicyInput,
    proposals: Mapping[uuid.UUID, frozenset[str]],
) -> PricingRow:
    """Persist the validated policy: upsert what was stated, retire what was not.

    A proposal identical to what is stored writes nothing, exactly as a location's own
    operation policy does. History records reviewed *changes*; a row rewritten to the same
    values would make the trail longer and "when did this become allowed" harder to answer.

    Nothing is deleted. The membership row is what the location deactivation fence reads and
    what the audit trail refers to, so a dropped location is retired instead (rule 4.12).
    """
    stored = await stored_policy(work.access, item_id)
    desired: dict[str, Any] = {
        "selection_mode": body.selection_mode,
        **{column: getattr(body, column) for column in ACTIVITY_DEFAULTS},
    }
    if stored is None:
        stored = await work.new(ItemWarehousePolicy, item_id=item_id, **desired)
    elif any(getattr(stored, key) != value for key, value in desired.items()):
        await work.update(stored, stored.row_version, **desired)
    existing = {
        entry.warehouse_id: entry
        for entry in await stored_rows(
            work.access, ItemWarehousePermission, item_id, active_only=False
        )
    }
    for warehouse_id, flags in proposals.items():
        values: dict[str, Any] = {
            "is_active": True,
            **{flag: flag in flags for flag in OPERATION_FLAGS},
        }
        current = existing.get(warehouse_id)
        if current is None:
            await work.new(
                ItemWarehousePermission, item_id=item_id, warehouse_id=warehouse_id, **values
            )
        elif any(bool(getattr(current, key)) != value for key, value in values.items()):
            await work.update(current, current.row_version, **values)
    for warehouse_id, current in existing.items():
        if warehouse_id not in proposals and current.is_active:
            await work.update(current, current.row_version, is_active=False)
    return stored


def band_values(scope: ReplenishmentScopeInput, band: Replenishment) -> dict[str, Any]:
    """The stored columns of one reviewed band, taken from the validated domain object."""
    return {
        "warehouse_id": scope.warehouse_id,
        "purchase_binding_id": scope.purchase_binding_id,
        "safety_quantity": band.safety_quantity,
        "reorder_quantity": band.reorder_quantity,
        "target_quantity": band.target_quantity,
        "min_order_quantity": band.min_order_quantity,
        "max_order_quantity": band.max_order_quantity,
        "order_multiple": band.order_multiple,
        "lead_time_days": band.lead_time_days,
        "is_active": True,
    }


async def set_replenishment(
    work: PricingWork, body: ItemReplenishmentPolicyInput, object_id: uuid.UUID | None
) -> PricingRow:
    """Command handler: state one product's whole set of replenishment bands.

    A band at a location the product may not be kept at is refused: it would raise orders
    for stock with nowhere to land, and the product's location policy is the place that
    decision belongs. Under the ``ALLOW_ALL_ACTIVE`` baseline every location passes, so a
    product with no stored policy is unaffected.

    An empty body against a product that has no bands at all is a conflict rather than a
    silent success: there is nothing to state and nothing to retire, so there is no reviewed
    row to answer with. A genuine retry of a retirement is the idempotency key's job.
    """
    assert object_id is not None
    await work.publication(body)
    item, family = await product(work.access, object_id)
    await assert_stocked(work.access, item, family)
    context = await work.access.context(ItemReplenishmentPolicy)
    policy = await effective_policy(work.access, object_id)
    config: CompanyWarehouseConfiguration | None = None
    grid: list[ItemUnitRevision] | None = None
    bands: dict[uuid.UUID, tuple[ReplenishmentScopeInput, Replenishment]] = {}
    for scope in body.scopes:
        band = Replenishment(
            safety_quantity=scope.safety_quantity,
            reorder_quantity=scope.reorder_quantity,
            target_quantity=scope.target_quantity,
            min_order_quantity=scope.min_order_quantity,
            max_order_quantity=scope.max_order_quantity,
            order_multiple=scope.order_multiple,
            lead_time_days=scope.lead_time_days,
        )
        if grid is None:
            grid = await ordering_grid(work.access, object_id)
        validate_band(grid, scope.purchase_binding_id, band)
        key = ITEM_WIDE_SCOPE
        if scope.warehouse_id is not None:
            if config is None:
                config = await location_configuration(work.access)
            warehouse = await selectable_location(
                work.access, config, scope.warehouse_id, context.features
            )
            policy.assert_permits(warehouse.id)
            key = warehouse.id
        bands[key] = (scope, band)
    return await write_bands(work, object_id, bands)


async def write_bands(
    work: PricingWork,
    item_id: uuid.UUID,
    bands: Mapping[uuid.UUID, tuple[ReplenishmentScopeInput, Replenishment]],
) -> PricingRow:
    """Persist the validated bands: upsert what was stated, retire what was not."""
    existing = {
        entry.scope_warehouse_id: entry
        for entry in await stored_rows(
            work.access, ItemReplenishmentPolicy, item_id, active_only=False
        )
    }
    written: PricingRow | None = None
    for key, (scope, band) in bands.items():
        values = band_values(scope, band)
        current = existing.get(key)
        if current is None:
            written = await work.new(
                ItemReplenishmentPolicy, item_id=item_id, scope_warehouse_id=key, **values
            )
            continue
        if any(getattr(current, name) != value for name, value in values.items()):
            await work.update(current, current.row_version, **values)
        written = current
    for key, current in existing.items():
        if key not in bands and current.is_active:
            await work.update(current, current.row_version, is_active=False)
            written = current
    if written is None:
        raise ConflictError("this product has no replenishment bands to state or retire")
    return written


async def readable_access(
    db: AsyncSession, actor: Actor, company: uuid.UUID, model: type[PricingRow]
) -> ConfigurationAccess:
    """The read context for one of these projections, with both keys resolved up front.

    ``warehouse.read`` is required as well as ``item_warehouse_policy.read``: these views
    answer with location identities, and a reader who may not see the company's locations
    must not enumerate them through one of its products (§3). The demand is unconditional
    on purpose — making it depend on whether a location-scoped row exists would turn the
    403 itself into an answer.
    """
    access = ConfigurationAccess(db, actor, company)
    await access.context(model)
    await access.context(Warehouse)
    return access


async def policy_view(
    db: AsyncSession, actor: Actor, company: uuid.UUID, item_id: uuid.UUID
) -> ItemWarehousePolicyView:
    """Where this product may be kept, and what it may do at each of those locations.

    ``is_configured`` is the honest distinction: ``false`` with ``ALLOW_ALL_ACTIVE`` says
    "no row, so the location's own policy decides", never "somebody chose this".

    An entry whose ``warehouse_id`` a field policy denies is omitted whole. Returning its
    flags with the identity blanked would still disclose that the product is stocked
    somewhere this reader may not see (docs/field-permissions.md §6).
    """
    access = await readable_access(db, actor, company, ItemWarehousePolicy)
    context = await access.context(ItemWarehousePolicy)
    item = await row(access, Item, item_id)
    stored = await stored_policy(access, item.id)
    state = await policy_state(db, actor, company)
    result: dict[str, Any] = {
        "item_id": item.id,
        "is_configured": stored is not None,
        "policy_generation": state.generation if state else 1,
        "source_version": context.source_version,
        "locations": [],
    }
    if stored is None:
        if "selection_mode" in context.readable():
            result["selection_mode"] = ALLOW_ALL_ACTIVE
        return ItemWarehousePolicyView.model_validate(result)
    values = await access.values(stored)
    readable = context.readable(values)
    result.update(
        {
            key: value
            for key, value in values.items()
            if key in readable and key in ItemWarehousePolicyView.model_fields
        }
    )
    result["locations"] = await membership_view(access, item.id)
    return ItemWarehousePolicyView.model_validate(result)


async def membership_view(
    access: ConfigurationAccess, item_id: uuid.UUID
) -> list[LocationPermissionDetail]:
    """The active memberships, each composed against the location's own reviewed policy.

    Only active rows: a retired membership is history, and returning it would make the
    projection something a client could not state back.

    The composition is reported only when all eight flags are readable on **both** sides —
    the product's row and the location's revision. A partial intersection would read as a
    denial, and a denied location flag must not become visible through a product that was
    narrowed against it (docs/field-permissions.md §6).
    """
    context = await access.context(ItemWarehousePermission)
    reviewed = await access.context(WarehouseOperationPolicyRevision)
    composable = frozenset(OPERATION_FLAGS) <= reviewed.readable()
    entries = await stored_rows(access, ItemWarehousePermission, item_id, active_only=True)
    revisions = await open_revisions(
        access.db, access.company, [entry.warehouse_id for entry in entries]
    )
    details: list[LocationPermissionDetail] = []
    for entry in entries:
        values = await access.values(entry)
        readable = context.readable(values)
        if "warehouse_id" not in readable:
            continue
        revision = revisions.get(entry.warehouse_id)
        detail: dict[str, Any] = {
            "id": entry.id,
            "location_revision": None if revision is None else revision.revision,
            **{
                key: value
                for key, value in values.items()
                if key in readable and key in LocationPermissionDetail.model_fields
            },
        }
        if composable and frozenset(OPERATION_FLAGS) <= readable:
            allowed = frozenset() if revision is None else allowed_flags(flag_values(revision))
            detail["effective_operations"] = sorted(
                OPERATION_KINDS[flag] for flag in allowed & entry_flags(entry)
            )
        details.append(LocationPermissionDetail.model_validate(detail))
    return details


async def replenishment_view(
    db: AsyncSession, actor: Actor, company: uuid.UUID, item_id: uuid.UUID
) -> ItemReplenishmentPolicyView:
    """This product's reviewed bands. No on-hand quantity appears: Catalog owns none.

    A location-scoped band is omitted whole when ``warehouse_id`` is denied, for the same
    reason a membership is: the count of location-scoped bands would otherwise disclose how
    many of the company's locations stock this product.
    """
    access = await readable_access(db, actor, company, ItemReplenishmentPolicy)
    context = await access.context(ItemReplenishmentPolicy)
    item = await row(access, Item, item_id)
    entries = await stored_rows(access, ItemReplenishmentPolicy, item.id, active_only=True)
    state = await policy_state(db, actor, company)
    scopes: list[ReplenishmentScopeDetail] = []
    for entry in entries:
        values = await access.values(entry)
        readable = context.readable(values)
        if entry.warehouse_id is not None and "warehouse_id" not in readable:
            continue
        scopes.append(
            ReplenishmentScopeDetail.model_validate(
                {
                    "id": entry.id,
                    "is_item_wide": entry.warehouse_id is None,
                    **{
                        key: value
                        for key, value in values.items()
                        if key in readable and key in ReplenishmentScopeDetail.model_fields
                    },
                }
            )
        )
    return ItemReplenishmentPolicyView(
        item_id=item.id,
        policy_generation=state.generation if state else 1,
        source_version=context.source_version,
        scopes=scopes,
    )
