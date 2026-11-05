"""Scoped classification commands; company policy lock serializes hierarchy edits."""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeVar, cast
from zoneinfo import ZoneInfo

from billing_platform.authz import ScopePath
from billing_platform.custom_fields import validate_values
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    FeatureNotEnabledError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.features import required_closure
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    canonical_json,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.listing import (
    FilterColumn,
    Page,
    SortColumn,
    apply_filters,
    apply_search,
    fetch_page,
    resolve_sort,
)
from pydantic import BaseModel, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from catalog.domain.classification import GroupNode, ParentInterval, validate_group_history
from catalog.domain.stock_facts import assert_no_stock_facts
from catalog.events.evidence import audit_change as audit_change
from catalog.models.classification import (
    CatalogPolicyState,
    CategoryScheme,
    ClassificationMaster,
    ItemCategory,
    ItemGroup,
    ItemGroupParent,
)
from catalog.models.commercial import Brand, Manufacturer, ProductType
from catalog.models.pricing import ItemPriceSeries
from catalog.models.profiles import IdentifierProfile
from catalog.models.sales_channel import SalesChannel
from catalog.models.warehouse_groups import (
    WarehouseGroup,
    WarehouseGroupAssignment,
    WarehouseGroupParent,
)
from catalog.models.warehouses import Warehouse
from catalog.schemas.classification import (
    CategoryCreate,
    CategoryDetail,
    CategoryListItem,
    ChildrenQuery,
    GroupCreate,
    GroupDetail,
    GroupListItem,
    GroupParentListItem,
    GroupParentQuery,
    MasterInput,
    MasterQuery,
    SchemeCreate,
    SchemeDetail,
    SchemeListItem,
)
from catalog.schemas.warehouses import WarehouseMerge
from catalog.tasks.attribute_policy import validate_attributes
from catalog.tasks.bom_policy import validate_master as validate_bom_master
from catalog.tasks.commercial_policy import validate_brands, validate_commercial
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.custom_fields import allocate_sequence, reserve_claims
from catalog.tasks.field_context import FieldContext, FieldWriteChecks, load_field_context
from catalog.tasks.field_indexes import apply_custom_filters, index_values, write_generations
from catalog.tasks.handling import validate_master as validate_handling_master
from catalog.tasks.identifier_policy import (
    authorize_requirements_replay,
    initialize_requirements,
    validate_identifier_header,
)
from catalog.tasks.inventory_templates import validate_master as validate_inventory_master
from catalog.tasks.listing import cursor_codec
from catalog.tasks.manufacturing_operations import validate_master as validate_operation_master
from catalog.tasks.options import validated_candidates
from catalog.tasks.policy_state import policy_state
from catalog.tasks.product_dependencies import (
    SEMANTIC_FIELDS,
    guard_active_group_move,
    product_dependencies,
)
from catalog.tasks.profile_bindings import validate_lifecycle as validate_profile_lifecycle
from catalog.tasks.returns import validate_master as validate_return_master
from catalog.tasks.warehouse_policy import assert_groupable, validate_location
from catalog.tasks.warranties import validate_master as validate_warranty_master


@dataclass(frozen=True)
class DatedEdge:
    """A dated child row a master's history appends to and closes, never rewrites.

    Two relations share this shape, which is why they share the code: a group's parent
    (``item_group_parent``, ``warehouse_group_parent``) and a location's primary group
    (``warehouse_group_assignment``). ``owner`` names the master's column on the edge and
    ``target`` the other end, so "who was I under on that date" keeps answering what it
    answered then, whichever relation is asking.
    """

    model: type[Any]
    entity: str
    #: The master this edge hangs off, and the row the edge points at.
    owner: str
    target: str
    target_model: type[ClassificationMaster]
    #: A hierarchy's ``NULL`` target is a root, and it is validated for cycles and depth.
    #: A membership's target is ``NOT NULL``: "no group" is the absence of an open
    #: interval, never a row pointing at nothing that a rollup would have to guess about.
    nullable_target: bool = True
    #: What the edge's own field context is loaded with, when that differs from the
    #: master's action permission. Assigning a location to a group is a grouping change,
    #: so it needs the grouping permission on top of authority over the location.
    permission: str | None = None


@dataclass(frozen=True)
class Classification:
    model: type[ClassificationMaster]
    entity: str
    permission: str
    create: type[BaseModel]
    detail: type[BaseModel]
    item: type[BaseModel]
    filters: frozenset[str]
    #: Opened on create, appended to by ``move``.
    hierarchy: DatedEdge | None = None
    #: Appended to by ``assign``. Never opened on create: a location may belong to no group.
    membership: DatedEdge | None = None
    required_feature: str | None = None
    validate: (
        Callable[[AsyncSession, Actor, ClassificationMaster, Mapping[str, Any]], Awaitable[None]]
        | None
    ) = None


#: Create-only inputs on a hierarchy master: they open the first interval rather than
#: describing the master, so an update merge revalidates the identity surface without them.
HIERARCHY_INPUT = frozenset({"parent_group_id", "valid_from"})

GROUP = Classification(
    ItemGroup,
    "catalog.item_group",
    "item_group",
    GroupCreate,
    GroupDetail,
    GroupListItem,
    frozenset({"code", "is_active", "allowed_kind"}),
    hierarchy=DatedEdge(
        ItemGroupParent, "catalog.item_group_parent", "group_id", "parent_group_id", ItemGroup
    ),
)
SCHEME = Classification(
    CategoryScheme,
    "catalog.category_scheme",
    "category_scheme",
    SchemeCreate,
    SchemeDetail,
    SchemeListItem,
    frozenset({"code", "is_active", "membership_mode"}),
)
CATEGORY = Classification(
    ItemCategory,
    "catalog.item_category",
    "item_category",
    CategoryCreate,
    CategoryDetail,
    CategoryListItem,
    frozenset({"code", "is_active", "scheme_id", "parent_id"}),
)


def row_values(row: ClassificationMaster, context: FieldContext) -> dict[str, Any]:
    values = {key: getattr(row, key) for key in context.native.fields}
    if isinstance(row, ItemGroup | ItemCategory | Brand | Manufacturer | ProductType):
        values.update(
            {"custom_field:" + key: value for key, value in (row.custom_fields or {}).items()}
        )
    return values


def protected_detail(
    row: ClassificationMaster, context: FieldContext, spec: Classification, generation: int
) -> BaseModel:
    values = row_values(row, context)
    readable = context.readable(values)
    result = {
        "id": row.id,
        "company_id": row.company_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "policy_generation": generation,
        **{
            key: value
            for key, value in values.items()
            if key in readable and not key.startswith("custom_field:")
        },
    }
    if isinstance(row, ItemGroup | ItemCategory | Brand | Manufacturer | ProductType):
        result["custom_fields"] = {
            key: value
            for key, value in (row.custom_fields or {}).items()
            if "custom_field:" + key in readable
        }
    return spec.detail.model_validate(result)


async def read(
    db: AsyncSession, actor: Actor, company: uuid.UUID, object_id: uuid.UUID, spec: Classification
) -> BaseModel:
    context = await load_field_context(db, actor, company, spec.entity)
    row = await company_object(db, spec.model, object_id, company_id=company)
    state = await policy_state(db, actor, company)
    return protected_detail(row, context, spec, state.generation if state else 1)


async def bounded_rows(db: AsyncSession, model: type[Any], company: uuid.UUID) -> list[Any]:
    """One company's rows, or a refusal. Cycle and depth checks run in memory, so the
    hierarchy has to fit in it; a company past the bound needs a reviewed job, not a
    silently truncated validation."""
    rows = list(await db.scalars(select(model).where(model.company_id == company).limit(10001)))
    if len(rows) > 10000:
        raise ConflictError(
            "hierarchy exceeds synchronous validation bounds; reviewed job required"
        )
    return rows


async def group_history(
    db: AsyncSession, company: uuid.UUID, edge: DatedEdge
) -> tuple[list[ClassificationMaster], list[Any]]:
    return (
        await bounded_rows(db, edge.target_model, company),
        await bounded_rows(db, edge.model, company),
    )


def validate_groups(
    groups: list[ClassificationMaster], parents: list[Any], company: uuid.UUID
) -> None:
    """Cycles and depth, for any dated hierarchy. ``allowed_kind`` is an item-group term;
    hierarchies without one are all-kinds, which constrains nothing on their own edges."""
    validate_group_history(
        tuple(
            GroupNode(
                row.id,
                row.company_id,
                cast(Literal["GOODS", "SERVICE", "BOTH"], getattr(row, "allowed_kind", "BOTH")),
            )
            for row in groups
        ),
        tuple(
            ParentInterval(row.group_id, row.parent_group_id, row.valid_from, row.valid_to)
            for row in parents
        ),
        company_id=company,
    )


async def validate_categories(db: AsyncSession, row: ItemCategory) -> None:
    rows = list(
        await db.scalars(
            select(ItemCategory)
            .where(
                ItemCategory.company_id == row.company_id, ItemCategory.scheme_id == row.scheme_id
            )
            .limit(10001)
        )
    )
    validate_group_history(
        tuple(GroupNode(item.id, item.company_id, "BOTH") for item in rows),
        tuple(ParentInterval(item.id, item.parent_id, dt.date.min, None) for item in rows),
        company_id=row.company_id,
    )


async def validate_custom(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    context: FieldContext,
    incoming: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    previous: Mapping[str, Any],
    *,
    creating: bool,
) -> dict[str, Any]:
    # The one gate every Catalog custom-field write passes through, so the stock-fact refusal
    # sits here rather than on each surface (docs/catalog-warehouse-plan.md, C7.11). Native
    # columns need no guard: `extra="forbid"` already refuses a name Catalog does not own.
    # Keys are reported as the caller spelled them in the body, so the dotted path goes in;
    # `custom_field` heads no reserved phrase, so the prefix cannot manufacture a match.
    assert_no_stock_facts("custom_fields." + key for key in incoming)
    await write_generations(db, context)
    readable = context.readable(before) & context.readable(after)
    condition_readable = readable | frozenset(
        key.removeprefix("custom_field:") for key in readable if key.startswith("custom_field:")
    )

    candidates = await validated_candidates(
        db, actor, company, context, incoming, previous, after, creating=creating
    )

    def options(source: str, parent: Any) -> frozenset[str]:
        return candidates.get((source, str(parent) if parent is not None else None), frozenset())

    try:
        values = validate_values(
            context.definitions,
            incoming,
            previous=previous,
            native_values=after,
            previous_native_values=before,
            creating=creating,
            readable_condition_fields=condition_readable,
            currencies=frozenset(
                {
                    context.company.base_currency,
                    *(value for value in (context.company.reporting_currency,) if value),
                }
            ),
            resolve_options=options,
        )
    except ValidationFailedError as exc:
        # Do not expose protected field identities/defaults through error details.
        raise ValidationFailedError(
            "custom field validation failed",
            fields={
                "custom_fields." + key: value
                for key, value in (exc.extra.get("fields") or {}).items()
                if "custom_field:" + key in readable
            }
            or None,
        ) from exc
    if creating:
        today = utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
        for definition in context.definitions:
            if definition.is_active and definition.data_type == "auto_number":
                config = definition.sequence_config
                assert config is not None
                if config.reset == "fiscal_year":
                    raise ConflictError("fiscal sequence source is unavailable")
                cycle = (
                    today.strftime("%Y-%m")
                    if config.reset == "month"
                    else str(today.year)
                    if config.reset == "calendar_year"
                    else ""
                )
                values[definition.key] = await allocate_sequence(
                    db,
                    company_id=company,
                    entity_type=context.native.entity_type,
                    field_key=definition.key,
                    cycle_key=cycle,
                    prefix=config.prefix,
                    padding=config.padding,
                    start=config.start,
                )
    return values


async def dependencies(
    db: AsyncSession, row: ItemGroup | CategoryScheme | ItemCategory | WarehouseGroup
) -> bool:
    if isinstance(row, WarehouseGroup):
        # Child groups or member locations both make the group's identity and lifecycle
        # something another row already relies on.
        for model, column in (
            (WarehouseGroupParent, WarehouseGroupParent.parent_group_id),
            (WarehouseGroupAssignment, WarehouseGroupAssignment.group_id),
        ):
            if (
                await db.scalar(
                    select(model.id)
                    .where(model.company_id == row.company_id, column == row.id)
                    .limit(1)
                )
                is not None
            ):
                return True
        return False
    if isinstance(row, ItemGroup):
        return (
            await db.scalar(
                select(ItemGroupParent.id)
                .where(
                    ItemGroupParent.company_id == row.company_id,
                    ItemGroupParent.parent_group_id == row.id,
                )
                .limit(1)
            )
            is not None
        )
    if isinstance(row, CategoryScheme):
        return (
            await db.scalar(
                select(ItemCategory.id)
                .where(ItemCategory.company_id == row.company_id, ItemCategory.scheme_id == row.id)
                .limit(1)
            )
            is not None
        )
    return (
        await db.scalar(
            select(ItemCategory.id)
            .where(ItemCategory.company_id == row.company_id, ItemCategory.parent_id == row.id)
            .limit(1)
        )
        is not None
    )


async def category_parent_authority(
    db: AsyncSession, actor: Actor, company: uuid.UUID, row: ItemCategory, *, active: bool = True
) -> None:
    access = ConfigurationAccess(db, actor, company)
    scheme = await access.scoped(CategoryScheme, row.scheme_id)
    await access.require(scheme)
    if active and not scheme.is_active:
        raise ConflictError("category scheme is inactive")
    if row.parent_id is not None:
        parent = await access.scoped(ItemCategory, row.parent_id)
        await access.require(parent)


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    spec: Classification,
    *,
    key: str,
    body: BaseModel,
    action: Literal["create", "update", "activate", "deactivate", "move", "assign"],
    object_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    context: FieldContext | None = None
    parent_context: FieldContext | None = None
    state: CatalogPolicyState | None = None
    #: Which dated relation this action writes, if any. `create` opens a hierarchy's first
    #: interval; `move` appends to it; `assign` appends to the membership relation instead.
    edge = spec.membership if action == "assign" else spec.hierarchy
    if action not in {"create", "move", "assign"}:
        edge = None
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        spec.entity + "." + action,
        key,
        {
            "body": body.model_dump(mode="json", exclude_unset=True),
            "id": str(object_id) if object_id else None,
        },
    )

    retirement_identity = {"operation": identity.operation, "request": identity.request}
    parent_checks: FieldWriteChecks | None = None

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal context, parent_context, state
        owner_permission = spec.permission + (".move" if action == "move" else ".manage")
        context = await load_field_context(
            db, actor, company, spec.entity, permission=owner_permission
        )
        if spec.required_feature is not None and action != "deactivate":
            for required in required_closure(spec.required_feature):
                if required not in context.features:
                    raise FeatureNotEnabledError("company capability is disabled", feature=required)
        if edge is not None:
            parent_context = await load_field_context(
                db, actor, company, edge.entity, permission=edge.permission or owner_permission
            )
        state = await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            row = await company_object(db, spec.model, uuid.UUID(receipt["id"]), company_id=company)
            if isinstance(row, ItemCategory):
                await category_parent_authority(db, actor, company, row, active=False)
            values = row_values(row, context)
            context.assert_writable(frozenset(receipt["changed"]), before=values, after=values)
            if isinstance(row, IdentifierProfile) and receipt.get("requirement_changed"):
                await authorize_requirements_replay(
                    db, actor, company, row.id, frozenset(receipt["requirement_changed"])
                )
            if isinstance(row, Warehouse) and receipt.get("policy_changed"):
                # Deferred: see the create branch.
                from catalog.tasks.warehouse_operations import authorize_policy_replay

                await authorize_policy_replay(
                    db, actor, company, row.id, frozenset(receipt["policy_changed"])
                )
            if parent_context is not None:
                if parent_checks is not None:
                    parent_checks.recheck(parent_context)
                else:
                    # Previous transactions may have changed the hierarchy;
                    # retained receipts cannot bypass new conditional denies.
                    assert_fields_writable(
                        frozenset(receipt.get("parent_changed", [])),
                        rules=parent_context.rules(),
                        target=ScopePath(company_id=company),
                    )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        nonlocal parent_checks
        from catalog.tasks.stock_retirement import COMMAND_HASH

        db.info[COMMAND_HASH] = hashlib.sha256(canonical_json(retirement_identity)).hexdigest()
        parent_checks = FieldWriteChecks()
        assert context is not None and state is not None
        incoming = body.model_dump(exclude_unset=True)
        parent_changed: frozenset[str] = frozenset()
        requirement_changed: frozenset[str] = frozenset()
        policy_changed: frozenset[str] = frozenset()
        before: dict[str, Any] = {}
        after: dict[str, Any]
        if action == "create":
            validated = spec.create.model_validate(incoming).model_dump()
            requirements = (
                validated.pop("requirements", None) if spec.model is IdentifierProfile else None
            )
            custom = validated.pop("custom_fields", {})
            parent_id = validated.pop("parent_group_id", None)
            start = validated.pop("valid_from", None)
            row = spec.model(
                id=uuid7(),
                tenant_id=actor.tenant_id,
                company_id=company,
                created_by=actor.user_id,
                updated_by=actor.user_id,
                row_version=1,
                is_active=True,
                **validated,
            )
            if (
                isinstance(row, ItemGroup)
                and row.code == "GENERAL"
                and (
                    row.allowed_kind != "BOTH"
                    or parent_id is not None
                    or start != dt.date(1000, 1, 1)
                )
            ):
                raise ValidationFailedError("GENERAL is a permanent BOTH root starting 1000-01-01")
            if isinstance(row, ItemCategory):
                await category_parent_authority(db, actor, company, row)
                if row.parent_id is not None:
                    parent = await company_object(
                        db, ItemCategory, row.parent_id, company_id=company
                    )
                    if parent.scheme_id != row.scheme_id or not parent.is_active:
                        raise ValidationFailedError(
                            "category parent must be active in the same scheme"
                        )
            if isinstance(row, CategoryScheme):
                row.is_required = False
            if isinstance(row, IdentifierProfile):
                row.normalization_version = 1
            if isinstance(row, Warehouse):
                # Deferred: the location commands reuse the pricing command framework,
                # which imports this module for audit emission.
                from catalog.tasks.warehouses import prepare_location

                await prepare_location(db, actor, company, state, row, context)
            after = row_values(row, context)
            if isinstance(row, ItemGroup | ItemCategory | Brand | Manufacturer | ProductType):
                row.custom_fields = await validate_custom(
                    db, actor, company, context, custom, {}, after, {}, creating=True
                )
                after = row_values(row, context)
            changed = frozenset(field for field, value in after.items() if value is not None) - {
                "row_version"
            }
            context.assert_writable(changed, before={}, after=after)
            if spec.validate is not None:
                await spec.validate(db, actor, row, {})
            await validate_commercial(
                db, row, {}, today=utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
            )
            await validate_attributes(db, row, {})
            await validate_location(
                db,
                row,
                {},
                features=context.features,
                actor=actor,
                today=utcnow().astimezone(ZoneInfo(context.company.timezone)).date(),
            )
            db.add(row)
            await db.flush()
            if isinstance(row, IdentifierProfile):
                requirement_changed = await initialize_requirements(db, actor, row, requirements)
            if isinstance(row, Warehouse):
                # Deferred, as above: the location commands reuse the pricing command
                # framework, which imports this module for audit emission. Runs after the
                # flush because the revision carries a composite foreign key to this row.
                from catalog.tasks.warehouse_operations import inherit_policy

                policy_changed = await inherit_policy(db, actor, company, state, row)
            if edge is not None:
                assert parent_context is not None and start is not None
                if parent_id is not None:
                    group_parent = await company_object(
                        db, edge.target_model, parent_id, company_id=company
                    )
                    if not group_parent.is_active:
                        raise ConflictError("group parent is inactive")
                child = edge.model(
                    tenant_id=actor.tenant_id,
                    company_id=company,
                    created_by=actor.user_id,
                    updated_by=actor.user_id,
                    **{edge.owner: row.id, edge.target: parent_id},
                    valid_from=start,
                    valid_to=None,
                )
                edge_values = {
                    field: getattr(child, field) for field in parent_context.native.fields
                }
                parent_changed = frozenset(edge_values)
                parent_context.assert_writable(
                    parent_changed, before={}, after=edge_values, checked=parent_checks
                )
                db.add(child)
                await db.flush()
                groups, parents = await group_history(db, company, edge)
                validate_groups(groups, parents, company)
                audit_change(
                    db,
                    actor,
                    company,
                    edge.entity,
                    child.id,
                    "create",
                    parent_changed,
                    before={},
                    after=edge_values,
                )
        else:
            assert object_id is not None
            row = await company_object(db, spec.model, object_id, company_id=company, lock=True)
            if isinstance(row, ItemCategory):
                await category_parent_authority(
                    db, actor, company, row, active=action != "deactivate"
                )
            if row.row_version != incoming.pop("expected_version"):
                raise ConflictError("resource version changed; reload before updating")
            before = row_values(row, context)
            after = dict(before)
            if action in {"move", "assign"}:
                if state.generation != incoming.pop("expected_generation"):
                    raise ConflictError("company policy changed; reload the hierarchy")
                if not row.is_active:
                    raise ConflictError("inactive classification cannot move")
                if edge is not None:
                    assert parent_context is not None
                    assert_groupable(row)
                    parent_changed = await move_edge(
                        db, actor, row, edge, parent_context, incoming, context, parent_checks
                    )
                elif isinstance(row, ItemCategory):
                    parent_id = incoming["parent_id"]
                    if parent_id is not None:
                        access = ConfigurationAccess(db, actor, company)
                        parent = await access.scoped(ItemCategory, parent_id)
                        await access.require(parent)
                        if parent.scheme_id != row.scheme_id or not parent.is_active:
                            raise ValidationFailedError(
                                "category parent must be active in the same scheme"
                            )
                    after["parent_id"] = parent_id
                elif isinstance(row, Brand):
                    after["parent_brand_id"] = incoming["parent_brand_id"]
                else:
                    raise ValidationFailedError("this master cannot move")
            elif action in {"activate", "deactivate"}:
                after["is_active"] = action == "activate"
            else:
                custom = incoming.pop("custom_fields", {})
                if spec.hierarchy is not None:
                    # The create model also opens the first interval. Merge and revalidate
                    # only the identity surface; `valid_from` is supplied to satisfy the
                    # model and discarded, since an update never rewrites history.
                    identity = set(spec.create.model_fields) - {"custom_fields", *HIERARCHY_INPUT}
                    validated = spec.create.model_validate(
                        {
                            **{key: before[key] for key in identity},
                            "valid_from": dt.date(1000, 1, 1),
                            **incoming,
                        }
                    ).model_dump(include=identity)
                elif isinstance(row, ItemCategory):
                    validated = CategoryCreate.model_validate(
                        {
                            **{
                                key: before[key]
                                for key in ("code", "name", "scheme_id", "parent_id")
                            },
                            **incoming,
                        }
                    ).model_dump(exclude={"custom_fields"})
                elif isinstance(row, IdentifierProfile):
                    validated = MasterInput.model_validate(
                        {"code": before["code"], "name": before["name"], **incoming}
                    ).model_dump()
                elif isinstance(row, CategoryScheme):
                    validated = SchemeCreate.model_validate(
                        {
                            **{key: before[key] for key in ("code", "name", "membership_mode")},
                            **incoming,
                        }
                    ).model_dump()
                elif isinstance(row, Warehouse):
                    # `WarehouseCreate` cannot round-trip a stored `INTERNAL_TRANSIT` kind, and
                    # `kind` is not updatable anyway; merge only the updatable surface so a
                    # reserved-row edit reaches `validate_location`'s 409 instead of a 422.
                    validated = WarehouseMerge.model_validate(
                        {**{key: before[key] for key in WarehouseMerge.model_fields}, **incoming}
                    ).model_dump()
                else:
                    validated = spec.create.model_validate(
                        {
                            **{
                                key: before[key]
                                for key in spec.create.model_fields
                                if key != "custom_fields"
                            },
                            **incoming,
                        }
                    ).model_dump(exclude={"custom_fields"})
                after.update(validated)
                if isinstance(row, ItemGroup | ItemCategory | Brand | Manufacturer | ProductType):
                    updated = await validate_custom(
                        db,
                        actor,
                        company,
                        context,
                        custom,
                        before,
                        after,
                        row.custom_fields or {},
                        creating=False,
                    )
                    after.update({"custom_field:" + key: value for key, value in updated.items()})
            changed = frozenset(
                field
                for field in before.keys() | after.keys()
                if before.get(field) != after.get(field)
            )
            context.assert_writable(changed, before=before, after=after)
            category_retirement = isinstance(row, ItemCategory) and action == "deactivate"
            if category_retirement:
                from catalog.models.product_definitions import FamilyCategory
                from catalog.tasks.category_membership import rows as category_rows

                access = ConfigurationAccess(db, actor, company)
                # Lifecycle integrity may inspect membership without exposing product IDs.
                # Field policies still apply under the authorized category management action.
                await access.context(FamilyCategory, "item_category.manage")
                today = utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
                children = await category_rows(
                    access,
                    ItemCategory,
                    ItemCategory.parent_id == row.id,
                    ItemCategory.is_active.is_(True),
                )
                memberships = await category_rows(
                    access,
                    FamilyCategory,
                    FamilyCategory.category_id == row.id,
                    or_(FamilyCategory.valid_to.is_(None), FamilyCategory.valid_to >= today),
                )
                if children or memberships:
                    raise ConflictError(
                        "category has active children or current/future memberships"
                    )
            if (
                isinstance(row, ItemGroup)
                and row.code == "GENERAL"
                and (changed & {"code", "allowed_kind", "is_active"} or parent_changed)
            ):
                raise ConflictError("GENERAL is a permanent root")
            if (
                isinstance(row, ItemGroup | CategoryScheme | ItemCategory | WarehouseGroup)
                and not category_retirement
                and changed & {"code", "is_active", "membership_mode"}
                and await dependencies(db, row)
            ):
                raise ConflictError(
                    "classification is referenced; preserve its identity and lifecycle"
                )
            if (
                isinstance(row, SalesChannel)
                and ("code" in changed or ("is_active" in changed and after["is_active"] is False))
                and await db.scalar(
                    select(ItemPriceSeries.id)
                    .where(
                        ItemPriceSeries.company_id == company,
                        ItemPriceSeries.channel_code == row.code,
                    )
                    .limit(1)
                )
                is not None
            ):
                raise ConflictError("sales channel is referenced by price series")
            if (
                isinstance(row, CategoryScheme)
                and row.is_required
                and after.get("is_active") is False
            ):
                raise ConflictError("retire a required scheme through its reviewed transition")
            if (
                not category_retirement
                and changed & SEMANTIC_FIELDS
                and await product_dependencies(db, row)
            ):
                raise ConflictError("master semantics are referenced by product definitions")
            for field in changed:
                if field.startswith("custom_field:"):
                    assert isinstance(
                        row, ItemGroup | ItemCategory | Brand | Manufacturer | ProductType
                    )
                    row.custom_fields = {
                        **(row.custom_fields or {}),
                        field.removeprefix("custom_field:"): after[field],
                    }
                else:
                    setattr(row, field, after[field])
            await validate_commercial(
                db,
                row,
                before,
                today=utcnow().astimezone(ZoneInfo(context.company.timezone)).date(),
            )
            await validate_attributes(db, row, before)
            await validate_identifier_header(db, row, before)
            await validate_inventory_master(db, row, before)
            await validate_operation_master(db, row, before)
            await validate_bom_master(db, row, before)
            if spec.validate is not None:
                await spec.validate(db, actor, row, before)
            await validate_warranty_master(db, row, before)
            await validate_return_master(db, row, before)
            await validate_handling_master(db, row, before)
            await validate_profile_lifecycle(db, row, before)
            await validate_location(
                db,
                row,
                before,
                features=context.features,
                actor=actor,
                today=utcnow().astimezone(ZoneInfo(context.company.timezone)).date(),
            )
            if changed or parent_changed:
                if row.row_version >= 2**31 - 1:
                    raise ConflictError(
                        "resource version is exhausted; create a replacement definition"
                    )
                row.row_version += 1
                row.updated_at, row.updated_by = utcnow(), actor.user_id
                if "is_active" in changed:
                    row.deactivated_at = None if row.is_active else utcnow()
                    row.deactivated_by = None if row.is_active else actor.user_id
            await db.flush()
            if spec.hierarchy is not None and "allowed_kind" in changed:
                groups, parents = await group_history(db, company, spec.hierarchy)
                validate_groups(groups, parents, company)
        if isinstance(row, Brand):
            await validate_brands(db, row)
        if isinstance(row, ItemCategory):
            await db.flush()
            await validate_categories(db, row)
        if isinstance(row, ItemGroup | ItemCategory | Brand | Manufacturer | ProductType):
            await reserve_claims(
                db,
                company_id=company,
                entity_type=spec.entity,
                entity_id=row.id,
                definitions=context.definitions,
                values=row.custom_fields or {},
            )
        if isinstance(row, ItemGroup | ItemCategory | Brand | Manufacturer | ProductType):
            await index_values(db, context, row.id, row.custom_fields or {})
        if changed or parent_changed or requirement_changed or policy_changed:
            if state.generation >= 2**63 - 1:
                raise ConflictError("company policy generation is exhausted")
            state.generation += 1
            audit_change(
                db,
                actor,
                company,
                spec.entity,
                row.id,
                action,
                changed
                | frozenset({"hierarchy"} if parent_changed else ())
                | frozenset({"requirements"} if requirement_changed else ())
                | frozenset({"operations"} if policy_changed else ()),
                before=before,
                after=after,
            )
        await db.flush()
        return CommandReceipt(
            201 if action == "create" else 200,
            {
                "id": str(row.id),
                "changed": sorted(changed),
                "parent_changed": sorted(parent_changed),
                "requirement_changed": sorted(requirement_changed),
                "policy_changed": sorted(policy_changed),
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        assert context is not None
        row = await company_object(db, spec.model, uuid.UUID(receipt["id"]), company_id=company)
        return protected_detail(row, context, spec, state.generation if state else 1)

    try:
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=render
        )
    except IntegrityError as exc:
        raise ConflictError(
            "classification code already exists or a reference prevents this change"
        ) from exc
    except ValidationError as exc:
        raise ValidationFailedError("classification validation failed") from exc


async def move_edge(
    db: AsyncSession,
    actor: Actor,
    row: ClassificationMaster,
    edge: DatedEdge,
    context: FieldContext,
    incoming: Mapping[str, Any],
    owner_context: FieldContext,
    checks: FieldWriteChecks | None = None,
) -> frozenset[str]:
    """Close the interval in force and open its successor. History is never rewritten.

    Both dated relations run through here. The one asymmetry is a target of ``null``: for a
    hierarchy that is a root, so a row is written; for a membership it means *no group*,
    which is the absence of an open interval and so writes nothing new. What is *in force* is
    therefore the last interval only while it is still open — a location whose membership was
    cleared has history but no group, and may be assigned one again.
    """
    history = await bounded_rows(db, edge.model, row.company_id)
    owned = sorted(
        (child for child in history if getattr(child, edge.owner) == row.id),
        key=lambda child: child.valid_from,
    )
    start, target_id = incoming["effective_from"], incoming[edge.target]
    previous = owned[-1] if owned else None
    current = previous if previous is not None and previous.valid_to is None else None
    if current is None and previous is None and edge.nullable_target:
        # A hierarchy opens its first interval on create, so a master without one is corrupt
        # rather than unparented; refuse instead of inventing the history it should have.
        raise ConflictError("group has no current parent history")
    if (getattr(current, edge.target) if current is not None else None) == target_id:
        # Also covers no group → no group: nothing in force and nothing asked for.
        return frozenset()
    if start < utcnow().astimezone(ZoneInfo(owner_context.company.timezone)).date() or (
        previous is not None
        and start <= (previous.valid_from if current is not None else previous.valid_to)
    ):
        raise ConflictError("reparenting must append a future interval without rewriting history")
    if target_id is not None:
        parent = await company_object(db, edge.target_model, target_id, company_id=row.company_id)
        if not parent.is_active:
            raise ConflictError("group parent is inactive")
    edge_values = (
        {field: getattr(current, field) for field in context.native.fields}
        if current is not None
        else {}
    )
    close = {**edge_values, "valid_to": start - dt.timedelta(days=1)}
    new = (
        {
            edge.owner: row.id,
            edge.target: target_id,
            "valid_from": start,
            "valid_to": None,
        }
        if target_id is not None or edge.nullable_target
        else {}
    )
    if current is not None:
        context.assert_writable(
            frozenset({"valid_to"}), before=edge_values, after=close, checked=checks
        )
    if new:
        context.assert_writable(frozenset(new), before={}, after=new, checked=checks)
    if isinstance(row, ItemGroup):
        await guard_active_group_move(db, actor, row.company_id, row.id, history, start)
    if current is not None:
        current.valid_to = close["valid_to"]
        current.updated_at, current.updated_by = utcnow(), actor.user_id
    child = None
    if new:
        child = edge.model(
            tenant_id=actor.tenant_id,
            company_id=row.company_id,
            created_by=actor.user_id,
            updated_by=actor.user_id,
            **new,
        )
        db.add(child)
        history.append(child)
    if edge.nullable_target:
        groups = await bounded_rows(db, edge.target_model, row.company_id)
        validate_groups(groups, history, row.company_id)
    await db.flush()
    if current is not None:
        audit_change(
            db,
            actor,
            row.company_id,
            edge.entity,
            current.id,
            "close",
            frozenset({"valid_to"}),
            before=edge_values,
            after=close,
        )
    if child is not None:
        audit_change(
            db,
            actor,
            row.company_id,
            edge.entity,
            child.id,
            "create",
            frozenset(new),
            before={},
            after=new,
        )
    return frozenset(new) | (frozenset({"valid_to"}) if current is not None else frozenset())


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    spec: Classification,
    query: MasterQuery,
    secret: bytes,
    *,
    criterion: ColumnElement[bool] | None = None,
    cursor_resource: str | None = None,
) -> Page[BaseModel]:
    context = await load_field_context(db, actor, company, spec.entity)
    readable = (context.readable() & frozenset(context.native.fields)) | {"id"}
    model = spec.model
    selected = readable & spec.item.model_fields.keys()
    stmt = select(*(getattr(model, field) for field in selected)).where(model.company_id == company)
    if criterion is not None:
        stmt = stmt.where(criterion)
    stmt = apply_filters(
        stmt,
        query.model_dump(exclude_none=True, include=set(spec.filters)),
        filters={field: FilterColumn(field, getattr(model, field)) for field in spec.filters},
        readable=readable,
    )
    stmt = apply_search(
        stmt, query.q, columns={"code": model.code, "name": model.name}, readable=readable
    )
    terms = resolve_sort(
        query.sort,
        default="code" if "code" in readable else "id",
        columns={
            "id": SortColumn(model.id, "uuid"),
            "code": SortColumn(model.code, "text"),
            "name": SortColumn(model.name, "text"),
        },
        readable=readable,
        supported=frozenset((field,) for field in ("id", "-id", "code", "-code", "name", "-name")),
    )
    stmt, index_token = await apply_custom_filters(db, stmt, context, query.predicates())
    codec = cursor_codec(
        secret, actor, company, (cursor_resource or spec.entity) + ":" + index_token, context, query
    )

    def project(values: Mapping[str, Any]) -> BaseModel:
        return spec.item.model_validate(values)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)


async def list_parent_history(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    group_id: uuid.UUID,
    query: GroupParentQuery,
    secret: bytes,
    spec: Classification = GROUP,
) -> Page[GroupParentListItem]:
    edge = spec.hierarchy
    assert edge is not None
    await load_field_context(db, actor, company, edge.entity)
    await company_object(db, spec.model, group_id, company_id=company)
    return await list_edge_history(
        db, actor, company, group_id, query, secret, edge, GroupParentListItem
    )


HistoryItem = TypeVar("HistoryItem", bound=BaseModel)


async def list_edge_history(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    owner_id: uuid.UUID,
    query: GroupParentQuery,
    secret: bytes,
    edge: DatedEdge,
    schema: type[HistoryItem],
) -> Page[HistoryItem]:
    """Protected lean dated history; callers authorize the owning object first."""
    context = await load_field_context(db, actor, company, edge.entity)
    readable = context.readable() | {"id"}
    model = edge.model
    stmt = select(*(getattr(model, field) for field in readable)).where(
        model.company_id == company, getattr(model, edge.owner) == owner_id
    )
    if query.valid_at is not None:
        if not {"valid_from", "valid_to"} <= readable:
            raise PermissionDeniedError("history date filters require readable date fields")
        stmt = stmt.where(
            model.valid_from <= query.valid_at,
            or_(model.valid_to.is_(None), model.valid_to >= query.valid_at),
        )
    # This resource has no indexed text field; do not silently ignore a search.
    if query.q is not None:
        raise ValidationFailedError("parent history supports date filters, not text search")
    terms = resolve_sort(
        query.sort,
        default="valid_from" if "valid_from" in readable else "id",
        columns={
            "id": SortColumn(model.id, "uuid"),
            "valid_from": SortColumn(model.valid_from, "date"),
        },
        readable=readable,
        supported=frozenset((field,) for field in ("id", "-id", "valid_from", "-valid_from")),
    )
    codec = cursor_codec(secret, actor, company, edge.entity + ":" + str(owner_id), context, query)

    def project(values: Mapping[str, Any]) -> HistoryItem:
        return schema.model_validate(values)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)


async def list_children(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    group_id: uuid.UUID,
    query: ChildrenQuery,
    secret: bytes,
    spec: Classification = GROUP,
) -> Page[BaseModel]:
    edge = spec.hierarchy
    assert edge is not None
    context = await load_field_context(db, actor, company, edge.entity)
    await company_object(db, spec.model, group_id, company_id=company)
    if not {edge.owner, edge.target, "valid_from", "valid_to"} <= context.readable():
        raise PermissionDeniedError("child browsing requires readable hierarchy fields")
    model = edge.model
    relation = (
        select(model.id)
        .where(
            model.company_id == company,
            getattr(model, edge.owner) == spec.model.id,
            getattr(model, edge.target) == group_id,
            model.valid_from <= query.valid_at,
            or_(model.valid_to.is_(None), model.valid_to >= query.valid_at),
        )
        .exists()
    )
    return await list_rows(
        db,
        actor,
        company,
        spec,
        query,
        secret,
        criterion=relation,
        cursor_resource=spec.entity + ".children:" + str(group_id),
    )
