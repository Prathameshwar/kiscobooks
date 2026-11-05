"""Scoped master commands and lean lists over verified Identity authority."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from billing_platform.db.access import company_object
from billing_platform.db.base import Base
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.listing import (
    FilterColumn,
    ListQuery,
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

from catalog.events.evidence import audit_change
from catalog.models import PackType, UnitOfMeasure
from catalog.models.identifier_masters import IdentifierNamespace, IdentifierType
from catalog.models.product_definitions import ItemBarcode
from catalog.schemas.identifier_masters import (
    IdentifierNamespaceCreate,
    IdentifierNamespaceDetail,
    IdentifierNamespaceListItem,
    IdentifierTypeCreate,
    IdentifierTypeDetail,
    IdentifierTypeListItem,
)
from catalog.schemas.units import (
    PackTypeDetail,
    PackTypeInput,
    PackTypeListItem,
    UnitCreate,
    UnitDetail,
    UnitListItem,
)
from catalog.tasks.field_context import FieldContext, load_field_context
from catalog.tasks.listing import cursor_codec
from catalog.tasks.policy_state import policy_state
from catalog.tasks.product_dependencies import SEMANTIC_FIELDS, product_dependencies


@dataclass(frozen=True)
class Master:
    model: type[UnitOfMeasure] | type[PackType] | type[IdentifierType] | type[IdentifierNamespace]
    entity: str
    permission: str
    create: type[BaseModel]
    detail: type[BaseModel]
    item: type[BaseModel]


UNIT = Master(
    UnitOfMeasure, "catalog.unit_of_measure", "unit", UnitCreate, UnitDetail, UnitListItem
)
PACK = Master(
    PackType, "catalog.pack_type", "pack_type", PackTypeInput, PackTypeDetail, PackTypeListItem
)
IDENTIFIER_TYPE = Master(
    IdentifierType,
    "catalog.identifier_type",
    "identifier_type",
    IdentifierTypeCreate,
    IdentifierTypeDetail,
    IdentifierTypeListItem,
)
IDENTIFIER_NAMESPACE = Master(
    IdentifierNamespace,
    "catalog.identifier_namespace",
    "identifier_namespace",
    IdentifierNamespaceCreate,
    IdentifierNamespaceDetail,
    IdentifierNamespaceListItem,
)

type MasterRow = UnitOfMeasure | PackType | IdentifierType | IdentifierNamespace


def values(row: MasterRow, context: FieldContext) -> dict[str, Any]:
    return {key: getattr(row, key) for key in context.native.fields}


def detail(row: MasterRow, context: FieldContext, spec: Master) -> BaseModel:
    native = values(row, context)
    return spec.detail.model_validate(
        {
            "id": row.id,
            "company_id": row.company_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            **{key: value for key, value in native.items() if key in context.readable(native)},
        }
    )


async def read_master(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    object_id: uuid.UUID,
    spec: Master,
) -> BaseModel:
    context = await load_field_context(db, actor, company, spec.entity)
    row = await company_object(db, spec.model, object_id, company_id=company)
    return detail(row, context, spec)


async def unit_dependencies(db: AsyncSession, row: UnitOfMeasure) -> bool:
    # Every retained direct reference carries the unit's meaning, including
    # compound components and non-product masters. Only trusted mapped schema
    # names are used; each check is a company/tenant-scoped FK existence lookup.
    for mapper in sorted(Base.registry.mappers, key=lambda value: str(value.local_table)):
        columns = {
            foreign.parent.name
            for foreign in mapper.local_table.foreign_keys
            if foreign.column.table is row.__table__ and foreign.column.name == "id"
        }
        if not columns:
            continue
        model = mapper.class_
        found = await db.scalar(
            select(model.id)
            .where(
                model.tenant_id == row.tenant_id,
                model.company_id == row.company_id,
                or_(*(getattr(model, column) == row.id for column in sorted(columns))),
            )
            .limit(1)
        )
        if found is not None:
            return True
    return False


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    spec: Master,
    *,
    key: str,
    body: BaseModel,
    action: Literal["create", "update", "activate", "deactivate"],
    object_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    context: FieldContext | None = None
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

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal context
        context = await load_field_context(
            db,
            actor,
            company,
            spec.entity,
            permission=spec.permission + ".manage",
        )
        if receipt is None:
            await policy_state(db, actor, company, lock=True)
        if receipt is not None:
            row = await company_object(db, spec.model, uuid.UUID(receipt["id"]), company_id=company)
            native = values(row, context)
            context.assert_writable(frozenset(receipt["changed"]), before=native, after=native)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert context is not None
        before: dict[str, Any] = {}
        incoming = body.model_dump(exclude_unset=True)
        if action == "create":
            validated = spec.create.model_validate(incoming).model_dump()
            after = {**validated, "is_active": True, "row_version": 1}
            changed = frozenset(after) - {"row_version"}
            context.assert_writable(changed, before={}, after=after)
            row = spec.model(
                tenant_id=actor.tenant_id,
                company_id=company,
                created_by=actor.user_id,
                updated_by=actor.user_id,
                **after,
            )
            db.add(row)
        else:
            assert object_id is not None
            row = await company_object(db, spec.model, object_id, company_id=company, lock=True)
            expected = incoming.pop("expected_version")
            if row.row_version != expected:
                raise ConflictError("resource version changed; reload before updating")
            before = values(row, context)
            if action in {"activate", "deactivate"}:
                incoming = {"is_active": action == "activate"}
                after = {**before, **incoming}
            else:
                editable = {key: before[key] for key in spec.create.model_fields}
                try:
                    validated = spec.create.model_validate({**editable, **incoming}).model_dump()
                except ValidationError as exc:
                    # Validate the merged rule, but never return Pydantic input
                    # or a protected saved counterpart in the error envelope.
                    fields = {}
                    for error in exc.errors(include_input=False, include_context=False):
                        location = error["loc"]
                        field = (
                            str(location[0])
                            if location and location[0] in spec.create.model_fields
                            else "quantity_increment"
                            if isinstance(row, UnitOfMeasure)
                            else "name"
                        )
                        fields[field] = (
                            "Use a positive increment that fits the selected decimal places."
                            if field == "quantity_increment"
                            else "Enter printable text within the allowed length."
                        )
                    raise ValidationFailedError(
                        "Updated master settings are inconsistent.", fields=fields
                    ) from exc
                after = {**before, **validated}
            changed = frozenset(key for key in before if before[key] != after[key])
            context.assert_writable(changed, before=before, after=after)
            if isinstance(row, IdentifierType | IdentifierNamespace):
                if changed & {"code", "is_barcode"}:
                    raise ConflictError("identifier code and classification are immutable")
                if "is_active" in changed and not after["is_active"]:
                    reference = (
                        ItemBarcode.identifier_type_code
                        if isinstance(row, IdentifierType)
                        else ItemBarcode.namespace_code
                    )
                    if (
                        await db.scalar(
                            select(ItemBarcode.id)
                            .where(
                                ItemBarcode.company_id == company,
                                reference == row.code,
                            )
                            .limit(1)
                        )
                        is not None
                    ):
                        raise ConflictError("identifier definition is referenced; it cannot retire")
            if (
                isinstance(row, UnitOfMeasure)
                and changed
                & {
                    "code",
                    "dimension",
                    "decimal_places",
                    "quantity_increment",
                    "is_active",
                }
                and await unit_dependencies(db, row)
            ):
                raise ConflictError("unit is referenced; create a new definition instead")
            if changed & SEMANTIC_FIELDS and await product_dependencies(db, row):
                raise ConflictError("master semantics are referenced by product definitions")
            if changed:
                for field in changed:
                    setattr(row, field, after[field])
                if row.row_version >= 2**31 - 1:
                    raise ConflictError(
                        "resource version is exhausted; create a replacement definition"
                    )
                row.row_version += 1
                row.updated_at, row.updated_by = utcnow(), actor.user_id
                if "is_active" in changed and isinstance(row, UnitOfMeasure | PackType):
                    row.deactivated_at = None if row.is_active else utcnow()
                    row.deactivated_by = None if row.is_active else actor.user_id
        await db.flush()
        if changed:
            state = await policy_state(db, actor, company, lock=True)
            assert state is not None
            if state.generation >= 2**63 - 1:
                raise ConflictError("company policy generation exhausted")
            state.generation += 1
            audit_change(
                db, actor, company, spec.entity, row.id, action, changed, before=before, after=after
            )
        return CommandReceipt(
            201 if action == "create" else 200, {"id": str(row.id), "changed": sorted(changed)}
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        assert context is not None
        row = await company_object(db, spec.model, uuid.UUID(receipt["id"]), company_id=company)
        return detail(row, context, spec)

    try:
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=render
        )
    except IntegrityError as exc:
        raise ConflictError(
            "master code already exists or a reference prevents this change"
        ) from exc


async def list_masters(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    spec: Master,
    query: ListQuery,
    signing_secret: bytes,
) -> Page[BaseModel]:
    context = await load_field_context(db, actor, company, spec.entity)
    readable = context.readable() | {"id"}
    model = spec.model
    columns = {key: getattr(model, key) for key in readable}
    stmt = select(*columns.values()).where(model.company_id == company)
    filter_names = {"code", "is_active"}
    if spec is UNIT:
        filter_names.add("dimension")
    if spec is IDENTIFIER_TYPE:
        filter_names.add("is_barcode")
    identifier = spec in {IDENTIFIER_TYPE, IDENTIFIER_NAMESPACE}
    filters = {key: FilterColumn(key, getattr(model, key)) for key in filter_names}
    requested = query.model_dump(exclude_none=True, include=filter_names)
    stmt = apply_filters(stmt, requested, filters=filters, readable=readable)
    stmt = apply_search(
        stmt,
        query.q,
        columns={"code": model.code} if identifier else {"code": model.code, "name": model.name},
        readable=readable,
    )
    sort_columns = {
        "id": SortColumn(model.id, "uuid"),
        "code": SortColumn(model.code, "text"),
        **({} if identifier else {"name": SortColumn(model.name, "text")}),
    }
    terms = resolve_sort(
        query.sort,
        default="code" if "code" in readable else "id",
        columns=sort_columns,
        readable=readable,
        supported=frozenset(
            (key,)
            for key in ("id", "-id", "code", "-code", *(() if identifier else ("name", "-name")))
        ),
    )
    codec = cursor_codec(signing_secret, actor, company, spec.entity, context, query)

    def project(native: Mapping[str, Any]) -> BaseModel:
        return spec.item.model_validate(native)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)
