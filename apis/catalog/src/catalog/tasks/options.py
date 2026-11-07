"""Scoped master options and bounded write-time candidate verification."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo

from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page, SortColumn, apply_search, fetch_page, resolve_sort
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.option_sources import OPTION_SOURCES
from catalog.models.attributes import AttributeDefinition, AttributeOption, AttributeSet
from catalog.models.classification import (
    CategoryScheme,
    ClassificationMaster,
    ItemCategory,
    ItemGroup,
)
from catalog.models.commercial import (
    Brand,
    BrandSeries,
    Manufacturer,
    ManufacturerSite,
    ProductType,
)
from catalog.models.handling import HandlingProfile
from catalog.models.inventory_templates import InventoryProfileTemplate
from catalog.models.profiles import IdentifierProfile
from catalog.models.returns import ReturnPolicy
from catalog.models.tax import TaxCategory, TaxClassification, TaxRule
from catalog.models.tax_governance import TaxHistoryAction
from catalog.models.units import PackType, UnitOfMeasure
from catalog.models.warranties import WarrantyPolicy
from catalog.schemas.options import OptionItem, OptionQuery
from catalog.tasks.field_context import FieldContext, load_field_context
from catalog.tasks.listing import cursor_codec

OptionModel = (
    type[UnitOfMeasure]
    | type[PackType]
    | type[ClassificationMaster]
    | type[TaxCategory]
    | type[TaxRule]
    | type[TaxClassification]
)

MODELS: dict[str, OptionModel] = {
    "catalog.tax_categories": TaxCategory,
    "catalog.tax_rules": TaxRule,
    "catalog.tax_classifications": TaxClassification,
    "catalog.handling_profiles": HandlingProfile,
    "catalog.return_policies": ReturnPolicy,
    "catalog.warranty_policies": WarrantyPolicy,
    "catalog.identifier_profiles": IdentifierProfile,
    "catalog.inventory_templates": InventoryProfileTemplate,
    "catalog.units": UnitOfMeasure,
    "catalog.pack_types": PackType,
    "catalog.item_groups": ItemGroup,
    "catalog.category_schemes": CategoryScheme,
    "catalog.item_categories": ItemCategory,
    "catalog.brands": Brand,
    "catalog.brand_series": BrandSeries,
    "catalog.manufacturers": Manufacturer,
    "catalog.manufacturer_sites": ManufacturerSite,
    "catalog.product_types": ProductType,
    "catalog.attribute_definitions": AttributeDefinition,
    "catalog.attribute_options": AttributeOption,
    "catalog.attribute_sets": AttributeSet,
}


async def option_query(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    source_key: str,
    parent: uuid.UUID | None,
    as_of: dt.date | None = None,
) -> tuple[Select[Any], FieldContext]:
    source = OPTION_SOURCES.get(source_key)
    if source is None:
        raise ValidationFailedError("unknown Catalog option source")
    if (parent is None) != (source.parent_source is None):
        raise ValidationFailedError("option source has an invalid parent")
    context = await load_field_context(db, actor, company, source.entity)
    model: Any = MODELS[source_key]
    dated = model is TaxClassification
    if as_of is not None and not dated:
        raise ValidationFailedError("as_of is supported only for dated classification options")
    required = (
        {"code", "description", "valid_from", "valid_to"}
        if dated
        else {"code", "name", "is_active"}
    )
    if parent is not None:
        assert source.parent_field is not None
        required.add(source.parent_field)
    if not required <= context.readable():
        raise PermissionDeniedError("option labels and filters require readable source fields")
    label = model.description if dated else model.name
    stmt = select(model.id, model.code, label.label("name")).where(model.company_id == company)
    if dated:
        history_context = await load_field_context(db, actor, company, "catalog.tax_history_action")
        if not {"resource", "target_id", "action"} <= history_context.readable():
            raise PermissionDeniedError(
                "classification options require readable withdrawal evidence"
            )
        date = as_of or utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
        excluded = select(TaxHistoryAction.target_id).where(
            TaxHistoryAction.company_id == company,
            TaxHistoryAction.resource == "tax_classification",
            TaxHistoryAction.action == "WITHDRAW",
        )
        stmt = stmt.where(
            model.valid_from <= date,
            or_(model.valid_to.is_(None), model.valid_to >= date),
            model.id.not_in(excluded),
        )
    else:
        stmt = stmt.where(model.is_active.is_(True))
    if parent is not None:
        assert source.parent_source is not None and source.parent_field is not None
        parent_source = OPTION_SOURCES[source.parent_source]
        parent_model: Any = MODELS[source.parent_source]
        parent_context = await load_field_context(db, actor, company, parent_source.entity)
        if "is_active" not in parent_context.readable():
            raise PermissionDeniedError("option parent status is unreadable")
        parent_query = select(parent_model.id).where(
            parent_model.company_id == company,
            parent_model.id == parent,
            parent_model.is_active.is_(True),
        )
        if await db.scalar(parent_query) is None:
            raise ValidationFailedError("option parent is unavailable")
        stmt = stmt.where(getattr(model, source.parent_field) == parent)
    return stmt, context


async def list_options(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    source_key: str,
    query: OptionQuery,
    secret: bytes,
) -> Page[OptionItem]:
    stmt, context = await option_query(db, actor, company, source_key, query.parent_id, query.as_of)
    model: Any = MODELS[source_key]
    if query.product_type_revision_id is not None:
        if source_key != "catalog.units":
            raise ValidationFailedError("product type filter is available only for units")
        if "dimension" not in context.readable():
            raise PermissionDeniedError("unit dimension is protected")
        from catalog.models.commercial import ProductTypeRevision
        from catalog.tasks.configuration_access import ConfigurationAccess

        revision = await ConfigurationAccess(db, actor, company).reference(
            ProductTypeRevision, query.product_type_revision_id
        )
        if revision.published_at is None:
            raise ValidationFailedError("select a published product type")
        stmt = stmt.where(model.dimension.in_(revision.unit_dimensions))
    readable = context.readable() | {"id"}
    label = model.description if model is TaxClassification else model.name
    if model is TaxClassification and "description" in readable:
        readable |= {"name"}
    stmt = apply_search(
        stmt, query.q, columns={"code": model.code, "name": label}, readable=readable
    )
    terms = resolve_sort(
        query.sort,
        default="code",
        columns={
            "id": SortColumn(model.id, "uuid"),
            "code": SortColumn(model.code, "text"),
            "name": SortColumn(label.label("name"), "text"),
        },
        readable=readable,
        supported=frozenset((key,) for key in ("id", "-id", "code", "-code", "name", "-name")),
    )
    codec = cursor_codec(secret, actor, company, "catalog.options:" + source_key, context, query)

    def project(row: Mapping[str, Any]) -> OptionItem:
        return OptionItem(value=str(row["id"]), code=row["code"], label=row["name"])

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)


async def validated_candidates(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    context: FieldContext,
    incoming: Mapping[str, Any],
    previous: Mapping[str, Any],
    native: Mapping[str, Any],
    *,
    creating: bool,
) -> dict[tuple[str, str | None], frozenset[str]]:
    values = {**previous, **incoming}
    if creating:
        for definition in context.definitions:
            if definition.key not in values and definition.default_value is not None:
                values[definition.key] = definition.default_value
    requests: dict[tuple[str, str | None], set[uuid.UUID]] = {}
    for definition in context.definitions:
        if not definition.is_active or definition.data_type != "dynamic_select":
            continue
        if (
            not creating
            and definition.key not in incoming
            and (definition.depends_on_key is None or definition.depends_on_key not in incoming)
        ):
            continue
        value = values.get(definition.key)
        if value is None:
            continue
        source = definition.option_source_key
        assert source is not None
        parent = (
            {**native, **values}.get(definition.depends_on_key)
            if definition.depends_on_key
            else None
        )
        try:
            candidate = uuid.UUID(str(value))
            parent_id = uuid.UUID(str(parent)) if parent is not None else None
        except ValueError as exc:
            raise ValidationFailedError("custom option reference is invalid") from exc
        requests.setdefault((source, str(parent_id) if parent_id else None), set()).add(candidate)
    result = {}
    for (source, parent_key), candidates in sorted(requests.items(), key=lambda pair: str(pair[0])):
        stmt, _ = await option_query(
            db, actor, company, source, uuid.UUID(parent_key) if parent_key else None
        )
        model = MODELS[source]
        # A fixed at-most-128 candidate query, never an unbounded options scan.
        rows = await db.execute(stmt.where(model.id.in_(candidates)).with_for_update(read=True))
        result[(source, parent_key)] = frozenset(str(row.id) for row in rows)
    return result
