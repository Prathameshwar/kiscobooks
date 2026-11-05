"""Complete native route aggregates; publication pins eligible operation revisions."""

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from billing_platform.listing import Page, SortColumn, apply_search, fetch_page, resolve_sort
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.manufacturing_operations import (
    ManufacturingOperation,
    ManufacturingOperationRevision,
)
from catalog.models.manufacturing_routes import ManufacturingRouteRevision, ManufacturingRouteStep
from catalog.schemas.manufacturing_routes import (
    OperationReferenceQuery,
    OperationRevisionOption,
    RouteStepInput,
    RouteStepListItem,
    RouteStepQuery,
)
from catalog.tasks.field_context import FieldContext, FieldWriteChecks, load_field_context
from catalog.tasks.listing import cursor_codec

STEP_FIELDS = tuple(key for key in RouteStepInput.model_fields if key != "id")


async def reference_context(db: AsyncSession, actor: Actor, company: uuid.UUID) -> FieldContext:
    actor.require_scope("manufacturing_route.read", target=ScopePath(company_id=company))
    context = await load_field_context(
        db, actor, company, "catalog.manufacturing_operation_revision"
    )
    parent = await load_field_context(db, actor, company, "catalog.manufacturing_operation")
    if (
        not {"operation_id", "revision", "status", "published_at"} <= context.readable()
        or not {"code", "name", "is_active"} <= parent.readable()
    ):
        raise PermissionDeniedError("operation reference labels and lifecycle are protected")
    return context


def reference_statement(
    company: uuid.UUID,
) -> Select[tuple[uuid.UUID, uuid.UUID, int, str, str, str, bool]]:
    revision, owner = ManufacturingOperationRevision, ManufacturingOperation
    return (
        select(
            revision.id,
            revision.operation_id,
            revision.revision,
            revision.status,
            owner.code,
            owner.name,
            owner.is_active,
        )
        .join(owner, revision.operation_id == owner.id)
        .where(revision.company_id == company, owner.company_id == company)
    )


async def operation_options(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    query: OperationReferenceQuery,
    secret: bytes,
) -> Page[OperationRevisionOption]:
    context = await reference_context(db, actor, company)
    revision, owner = ManufacturingOperationRevision, ManufacturingOperation
    statement = reference_statement(company).where(
        revision.status == "PUBLISHED",
        revision.published_at.is_not(None),
        owner.is_active.is_(True),
    )
    if query.value is not None:
        if query.value.int == 0:
            raise ValidationFailedError("a real operation reference is required")
        statement = statement.where(revision.id == query.value)
    statement = apply_search(
        statement,
        query.q,
        columns={"code": owner.code, "name": owner.name},
        readable=frozenset({"code", "name"}),
    )
    terms = resolve_sort(
        query.sort,
        default="code",
        columns={
            "id": SortColumn(revision.id, "uuid"),
            "code": SortColumn(owner.code, "text"),
            "name": SortColumn(owner.name, "text"),
        },
        readable=frozenset({"id", "code", "name"}),
        supported=frozenset((key,) for key in ("id", "-id", "code", "-code", "name", "-name")),
    )
    codec = cursor_codec(secret, actor, company, "catalog.route_operation_options", context, query)
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=codec,
        project=lambda row: OperationRevisionOption.model_validate(row),
    )


async def operation_reference(
    db: AsyncSession, actor: Actor, company: uuid.UUID, identifier: uuid.UUID
) -> OperationRevisionOption:
    await reference_context(db, actor, company)
    # Exact historical hydration may show retired/inactive references. Selection
    # and publication eligibility remain independently strict.
    await company_object(db, ManufacturingOperationRevision, identifier, company_id=company)
    row = (
        (
            await db.execute(
                reference_statement(company).where(ManufacturingOperationRevision.id == identifier)
            )
        )
        .mappings()
        .one()
    )
    return OperationRevisionOption.model_validate(row)


async def steps(
    db: AsyncSession, revision: ManufacturingRouteRevision
) -> list[ManufacturingRouteStep]:
    rows = list(
        await db.scalars(
            select(ManufacturingRouteStep)
            .where(
                ManufacturingRouteStep.company_id == revision.company_id,
                ManufacturingRouteStep.revision_id == revision.id,
            )
            .order_by(ManufacturingRouteStep.sequence, ManufacturingRouteStep.id)
            .limit(51)
        )
    )
    if (
        len(rows) != revision.step_count
        or len(rows) > 50
        or tuple(row.sequence for row in rows) != tuple(range(1, len(rows) + 1))
    ):
        raise ConflictError("route step set is incomplete or not sequential")
    for row in rows:
        RouteStepInput.model_validate(
            {"id": row.id, **{key: getattr(row, key) for key in STEP_FIELDS}}
        )
    return rows


def values(row: ManufacturingRouteStep, context: FieldContext) -> dict[str, Any]:
    return {key: getattr(row, key) for key in context.native.fields}


async def validate_operation(
    db: AsyncSession, actor: Actor, company: uuid.UUID, identifier: uuid.UUID
) -> None:
    access = await load_field_context(
        db, actor, company, "catalog.manufacturing_operation_revision"
    )
    owner_access = await load_field_context(db, actor, company, "catalog.manufacturing_operation")
    if (
        not {"operation_id", "status", "published_at"} <= access.readable()
        or "is_active" not in owner_access.readable()
    ):
        raise PermissionDeniedError("route operation eligibility fields are protected")
    revision = await company_object(
        db, ManufacturingOperationRevision, identifier, company_id=company, lock=True
    )
    operation = await company_object(
        db, ManufacturingOperation, revision.operation_id, company_id=company, lock=True
    )
    if not operation.is_active or revision.status != "PUBLISHED" or revision.published_at is None:
        raise ValidationFailedError(
            "choose a published, nonretired revision of an active operation"
        )


async def replace_steps(
    db: AsyncSession,
    actor: Actor,
    revision: ManufacturingRouteRevision,
    incoming: Sequence[Mapping[str, Any]],
    checks: FieldWriteChecks,
) -> frozenset[str]:
    old = await steps(db, revision)
    context = await load_field_context(
        db,
        actor,
        revision.company_id,
        "catalog.manufacturing_route_step",
        permission="manufacturing_route.manage",
    )
    prior = {row.id: row for row in old}
    proposed: dict[uuid.UUID, dict[str, Any]] = {}
    for item in incoming:
        body = RouteStepInput.model_validate(item)
        if body.id is not None and body.id not in prior:
            raise PermissionDeniedError("route step identity is outside this draft revision")
        proposed[body.id or uuid7()] = {
            "revision_id": revision.id,
            **body.model_dump(exclude={"id"}),
        }
    changed: frozenset[str] = frozenset()
    for identifier in prior.keys() | proposed.keys():
        before = values(prior[identifier], context) if identifier in prior else {}
        after = proposed.get(identifier, {})
        difference = frozenset(
            key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
        )
        context.assert_writable(difference, before=before, after=after, checked=checks)
        changed |= difference
    # Reject field-policy denials before resolving any caller-supplied reference.
    for item in proposed.values():
        await validate_operation(db, actor, revision.company_id, item["operation_revision_id"])
    if not changed:
        return changed
    # Draft children have no published external consumers. Remove before insert
    # to satisfy immediate unique sequence constraints while retaining stable IDs.
    timestamps = {row.id: (row.created_at, row.created_by) for row in old}
    for row in old:
        await db.delete(row)
    await db.flush()
    for identifier, item in proposed.items():
        created_at, created_by = timestamps.get(identifier, (utcnow(), actor.user_id))
        db.add(
            ManufacturingRouteStep(
                id=identifier,
                tenant_id=actor.tenant_id,
                company_id=revision.company_id,
                created_at=created_at,
                created_by=created_by,
                updated_at=utcnow(),
                updated_by=actor.user_id,
                **item,
            )
        )
    revision.step_count = len(proposed)
    return changed


async def publish_steps(
    db: AsyncSession, actor: Actor, revision: ManufacturingRouteRevision, checks: FieldWriteChecks
) -> frozenset[str]:
    rows = await steps(db, revision)
    if not rows:
        raise ValidationFailedError("a published route requires at least one sequential step")
    context = await load_field_context(
        db,
        actor,
        revision.company_id,
        "catalog.manufacturing_route_step",
        permission="manufacturing_route.publish",
    )
    changed: frozenset[str] = frozenset()
    for row in rows:
        native = values(row, context)
        context.assert_writable(frozenset(native), before=native, after=native, checked=checks)
        changed |= frozenset(native)
    for row in rows:
        await validate_operation(db, actor, revision.company_id, row.operation_revision_id)
    return changed


async def authorize_step_replay(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    changed: frozenset[str],
    *,
    publishing: bool,
    checks: FieldWriteChecks | None,
) -> None:
    context = await load_field_context(
        db,
        actor,
        company,
        "catalog.manufacturing_route_step",
        permission="manufacturing_route.publish" if publishing else "manufacturing_route.manage",
    )
    if checks is not None:
        checks.recheck(context)
    else:
        assert_fields_writable(changed, rules=context.rules(), target=ScopePath(company_id=company))


async def list_steps(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    route_id: uuid.UUID,
    revision_id: uuid.UUID,
    query: RouteStepQuery,
    secret: bytes,
) -> Page[RouteStepListItem]:
    context = await load_field_context(db, actor, company, "catalog.manufacturing_route_step")
    parent_context = await load_field_context(
        db, actor, company, "catalog.manufacturing_route_revision"
    )
    if "revision_id" not in context.readable() or "route_id" not in parent_context.readable():
        raise PermissionDeniedError("route step browsing requires readable parent membership")
    revision = await company_object(db, ManufacturingRouteRevision, revision_id, company_id=company)
    if revision.route_id != route_id:
        raise PermissionDeniedError("revision belongs to another manufacturing route")
    await steps(db, revision)
    if query.q is not None:
        raise ValidationFailedError("route steps use sequential browsing, not text search")
    model = ManufacturingRouteStep
    readable = context.readable() | {"id"}
    statement = select(*(getattr(model, key) for key in readable)).where(
        model.company_id == company, model.revision_id == revision_id
    )
    terms = resolve_sort(
        query.sort,
        default="sequence" if "sequence" in readable else "id",
        columns={
            "id": SortColumn(model.id, "uuid"),
            "sequence": SortColumn(model.sequence, "integer"),
        },
        readable=readable,
        supported=frozenset((key,) for key in ("id", "-id", "sequence", "-sequence")),
    )
    codec = cursor_codec(
        secret,
        actor,
        company,
        "catalog.manufacturing_route_step:" + str(revision_id),
        context,
        query,
    )
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=codec,
        project=lambda row: RouteStepListItem.model_validate(row),
    )
