"""Native, company-locked stack drafts and immutable definition publication."""

import hashlib
import json
import uuid
from typing import Any, Literal

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, FeatureNotEnabledError, PermissionDeniedError
from billing_platform.field_policy import assert_fields_writable
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
    Page,
    SortColumn,
    apply_filters,
    apply_search,
    fetch_page,
    resolve_sort,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.events.evidence import audit_change
from catalog.models.promotion_authoring import (
    PromotionStackDraft,
    PromotionStackDraftGroup,
    PromotionStackDraftPermission,
)
from catalog.models.promotions import (
    PromotionStackGroup,
    PromotionStackPermission,
    PromotionStackPolicy,
)
from catalog.schemas.promotion_authoring import (
    StackDraftDetail,
    StackDraftInput,
    StackDraftListItem,
    StackDraftUpdate,
    StackPolicyDetail,
    StackPolicyListItem,
    StackQuery,
)
from catalog.schemas.promotions import StackGroup, StackPermission, StackPolicyTerms
from catalog.schemas.units import ExpectedVersion
from catalog.tasks.aggregate_work import AggregateWork
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import FieldWriteChecks, load_field_context
from catalog.tasks.listing import cursor_codec
from catalog.tasks.policy_state import policy_state

DRAFT_MODELS = (PromotionStackDraft, PromotionStackDraftGroup, PromotionStackDraftPermission)
PUBLISHED_MODELS = (PromotionStackPolicy, PromotionStackGroup, PromotionStackPermission)
ALL_MODELS = (*DRAFT_MODELS, *PUBLISHED_MODELS)


def feature(context: Any) -> None:
    if "sales_promotions" not in context.features:
        raise FeatureNotEnabledError(
            "Enable sales promotions before authoring stack policies", feature="sales_promotions"
        )


async def collection(access: ConfigurationAccess, row: Any) -> tuple[list[Any], list[Any]]:
    draft = isinstance(row, PromotionStackDraft)
    models = DRAFT_MODELS if draft else PUBLISHED_MODELS
    parent = "draft_id" if draft else "policy_revision_id"
    results: list[list[Any]] = []
    for model, bound in ((models[1], 20), (models[2], 190)):
        context = await access.context(model)
        if parent not in context.readable():
            raise PermissionDeniedError("stack group membership is protected")
        rows = list(
            await access.db.scalars(
                select(model)
                .where(model.company_id == access.company, getattr(model, parent) == row.id)
                .order_by(model.id)
                .limit(bound + 1)
            )
        )
        if len(rows) > bound:
            raise ConflictError("stack policy exceeds the supported native bounds")
        results.append(rows)
    groups, permissions = results
    groups.sort(key=lambda value: value.position)
    if [value.position for value in groups] != list(range(len(groups))) or (
        draft and (len(groups) != row.group_count or len(permissions) != row.permission_count)
    ):
        raise ConflictError("stack policy collection is incomplete; reload before continuing")
    return groups, permissions


async def terms(
    access: ConfigurationAccess, row: Any
) -> tuple[tuple[StackGroup, ...], tuple[StackPermission, ...]]:
    await access.require(row)
    groups, permissions = await collection(access, row)
    for child in (*groups, *permissions):
        await access.require(child)
    return (
        tuple(
            StackGroup(
                group_id=value.id,
                stage=value.stage,
                selection=value.selection,
                changes_basket=value.changes_basket,
            )
            for value in groups
        ),
        tuple(
            StackPermission(
                earlier_group_id=value.earlier_group_id,
                later_group_id=value.later_group_id,
                include_reward_units=value.include_reward_units,
            )
            for value in permissions
        ),
    )


async def read(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    object_id: uuid.UUID,
    *,
    published: bool = False,
) -> BaseModel:
    model = PromotionStackPolicy if published else PromotionStackDraft
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(model)
    row = await company_object(db, model, object_id, company_id=company)
    values = await access.values(row)
    readable = context.readable(values)
    schema = StackPolicyDetail if published else StackDraftDetail
    result: dict[str, Any] = {
        "id": row.id,
        "company_id": company,
        "complete": False,
        "operational_ready": False,
        **{
            key: value
            for key, value in values.items()
            if key in readable and key in schema.model_fields
        },
    }
    if not published:
        state = await policy_state(db, actor, company)
        result["policy_generation"] = state.generation if state else 1
    models = PUBLISHED_MODELS if published else DRAFT_MODELS
    # Read-denied children are retained, never represented as an editable empty set.
    children_readable = set(values) <= readable
    for child in models[1:]:
        child_context = await access.context(child)
        children_readable &= set(child_context.native.fields) <= child_context.readable()
    if children_readable:
        try:
            groups, permissions = await terms(access, row)
        except PermissionDeniedError:
            pass
        else:
            result.update(groups=groups, permissions=permissions, complete=True)
    return schema.model_validate(result)


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    query: StackQuery,
    secret: bytes,
    *,
    published: bool = False,
) -> Page[BaseModel]:
    model = PromotionStackPolicy if published else PromotionStackDraft
    schema = StackPolicyListItem if published else StackDraftListItem
    context = await load_field_context(db, actor, company, "catalog." + model.__tablename__)
    readable = context.readable() | {"id"}
    statement = select(
        *(getattr(model, key) for key in readable & schema.model_fields.keys())
    ).where(model.company_id == company)
    filters: dict[str, Any] = {"code": query.code}
    columns = {"code": FilterColumn("code", model.code)}
    if query.status is not None:
        if published:
            raise ConflictError(
                "published stack definitions use immutable versions, not draft status"
            )
        filters["status"] = query.status
        columns["status"] = FilterColumn("status", PromotionStackDraft.status)
    statement = apply_filters(
        statement,
        {key: value for key, value in filters.items() if value is not None},
        filters=columns,
        readable=readable,
    )
    statement = apply_search(statement, query.q, columns={"code": model.code}, readable=readable)
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(model.id, "uuid"), "code": SortColumn(model.code, "text")},
        readable=readable,
        supported=frozenset((key,) for key in ("id", "-id", "code", "-code")),
    )
    return await fetch_page(
        db,
        statement,
        query=query,
        terms=terms,
        codec=cursor_codec(
            secret, actor, company, "catalog." + model.__tablename__, context, query
        ),
        project=lambda values: schema.model_validate(dict(values)),
    )


async def replace(work: AggregateWork, row: PromotionStackDraft, body: StackDraftInput) -> None:
    child: Any
    groups, permissions = await collection(work.access, row)
    old_groups = {value.id: value for value in groups}
    identities = {
        value.group_id: value.group_id if value.group_id in old_groups else uuid7()
        for value in body.groups
    }
    for existing in (permissions, groups):
        for child in existing:
            await work.access.require(child)
            before = await work.access.values(child)
            await work.authorize_values(type(child), before, {})
            work.changed.setdefault("catalog." + child.__tablename__, set()).update(before)
            audit_change(
                work.db,
                work.actor,
                work.company,
                "catalog." + child.__tablename__,
                child.id,
                "update",
                frozenset(before),
                before=before,
                after={},
            )
            await work.db.delete(child)
        await work.db.flush()
    for position, group in enumerate(body.groups):
        values = work.common()
        previous = old_groups.get(group.group_id)
        values["id"] = identities[group.group_id]
        if previous is not None:
            values.update(created_at=previous.created_at, created_by=previous.created_by)
        child = PromotionStackDraftGroup(
            **values, draft_id=row.id, position=position, **group.model_dump(exclude={"group_id"})
        )
        await work.record(child, {}, "create", all_fields=True)
        work.db.add(child)
    await work.db.flush()
    for pair in body.permissions:
        child = PromotionStackDraftPermission(
            **work.common(),
            draft_id=row.id,
            earlier_group_id=identities[pair.earlier_group_id],
            later_group_id=identities[pair.later_group_id],
            include_reward_units=pair.include_reward_units,
        )
        await work.record(child, {}, "create", all_fields=True)
        work.db.add(child)
    row.group_count, row.permission_count = len(body.groups), len(body.permissions)


async def publish(work: AggregateWork, row: PromotionStackDraft) -> PromotionStackPolicy:
    child: Any
    groups, permissions = await terms(work.access, row)
    if not groups:
        raise ConflictError("publication requires at least one reviewed stack group")
    reviewed = StackPolicyTerms(
        groups=groups, permissions=permissions, maximum_applied=row.maximum_applied
    )
    maximum = await work.db.scalar(
        select(func.max(PromotionStackPolicy.version)).where(
            PromotionStackPolicy.company_id == work.company, PromotionStackPolicy.code == row.code
        )
    )
    if maximum is not None and maximum >= 2**31 - 1:
        raise ConflictError("stack policy revision numbering is exhausted")
    mapped_ids = {group.group_id: uuid7() for group in groups}
    snapshot = StackPolicyTerms(
        groups=tuple(
            StackGroup(**{**group.model_dump(), "group_id": mapped_ids[group.group_id]})
            for group in reviewed.groups
        ),
        permissions=tuple(
            StackPermission(
                earlier_group_id=mapped_ids[pair.earlier_group_id],
                later_group_id=mapped_ids[pair.later_group_id],
                include_reward_units=pair.include_reward_units,
            )
            for pair in reviewed.permissions
        ),
        maximum_applied=row.maximum_applied,
    )
    policy = PromotionStackPolicy(
        **work.common(),
        code=row.code,
        version=(maximum or 0) + 1,
        maximum_applied=row.maximum_applied,
        published_at=utcnow(),
        source_sha256=hashlib.sha256(
            json.dumps(
                snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
    )
    await work.record(policy, {}, "publish", all_fields=True)
    work.db.add(policy)
    await work.db.flush([policy])
    for position, group in enumerate(snapshot.groups):
        values = work.common()
        values["id"] = group.group_id
        child = PromotionStackGroup(
            **values,
            policy_revision_id=policy.id,
            position=position,
            **group.model_dump(exclude={"group_id"}),
        )
        await work.record(child, {}, "publish", all_fields=True)
        work.db.add(child)
    await work.db.flush()
    for pair in snapshot.permissions:
        child = PromotionStackPermission(
            **work.common(), policy_revision_id=policy.id, **pair.model_dump()
        )
        await work.record(child, {}, "publish", all_fields=True)
        work.db.add(child)
    row.status, row.published_policy_id = "PUBLISHED", policy.id
    return policy


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    body: StackDraftInput | StackDraftUpdate | ExpectedVersion,
    key: str,
    action: Literal["create", "update", "publish"],
    object_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    permission = "promotion_stack_policy." + ("publish" if action == "publish" else "manage")
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        "promotion_stack." + action,
        key,
        {"id": str(object_id) if object_id else None, "body": body.model_dump(mode="json")},
    )
    checks: dict[str, FieldWriteChecks] = {}
    work: AggregateWork | None = None
    state: Any = None

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal work, state
        work = AggregateWork(db, actor, company, permission)
        work.checks = checks
        context = await work.context(PromotionStackDraft)
        feature(context)
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
            await read(db, actor, company, uuid.UUID(receipt["id"]))

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert work is not None and state is not None
        if state.generation >= 2**63 - 1:
            raise ConflictError("company policy generation is exhausted")
        if action == "create":
            assert isinstance(body, StackDraftInput)
            row = PromotionStackDraft(
                **work.common(),
                code=body.code,
                change_reason=body.change_reason,
                maximum_applied=body.maximum_applied,
                row_version=1,
                status="DRAFT",
                group_count=0,
                permission_count=0,
                published_policy_id=None,
            )
            before: dict[str, Any] = {}
            await work.authorize_values(PromotionStackDraft, {}, await work.access.values(row))
            db.add(row)
            await db.flush([row])
        else:
            assert object_id is not None and isinstance(body, ExpectedVersion)
            row = await company_object(
                db, PromotionStackDraft, object_id, company_id=company, lock=True
            )
            await work.access.require(row)
            if row.row_version != body.expected_version or row.status != "DRAFT":
                raise ConflictError(
                    "stack draft changed or is already published; reload before continuing"
                )
            before = await work.access.values(row)
        if action == "publish":
            await publish(work, row)
        else:
            assert isinstance(body, StackDraftInput)
            row.code, row.change_reason, row.maximum_applied = (
                body.code,
                body.change_reason,
                body.maximum_applied,
            )
            await replace(work, row, body)
        if action != "create":
            if row.row_version >= 2**31 - 1:
                raise ConflictError("stack draft version is exhausted")
            row.row_version += 1
        row.updated_by = actor.user_id
        await work.record(row, before, action, all_fields=action == "create")
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
        return await read(db, actor, company, uuid.UUID(receipt["id"]))

    try:
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=render
        )
    except IntegrityError as exc:
        raise ConflictError("stack policy conflicts with a native scoped definition") from exc
