"""Generation readiness and ordinary-command integration for derived custom indexes."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, cast

from billing_platform.custom_fields import CustomDefinition
from billing_platform.custom_query import (
    CustomPredicate,
    ReadyIndex,
    custom_predicate,
    definition_digest,
)
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import ItemCategory, ItemGroup
from catalog.models.commercial import Brand, Manufacturer, ProductType
from catalog.models.custom_fields import CustomFieldValueIndex, CustomFieldValueMember
from catalog.models.field_indexes import FieldIndexState
from catalog.models.products import Item, ProductFamily
from catalog.tasks.custom_fields import replace_indexes
from catalog.tasks.field_context import FieldContext

INDEX_MODELS: dict[
    str,
    type[ItemGroup]
    | type[ItemCategory]
    | type[Brand]
    | type[Manufacturer]
    | type[ProductType]
    | type[Item]
    | type[ProductFamily],
] = {
    "catalog.product_family": ProductFamily,
    "catalog.item": Item,
    "catalog.item_group": ItemGroup,
    "catalog.item_category": ItemCategory,
    "catalog.brand": Brand,
    "catalog.manufacturer": Manufacturer,
    "catalog.product_type": ProductType,
}


def index_definition(context: FieldContext, field_key: str) -> CustomDefinition:
    if context.native.entity_type not in INDEX_MODELS:
        raise ValidationFailedError("custom index owner is not implemented")
    if "custom_field:" + field_key not in context.readable():
        raise PermissionDeniedError("custom index field is not readable")
    definition = next((item for item in context.definitions if item.key == field_key), None)
    if definition is None or not definition.is_active or not definition.is_searchable:
        raise ValidationFailedError("custom field is not an active searchable definition")
    if definition.validation.unique_within != "none" and context.native.entity_type not in {
        "catalog.item",
        "catalog.product_family",
    }:
        raise ConflictError("unique-field adoption requires an owner-specific reviewed workflow")
    return definition


async def load_index_state(
    db: AsyncSession,
    company: uuid.UUID,
    entity: str,
    key: str,
    *,
    lock: bool = False,
    read_lock: bool = False,
) -> FieldIndexState | None:
    stmt = select(FieldIndexState).where(
        FieldIndexState.company_id == company,
        FieldIndexState.entity_type == entity,
        FieldIndexState.field_key == key,
    )
    if lock:
        stmt = stmt.with_for_update()
    elif read_lock:
        stmt = stmt.with_for_update(read=True)
    row = await db.scalar(stmt.execution_options(populate_existing=True))
    assert row is None or isinstance(row, FieldIndexState)
    return row


async def write_generations(db: AsyncSession, context: FieldContext) -> dict[str, tuple[int, ...]]:
    result = {}
    for definition in context.definitions:
        if not definition.is_active or not definition.is_searchable:
            continue
        if definition.validation.unique_within != "none" and context.native.entity_type not in {
            "catalog.item",
            "catalog.product_family",
        }:
            raise ConflictError(
                "unique-field adoption requires an owner-specific reviewed workflow"
            )
        state = await load_index_state(
            db, context.company.company_id, context.native.entity_type, definition.key
        )
        digest = definition_digest(definition)
        if state is None and definition.validation.unique_within != "none":
            # No historical owners means no backfill or uniqueness review is needed.
            from billing_platform.constants import SCOPE_ALL

            from catalog.tasks.field_adoption import state as adoption_state
            from catalog.tasks.product_field_rollout import owners, prepare_claims

            if context.native.entity_type not in {"catalog.item", "catalog.product_family"}:
                raise ConflictError("unique definition requires an owner adoption workflow")
            await adoption_state(db, SCOPE_ALL, context.native.entity_type, lock=True)
            rows = await owners(
                db,
                context.company.company_id,
                context.native.entity_type,
                tenant_wide=definition.validation.unique_within == "tenant",
            )
            if rows:
                raise ConflictError("prepare the unique field index before writing existing owners")
            await prepare_claims(db, context, (definition,), rows)
            state = FieldIndexState(
                tenant_id=context.company.tenant_id,
                company_id=context.company.company_id,
                entity_type=context.native.entity_type,
                field_key=definition.key,
                generation=1,
                ready_generation=1,
                ready_digest=digest,
                row_version=1,
            )
            db.add(state)
            await db.flush()
        targets = (
            ()
            if state is None
            else tuple(
                generation
                for generation, fingerprint in (
                    (state.ready_generation, state.ready_digest),
                    (state.building_generation, state.building_digest),
                )
                if generation is not None and fingerprint == digest
            )
        )
        if not targets:
            raise ConflictError("custom search index generation must be prepared before writing")
        result[definition.key] = targets
    return result


async def index_values(
    db: AsyncSession, context: FieldContext, entity_id: uuid.UUID, values: Mapping[str, Any]
) -> None:
    generations = await write_generations(db, context)
    if generations:
        await replace_indexes(
            db,
            company_id=context.company.company_id,
            entity_type=context.native.entity_type,
            entity_id=entity_id,
            definitions=context.definitions,
            values=values,
            generations=generations,
        )


async def apply_custom_filters(
    db: AsyncSession, stmt: Select[Any], context: FieldContext, predicates: list[CustomPredicate]
) -> tuple[Select[Any], str]:
    if len(predicates) > 16:
        raise ValidationFailedError("custom query exceeds its predicate bound")
    version_parts = []
    for predicate in predicates:
        definition = index_definition(context, predicate.key)
        state = await load_index_state(
            db,
            context.company.company_id,
            context.native.entity_type,
            predicate.key,
            read_lock=True,
        )
        digest = definition_digest(definition)
        if state is None or state.ready_generation is None or state.ready_digest != digest:
            raise ConflictError("custom query generation is not ready")
        stmt = stmt.where(
            custom_predicate(
                predicate,
                binding=ReadyIndex(definition, state.ready_generation, digest),
                scalar_model=CustomFieldValueIndex,
                member_model=CustomFieldValueMember,
                owner_id=cast(ColumnElement[Any], INDEX_MODELS[context.native.entity_type].id),
                company_id=context.company.company_id,
                entity_type=context.native.entity_type,
                readable=context.readable(),
                currencies=frozenset(
                    {
                        context.company.base_currency,
                        *(v for v in (context.company.reporting_currency,) if v),
                    }
                ),
            )
        )
        version_parts.append(f"{predicate.key}:{state.ready_generation}:{digest}")
    return stmt, ";".join(sorted(set(version_parts)))
