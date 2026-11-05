"""Bounded, atomic product field adoption with actor-bound impact review."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.custom_fields import (
    CustomDefinition,
    canonical_claim,
    scalar_value,
    validate_stored_values,
)
from billing_platform.custom_query import definition_digest
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    canonical_json,
    execute_idempotent,
)
from billing_platform.pagination import CursorCodec
from pydantic_core import to_jsonable_python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.custom_fields import CustomFieldValueIndex, CustomFieldValueMember
from catalog.models.field_indexes import FieldIndexState
from catalog.models.products import Item, ProductFamily
from catalog.models.projections import CustomFieldDefinitionProjection
from catalog.schemas.field_adoption import (
    AdoptionInput,
    AdoptionIssue,
    AdoptionResult,
    AdoptionReview,
)
from catalog.tasks.classification import audit_change
from catalog.tasks.custom_fields import replace_indexes, reserve_claims
from catalog.tasks.field_adoption import PRODUCT_ENTITIES, state
from catalog.tasks.field_context import FieldContext, custom_definition, load_field_context
from catalog.tasks.policy_state import policy_state

MAX_OWNERS = 1000


def codec(actor: Actor, company: uuid.UUID, entity: str, secret: bytes) -> CursorCodec:
    return CursorCodec(
        hmac.digest(secret, b"catalog.product-field-adoption.v1", hashlib.sha256),
        context=f"product-fields:{actor.tenant_id}:{company}:{actor.user_id}:{entity}",
        ttl_seconds=900,
    )


async def owners(
    db: AsyncSession, company: uuid.UUID, entity: str, *, tenant_wide: bool = False
) -> list[Any]:
    model = Item if entity == "catalog.item" else ProductFamily
    stmt = select(model).order_by(model.id).limit(MAX_OWNERS + 1)
    if not tenant_wide:
        stmt = stmt.where(model.company_id == company)
    records = list(await db.scalars(stmt))
    if len(records) > MAX_OWNERS:
        raise ConflictError("product field adoption exceeds the 1000-owner review bound")
    return records


async def authority(
    db: AsyncSession, actor: Actor, company: uuid.UUID, entity: str
) -> FieldContext:
    if entity not in PRODUCT_ENTITIES:
        raise ValidationFailedError("product custom-field owner is not supported")
    for permission in ("custom_field.manage", "item.read", "item.update"):
        actor.require_scope(permission, target=ScopePath(company_id=company))
    context = await load_field_context(db, actor, company, entity, candidates=True)
    required = set(context.native.fields) | {"custom_field:" + d.key for d in context.definitions}
    if not required <= context.readable():
        raise PermissionDeniedError("definition review requires readable owner and custom fields")
    return context


@dataclass
class ReviewWork:
    context: FieldContext
    records: list[Any]
    evidence: dict[str, Any]
    issues: list[AdoptionIssue]


async def inspect(db: AsyncSession, actor: Actor, company: uuid.UUID, entity: str) -> ReviewWork:
    context = await authority(db, actor, company, entity)
    current = await load_field_context(db, actor, company, entity)
    tenant_unique = any(
        d.is_active and d.validation.unique_within == "tenant" for d in context.definitions
    )
    if tenant_unique:
        for permission in ("custom_field.manage", "item.read", "item.update"):
            actor.require_scope(permission, target=ScopePath())
    records = await owners(db, company, entity, tenant_wide=tenant_unique)
    previous = {d.key: d for d in current.definitions}
    digest = hashlib.sha256()
    issues: list[AdoptionIssue] = []
    seen: set[tuple[uuid.UUID, str, bytes]] = set()
    contexts = {company: context}
    for row in records:
        if row.company_id not in contexts:
            contexts[row.company_id] = await load_field_context(db, actor, row.company_id, entity)
        source = contexts[row.company_id]
        native = {key: getattr(row, key) for key in source.native.fields}
        native.update({"custom_field:" + k: v for k, v in (row.custom_fields or {}).items()})
        readable = source.readable(native)
        keys = {
            d.key
            for d in context.definitions
            if row.company_id == company or d.validation.unique_within == "tenant"
        }
        if not set(source.native.fields) <= readable or any(
            "custom_field:" + k not in readable for k in keys if k in (row.custom_fields or {})
        ):
            raise PermissionDeniedError("definition review requires readable affected owners")
        digest.update(
            canonical_json(
                to_jsonable_python(
                    {
                        "id": row.id,
                        "company": row.company_id,
                        "version": row.row_version,
                        "values": native,
                        "custom": row.custom_fields or {},
                    }
                )
            )
        )
        for definition in context.definitions:
            if definition.key not in keys:
                continue
            old = previous.get(definition.key)
            value = (row.custom_fields or {}).get(definition.key)
            if (
                value is not None
                and old is not None
                and old.is_active
                and (
                    old.data_type != definition.data_type
                    or old.sequence_config != definition.sequence_config
                    or old.validation.case_sensitive != definition.validation.case_sensitive
                    or (
                        old.validation.unique_within != "none"
                        and old.validation.unique_within != definition.validation.unique_within
                    )
                )
            ):
                issues.append(
                    AdoptionIssue(
                        owner_id=row.id,
                        field_key=definition.key,
                        reason="used type, sequence, comparison and uniqueness scope are immutable",
                    )
                )
                continue
            if row.company_id == company:
                try:
                    validate_stored_values(
                        context.definitions,
                        values=row.custom_fields or {},
                        native_values=native,
                        readable_fields=readable
                        | {k.removeprefix("custom_field:") for k in readable},
                        currencies=frozenset(
                            {
                                context.company.base_currency,
                                *(v for v in (context.company.reporting_currency,) if v),
                            }
                        ),
                        keys=frozenset({definition.key}),
                    )
                except ValidationFailedError:
                    issues.append(
                        AdoptionIssue(
                            owner_id=row.id,
                            field_key=definition.key,
                            reason=(
                                "stored value fails the proposed contract; "
                                "backfill under an optional contract first"
                            ),
                        )
                    )
            if definition.is_active:
                try:
                    if value is not None:
                        value = scalar_value(
                            definition,
                            value,
                            currencies=frozenset(
                                {
                                    source.company.base_currency,
                                    *(v for v in (source.company.reporting_currency,) if v),
                                }
                            ),
                        )
                except (ValueError, TypeError):
                    issues.append(
                        AdoptionIssue(
                            owner_id=row.id,
                            field_key=definition.key,
                            reason="stored value is incompatible with the proposed type or bounds",
                        )
                    )
                    continue
                claim = canonical_claim(definition, value)
                if claim is not None:
                    scope = (
                        SCOPE_ALL
                        if definition.validation.unique_within == "tenant"
                        else row.company_id
                    )
                    key = (scope, definition.key, claim[0])
                    if key in seen:
                        issues.append(
                            AdoptionIssue(
                                owner_id=row.id,
                                field_key=definition.key,
                                reason="duplicate custom value",
                            )
                        )
                    seen.add(key)
    adopted = await state(db, company, entity)
    global_state = await state(db, SCOPE_ALL, entity)
    evidence = {
        "source": context.source_version,
        "owners": digest.hexdigest(),
        "definitions": hashlib.sha256(
            canonical_json([definition_digest(d) for d in context.definitions])
        ).hexdigest(),
        "version": adopted.row_version if adopted else 0,
        "claims_version": global_state.row_version
        if global_state and global_state.definitions
        else 0,
    }
    return ReviewWork(context, records, evidence, issues)


async def source_definition_digests(
    db: AsyncSession, company: uuid.UUID, entity: str
) -> dict[str, str]:
    """Match Identity's authored definition digest, before feature/layout resolution."""
    rows = await db.scalars(
        select(CustomFieldDefinitionProjection).where(
            CustomFieldDefinitionProjection.company_id == company,
            CustomFieldDefinitionProjection.entity_type == entity,
        )
    )
    result = {}
    for row in rows:
        data = {
            key: getattr(row, key)
            for key in (
                "entity_type",
                "label",
                "help_text",
                "placeholder",
                "display_order",
                "display_group",
                "requires_feature",
            )
        }
        data.update(
            company_id=str(row.source_company_id),
            definition=custom_definition(
                row, frozenset({row.requires_feature}) if row.requires_feature else frozenset()
            ).model_dump(mode="json"),
        )
        result[str(row.source_id)] = hashlib.sha256(canonical_json(data)).hexdigest()
    return result


async def preview(
    db: AsyncSession, actor: Actor, company: uuid.UUID, entity: str, secret: bytes
) -> AdoptionReview:
    work = await inspect(db, actor, company, entity)
    return AdoptionReview(
        entity_type=entity,
        owner_count=len(work.records),
        eligible=not work.issues,
        issues=work.issues[:200],
        definitions=list(work.context.definitions),
        source_definition_digests=await source_definition_digests(db, company, entity),
        preview_token=codec(actor, company, entity, secret).encode(work.evidence),
    )


async def prepare_claims(
    db: AsyncSession,
    context: FieldContext,
    definitions: tuple[CustomDefinition, ...],
    records: list[Any],
) -> None:
    """Caller owns the company lock and complete owner scan; tenant guard serializes writes."""
    guard = await state(db, SCOPE_ALL, context.native.entity_type, lock=True)
    assert guard is not None
    global_rules = {v["key"]: CustomDefinition.model_validate(v) for v in guard.definitions}
    for definition in definitions:
        if definition.is_active and definition.validation.unique_within == "tenant":
            prior = global_rules.get(definition.key)
            if prior is not None and (
                prior.data_type != definition.data_type
                or prior.validation.case_sensitive != definition.validation.case_sensitive
            ):
                raise ConflictError("tenant uniqueness contract cannot change comparison semantics")
            global_rules[definition.key] = definition
    if guard.row_version >= 2**63 - 1:
        raise ConflictError("unique contract version is exhausted")
    guard.definitions = [d.model_dump(mode="json") for d in global_rules.values()]
    guard.row_version += 1
    await db.flush()
    for row in records:
        selected = (
            definitions
            if row.company_id == context.company.company_id
            else tuple(global_rules.values())
        )
        await reserve_claims(
            db,
            company_id=row.company_id,
            entity_type=context.native.entity_type,
            entity_id=row.id,
            definitions=selected,
            values=row.custom_fields or {},
        )


async def adopt(
    factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    body: AdoptionInput,
    key: str,
    secret: bytes,
) -> CommandResult[AdoptionResult]:
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        "catalog.custom_field_adoption.adopt",
        key,
        {"entity": entity, "body": body.model_dump(mode="json")},
    )

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        await authority(db, actor, company, entity)
        await policy_state(db, actor, company, lock=receipt is None)

    async def mutate(db: AsyncSession) -> CommandReceipt:
        # Serialize with every product claim writer before scanning cross-company values.
        await state(db, SCOPE_ALL, entity, lock=True)
        work = await inspect(db, actor, company, entity)
        if codec(actor, company, entity, secret).decode(body.preview_token) != work.evidence:
            raise ConflictError("product values or definitions changed; preview again")
        if work.issues:
            raise ConflictError("resolve the preview issues before adopting this contract")
        context = work.context
        await prepare_claims(db, context, context.definitions, work.records)
        for definition in context.definitions:
            index = await db.scalar(
                select(FieldIndexState)
                .where(
                    FieldIndexState.company_id == company,
                    FieldIndexState.entity_type == entity,
                    FieldIndexState.field_key == definition.key,
                )
                .with_for_update()
            )
            if index is not None and (
                index.building_generation is not None or index.retired_generation is not None
            ):
                raise ConflictError(
                    "finish or cancel and clean up the field index job before adoption"
                )
            if not definition.is_active or not definition.is_searchable:
                continue
            if index is None:
                index = FieldIndexState(
                    tenant_id=actor.tenant_id,
                    company_id=company,
                    entity_type=entity,
                    field_key=definition.key,
                    generation=0,
                    row_version=1,
                    created_by=actor.user_id,
                )
                db.add(index)
            if index.generation >= 2**63 - 1:
                raise ConflictError("custom index generation is exhausted")
            index.generation += 1
            index.ready_generation, index.ready_digest = (
                index.generation,
                definition_digest(definition),
            )
            index.row_version += 1
            for model in (CustomFieldValueIndex, CustomFieldValueMember):
                obsolete = list(
                    await db.scalars(
                        select(model).where(
                            model.company_id == company,
                            model.entity_type == entity,
                            model.field_key == definition.key,
                        )
                    )
                )
                for entry in obsolete:
                    await db.delete(entry)
            for row in work.records:
                if row.company_id == company:
                    await replace_indexes(
                        db,
                        company_id=company,
                        entity_type=entity,
                        entity_id=row.id,
                        definitions=(definition,),
                        values=row.custom_fields or {},
                        generations={definition.key: (index.generation,)},
                    )
        accepted = await state(db, company, entity, lock=True)
        assert accepted is not None
        if accepted.row_version >= 2**63 - 1:
            raise ConflictError("adopted contract version is exhausted")
        accepted.definitions = [d.model_dump(mode="json") for d in context.definitions]
        accepted.row_version += 1
        accepted.updated_by = actor.user_id
        company_state = await policy_state(db, actor, company, lock=True)
        assert company_state is not None
        if company_state.generation >= 2**63 - 1:
            raise ConflictError("company policy generation is exhausted")
        company_state.generation += 1
        audit_change(
            db,
            actor,
            company,
            "catalog.custom_field_adoption",
            accepted.id,
            "adopt",
            frozenset({"definitions", "indexes", "claims"}),
        )
        await db.flush()
        return CommandReceipt(
            200, {"version": accepted.row_version, "owner_count": len(work.records)}
        )

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> AdoptionResult:
        return AdoptionResult(
            entity_type=entity, version=receipt["version"], owner_count=receipt["owner_count"]
        )

    return await execute_idempotent(
        factory, identity, authorize=authorize, mutate=mutate, render=render
    )
