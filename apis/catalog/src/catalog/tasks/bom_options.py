"""Protected native reference lists, bounded and signed for BOM authoring."""

import uuid
from typing import Any, Literal

from billing_platform.db.access import company_object
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page, SortColumn, apply_search, fetch_page, resolve_sort
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.boms import Bom, BomRevision
from catalog.models.manufacturing_routes import ManufacturingRoute, ManufacturingRouteRevision
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.products import Item
from catalog.models.units import UnitOfMeasure
from catalog.schemas.boms import (
    BomReferenceOption,
    BomReferenceQuery,
    BomRevisionOptionsQuery,
    BomStoredReference,
    BomUnitOption,
    BomUnitQuery,
)
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import load_field_context
from catalog.tasks.listing import cursor_codec


async def require_fields(access: ConfigurationAccess, model: type[Any], keys: set[str]) -> None:
    context = await access.context(model)
    if keys - context.readable():
        raise PermissionDeniedError("BOM choices require readable reference labels and lifecycle")


async def stored_reference(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    source: Literal["goods", "units", "routes", "revisions"],
    object_id: uuid.UUID,
) -> BomStoredReference:
    await load_field_context(db, actor, company, "catalog.bom")
    access = ConfigurationAccess(db, actor, company)
    if source == "goods":
        await require_fields(access, Item, {"sku", "name", "family_id"})
        item = await company_object(db, Item, object_id, company_id=company)
        return BomStoredReference(
            id=item.id, source=source, parent_id=item.family_id, code=item.sku, name=item.name
        )
    if source == "units":
        await require_fields(access, ItemUnitRevision, {"binding_id", "revision"})
        await require_fields(access, ItemUnitBinding, {"code", "item_id", "unit_id"})
        await require_fields(access, UnitOfMeasure, {"name"})
        revision = await company_object(db, ItemUnitRevision, object_id, company_id=company)
        binding = await company_object(db, ItemUnitBinding, revision.binding_id, company_id=company)
        unit = await company_object(db, UnitOfMeasure, binding.unit_id, company_id=company)
        return BomStoredReference(
            id=revision.id,
            source=source,
            parent_id=binding.item_id,
            code=binding.code,
            name=unit.name,
            revision=revision.revision,
        )
    model, parent, field = (
        (ManufacturingRouteRevision, ManufacturingRoute, "route_id")
        if source == "routes"
        else (BomRevision, Bom, "bom_id")
    )
    await require_fields(access, model, {field, "revision"})
    if source == "routes":
        await require_fields(access, model, {"step_count"})
    await require_fields(access, parent, {"code", "name"})
    row: Any = await company_object(db, model, object_id, company_id=company)
    owner = await company_object(db, parent, getattr(row, field), company_id=company)
    return BomStoredReference(
        id=row.id,
        source=source,
        parent_id=owner.id,
        code=owner.code,
        name=owner.name,
        revision=row.revision,
        step_count=getattr(row, "step_count", None),
    )


async def revision_options(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    kind: Literal["routes", "boms"],
    query: BomReferenceQuery | BomRevisionOptionsQuery,
    secret: bytes,
) -> Page[BomReferenceOption]:
    owner = await load_field_context(db, actor, company, "catalog.bom")
    access = ConfigurationAccess(db, actor, company)
    model, parent, field = (
        (ManufacturingRouteRevision, ManufacturingRoute, "route_id")
        if kind == "routes"
        else (BomRevision, Bom, "bom_id")
    )
    await require_fields(access, model, {field, "revision", "status", "published_at"})
    await require_fields(access, parent, {"code", "name", "is_active"})
    statement = (
        select(model.id, parent.id.label("parent_id"), parent.code, parent.name, model.revision)
        .join(parent, getattr(model, field) == parent.id)
        .where(
            model.company_id == company,
            parent.company_id == company,
            parent.is_active.is_(True),
            model.status == "PUBLISHED",
        )
    )
    if query.value is not None:
        statement = statement.where(model.id == query.value)
    if isinstance(query, BomRevisionOptionsQuery) and query.bom_id is not None:
        if kind != "boms":
            raise ValidationFailedError("BOM identity filtering applies to BOM revisions only")
        context = await access.context(BomRevision)
        if "bom_id" not in context.readable():
            raise PermissionDeniedError("BOM revision membership is protected")
        statement = statement.where(BomRevision.bom_id == query.bom_id)
    statement = apply_search(
        statement,
        query.q,
        columns={"code": parent.code, "name": parent.name},
        readable=frozenset({"code", "name"}),
    )
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(model.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=cursor_codec(secret, actor, company, "catalog.bom.options:" + kind, owner, query),
        project=lambda values: BomReferenceOption.model_validate(dict(values)),
    )


async def unit_options(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    query: BomUnitQuery,
    secret: bytes,
) -> Page[BomUnitOption]:
    from catalog.tasks.bom_dependencies import goods

    owner = await load_field_context(db, actor, company, "catalog.bom")
    access = ConfigurationAccess(db, actor, company)
    await goods(access, query.item_id)
    await require_fields(access, ItemUnitBinding, {"code", "item_id", "unit_id", "usage_role"})
    await require_fields(
        access,
        ItemUnitRevision,
        {"binding_id", "revision", "valid_from", "valid_to", "conversion_mode"},
    )
    await require_fields(access, UnitOfMeasure, {"code", "name", "is_active"})
    if query.q is not None:
        raise ValidationFailedError("SKU unit choices use exact SKU and business-date filtering")
    statement = (
        select(
            ItemUnitRevision.id,
            ItemUnitBinding.item_id.label("parent_id"),
            ItemUnitBinding.code,
            UnitOfMeasure.name,
            ItemUnitRevision.revision,
            ItemUnitBinding.unit_id,
            ItemUnitRevision.valid_from,
            ItemUnitRevision.valid_to,
        )
        .join(ItemUnitBinding, ItemUnitRevision.binding_id == ItemUnitBinding.id)
        .join(UnitOfMeasure, ItemUnitBinding.unit_id == UnitOfMeasure.id)
        .where(
            ItemUnitRevision.company_id == company,
            ItemUnitBinding.company_id == company,
            UnitOfMeasure.company_id == company,
            ItemUnitBinding.item_id == query.item_id,
            UnitOfMeasure.is_active.is_(True),
            ItemUnitRevision.conversion_mode == "FIXED",
            ItemUnitRevision.valid_from <= query.as_of,
            or_(ItemUnitRevision.valid_to.is_(None), ItemUnitRevision.valid_to >= query.as_of),
        )
    )
    if query.value is not None:
        statement = statement.where(ItemUnitRevision.id == query.value)
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(ItemUnitRevision.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=cursor_codec(secret, actor, company, "catalog.bom.unit_options", owner, query),
        project=lambda values: BomUnitOption.model_validate(dict(values)),
    )
