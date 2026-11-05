"""Dated manufacturer relationships and immutable published type requirements."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.listing import (
    FilterColumn,
    ListQuery,
    Page,
    SortColumn,
    SortKind,
    apply_filters,
    fetch_page,
    resolve_sort,
)
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.product_types import TypeRequirements
from catalog.models.attributes import AttributeSet, AttributeSetRevision
from catalog.models.classification import CatalogPolicyState, ClassificationMaster
from catalog.models.commercial import (
    Brand,
    BrandManufacturer,
    Manufacturer,
    ProductType,
    ProductTypeRevision,
)
from catalog.models.handling import HandlingProfile, HandlingProfileRevision
from catalog.models.inventory_templates import (
    InventoryProfileTemplate,
    InventoryProfileTemplateRevision,
)
from catalog.models.manufacturing_operations import (
    ManufacturingOperation,
    ManufacturingOperationRevision,
)
from catalog.models.manufacturing_routes import ManufacturingRoute, ManufacturingRouteRevision
from catalog.models.returns import ReturnPolicy, ReturnPolicyRevision
from catalog.models.warranties import WarrantyPolicy, WarrantyPolicyRevision
from catalog.schemas.attributes import (
    AttributeSetRevisionCreate,
    AttributeSetRevisionDetail,
    AttributeSetRevisionListItem,
    AttributeSetRevisionQuery,
)
from catalog.schemas.commercial import (
    BrandManufacturerCreate,
    BrandManufacturerDetail,
    BrandManufacturerListItem,
    BrandManufacturerQuery,
    TypeRevisionDetail,
    TypeRevisionInput,
    TypeRevisionListItem,
    TypeRevisionQuery,
)
from catalog.schemas.handling import (
    HandlingRevisionDetail,
    HandlingRevisionInput,
    HandlingRevisionListItem,
    HandlingRevisionQuery,
)
from catalog.schemas.inventory_templates import (
    InventoryRevisionDetail,
    InventoryRevisionInput,
    InventoryRevisionListItem,
    InventoryRevisionQuery,
)
from catalog.schemas.manufacturing_operations import (
    OperationRevisionDetail,
    OperationRevisionInput,
    OperationRevisionListItem,
    OperationRevisionQuery,
)
from catalog.schemas.manufacturing_routes import (
    RouteRevisionDetail,
    RouteRevisionInput,
    RouteRevisionListItem,
    RouteRevisionQuery,
)
from catalog.schemas.returns import (
    ReturnRevisionDetail,
    ReturnRevisionInput,
    ReturnRevisionListItem,
    ReturnRevisionQuery,
)
from catalog.schemas.warranties import (
    WarrantyRevisionDetail,
    WarrantyRevisionInput,
    WarrantyRevisionListItem,
    WarrantyRevisionQuery,
)
from catalog.tasks.attribute_sets import (
    authorize_member_replay,
    publish_members,
    replace_members,
    validate_type_binding,
)
from catalog.tasks.classification import audit_change
from catalog.tasks.field_context import (
    FieldContext,
    FieldWriteChecks,
    load_field_context,
)
from catalog.tasks.inventory_templates import requirements as inventory_requirements
from catalog.tasks.listing import cursor_codec
from catalog.tasks.manufacturing_operations import requirements as operation_requirements
from catalog.tasks.manufacturing_routes import (
    STEP_FIELDS,
    authorize_step_replay,
    publish_steps,
    replace_steps,
    steps,
)
from catalog.tasks.policy_state import policy_state
from catalog.tasks.profile_bindings import BINDINGS, validate_defaults
from catalog.tasks.return_conditions import (
    authorize_condition_replay,
    conditions,
    publish_conditions,
    replace_conditions,
)

HistoryRow = (
    BrandManufacturer
    | ProductTypeRevision
    | AttributeSetRevision
    | InventoryProfileTemplateRevision
    | WarrantyPolicyRevision
    | ReturnPolicyRevision
    | HandlingProfileRevision
    | ManufacturingOperationRevision
    | ManufacturingRouteRevision
)


@dataclass(frozen=True)
class History:
    model: (
        type[BrandManufacturer]
        | type[ProductTypeRevision]
        | type[AttributeSetRevision]
        | type[InventoryProfileTemplateRevision]
        | type[WarrantyPolicyRevision]
        | type[ReturnPolicyRevision]
        | type[HandlingProfileRevision]
        | type[ManufacturingOperationRevision]
        | type[ManufacturingRouteRevision]
    )
    entity: str
    permission: str
    detail: type[BaseModel]
    item: type[BaseModel]
    parent_field: str | None = None
    parent_model: type[ClassificationMaster] | None = None
    profile_input: type[BaseModel] | None = None
    profile_label: str = "profile"
    filters: tuple[str, ...] = ()


PRODUCTION = History(
    BrandManufacturer,
    "catalog.brand_manufacturer",
    "brand_manufacturer",
    BrandManufacturerDetail,
    BrandManufacturerListItem,
)
REVISION = History(
    ProductTypeRevision,
    "catalog.product_type_revision",
    "product_type",
    TypeRevisionDetail,
    TypeRevisionListItem,
    "product_type_id",
    ProductType,
)
SET_REVISION = History(
    AttributeSetRevision,
    "catalog.attribute_set_revision",
    "attribute_set",
    AttributeSetRevisionDetail,
    AttributeSetRevisionListItem,
    "attribute_set_id",
    AttributeSet,
)

INVENTORY_REVISION = History(
    InventoryProfileTemplateRevision,
    "catalog.inventory_profile_template_revision",
    "inventory_profile_template",
    InventoryRevisionDetail,
    InventoryRevisionListItem,
    "template_id",
    InventoryProfileTemplate,
    InventoryRevisionInput,
    "inventory template",
    (
        "lot_tracking",
        "serial_tracking",
        "expiry_required",
        "identifier_profile_id",
        "issue_strategy",
        "valuation_method",
    ),
)

WARRANTY_REVISION = History(
    WarrantyPolicyRevision,
    "catalog.warranty_policy_revision",
    "warranty_policy",
    WarrantyRevisionDetail,
    WarrantyRevisionListItem,
    "policy_id",
    WarrantyPolicy,
    WarrantyRevisionInput,
    "warranty policy",
    ("duration_unit", "start_trigger"),
)


RETURN_REVISION = History(
    ReturnPolicyRevision,
    "catalog.return_policy_revision",
    "return_policy",
    ReturnRevisionDetail,
    ReturnRevisionListItem,
    "policy_id",
    ReturnPolicy,
    ReturnRevisionInput,
    "return policy",
    ("returns_allowed",),
)


HANDLING_REVISION = History(
    HandlingProfileRevision,
    "catalog.handling_profile_revision",
    "handling_profile",
    HandlingRevisionDetail,
    HandlingRevisionListItem,
    "profile_id",
    HandlingProfile,
    HandlingRevisionInput,
    "handling profile",
    ("fragile", "keep_dry", "keep_upright"),
)


OPERATION_REVISION = History(
    ManufacturingOperationRevision,
    "catalog.manufacturing_operation_revision",
    "manufacturing_operation",
    OperationRevisionDetail,
    OperationRevisionListItem,
    "operation_id",
    ManufacturingOperation,
    OperationRevisionInput,
    "manufacturing operation",
    ("status",),
)


ROUTE_REVISION = History(
    ManufacturingRouteRevision,
    "catalog.manufacturing_route_revision",
    "manufacturing_route",
    RouteRevisionDetail,
    RouteRevisionListItem,
    "route_id",
    ManufacturingRoute,
    RouteRevisionInput,
    "manufacturing route",
    ("status",),
)


async def profile_requirements(
    db: AsyncSession,
    company: uuid.UUID,
    spec: History,
    incoming: Mapping[str, Any],
    actor: Actor | None = None,
) -> dict[str, Any]:
    assert spec.profile_input is not None
    if spec is OPERATION_REVISION:
        assert actor is not None
        return await operation_requirements(db, actor, company, incoming)
    if spec is INVENTORY_REVISION:
        return await inventory_requirements(db, company, incoming)
    return spec.profile_input.model_validate(incoming).model_dump()


def values(row: HistoryRow, context: FieldContext) -> dict[str, Any]:
    return {key: getattr(row, key) for key in context.native.fields}


def detail(row: HistoryRow, context: FieldContext, spec: History, generation: int) -> BaseModel:
    native = values(row, context)
    return spec.detail.model_validate(
        {
            "id": row.id,
            "company_id": row.company_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "policy_generation": generation,
            **{key: value for key, value in native.items() if key in context.readable(native)},
        }
    )


async def get_row(
    db: AsyncSession,
    company: uuid.UUID,
    object_id: uuid.UUID,
    spec: History,
    parent_id: uuid.UUID | None,
    *,
    lock: bool = False,
) -> HistoryRow:
    row = await company_object(db, spec.model, object_id, company_id=company, lock=lock)
    if spec.parent_field is not None and getattr(row, spec.parent_field) != parent_id:
        raise PermissionDeniedError("revision belongs to another parent")
    return row


async def read(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    object_id: uuid.UUID,
    spec: History,
    parent_id: uuid.UUID | None = None,
) -> BaseModel:
    context = await load_field_context(db, actor, company, spec.entity)
    if spec.parent_field is not None and spec.parent_field not in context.readable():
        raise PermissionDeniedError("revision access requires readable parent membership")
    row = await get_row(db, company, object_id, spec, parent_id)
    state = await policy_state(db, actor, company)
    return detail(row, context, spec, state.generation if state else 1)


def requirements(kind: str, incoming: Mapping[str, Any]) -> tuple[dict[str, Any], TypeRequirements]:
    parsed = TypeRevisionInput.model_validate(incoming)
    rules = TypeRequirements(
        kind,
        frozenset(parsed.inventory_modes),
        frozenset(parsed.tracking_modes),
        frozenset(parsed.unit_dimensions),
        parsed.allow_variants,
        parsed.require_brand,
        parsed.require_manufacturer,
        parsed.require_expiry,
    )
    result = parsed.model_dump(mode="json")
    for field in ("attribute_set_revision_id", *(binding.field for binding in BINDINGS)):
        result[field] = getattr(parsed, field)
    return result, rules


async def create_row(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    spec: History,
    incoming: Mapping[str, Any],
    parent_id: uuid.UUID | None,
    context: FieldContext,
) -> HistoryRow:
    common = {
        "tenant_id": actor.tenant_id,
        "company_id": company,
        "created_by": actor.user_id,
        "updated_by": actor.user_id,
        "row_version": 1,
    }
    if spec is PRODUCTION:
        body = BrandManufacturerCreate.model_validate(incoming)
        for model, object_id in (
            (Brand, body.brand_id),
            (Manufacturer, body.manufacturer_id),
        ):
            parent = await company_object(db, model, object_id, company_id=company)
            if not parent.is_active:
                raise ConflictError("production relationship requires active masters")
        overlap = await db.scalar(
            select(BrandManufacturer.id)
            .where(
                BrandManufacturer.company_id == company,
                BrandManufacturer.brand_id == body.brand_id,
                BrandManufacturer.manufacturer_id == body.manufacturer_id,
                BrandManufacturer.production_role == body.production_role,
                BrandManufacturer.valid_from <= (body.valid_to or dt.date.max),
                or_(
                    BrandManufacturer.valid_to.is_(None),
                    BrandManufacturer.valid_to >= body.valid_from,
                ),
            )
            .limit(1)
        )
        if overlap is not None:
            raise ConflictError("production relationship overlaps an existing interval")
        return BrandManufacturer(**common, **body.model_dump())
    assert parent_id is not None and spec.parent_field is not None
    if spec.profile_input is not None:
        assert spec.parent_model is not None
        profile = await company_object(db, spec.parent_model, parent_id, company_id=company)
        if not profile.is_active:
            raise ConflictError(spec.profile_label + " is inactive")
        if spec in (OPERATION_REVISION, ROUTE_REVISION):
            context.assert_writable(
                (frozenset(incoming) - {"steps"}) | {spec.parent_field},
                before={},
                after={**incoming, spec.parent_field: parent_id},
            )
        validated_profile = await profile_requirements(db, company, spec, incoming, actor)
        if spec is RETURN_REVISION:
            validated_profile.pop("condition_codes")
            validated_profile["condition_count"] = 0
        if spec is ROUTE_REVISION:
            validated_profile.pop("steps")
            validated_profile["step_count"] = 0
        profile_model = spec.model
        assert issubclass(
            profile_model,
            InventoryProfileTemplateRevision
            | WarrantyPolicyRevision
            | ReturnPolicyRevision
            | HandlingProfileRevision
            | ManufacturingOperationRevision
            | ManufacturingRouteRevision,
        )
        return profile_model(
            **common,
            **{spec.parent_field: parent_id},
            revision=await next_revision(db, profile_model, spec.parent_field, company, parent_id),
            published_at=None,
            **({"status": "DRAFT"} if spec in (OPERATION_REVISION, ROUTE_REVISION) else {}),
            **validated_profile,
        )
    if spec is SET_REVISION:
        AttributeSetRevisionCreate.model_validate(incoming)
        template = await company_object(db, AttributeSet, parent_id, company_id=company)
        if not template.is_active:
            raise ConflictError("attribute set is inactive")
        return AttributeSetRevision(
            id=uuid7(),
            **common,
            attribute_set_id=parent_id,
            revision=await next_revision(
                db, AttributeSetRevision, "attribute_set_id", company, parent_id
            ),
            published_at=None,
        )
    product_type = await company_object(db, ProductType, parent_id, company_id=company)
    if not product_type.is_active:
        raise ConflictError("product type is inactive")
    validated, rules = requirements(product_type.kind, incoming)
    row = ProductTypeRevision(
        **common,
        product_type_id=parent_id,
        revision=await next_revision(
            db, ProductTypeRevision, "product_type_id", company, parent_id
        ),
        kind=product_type.kind,
        published_at=None,
        **validated,
    )
    after = values(row, context)
    generated = {"row_version", "revision", "published_at", "kind"}
    changed = frozenset(field for field, value in after.items() if value is not None) - generated
    # Reject prohibited native assignments before dereferencing caller-supplied IDs.
    context.assert_writable(changed, before={}, after=after)
    await validate_defaults(db, company, rules, validated)
    await validate_type_binding(db, company, validated["attribute_set_revision_id"])
    return row


async def next_revision(
    db: AsyncSession,
    model: type[ProductTypeRevision]
    | type[AttributeSetRevision]
    | type[InventoryProfileTemplateRevision]
    | type[WarrantyPolicyRevision]
    | type[ReturnPolicyRevision]
    | type[HandlingProfileRevision]
    | type[ManufacturingOperationRevision]
    | type[ManufacturingRouteRevision],
    parent_field: str,
    company: uuid.UUID,
    parent_id: uuid.UUID,
) -> int:
    latest = await db.scalar(
        select(func.max(model.revision)).where(
            model.company_id == company, getattr(model, parent_field) == parent_id
        )
    )
    number = (latest or 0) + 1
    if number > 2**31 - 1:
        raise ConflictError("master revision numbers are exhausted")
    return number


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    spec: History,
    *,
    key: str,
    body: BaseModel,
    action: Literal["create", "update", "close", "publish", "retire"],
    object_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    context: FieldContext | None = None
    state: CatalogPolicyState | None = None
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        spec.entity + "." + action,
        key,
        {
            "body": body.model_dump(mode="json", exclude_unset=True),
            "id": str(object_id) if object_id else None,
            "parent_id": str(parent_id) if parent_id else None,
        },
    )

    member_checks: FieldWriteChecks | None = None

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal context, state
        context = await load_field_context(
            db,
            actor,
            company,
            spec.entity,
            permission=spec.permission
            + (".publish" if action in {"publish", "retire"} else ".manage"),
        )
        if spec.parent_field is not None and spec.parent_field not in context.readable():
            raise PermissionDeniedError("revision access requires readable parent membership")
        state = await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            row = await get_row(db, company, uuid.UUID(receipt["id"]), spec, parent_id)
            native = values(row, context)
            context.assert_writable(frozenset(receipt["changed"]), before=native, after=native)
            if spec is SET_REVISION:
                await authorize_member_replay(
                    db,
                    actor,
                    company,
                    frozenset(receipt.get("member_changed", [])),
                    publishing=action == "publish",
                    checks=member_checks,
                )
            if spec is RETURN_REVISION:
                assert isinstance(row, ReturnPolicyRevision)
                await conditions(db, row)
                await authorize_condition_replay(
                    db,
                    actor,
                    company,
                    frozenset(receipt.get("member_changed", [])),
                    publishing=action == "publish",
                    checks=member_checks,
                )

            if spec is ROUTE_REVISION:
                assert isinstance(row, ManufacturingRouteRevision)
                await steps(db, row)
                await authorize_step_replay(
                    db,
                    actor,
                    company,
                    frozenset(receipt.get("member_changed", [])),
                    publishing=action == "publish",
                    checks=member_checks,
                )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        nonlocal member_checks
        member_checks = FieldWriteChecks()
        assert context is not None and state is not None
        incoming = body.model_dump(exclude_unset=True)
        before: dict[str, Any] = {}
        member_changed: frozenset[str] = frozenset()
        if action == "create":
            row = await create_row(db, actor, company, spec, incoming, parent_id, context)
            after = values(row, context)
            generated = (
                {
                    "row_version",
                    "revision",
                    "published_at",
                    "kind",
                    "condition_count",
                    "step_count",
                    "status",
                }
                if isinstance(
                    row,
                    ProductTypeRevision
                    | AttributeSetRevision
                    | InventoryProfileTemplateRevision
                    | WarrantyPolicyRevision
                    | ReturnPolicyRevision
                    | HandlingProfileRevision
                    | ManufacturingOperationRevision
                    | ManufacturingRouteRevision,
                )
                else {"row_version"}
            )
            changed = (
                frozenset(field for field, value in after.items() if value is not None) - generated
            )
            db.add(row)
            if isinstance(row, AttributeSetRevision):
                await db.flush()
                member_changed = await replace_members(
                    db, actor, row, incoming.get("members", []), member_checks
                )
            if isinstance(row, ReturnPolicyRevision):
                await db.flush()
                member_changed = await replace_conditions(
                    db,
                    actor,
                    row,
                    tuple(incoming.get("condition_codes", ())),
                    member_checks,
                )
            if isinstance(row, ManufacturingRouteRevision):
                await db.flush()
                member_changed = await replace_steps(
                    db, actor, row, incoming.get("steps", ()), member_checks
                )
        else:
            assert object_id is not None
            row = await get_row(db, company, object_id, spec, parent_id, lock=True)
            if row.row_version != incoming.pop("expected_version"):
                raise ConflictError("resource version changed; reload before updating")
            before = values(row, context)
            if action == "retire":
                if (
                    not isinstance(row, ManufacturingOperationRevision | ManufacturingRouteRevision)
                    or row.status != "PUBLISHED"
                ):
                    raise ConflictError("only a published definition revision can be retired")
                row.status = "RETIRED"
            elif isinstance(row, BrandManufacturer):
                if action != "close":
                    raise ValidationFailedError("production relationships only support closing")
                end = incoming["valid_to"]
                if end < row.valid_from or (row.valid_to is not None and end != row.valid_to):
                    raise ConflictError("relationship cannot rewrite its closed interval")
                row.valid_to = end
            elif isinstance(row, ProductTypeRevision):
                if row.published_at is not None:
                    raise ConflictError("published product-type revisions are immutable")
                product_type = await company_object(
                    db, ProductType, row.product_type_id, company_id=company
                )
                if not product_type.is_active:
                    raise ConflictError("product type is inactive")
                merged = {key: before[key] for key in TypeRevisionInput.model_fields}
                if action == "update":
                    merged.update(incoming)
                elif action != "publish":
                    raise ValidationFailedError("unsupported revision command")
                validated, rules = requirements(row.kind, merged)
                proposed = {**before, **validated}
                if action == "publish":
                    proposed["published_at"] = utcnow()
                proposed_changes = frozenset(
                    field for field in proposed if before.get(field) != proposed[field]
                )
                if action == "publish":
                    proposed_changes |= frozenset(
                        field
                        for field in TypeRevisionInput.model_fields
                        if proposed[field] is not None
                    )
                if proposed_changes:
                    proposed["row_version"] = row.row_version + 1
                context.assert_writable(proposed_changes, before=before, after=proposed)
                await validate_defaults(db, company, rules, validated)
                await validate_type_binding(db, company, validated["attribute_set_revision_id"])
                for key, value in validated.items():
                    setattr(row, key, value)
                if action == "publish":
                    row.published_at = proposed["published_at"]
            elif isinstance(
                row,
                InventoryProfileTemplateRevision
                | WarrantyPolicyRevision
                | ReturnPolicyRevision
                | HandlingProfileRevision
                | ManufacturingOperationRevision
                | ManufacturingRouteRevision,
            ):
                assert spec.profile_input is not None and spec.parent_model is not None
                assert spec.parent_field is not None
                if row.published_at is not None:
                    raise ConflictError(
                        "published " + spec.profile_label + " revisions are immutable"
                    )
                profile = await company_object(
                    db,
                    spec.parent_model,
                    getattr(row, spec.parent_field),
                    company_id=company,
                )
                if not profile.is_active:
                    raise ConflictError(spec.profile_label + " is inactive")
                merged_profile = {
                    key: before[key] for key in spec.profile_input.model_fields if key in before
                }
                if isinstance(row, ReturnPolicyRevision):
                    merged_profile["condition_codes"] = tuple(
                        item.condition_code for item in await conditions(db, row)
                    )
                if isinstance(row, ManufacturingRouteRevision):
                    merged_profile["steps"] = [
                        {"id": item.id, **{key: getattr(item, key) for key in STEP_FIELDS}}
                        for item in await steps(db, row)
                    ]
                if action == "update":
                    merged_profile.update(incoming)
                elif action != "publish":
                    raise ValidationFailedError(
                        "unsupported " + spec.profile_label.split()[0] + " revision command"
                    )
                if spec in (OPERATION_REVISION, ROUTE_REVISION):
                    checked = (
                        frozenset(incoming) if action == "update" else frozenset(merged_profile)
                    )
                    context.assert_writable(
                        checked - {"steps"}, before=before, after={**before, **merged_profile}
                    )
                validated_profile = await profile_requirements(
                    db, company, spec, merged_profile, actor
                )
                if isinstance(row, ReturnPolicyRevision):
                    proposed_codes = validated_profile.pop("condition_codes")
                    if action == "publish":
                        member_changed = await publish_conditions(db, actor, row, member_checks)
                    else:
                        member_changed = await replace_conditions(
                            db, actor, row, proposed_codes, member_checks
                        )
                if isinstance(row, ManufacturingRouteRevision):
                    proposed_steps = validated_profile.pop("steps")
                    if action == "publish":
                        member_changed = await publish_steps(db, actor, row, member_checks)
                    else:
                        member_changed = await replace_steps(
                            db, actor, row, proposed_steps, member_checks
                        )
                for key, value in validated_profile.items():
                    setattr(row, key, value)
                if action == "publish":
                    row.published_at = utcnow()
                    if isinstance(row, ManufacturingOperationRevision | ManufacturingRouteRevision):
                        row.status = "PUBLISHED"
            else:
                if row.published_at is not None:
                    raise ConflictError("published attribute template revisions are immutable")
                template = await company_object(
                    db, AttributeSet, row.attribute_set_id, company_id=company
                )
                if not template.is_active:
                    raise ConflictError("attribute set is inactive")
                if action == "update":
                    member_changed = await replace_members(
                        db, actor, row, incoming["members"], member_checks
                    )
                elif action == "publish":
                    member_changed = await publish_members(db, actor, row, member_checks)
                    row.published_at = utcnow()
                else:
                    raise ValidationFailedError("unsupported template revision command")
            after = values(row, context)
            changed = frozenset(field for field in after if before.get(field) != after[field])
            if action == "publish" and isinstance(row, ProductTypeRevision):
                changed |= frozenset(
                    field for field in TypeRevisionInput.model_fields if after[field] is not None
                )
            if action == "publish" and spec.profile_input is not None:
                changed |= frozenset(
                    field
                    for field in spec.profile_input.model_fields
                    if field in after and after[field] is not None
                )
            if changed or member_changed:
                if row.row_version >= 2**31 - 1:
                    raise ConflictError(
                        "resource version is exhausted; create a replacement definition"
                    )
                row.row_version += 1
                row.updated_by, row.updated_at = actor.user_id, utcnow()
        context.assert_writable(changed, before=before, after=after)
        if changed or member_changed:
            if state.generation >= 2**63 - 1:
                raise ConflictError("company policy generation is exhausted")
            state.generation += 1
            await db.flush()
            audit_change(
                db,
                actor,
                company,
                spec.entity,
                row.id,
                action,
                changed
                | frozenset(
                    {
                        "condition_codes"
                        if spec is RETURN_REVISION
                        else "steps"
                        if spec is ROUTE_REVISION
                        else "members"
                    }
                    if member_changed
                    else ()
                ),
                before=before,
                after=after,
            )
        await db.flush()
        return CommandReceipt(
            201 if action == "create" else 200,
            {
                "id": str(row.id),
                "changed": sorted(changed),
                "member_changed": sorted(member_changed),
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        assert context is not None
        row = await get_row(db, company, uuid.UUID(receipt["id"]), spec, parent_id)
        return detail(row, context, spec, state.generation if state else 1)

    try:
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=render
        )
    except IntegrityError as exc:
        raise ConflictError(
            "commercial reference or revision conflicts with existing data"
        ) from exc
    except ValidationError as exc:
        raise ValidationFailedError("commercial requirements are invalid") from exc


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    spec: History,
    query: ListQuery,
    secret: bytes,
    parent_id: uuid.UUID | None = None,
) -> Page[BaseModel]:
    context = await load_field_context(db, actor, company, spec.entity)
    readable = context.readable() | {"id"}
    model = spec.model
    stmt = select(
        *(getattr(model, field) for field in readable & spec.item.model_fields.keys())
    ).where(model.company_id == company)
    sort_type: SortKind
    if isinstance(query, BrandManufacturerQuery):
        filters = {
            field: FilterColumn(field, getattr(model, field))
            for field in ("brand_id", "manufacturer_id", "production_role")
        }
        stmt = apply_filters(
            stmt,
            query.model_dump(exclude_none=True, include=set(filters)),
            filters=filters,
            readable=readable,
        )
        if query.valid_at is not None:
            if not {"valid_from", "valid_to"} <= readable:
                raise PermissionDeniedError("date filters require readable interval fields")
            stmt = stmt.where(
                BrandManufacturer.valid_from <= query.valid_at,
                or_(
                    BrandManufacturer.valid_to.is_(None),
                    BrandManufacturer.valid_to >= query.valid_at,
                ),
            )
        sort_key, sort_type = "valid_from", "date"
    else:
        assert (
            isinstance(
                query,
                TypeRevisionQuery
                | AttributeSetRevisionQuery
                | InventoryRevisionQuery
                | WarrantyRevisionQuery
                | ReturnRevisionQuery
                | HandlingRevisionQuery
                | OperationRevisionQuery
                | RouteRevisionQuery,
            )
            and parent_id is not None
            and spec.parent_field is not None
            and spec.parent_model is not None
        )
        await company_object(db, spec.parent_model, parent_id, company_id=company)
        if spec.parent_field not in readable:
            raise PermissionDeniedError("revision browsing requires readable product type")
        stmt = stmt.where(getattr(model, spec.parent_field) == parent_id)
        revision_model = spec.model
        assert issubclass(
            revision_model,
            ProductTypeRevision
            | AttributeSetRevision
            | InventoryProfileTemplateRevision
            | WarrantyPolicyRevision
            | ReturnPolicyRevision
            | HandlingProfileRevision
            | ManufacturingOperationRevision
            | ManufacturingRouteRevision,
        )
        if query.published is not None:
            if "published_at" not in readable:
                raise PermissionDeniedError(
                    "publication filter requires readable publication state"
                )
            stmt = stmt.where(
                revision_model.published_at.is_not(None)
                if query.published
                else revision_model.published_at.is_(None)
            )
        if spec.filters:
            filters = {field: FilterColumn(field, getattr(model, field)) for field in spec.filters}
            stmt = apply_filters(
                stmt,
                query.model_dump(exclude_none=True, include=set(filters)),
                filters=filters,
                readable=readable,
            )
        sort_key, sort_type = "revision", "integer"
    if query.q is not None:
        raise ValidationFailedError("commercial history supports typed filters, not text search")
    terms = resolve_sort(
        query.sort,
        default=sort_key if sort_key in readable else "id",
        columns={
            "id": SortColumn(model.id, "uuid"),
            sort_key: SortColumn(getattr(model, sort_key), sort_type),
        },
        readable=readable,
        supported=frozenset((key,) for key in ("id", "-id", sort_key, "-" + sort_key)),
    )
    codec = cursor_codec(secret, actor, company, spec.entity + ":" + str(parent_id), context, query)

    def project(native: Mapping[str, Any]) -> BaseModel:
        return spec.item.model_validate(native)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)
