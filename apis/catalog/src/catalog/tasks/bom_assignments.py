"""Dated BOM applicability, serialized by the existing company policy lock."""

import datetime as dt
import uuid
from typing import Any, Literal, cast

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, PermissionDeniedError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.listing import (
    FilterColumn,
    Page,
    SortColumn,
    apply_filters,
    fetch_page,
    resolve_sort,
)
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.boms import Bom, BomAssignment, BomOutput, BomRevision
from catalog.models.warehouses import Warehouse
from catalog.schemas.boms import (
    AssignmentDetail,
    AssignmentInput,
    AssignmentListItem,
    AssignmentQuery,
    AssignmentUpdate,
    SelectionDetail,
    SelectionQuery,
)
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.bom_dependencies import goods
from catalog.tasks.bom_publication import require_current_publication
from catalog.tasks.boms import BomWork, project, require_feature
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import FieldWriteChecks, load_field_context
from catalog.tasks.listing import cursor_codec
from catalog.tasks.policy_state import policy_state


async def require_revision(
    access: ConfigurationAccess, revision_id: uuid.UUID, item_id: uuid.UUID
) -> BomRevision:
    revision = await access.reference(BomRevision, revision_id)
    await access.reference(Bom, revision.bom_id)
    await goods(access, item_id)
    if revision.status != "PUBLISHED":
        raise ConflictError("BOM applicability requires a published, nonretired revision")
    context = await access.context(BomOutput)
    if {"revision_id", "item_id", "role"} - context.readable():
        raise PermissionDeniedError("BOM primary-output applicability is protected")
    primary = await access.db.scalar(
        select(BomOutput.id)
        .where(
            BomOutput.company_id == access.company,
            BomOutput.revision_id == revision.id,
            BomOutput.item_id == item_id,
            BomOutput.role == "PRIMARY",
        )
        .limit(1)
    )
    if primary is None:
        raise ConflictError("BOM applicability must use its exact primary output SKU")
    await require_current_publication(access, revision)
    return cast(BomRevision, revision)


async def read(
    db: AsyncSession, actor: Actor, company: uuid.UUID, object_id: uuid.UUID
) -> AssignmentDetail:
    context = await load_field_context(db, actor, company, "catalog.bom_assignment")
    row = await company_object(db, BomAssignment, object_id, company_id=company)
    state = await policy_state(db, actor, company)
    return AssignmentDetail.model_validate(
        project(row, context, state.generation if state else 1).model_dump(exclude_unset=True)
    )


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    body: AssignmentInput | AssignmentUpdate | ExpectedVersion,
    key: str,
    action: Literal["create", "update", "deactivate"],
    object_id: uuid.UUID | None = None,
) -> CommandResult[AssignmentDetail]:
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        "bom_assignment." + action,
        key,
        {"id": str(object_id) if object_id else None, "body": body.model_dump(mode="json")},
    )
    work: BomWork | None = None
    state: Any = None
    checks: dict[str, FieldWriteChecks] = {}

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal work, state
        work = BomWork(db, actor, company, "bom.assign")
        work.checks = checks
        context = await work.context(BomAssignment)
        if action != "deactivate":
            require_feature(context)
        state = await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            await company_object(db, BomAssignment, uuid.UUID(receipt["id"]), company_id=company)
            if context.native.entity_type in checks:
                checks[context.native.entity_type].recheck(context)
            else:
                assert_fields_writable(
                    frozenset(receipt["changed"]),
                    rules=context.rules(),
                    target=ScopePath(company_id=company),
                )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert work is not None and state is not None
        if state.generation >= 2**63 - 1:
            raise ConflictError("company policy generation is exhausted")
        before: dict[str, Any] = {}
        if action == "create":
            assert isinstance(body, AssignmentInput)
            row = BomAssignment(
                **work.common(),
                row_version=1,
                is_active=True,
                output_role="PRIMARY",
                **body.model_dump(),
            )
        else:
            assert object_id is not None and isinstance(body, ExpectedVersion)
            row = await company_object(db, BomAssignment, object_id, company_id=company, lock=True)
            before = await work.access.values(row)
            if row.row_version != body.expected_version or row.row_version >= 2**31 - 1:
                raise ConflictError("BOM applicability version changed or is exhausted")
            if not row.is_active:
                raise ConflictError("withdrawn BOM applicability cannot be rewritten")
            if action == "deactivate":
                row.is_active = False
            else:
                assert isinstance(body, AssignmentUpdate)
                for key in AssignmentInput.model_fields:
                    setattr(row, key, getattr(body, key))
            row.row_version += 1
            row.updated_at, row.updated_by = utcnow(), actor.user_id
        await work.authorize_values(BomAssignment, before, await work.access.values(row))
        if row.is_active:
            await require_revision(work.access, row.bom_revision_id, row.item_id)
            if row.warehouse_id is not None:
                warehouse = await work.access.reference(Warehouse, row.warehouse_id)
                if warehouse.kind == "INTERNAL_TRANSIT":
                    raise ConflictError("BOM production applicability cannot use internal transit")
            overlap = select(BomAssignment.id).where(
                BomAssignment.company_id == company,
                BomAssignment.item_id == row.item_id,
                BomAssignment.scope_key
                == (row.warehouse_id.hex.upper() if row.warehouse_id else "*"),
                BomAssignment.is_active.is_(True),
                BomAssignment.valid_from <= (row.valid_to or dt.date.max),
                or_(BomAssignment.valid_to.is_(None), BomAssignment.valid_to >= row.valid_from),
            )
            if action != "create":
                overlap = overlap.where(BomAssignment.id != row.id)
            if await db.scalar(overlap.limit(1)) is not None:
                raise ConflictError("BOM applicability overlaps an active interval in this scope")
        await work.record(row, before, action)
        db.add(row)
        state.generation += 1
        await db.flush()
        return CommandReceipt(
            201 if action == "create" else 200,
            {
                "id": str(row.id),
                "changed": sorted(work.changed.get("catalog.bom_assignment", set())),
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> AssignmentDetail:
        return await read(db, actor, company, uuid.UUID(receipt["id"]))

    try:
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=render
        )
    except IntegrityError as exc:
        raise ConflictError(
            "BOM applicability conflicts with scoped reference or interval history"
        ) from exc


async def list_rows(
    db: AsyncSession, actor: Actor, company: uuid.UUID, query: AssignmentQuery, secret: bytes
) -> Page[AssignmentListItem]:
    context = await load_field_context(db, actor, company, "catalog.bom_assignment")
    readable = context.readable() | {"id"}
    if query.q is not None:
        from billing_platform.errors import ValidationFailedError

        raise ValidationFailedError("BOM applicability does not support text search")
    statement = select(
        *(getattr(BomAssignment, key) for key in readable & AssignmentListItem.model_fields.keys())
    ).where(BomAssignment.company_id == company)
    if query.bom_id is not None:
        context_revision = await load_field_context(db, actor, company, "catalog.bom_revision")
        if "bom_revision_id" not in readable or "bom_id" not in context_revision.readable():
            raise PermissionDeniedError("BOM applicability membership filter is protected")
        statement = statement.join(
            BomRevision, BomAssignment.bom_revision_id == BomRevision.id
        ).where(
            BomRevision.company_id == company,
            BomRevision.bom_id == query.bom_id,
        )
    statement = apply_filters(
        statement,
        {
            key: getattr(query, key)
            for key in ("item_id", "warehouse_id", "is_active")
            if getattr(query, key) is not None
        },
        filters={
            key: FilterColumn(key, getattr(BomAssignment, key))
            for key in ("item_id", "warehouse_id", "is_active")
        },
        readable=readable,
    )
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(BomAssignment.id, "uuid")},
        readable=readable,
        supported=frozenset({("id",), ("-id",)}),
    )
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=cursor_codec(secret, actor, company, "catalog.bom_assignment", context, query),
        project=lambda values: AssignmentListItem.model_validate(dict(values)),
    )


async def resolve(
    db: AsyncSession, actor: Actor, company: uuid.UUID, query: SelectionQuery
) -> SelectionDetail:
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(BomAssignment)
    require_feature(context)
    if (
        set(AssignmentInput.model_fields) - context.readable()
        or "is_active" not in context.readable()
    ):
        raise PermissionDeniedError("BOM selection requires complete readable applicability")
    for warehouse in (query.warehouse_id, None) if query.warehouse_id is not None else (None,):
        rows = list(
            await db.scalars(
                select(BomAssignment)
                .where(
                    BomAssignment.company_id == company,
                    BomAssignment.item_id == query.item_id,
                    BomAssignment.scope_key == (warehouse.hex.upper() if warehouse else "*"),
                    BomAssignment.is_active.is_(True),
                    BomAssignment.valid_from <= query.as_of,
                    or_(BomAssignment.valid_to.is_(None), BomAssignment.valid_to >= query.as_of),
                )
                .order_by(BomAssignment.valid_from.desc(), BomAssignment.id)
                .limit(2)
            )
        )
        if len(rows) > 1:
            raise ConflictError("BOM applicability is ambiguous in the selected scope")
        if rows:
            row = rows[0]
            await access.require(row)
            await require_revision(access, row.bom_revision_id, query.item_id)
            if warehouse is not None:
                await access.reference(Warehouse, warehouse)
            return SelectionDetail(assignment_id=row.id, bom_revision_id=row.bom_revision_id)
    raise NotFoundError("no BOM definition applies to this SKU, date and production scope")
