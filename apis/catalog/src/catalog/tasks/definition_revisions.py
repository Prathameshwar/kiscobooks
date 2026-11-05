"""Shared native scalar-definition authoring with current field authority and evidence."""

import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    FeatureNotEnabledError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.listing import ListQuery, Page, SortColumn, fetch_page, resolve_sort
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.schemas.units import ExpectedVersion
from catalog.tasks.aggregate_work import AggregateWork
from catalog.tasks.field_context import FieldWriteChecks, load_field_context
from catalog.tasks.listing import cursor_codec
from catalog.tasks.policy_state import policy_state

Validator = Callable[[AggregateWork, Any, Mapping[str, Any], bool], Awaitable[None]]


@dataclass(frozen=True)
class DefinitionRevision:
    model: type[Any]
    parent: type[Any]
    parent_field: str
    permission: str
    input: type[BaseModel]
    item: type[BaseModel]
    detail: type[BaseModel]
    validate: Validator
    feature: str = "sales_promotions"

    def __post_init__(self) -> None:
        if not set(self.input.model_fields) <= set(self.model.__table__.columns.keys()):
            raise ValueError("definition inputs must name native columns")

    @property
    def entity(self) -> str:
        return f"catalog.{self.model.__tablename__}"


async def read(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    parent_id: uuid.UUID,
    object_id: uuid.UUID,
    spec: DefinitionRevision,
) -> BaseModel:
    context = await load_field_context(db, actor, company, spec.entity)
    if spec.parent_field not in context.readable():
        raise PermissionDeniedError("definition history requires readable parent membership")
    row = await company_object(db, spec.model, object_id, company_id=company)
    if getattr(row, spec.parent_field) != parent_id:
        raise PermissionDeniedError("definition belongs to another parent")
    values = {key: getattr(row, key) for key in context.native.fields}
    readable = context.readable(values)
    state = await policy_state(db, actor, company)
    return spec.detail.model_validate(
        {
            "id": row.id,
            "company_id": company,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "policy_generation": state.generation if state else 1,
            "complete": (
                set(spec.input.model_fields)
                | {spec.parent_field, "row_version", "revision", "published_at"}
            )
            <= readable,
            "operational_ready": False,
            **{
                key: value
                for key, value in values.items()
                if key in readable and key in spec.detail.model_fields
            },
        }
    )


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    parent_id: uuid.UUID,
    spec: DefinitionRevision,
    query: ListQuery,
    secret: bytes,
) -> Page[BaseModel]:
    context = await load_field_context(db, actor, company, spec.entity)
    readable = context.readable() | {"id"}
    if spec.parent_field not in readable:
        raise PermissionDeniedError("definition history membership is protected")
    if query.q is not None:
        raise ValidationFailedError("definition revisions do not support text search")
    statement = select(
        *(getattr(spec.model, key) for key in readable & spec.item.model_fields.keys())
    ).where(spec.model.company_id == company, getattr(spec.model, spec.parent_field) == parent_id)
    published = getattr(query, "published", None)
    if published is not None:
        if "published_at" not in readable:
            raise PermissionDeniedError("definition publication filter is protected")
        statement = statement.where(
            spec.model.published_at.is_not(None) if published else spec.model.published_at.is_(None)
        )
    terms = resolve_sort(
        query.sort,
        default="-id",
        columns={
            "id": SortColumn(spec.model.id, "uuid"),
            "revision": SortColumn(spec.model.revision, "integer"),
        },
        readable=readable,
        supported=frozenset({("id",), ("-id",), ("revision", "id"), ("-revision", "id")}),
    )
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=cursor_codec(
            secret, actor, company, spec.entity + ":" + str(parent_id), context, query
        ),
        project=lambda values: spec.item.model_validate(dict(values)),
    )


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    parent_id: uuid.UUID,
    spec: DefinitionRevision,
    body: BaseModel,
    key: str,
    action: Literal["create", "update", "publish"],
    object_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    permission = spec.permission + (".publish" if action == "publish" else ".manage")
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        spec.entity + "." + action,
        key,
        {
            "parent_id": str(parent_id),
            "id": str(object_id) if object_id else None,
            "body": body.model_dump(mode="json"),
        },
    )
    checks: dict[str, FieldWriteChecks] = {}
    work: AggregateWork | None = None
    state: Any = None

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal work, state
        work = AggregateWork(db, actor, company, permission)
        work.checks = checks
        context = await work.context(spec.model)
        if spec.feature not in context.features:
            raise FeatureNotEnabledError(
                "Enable this company capability before authoring definitions", feature=spec.feature
            )
        state = await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            for entity, changed in receipt["changed"].items():
                current = await load_field_context(
                    db, actor, company, entity, permission=permission
                )
                if entity in checks:
                    checks[entity].recheck(current)
                else:
                    assert_fields_writable(
                        frozenset(changed),
                        rules=current.rules(),
                        target=ScopePath(company_id=company),
                    )
            await read(db, actor, company, parent_id, uuid.UUID(receipt["id"]), spec)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert work is not None and state is not None
        if state.generation >= 2**63 - 1:
            raise ConflictError("company policy generation is exhausted")
        # The same company lock serializes parent semantic edits and revision creation.
        parent = await work.access.reference(spec.parent, parent_id)
        incoming = body.model_dump(exclude={"expected_version"})
        if action == "create":
            number = await db.scalar(
                select(func.max(spec.model.revision)).where(
                    spec.model.company_id == company,
                    getattr(spec.model, spec.parent_field) == parent_id,
                )
            )
            if number is not None and number >= 2**31 - 1:
                raise ConflictError("definition revision numbering is exhausted")
            row = spec.model(
                **work.common(),
                **{spec.parent_field: parent_id},
                revision=(number or 0) + 1,
                row_version=1,
                published_at=None,
                published_source_version=None,
                publication_generation=None,
                **incoming,
            )
            before: dict[str, Any] = {}
        else:
            assert object_id is not None and isinstance(body, ExpectedVersion)
            row = await company_object(db, spec.model, object_id, company_id=company, lock=True)
            if getattr(row, spec.parent_field) != parent_id:
                raise PermissionDeniedError("definition belongs to another parent")
            before = await work.access.values(row)
            if row.published_at is not None or row.row_version != body.expected_version:
                raise ConflictError(
                    "definition changed or is already published; reload before continuing"
                )
            await work.access.require(row)
            if action == "update":
                for name, value in incoming.items():
                    setattr(row, name, value)
            if row.row_version >= 2**31 - 1:
                raise ConflictError("definition version is exhausted")
            row.row_version += 1
        # Field denies are checked before current dependency validation can reveal data.
        after = await work.access.values(row)
        await work.authorize_values(
            spec.model, before, after, all_fields=action in {"create", "publish"}
        )
        validated = {name: getattr(row, name) for name in spec.input.model_fields}
        await spec.validate(work, parent, validated, action == "publish")
        if action == "publish":
            row.published_at = utcnow()
            row.published_source_version = (await work.context(spec.model)).source_version
            row.publication_generation = state.generation
        row.updated_by = actor.user_id
        await work.record(row, before, action, all_fields=action in {"create", "publish"})
        db.add(row)
        state.generation += 1
        await db.flush()
        return CommandReceipt(
            201 if action == "create" else 200,
            {
                "id": str(row.id),
                "changed": {entity: sorted(keys) for entity, keys in work.changed.items()},
            },
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        return await read(db, actor, company, parent_id, uuid.UUID(receipt["id"]), spec)

    try:
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=render
        )
    except IntegrityError as exc:
        raise ConflictError(
            "definition conflicts with native scoped references or revision history"
        ) from exc
