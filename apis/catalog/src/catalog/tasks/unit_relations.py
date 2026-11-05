"""Immutable canonical relations and nonoverlapping dated official unit codes."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.exact import RationalConversion
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
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.units import CanonicalRelation, QuantityRule, UnitDefinition, storage_quantity
from catalog.events.evidence import audit_change
from catalog.models import UnitConversion, UnitOfMeasure, UnitTaxCode
from catalog.schemas.units import (
    UnitConversionDetail,
    UnitConversionInput,
    UnitConversionListItem,
    UnitConvertInput,
    UnitConvertResult,
    UnitTaxCodeClose,
    UnitTaxCodeDetail,
    UnitTaxCodeInput,
    UnitTaxCodeListItem,
)
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import FieldContext, load_field_context
from catalog.tasks.listing import cursor_codec
from catalog.tasks.policy_state import policy_state
from catalog.tasks.unit_consistency import guard_relation


@dataclass(frozen=True)
class Relation:
    model: type[UnitConversion] | type[UnitTaxCode]
    entity: str
    detail: type[UnitConversionDetail] | type[UnitTaxCodeDetail]
    item: type[UnitConversionListItem] | type[UnitTaxCodeListItem]
    filters: frozenset[str]


CONVERSION = Relation(
    UnitConversion,
    "catalog.unit_conversion",
    UnitConversionDetail,
    UnitConversionListItem,
    frozenset({"from_unit_id", "canonical_unit_id"}),
)
TAX_CODE = Relation(
    UnitTaxCode,
    "catalog.unit_tax_code",
    UnitTaxCodeDetail,
    UnitTaxCodeListItem,
    frozenset({"unit_id", "jurisdiction"}),
)


def native_values(row: UnitConversion | UnitTaxCode, context: FieldContext) -> dict[str, Any]:
    return {key: getattr(row, key) for key in context.native.fields}


def render(row: UnitConversion | UnitTaxCode, context: FieldContext, spec: Relation) -> BaseModel:
    native = native_values(row, context)
    return spec.detail.model_validate(
        {
            "id": row.id,
            "company_id": row.company_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            **{key: value for key, value in native.items() if key in context.readable(native)},
        }
    )


async def read_relation(
    db: AsyncSession, actor: Actor, company: uuid.UUID, object_id: uuid.UUID, spec: Relation
) -> BaseModel:
    context = await load_field_context(db, actor, company, spec.entity)
    row = await company_object(db, spec.model, object_id, company_id=company)
    return render(row, context, spec)


def unit_definition(row: UnitOfMeasure) -> UnitDefinition:
    return UnitDefinition(
        row.id,
        row.company_id,
        row.dimension,
        QuantityRule(row.decimal_places, row.quantity_increment),
    )


async def create_relation(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    body: UnitConversionInput | UnitTaxCodeInput,
) -> UnitConversion | UnitTaxCode:
    ids = (
        (body.from_unit_id, body.canonical_unit_id)
        if isinstance(body, UnitConversionInput)
        else (body.unit_id,)
    )
    units = {}
    # Consistent lock order serializes graph creation with master mutation.
    for unit_id in sorted(set(ids)):
        row = await company_object(db, UnitOfMeasure, unit_id, company_id=company, lock=True)
        if not row.is_active:
            raise ConflictError("unit is inactive")
        units[unit_id] = row
    if isinstance(body, UnitConversionInput):
        ratio = RationalConversion(body.numerator, body.denominator)
        CanonicalRelation(
            unit_definition(units[body.from_unit_id]),
            unit_definition(units[body.canonical_unit_id]),
            ratio,
        )
        if body.from_unit_id != body.canonical_unit_id:
            root = await db.scalar(
                select(UnitConversion).where(
                    UnitConversion.company_id == company,
                    UnitConversion.from_unit_id == body.canonical_unit_id,
                )
            )
            if root is None or root.canonical_unit_id != root.from_unit_id:
                raise ValidationFailedError(
                    "conversion must point directly to a declared canonical root"
                )
        candidate = UnitConversion(
            tenant_id=actor.tenant_id,
            company_id=company,
            created_by=actor.user_id,
            updated_by=actor.user_id,
            from_unit_id=body.from_unit_id,
            canonical_unit_id=body.canonical_unit_id,
            numerator=ratio.numerator,
            denominator=ratio.denominator,
        )
        await guard_relation(ConfigurationAccess(db, actor, company), candidate)
        return candidate
    overlap = await db.scalar(
        select(UnitTaxCode.id)
        .where(
            UnitTaxCode.company_id == company,
            UnitTaxCode.unit_id == body.unit_id,
            UnitTaxCode.jurisdiction == body.jurisdiction,
            UnitTaxCode.valid_from <= (body.valid_to or dt.date.max),
            or_(UnitTaxCode.valid_to.is_(None), UnitTaxCode.valid_to >= body.valid_from),
        )
        .limit(1)
    )
    if overlap is not None:
        raise ConflictError("official unit-code dates overlap an existing mapping")
    return UnitTaxCode(
        tenant_id=actor.tenant_id,
        company_id=company,
        created_by=actor.user_id,
        updated_by=actor.user_id,
        **body.model_dump(),
    )


async def relation_command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    spec: Relation,
    body: UnitConversionInput | UnitTaxCodeInput | UnitTaxCodeClose,
    key: str,
    object_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    context: FieldContext | None = None
    action = "close" if isinstance(body, UnitTaxCodeClose) else "create"
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        spec.entity + "." + action,
        key,
        {"body": body.model_dump(mode="json"), "id": str(object_id) if object_id else None},
    )

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal context
        context = await load_field_context(
            db, actor, company, spec.entity, permission="unit.manage"
        )
        if receipt is None:
            await policy_state(db, actor, company, lock=True)
        if receipt:
            row = await company_object(db, spec.model, uuid.UUID(receipt["id"]), company_id=company)
            native = native_values(row, context)
            context.assert_writable(frozenset(receipt["changed"]), before=native, after=native)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert context is not None
        row: UnitConversion | UnitTaxCode
        if isinstance(body, UnitTaxCodeClose):
            assert object_id is not None and spec is TAX_CODE
            # Lock parent first, just like insertion; the child's identity is immutable.
            row = await company_object(db, UnitTaxCode, object_id, company_id=company)
            await company_object(db, UnitOfMeasure, row.unit_id, company_id=company, lock=True)
            row = await company_object(db, UnitTaxCode, object_id, company_id=company, lock=True)
            if row.valid_to != body.expected_valid_to:
                raise ConflictError("mapping end date changed; reload before closing")
            if body.valid_to < row.valid_from or (row.valid_to and body.valid_to > row.valid_to):
                raise ValidationFailedError("closure must shorten the existing effective interval")
            before = native_values(row, context)
            after = {**before, "valid_to": body.valid_to}
            changed = frozenset({"valid_to"}) if row.valid_to != body.valid_to else frozenset()
            context.assert_writable(changed, before=before, after=after)
            if changed:
                row.valid_to, row.updated_by = body.valid_to, actor.user_id
        else:
            created = await create_relation(db, actor, company, body)
            before, after = {}, native_values(created, context)
            changed = frozenset(after)
            context.assert_writable(changed, before=before, after=after)
            db.add(created)
            row = created
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
            200 if action == "close" else 201, {"id": str(row.id), "changed": sorted(changed)}
        )

    async def current_response(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        assert context is not None
        row = await company_object(db, spec.model, uuid.UUID(receipt["id"]), company_id=company)
        return render(row, context, spec)

    try:
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=current_response
        )
    except IntegrityError as exc:
        raise ConflictError("unit relation already exists or has an invalid reference") from exc


async def list_relations(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    spec: Relation,
    query: ListQuery,
    signing_secret: bytes,
) -> Page[BaseModel]:
    context = await load_field_context(db, actor, company, spec.entity)
    readable = context.readable() | {"id"}
    stmt = select(*(getattr(spec.model, key) for key in readable)).where(
        spec.model.company_id == company
    )
    stmt = apply_filters(
        stmt,
        query.model_dump(exclude_none=True, include=set(spec.filters)),
        filters={key: FilterColumn(key, getattr(spec.model, key)) for key in spec.filters},
        readable=readable,
    )
    valid_at = query.model_dump().get("valid_at")
    if spec is TAX_CODE:
        stmt = apply_search(
            stmt, query.q, columns={"official_code": UnitTaxCode.official_code}, readable=readable
        )
        if valid_at is not None:
            if not {"valid_from", "valid_to"} <= readable:
                raise PermissionDeniedError("date filters require readable validity fields")
            stmt = stmt.where(
                UnitTaxCode.valid_from <= valid_at,
                or_(UnitTaxCode.valid_to.is_(None), UnitTaxCode.valid_to >= valid_at),
            )
    elif query.q is not None:
        raise ValidationFailedError("conversion search uses exact unit filters")
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(spec.model.id, "uuid")},
        readable=readable,
        supported=frozenset({("id",), ("-id",)}),
    )

    def project(native: Mapping[str, Any]) -> BaseModel:
        return spec.item.model_validate(native)

    return await fetch_page(
        db,
        stmt,
        query=query,
        terms=terms,
        codec=cursor_codec(signing_secret, actor, company, spec.entity, context, query),
        project=project,
    )


async def convert_units(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    body: UnitConvertInput,
) -> UnitConvertResult:
    context = await load_field_context(db, actor, company, "catalog.unit_of_measure")
    units = {}
    for unit_id in sorted({body.from_unit_id, body.to_unit_id}):
        row = await company_object(db, UnitOfMeasure, unit_id, company_id=company)
        native = {key: getattr(row, key) for key in context.native.fields}
        if not {
            "dimension",
            "decimal_places",
            "quantity_increment",
            "is_active",
        } <= context.readable(native):
            raise PermissionDeniedError("conversion requires readable measurement fields")
        if not row.is_active:
            raise ConflictError("unit is inactive")
        units[unit_id] = row
    source, target = units[body.from_unit_id], units[body.to_unit_id]
    if source.dimension != target.dimension:
        raise ValidationFailedError("conversion requires compatible dimensions")
    ratio = Fraction(1)
    if source.id != target.id:
        relation_context = await load_field_context(db, actor, company, "catalog.unit_conversion")
        relations = list(
            await db.scalars(
                select(UnitConversion).where(
                    UnitConversion.company_id == company, UnitConversion.from_unit_id.in_(units)
                )
            )
        )
        by_source = {row.from_unit_id: row for row in relations}
        if set(by_source) != set(units):
            raise ValidationFailedError("both units require declared canonical conversions")
        for relation in relations:
            if not set(relation_context.native.fields) <= relation_context.readable(
                native_values(relation, relation_context)
            ):
                raise PermissionDeniedError("conversion requires readable canonical relations")
        left, right = by_source[source.id], by_source[target.id]
        if left.canonical_unit_id != right.canonical_unit_id:
            raise ValidationFailedError("units do not share a canonical root")
        ratio = Fraction(left.numerator * right.denominator, left.denominator * right.numerator)
    try:
        entered = unit_definition(source).quantity.validate(body.quantity)
        result = unit_definition(target).quantity.validate(
            storage_quantity(Fraction(entered) * ratio)
        )
    except ValueError as exc:
        raise ValidationFailedError("quantity conversion is not exactly representable") from exc
    return UnitConvertResult(
        from_unit_id=source.id, to_unit_id=target.id, input_quantity=entered, quantity=result
    )
