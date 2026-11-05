"""Audited immutable mapping identities with protected lifecycle commands."""

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.master_references import NORMALIZATION_VERSION, external_key, normalized_alias
from catalog.models.classification import CatalogPolicyState
from catalog.models.master_references import MasterAlias, MasterExternalKey
from catalog.schemas.master_references import (
    AliasCreate,
    AliasDetail,
    ExternalKeyCreate,
    ExternalKeyDetail,
)
from catalog.tasks.classification import audit_change
from catalog.tasks.field_context import (
    FieldContext,
    FieldWriteChecks,
    load_field_context,
)
from catalog.tasks.master_owners import (
    disclosed_fields,
    owner_available,
    owner_context,
    owner_values,
)
from catalog.tasks.policy_state import policy_state

ReferenceRow = MasterAlias | MasterExternalKey


@dataclass(frozen=True)
class Reference:
    model: type[MasterAlias] | type[MasterExternalKey]
    entity: str
    permission: str
    detail: type[BaseModel]
    input: type[BaseModel]


ALIAS = Reference(MasterAlias, "catalog.master_alias", "master_alias", AliasDetail, AliasCreate)
EXTERNAL = Reference(
    MasterExternalKey,
    "catalog.master_external_key",
    "master_external_key",
    ExternalKeyDetail,
    ExternalKeyCreate,
)


def validate_identity(native: dict[str, Any], spec: Reference) -> None:
    try:
        if spec is ALIAS:
            display, canonical = normalized_alias(native["alias"])
            if (
                display != native["alias"]
                or canonical != native["canonical_value"]
                or native["normalization_version"] != NORMALIZATION_VERSION
            ):
                raise ConflictError("master reference identity is inconsistent")
        else:
            ExternalKeyCreate.model_validate(
                {
                    "source_namespace": native["source_namespace"],
                    "external_key": external_key(native["external_key"]),
                }
            )
    except (ValueError, ValidationFailedError) as exc:
        raise ConflictError("master reference identity is inconsistent") from exc


def values(row: ReferenceRow, context: FieldContext) -> dict[str, Any]:
    return {key: getattr(row, key) for key in context.native.fields}


def detail(row: ReferenceRow, context: FieldContext, spec: Reference, generation: int) -> BaseModel:
    native = values(row, context)
    validate_identity(native, spec)
    readable = disclosed_fields(context, native)
    return spec.detail.model_validate(
        {
            "id": row.id,
            "company_id": row.company_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "policy_generation": generation,
            **{key: value for key, value in native.items() if key in readable},
        }
    )


async def get_row(
    db: AsyncSession,
    company: uuid.UUID,
    entity: str,
    target: uuid.UUID,
    object_id: uuid.UUID,
    spec: Reference,
    *,
    lock: bool = False,
) -> ReferenceRow:
    row = await company_object(db, spec.model, object_id, company_id=company, lock=lock)
    if row.entity_type != entity or row.target_id != target:
        raise PermissionDeniedError("master reference belongs to another owner")
    validate_identity(
        {column.key: getattr(row, column.key) for column in row.__table__.columns}, spec
    )
    return row


def require_membership(context: FieldContext) -> None:
    if not {"entity_type", "target_id"} <= context.readable():
        raise PermissionDeniedError("master reference access requires readable owner membership")


def require_owner_activity(context: FieldContext) -> None:
    required = (
        {"valid_from", "valid_to"}
        if context.native.entity_type == "catalog.tax_classification"
        else {"is_active"}
    )
    if not required <= context.readable():
        raise PermissionDeniedError("master identity commands require readable owner activity")


async def command(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    target: uuid.UUID,
    spec: Reference,
    *,
    key: str,
    body: BaseModel,
    action: Literal["create", "activate", "deactivate"],
    object_id: uuid.UUID | None = None,
) -> CommandResult[BaseModel]:
    context: FieldContext | None = None
    state: CatalogPolicyState | None = None
    mapping_checks = FieldWriteChecks()
    owner_checks = FieldWriteChecks()
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        spec.entity + "." + action,
        key,
        {
            "body": body.model_dump(mode="json", exclude_unset=True),
            "entity_type": entity,
            "target_id": str(target),
            "id": str(object_id) if object_id else None,
        },
    )

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        nonlocal context, state
        actor.require_scope(spec.permission + ".read", target=ScopePath(company_id=company))
        context = await load_field_context(
            db, actor, company, spec.entity, permission=spec.permission + ".manage"
        )
        require_membership(context)
        state = await policy_state(db, actor, company, lock=receipt is None)
        if receipt is not None:
            if mapping_checks.writes:
                mapping_checks.recheck(context)
            else:
                assert_fields_writable(
                    frozenset(receipt["changed"]),
                    rules=context.rules(),
                    target=ScopePath(company_id=company),
                )
            await get_row(db, company, entity, target, uuid.UUID(receipt["id"]), spec)
            _, parent_context = await owner_context(
                db, actor, company, entity, target, writing=True
            )
            if action in {"create", "activate"}:
                require_owner_activity(parent_context)
                if owner_checks.writes:
                    owner_checks.recheck(parent_context)
                else:
                    assert_fields_writable(
                        frozenset({"code"}),
                        rules=parent_context.rules(),
                        target=ScopePath(company_id=company),
                    )

    async def mutate(db: AsyncSession) -> CommandReceipt:
        assert context is not None and state is not None
        before: dict[str, Any] = {}
        if action == "create":
            incoming = spec.input.model_validate(body.model_dump()).model_dump()
            if spec is ALIAS:
                incoming["alias"], incoming["canonical_value"] = normalized_alias(incoming["alias"])
                incoming["normalization_version"] = NORMALIZATION_VERSION
            row = spec.model(
                tenant_id=actor.tenant_id,
                company_id=company,
                entity_type=entity,
                target_id=target,
                is_active=True,
                row_version=1,
                created_by=actor.user_id,
                updated_by=actor.user_id,
                **incoming,
            )
        else:
            assert object_id is not None
            row = await get_row(db, company, entity, target, object_id, spec, lock=True)
            if row.row_version != body.model_dump()["expected_version"]:
                raise ConflictError("resource version changed; reload before updating")
            before = values(row, context)
            row.is_active = action == "activate"
            if row.is_active != before["is_active"]:
                row.deactivated_at = None if row.is_active else utcnow()
                row.deactivated_by = None if row.is_active else actor.user_id
        after = values(row, context)
        changed = frozenset(key for key, value in after.items() if before.get(key) != value)
        changed -= {"row_version", "normalization_version"}
        if changed and action != "create":
            if row.row_version >= 2**31 - 1:
                raise ConflictError("resource version is exhausted")
            row.row_version += 1
            row.updated_by, row.updated_at = actor.user_id, utcnow()
            after["row_version"] = row.row_version
        context.assert_writable(changed, before=before, after=after, checked=mapping_checks)
        owner, parent_context = await owner_context(
            db, actor, company, entity, target, writing=True
        )
        if action in {"create", "activate"}:
            require_owner_activity(parent_context)
            native_owner = owner_values(owner, parent_context)
            parent_context.assert_writable(
                frozenset({"code"}),
                before=native_owner,
                after=native_owner,
                checked=owner_checks,
            )
            if not await owner_available(db, actor, company, owner):
                raise ConflictError("new or reactivated references require an active master")
        if action == "create":
            db.add(row)
        if changed:
            if state.generation >= 2**63 - 1:
                raise ConflictError("company policy generation is exhausted")
            state.generation += 1
            await db.flush()
            audit_change(
                db, actor, company, spec.entity, row.id, action, changed, before=before, after=after
            )
        await db.flush()
        return CommandReceipt(
            201 if action == "create" else 200,
            {"id": str(row.id), "changed": sorted(changed)},
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> BaseModel:
        assert context is not None
        row = await get_row(db, company, entity, target, uuid.UUID(receipt["id"]), spec)
        return detail(row, context, spec, state.generation if state else 1)

    try:
        return await execute_idempotent(
            factory, identity, authorize=authorize, mutate=mutate, render=render
        )
    except IntegrityError as exc:
        raise ConflictError("master reference identity conflicts with an existing mapping") from exc
