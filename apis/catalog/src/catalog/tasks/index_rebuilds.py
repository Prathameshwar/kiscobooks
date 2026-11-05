"""Audited rebuild commands and restartable, proof-authorized DB chunks."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from billing_platform.actor_authorization import ActorAuthorizationProof
from billing_platform.authz import ScopePath
from billing_platform.custom_fields import CustomDefinition, scalar_value, validate_stored_values
from billing_platform.custom_query import definition_digest
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from billing_platform.outbox import audit_payload, emit
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.events.audit_contract import audit_event
from catalog.models.classification import ItemCategory, ItemGroup
from catalog.models.commercial import Brand, Manufacturer, ProductType
from catalog.models.custom_fields import CustomFieldValueIndex, CustomFieldValueMember
from catalog.models.field_indexes import FieldIndexState, FieldRebuildJob
from catalog.models.products import Item, ProductFamily
from catalog.schemas.field_indexes import (
    IndexStateDetail,
    RebuildDetail,
    RebuildListItem,
    RebuildQuery,
)
from catalog.tasks.actor_authorization import require_job_actor
from catalog.tasks.custom_fields import replace_indexes
from catalog.tasks.field_context import (
    MANAGE_PERMISSIONS,
    READ_PERMISSIONS,
    FieldContext,
    load_field_context,
)
from catalog.tasks.field_indexes import INDEX_MODELS, index_definition, load_index_state
from catalog.tasks.listing import cursor_codec
from catalog.tasks.policy_state import company_policy_state, policy_state


def permissions(entity: str) -> frozenset[str]:
    if entity not in INDEX_MODELS:
        raise ValidationFailedError("custom index owner is not implemented")
    return frozenset({"custom_field.manage", READ_PERMISSIONS[entity], MANAGE_PERMISSIONS[entity]})


async def authority(
    db: AsyncSession, actor: Actor, company: uuid.UUID, entity: str, key: str, *, write: bool
) -> FieldContext:
    for permission in (
        permissions(entity) if write else {READ_PERMISSIONS.get(entity, "custom_field.manage")}
    ):
        actor.require_scope(permission, target=ScopePath(company_id=company))
    context = await load_field_context(db, actor, company, entity)
    index_definition(context, key)
    return context


def audit(
    db: AsyncSession,
    tenant: uuid.UUID,
    company: uuid.UUID,
    job: FieldRebuildJob,
    action: str,
    *,
    actor_id: uuid.UUID | None,
) -> None:
    event = audit_event("catalog.field_rebuild_job", action)
    emit(
        db,
        tenant_id=tenant,
        aggregate_type="catalog.field_rebuild_job",
        aggregate_id=job.id,
        event_type=event,
        payload=audit_payload(
            action=event,
            entity_type="catalog.field_rebuild_job",
            entity_id=job.id,
            actor_user_id=actor_id,
            company_id=company,
            category="system" if actor_id is None else "admin",
            changes={"status": {"changed": True}, "progress": {"changed": True}},
        )
        | {"actor_type": "system" if actor_id is None else "user"},
    )


def detail(row: FieldRebuildJob, state: FieldIndexState) -> RebuildDetail:
    return RebuildDetail.model_validate(
        {
            "entity_type": state.entity_type,
            "field_key": state.field_key,
            **{
                key: getattr(row, key)
                for key in RebuildDetail.model_fields
                if key not in {"entity_type", "field_key"}
            },
        }
    )


async def state_detail(
    db: AsyncSession, actor: Actor, company: uuid.UUID, entity: str, key: str
) -> IndexStateDetail:
    context = await authority(db, actor, company, entity, key, write=False)
    definition = index_definition(context, key)
    state = await load_index_state(db, company, entity, key)
    return IndexStateDetail(
        company_id=company,
        entity_type=entity,
        field_key=key,
        row_version=state.row_version if state else 0,
        generation=state.generation if state else 0,
        ready_generation=state.ready_generation if state else None,
        building_generation=state.building_generation if state else None,
        retired_generation=state.retired_generation if state else None,
        ready_for_current_definition=state is not None
        and state.ready_generation is not None
        and state.ready_digest == definition_digest(definition),
    )


async def scoped_job(
    db: AsyncSession,
    company: uuid.UUID,
    entity: str,
    key: str,
    job_id: uuid.UUID,
    *,
    lock: bool = False,
) -> tuple[FieldRebuildJob, FieldIndexState]:
    state = await load_index_state(db, company, entity, key, lock=lock)
    row = await company_object(db, FieldRebuildJob, job_id, company_id=company, lock=lock)
    if state is None or row.state_id != state.id:
        raise PermissionDeniedError("rebuild belongs to another field")
    return row, state


async def read_job(
    db: AsyncSession, actor: Actor, company: uuid.UUID, entity: str, key: str, job_id: uuid.UUID
) -> RebuildDetail:
    await authority(db, actor, company, entity, key, write=False)
    return detail(*(await scoped_job(db, company, entity, key, job_id)))


async def list_jobs(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    key: str,
    query: RebuildQuery,
    secret: bytes,
) -> Page[RebuildListItem]:
    context = await authority(db, actor, company, entity, key, write=False)
    if query.q is not None:
        raise ValidationFailedError("rebuild history supports status filters, not text search")
    columns = [
        getattr(FieldRebuildJob, name)
        for name in RebuildListItem.model_fields
        if name not in {"entity_type", "field_key"}
    ]
    stmt = (
        select(*columns)
        .join(FieldIndexState, FieldIndexState.id == FieldRebuildJob.state_id)
        .where(
            FieldRebuildJob.company_id == company,
            FieldIndexState.company_id == company,
            FieldIndexState.entity_type == entity,
            FieldIndexState.field_key == key,
        )
    )
    if query.status is not None:
        stmt = stmt.where(FieldRebuildJob.status == query.status)
    terms = resolve_sort(
        query.sort,
        default="-id",
        columns={"id": SortColumn(FieldRebuildJob.id, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )

    def project(values: Any) -> RebuildListItem:
        return RebuildListItem.model_validate(values)

    return await fetch_page(
        db,
        stmt,
        query=query,
        terms=terms,
        codec=cursor_codec(
            secret, actor, company, "catalog.rebuilds:" + entity + ":" + key, context, query
        ),
        project=project,
    )


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    field_key: str,
    body: BaseModel,
    *,
    key: str,
    action: Literal["start", "cancel"],
    job_id: uuid.UUID | None = None,
) -> CommandResult[RebuildDetail]:
    context: FieldContext | None = None
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        "catalog.field_rebuild_job." + action,
        key,
        {
            "entity": entity,
            "field": field_key,
            "job": str(job_id) if job_id else None,
            "body": body.model_dump(mode="json"),
        },
    )

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal context
        context = await authority(db, actor, company, entity, field_key, write=True)
        await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            await scoped_job(db, company, entity, field_key, uuid.UUID(receipt["id"]))

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert context is not None
        expected = body.model_dump()["expected_version"]
        if action == "start":
            state = await load_index_state(db, company, entity, field_key, lock=True)
            if (state.row_version if state else 0) != expected:
                raise ConflictError("index state changed; reload before starting")
            if state is None:
                state = FieldIndexState(
                    tenant_id=actor.tenant_id,
                    company_id=company,
                    entity_type=entity,
                    field_key=field_key,
                    generation=0,
                    row_version=1,
                    created_by=actor.user_id,
                    updated_by=actor.user_id,
                )
                db.add(state)
                await db.flush()
            if state.building_generation is not None or state.retired_generation is not None:
                raise ConflictError("previous index build or cleanup is still pending")
            if state.generation >= 2**63 - 1:
                raise ConflictError("index generation is exhausted")
            definition = index_definition(context, field_key)
            if definition.validation.unique_within != "none":
                from billing_platform.constants import SCOPE_ALL

                from catalog.tasks.field_adoption import state as adoption_state
                from catalog.tasks.product_field_rollout import owners, prepare_claims

                if entity not in {"catalog.item", "catalog.product_family"}:
                    raise ValidationFailedError("unique adoption owner is not supported")
                tenant_wide = definition.validation.unique_within == "tenant"
                if tenant_wide:
                    for permission in permissions(entity):
                        actor.require_scope(permission, target=ScopePath())
                await adoption_state(db, SCOPE_ALL, entity, lock=True)
                records = await owners(db, company, entity, tenant_wide=tenant_wide)
                contexts = {company: context}
                for record in records:
                    if record.company_id not in contexts:
                        contexts[record.company_id] = await load_field_context(
                            db, actor, record.company_id, entity
                        )
                    source = contexts[record.company_id]
                    if "custom_field:" + field_key not in source.readable():
                        raise PermissionDeniedError(
                            "unique preparation requires readable affected fields"
                        )
                await prepare_claims(db, context, (definition,), records)
            state.generation += 1
            state.building_generation, state.building_digest = (
                state.generation,
                definition_digest(definition),
            )
            state.row_version += 1
            row = FieldRebuildJob(
                id=uuid7(),
                tenant_id=actor.tenant_id,
                company_id=company,
                state_id=state.id,
                actor_user_id=actor.user_id,
                generation=state.generation,
                source_version=context.source_version,
                definition_digest=definition_digest(definition),
                definition=definition.model_dump(mode="json"),
                status="pending",
                phase="build",
                processed_count=0,
                cleanup_count=0,
                row_version=1,
                created_by=actor.user_id,
                updated_by=actor.user_id,
            )
            db.add(row)
        else:
            assert job_id is not None
            row, state = await scoped_job(db, company, entity, field_key, job_id, lock=True)
            if row.row_version != expected:
                raise ConflictError("rebuild version changed; reload before cancelling")
            if row.phase != "build" or row.status not in {"pending", "running"}:
                raise ConflictError("only an unactivated build can be cancelled")
            state.retired_generation, state.building_generation, state.building_digest = (
                row.generation,
                None,
                None,
            )
            state.row_version += 1
            row.status, row.phase, row.reason_code = "cancelled", "cleanup", "cancelled_by_actor"
            row.row_version += 1
        row.updated_by = actor.user_id
        state.updated_by = actor.user_id
        await db.flush()
        audit(db, actor.tenant_id, company, row, action, actor_id=actor.user_id)
        return CommandReceipt(201 if action == "start" else 200, {"id": str(row.id)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> RebuildDetail:
        return detail(*(await scoped_job(db, company, entity, field_key, uuid.UUID(receipt["id"]))))

    return await execute_idempotent(
        factory, identity, authorize=authorize, mutate=mutate, render=render
    )


async def build_chunk(
    db: AsyncSession,
    proof: ActorAuthorizationProof,
    *,
    company: uuid.UUID,
    entity: str,
    key: str,
    job_id: uuid.UUID,
    limit: int = 25,
) -> RebuildDetail:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationFailedError("rebuild chunk size must be 1-100")
    current = await require_job_actor(
        db, proof, company_id=company, user_id=proof.user_id, permissions=permissions(entity)
    )
    await policy_state(db, current, company, lock=True)
    row, state = await scoped_job(db, company, entity, key, job_id, lock=True)
    if row.actor_user_id != current.user_id:
        raise PermissionDeniedError("rebuild must execute as its original actor")
    if row.phase != "build" or row.status not in {"pending", "running"}:
        raise ConflictError("rebuild no longer accepts build chunks")
    context = await authority(db, current, company, entity, key, write=True)
    definition = index_definition(context, key)
    digest = definition_digest(definition)
    if (
        digest != row.definition_digest
        or definition_digest(CustomDefinition.model_validate(row.definition)) != digest
        or state.building_generation != row.generation
        or state.building_digest != digest
    ):
        raise ConflictError("rebuild definition changed; cancel and prepare a new generation")
    model = INDEX_MODELS[entity]
    stmt = select(model).where(model.company_id == company).order_by(model.id).limit(limit)
    if row.checkpoint_id is not None:
        stmt = stmt.where(model.id > row.checkpoint_id)
    records = list(await db.scalars(stmt.with_for_update()))
    currencies = frozenset(
        {context.company.base_currency, *(v for v in (context.company.reporting_currency,) if v)}
    )
    for record in records:
        assert isinstance(
            record,
            ItemGroup | ItemCategory | Brand | Manufacturer | ProductType | Item | ProductFamily,
        )
        # authority() requires conservative field-wide read access. Conditional
        # denies prevent rebuilding; a partial readable subset cannot be indexed.
        value = (record.custom_fields or {}).get(key)
        native_values = {name: getattr(record, name) for name in context.native.fields}
        readable = context.readable()
        validate_stored_values(
            context.definitions,
            values=record.custom_fields or {},
            native_values=native_values,
            readable_fields=readable | {name.removeprefix("custom_field:") for name in readable},
            currencies=currencies,
            keys=frozenset({key}),
        )
        validated = (
            None if value is None else scalar_value(definition, value, currencies=currencies)
        )
        await replace_indexes(
            db,
            company_id=company,
            entity_type=entity,
            entity_id=record.id,
            definitions=(definition,),
            values={key: validated},
            generations={key: (row.generation,)},
        )
        row.checkpoint_id = record.id
        row.processed_count += 1
    row.status = "running"
    if len(records) < limit:
        state.retired_generation = state.ready_generation
        state.ready_generation, state.ready_digest = row.generation, digest
        state.building_generation, state.building_digest = None, None
        state.row_version += 1
        state.updated_by = current.user_id
        row.phase = "cleanup" if state.retired_generation is not None else "complete"
        row.status = "succeeded"
    row.row_version += 1
    row.updated_at, row.updated_by = utcnow(), current.user_id
    await require_job_actor(
        db, proof, company_id=company, user_id=row.actor_user_id, permissions=permissions(entity)
    )
    audit(db, current.tenant_id, company, row, "chunk", actor_id=current.user_id)
    await db.flush()
    return detail(row, state)


async def cleanup_chunk(
    db: AsyncSession,
    *,
    tenant: uuid.UUID,
    company: uuid.UUID,
    entity: str,
    key: str,
    job_id: uuid.UUID,
    limit: int = 200,
) -> RebuildDetail:
    """Internal subscription-scoped garbage collection; no public mutation route.

    Only an already retired generation is eligible. No original user privilege is
    needed to remove unreachable derived rows after cancellation or activation.
    """
    from billing_platform.db.tenant_context import require_current_tenant

    if tenant != require_current_tenant() or type(limit) is not int or not 1 <= limit <= 500:
        raise ValidationFailedError("invalid cleanup scope or bound")
    await company_policy_state(db, tenant, company, lock=True)
    row, state = await scoped_job(db, company, entity, key, job_id, lock=True)
    if row.phase != "cleanup" or state.retired_generation is None:
        raise ConflictError("rebuild has no retired generation to clean")
    remaining = limit
    for model in (CustomFieldValueIndex, CustomFieldValueMember):
        records = list(
            await db.scalars(
                select(model)
                .where(
                    model.company_id == company,
                    model.entity_type == entity,
                    model.field_key == key,
                    model.generation == state.retired_generation,
                )
                .order_by(model.id)
                .limit(remaining)
                .with_for_update()
            )
        )
        for record in records:
            await db.delete(record)
        row.cleanup_count += len(records)
        remaining -= len(records)
        if remaining == 0:
            break
    if remaining > 0:
        state.retired_generation = None
        state.row_version += 1
        state.updated_by = None
        row.phase = "complete"
    row.row_version += 1
    row.updated_at = utcnow()
    row.updated_by = None
    audit(db, tenant, company, row, "cleanup", actor_id=None)
    await db.flush()
    return detail(row, state)
