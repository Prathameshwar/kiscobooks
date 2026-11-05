"""Bounded return condition aggregates under the common revision transaction."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import (
    ConflictError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.listing import (
    FilterColumn,
    Page,
    SortColumn,
    apply_filters,
    fetch_page,
    resolve_sort,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.profiles import ReturnRules
from catalog.models.returns import ReturnPolicyCondition, ReturnPolicyRevision
from catalog.schemas.returns import ReturnConditionListItem, ReturnConditionQuery
from catalog.tasks.field_context import (
    FieldContext,
    FieldWriteChecks,
    load_field_context,
)
from catalog.tasks.listing import cursor_codec


async def conditions(
    db: AsyncSession, revision: ReturnPolicyRevision
) -> list[ReturnPolicyCondition]:
    rows = list(
        await db.scalars(
            select(ReturnPolicyCondition)
            .where(
                ReturnPolicyCondition.company_id == revision.company_id,
                ReturnPolicyCondition.revision_id == revision.id,
            )
            .order_by(ReturnPolicyCondition.condition_code, ReturnPolicyCondition.id)
            .limit(6)
        )
    )
    # Native count/code constraints bound the set to five; the sixth-row sentinel
    # also fails this comparison if restored rows violate that bound.
    if len(rows) != revision.condition_count:
        raise ConflictError("return policy condition set is incomplete or exceeds supported bounds")
    ReturnRules(
        revision.returns_allowed,
        revision.window_days,
        tuple(row.condition_code for row in rows),
    )
    return rows


def values(row: ReturnPolicyCondition, context: FieldContext) -> dict[str, Any]:
    return {key: getattr(row, key) for key in context.native.fields}


async def replace_conditions(
    db: AsyncSession,
    actor: Actor,
    revision: ReturnPolicyRevision,
    codes: tuple[str, ...],
    checks: FieldWriteChecks,
) -> frozenset[str]:
    # Full proposed parent/child coherence has already been validated by ReturnRevisionInput.
    # Validate the stored aggregate before altering it, including restoration completeness.
    old = await conditions(db, revision)
    context = await load_field_context(
        db,
        actor,
        revision.company_id,
        "catalog.return_policy_condition",
        permission="return_policy.manage",
    )
    prior = {row.condition_code: row for row in old}
    proposed = {code: {"revision_id": revision.id, "condition_code": code} for code in codes}
    changed: frozenset[str] = frozenset()
    for code in prior.keys() | proposed.keys():
        before = values(prior[code], context) if code in prior else {}
        after = proposed.get(code, {})
        difference = frozenset(
            key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
        )
        context.assert_writable(difference, before=before, after=after, checked=checks)
        changed |= difference
    for code in prior.keys() - proposed.keys():
        await db.delete(prior[code])
    for code in proposed.keys() - prior.keys():
        db.add(
            ReturnPolicyCondition(
                tenant_id=actor.tenant_id,
                company_id=revision.company_id,
                created_by=actor.user_id,
                updated_by=actor.user_id,
                **proposed[code],
            )
        )
    revision.condition_count = len(codes)
    return changed


async def publish_conditions(
    db: AsyncSession,
    actor: Actor,
    revision: ReturnPolicyRevision,
    checks: FieldWriteChecks,
) -> frozenset[str]:
    rows = await conditions(db, revision)
    context = await load_field_context(
        db,
        actor,
        revision.company_id,
        "catalog.return_policy_condition",
        permission="return_policy.publish",
    )
    changed: frozenset[str] = frozenset()
    for row in rows:
        native = values(row, context)
        row_changed = frozenset(native)
        context.assert_writable(row_changed, before=native, after=native, checked=checks)
        changed |= row_changed
    return changed


async def authorize_condition_replay(
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
        "catalog.return_policy_condition",
        permission="return_policy.publish" if publishing else "return_policy.manage",
    )
    if checks is not None:
        checks.recheck(context)
    else:
        assert_fields_writable(changed, rules=context.rules(), target=ScopePath(company_id=company))


async def list_conditions(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    policy_id: uuid.UUID,
    revision_id: uuid.UUID,
    query: ReturnConditionQuery,
    secret: bytes,
) -> Page[ReturnConditionListItem]:
    context = await load_field_context(db, actor, company, "catalog.return_policy_condition")
    readable = context.readable() | {"id"}
    if "revision_id" not in readable:
        raise PermissionDeniedError("condition browsing requires readable revision membership")
    parent_context = await load_field_context(db, actor, company, "catalog.return_policy_revision")
    if "policy_id" not in parent_context.readable():
        raise PermissionDeniedError("condition browsing requires readable policy membership")
    revision = await company_object(db, ReturnPolicyRevision, revision_id, company_id=company)
    if revision.policy_id != policy_id:
        raise PermissionDeniedError("revision belongs to another return policy")
    await conditions(db, revision)
    model = ReturnPolicyCondition
    stmt = select(*(getattr(model, field) for field in readable)).where(
        model.company_id == company, model.revision_id == revision_id
    )
    filters = {"condition_code": FilterColumn("condition_code", model.condition_code)}
    stmt = apply_filters(
        stmt,
        query.model_dump(exclude_none=True, include=set(filters)),
        filters=filters,
        readable=readable,
    )
    if query.q is not None:
        raise ValidationFailedError("return conditions support typed filters, not text search")
    terms = resolve_sort(
        query.sort,
        default="condition_code" if "condition_code" in readable else "id",
        columns={
            "id": SortColumn(model.id, "uuid"),
            "condition_code": SortColumn(model.condition_code, "text"),
        },
        readable=readable,
        supported=frozenset((key,) for key in ("id", "-id", "condition_code", "-condition_code")),
    )
    codec = cursor_codec(
        secret,
        actor,
        company,
        "catalog.return_policy_condition:" + str(revision_id),
        context,
        query,
    )

    def project(native: Mapping[str, Any]) -> ReturnConditionListItem:
        return ReturnConditionListItem.model_validate(native)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)
