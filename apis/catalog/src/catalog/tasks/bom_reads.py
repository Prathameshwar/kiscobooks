"""Lean signed-keyset BOM history/lines and exact non-posting preview."""

import uuid
from typing import Any, Literal, cast

from billing_platform.db.access import company_object
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import ListQuery, Page, SortColumn, fetch_page, resolve_sort
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.bom_definitions import BatchRule
from catalog.domain.bom_requirements import Component, Output, preview
from catalog.models.boms import BomComponent, BomDraft, BomOutput, BomRevision
from catalog.schemas.boms import (
    BomDraftListItem,
    BomHistoryQuery,
    BomRevisionListItem,
    ComponentListItem,
    OutputListItem,
    PreviewDetail,
    PreviewInput,
    PreviewOutput,
    PreviewRequirement,
)
from catalog.tasks.bom_dependencies import line_dependency, route_dependency
from catalog.tasks.bom_publication import require_current_publication
from catalog.tasks.boms import definition_input, read_definition, require_feature
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import load_field_context
from catalog.tasks.listing import cursor_codec

LISTS: dict[type[Any], type[BaseModel]] = {
    BomDraft: BomDraftListItem,
    BomRevision: BomRevisionListItem,
    BomComponent: ComponentListItem,
    BomOutput: OutputListItem,
}


async def list_children(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    parent_model: type[Any],
    model: type[Any],
    query: ListQuery,
    secret: bytes,
) -> Page[BaseModel]:
    await read_definition(db, actor, company, bom_id, object_id, parent_model)
    parent = await company_object(db, parent_model, object_id, company_id=company)
    return await list_rows(db, actor, company, bom_id, model, query, secret, parent)


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    bom_id: uuid.UUID,
    model: type[Any],
    query: ListQuery,
    secret: bytes,
    parent: BomDraft | BomRevision | None = None,
) -> Page[BaseModel]:
    entity = "catalog." + model.__tablename__
    context = await load_field_context(db, actor, company, entity)
    readable = context.readable() | {"id"}
    schema = LISTS[model]
    statement = select(
        *(getattr(model, key) for key in readable & schema.model_fields.keys())
    ).where(model.company_id == company)
    if query.q is not None:
        raise ValidationFailedError("BOM history and lines do not support text search")
    if parent is None:
        if "bom_id" not in readable:
            raise PermissionDeniedError("BOM history requires readable parent membership")
        statement = statement.where(model.bom_id == bom_id)
        order = "draft_number" if model is BomDraft else "revision"
        if isinstance(query, BomHistoryQuery) and query.status is not None:
            if "status" not in readable:
                raise PermissionDeniedError("BOM lifecycle filter is protected")
            statement = statement.where(model.status == query.status)
    else:
        parent_field = "draft_id" if isinstance(parent, BomDraft) else "revision_id"
        if parent_field not in readable:
            raise PermissionDeniedError("BOM lines require readable parent membership")
        statement = statement.where(getattr(model, parent_field) == parent.id)
        order = "sequence"
    terms = resolve_sort(
        query.sort,
        default=order + ",id",
        columns={
            order: SortColumn(getattr(model, order), "integer"),
            "id": SortColumn(model.id, "uuid"),
        },
        readable=readable,
        supported=frozenset({(order, "id"), ("-" + order, "id"), ("id",), ("-id",)}),
    )
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=cursor_codec(
            secret,
            actor,
            company,
            entity + ":" + str(parent.id if parent else bom_id),
            context,
            query,
        ),
        project=lambda values: schema.model_validate(dict(values)),
    )


async def preview_definition(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    bom_id: uuid.UUID,
    object_id: uuid.UUID,
    model: type[Any],
    body: PreviewInput,
) -> PreviewDetail:
    context = await load_field_context(db, actor, company, "catalog." + model.__tablename__)
    require_feature(context)
    access = ConfigurationAccess(db, actor, company)
    row = await company_object(db, model, object_id, company_id=company)
    await access.require(row)
    if row.bom_id != bom_id:
        raise PermissionDeniedError("BOM definition belongs to another parent")
    if isinstance(row, BomRevision) and row.status != "PUBLISHED":
        raise ValidationFailedError("new previews require a nonretired BOM revision")
    definition = (
        await require_current_publication(access, row)
        if isinstance(row, BomRevision)
        else await definition_input(access, row)
    )
    await route_dependency(access, definition)
    result = preview(
        body.requested_good_quantity,
        tuple(
            Component(
                line.line_key,
                line.item_id,
                line.quantity,
                line.basis,
                line.loss_fraction,
                line.timing,
            )
            for line in definition.components
        ),
        tuple(
            Output(
                line.line_key, line.item_id, line.nominal_quantity, line.yield_fraction, line.role
            )
            for line in definition.outputs
        ),
        run_count=body.run_count,
    )
    BatchRule(
        definition.batch_minimum, definition.batch_maximum, definition.batch_multiple
    ).validate(result.nominal_run_quantity, body.run_count, body.run_quantities)
    dependencies = {}
    for line in (*definition.components, *definition.outputs):
        dependencies[line.line_key] = await line_dependency(
            access, line, definition.definition_date
        )
    return PreviewDetail(
        nominal_run_quantity=result.nominal_run_quantity,
        requirements=tuple(
            PreviewRequirement(
                line_key=value.line_key,
                item_id=value.item_id,
                required_quantity=value.required_quantity,
                base_quantity=dependencies[value.line_key].validate(value.required_quantity),
            )
            for value in result.requirements
        ),
        outputs=tuple(
            PreviewOutput(
                line_key=value.line_key,
                item_id=value.item_id,
                role=cast(Literal["PRIMARY", "CO_PRODUCT", "BY_PRODUCT", "SCRAP"], value.role),
                expected_quantity=value.expected_quantity,
                base_quantity=dependencies[value.line_key].validate(value.expected_quantity),
            )
            for value in result.outputs
        ),
    )
