"""Bounded native template membership, edited only through its revision aggregate."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import assert_fields_writable
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
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

from catalog.domain.attributes import MemberRule, validate_members
from catalog.models.attributes import (
    AttributeDefinition,
    AttributeSet,
    AttributeSetMember,
    AttributeSetRevision,
)
from catalog.schemas.attributes import (
    AttributeMemberListItem,
    AttributeMemberQuery,
    AttributeSetRevisionCreate,
)
from catalog.tasks.attribute_policy import definition_rules
from catalog.tasks.field_context import FieldContext, FieldWriteChecks, load_field_context
from catalog.tasks.listing import cursor_codec


async def members(db: AsyncSession, revision: AttributeSetRevision) -> list[AttributeSetMember]:
    rows = list(
        await db.scalars(
            select(AttributeSetMember)
            .where(
                AttributeSetMember.company_id == revision.company_id,
                AttributeSetMember.revision_id == revision.id,
            )
            .order_by(AttributeSetMember.position, AttributeSetMember.id)
            .limit(129)
        )
    )
    if len(rows) > 128:
        raise ConflictError("attribute template exceeds synchronous membership bounds")
    return rows


def values(row: AttributeSetMember, context: FieldContext) -> dict[str, Any]:
    return {key: getattr(row, key) for key in context.native.fields}


async def validate_rules(
    db: AsyncSession, company: uuid.UUID, rules: tuple[MemberRule, ...], *, allow_empty: bool
) -> None:
    definitions = (
        list(
            await db.scalars(
                select(AttributeDefinition)
                .where(
                    AttributeDefinition.company_id == company,
                    AttributeDefinition.id.in_([rule.definition_id for rule in rules]),
                )
                .limit(128)
            )
        )
        if rules
        else []
    )
    validate_members(
        rules, {row.id: definition_rules(row) for row in definitions}, allow_empty=allow_empty
    )


async def replace_members(
    db: AsyncSession,
    actor: Actor,
    revision: AttributeSetRevision,
    incoming: Any,
    checks: FieldWriteChecks | None = None,
) -> frozenset[str]:
    body = AttributeSetRevisionCreate.model_validate({"members": incoming})
    context = await load_field_context(
        db,
        actor,
        revision.company_id,
        "catalog.attribute_set_member",
        permission="attribute_set.manage",
    )
    old = await members(db, revision)
    rules = tuple(
        MemberRule(item.definition_id, item.position, item.is_required, item.allow_variant_axis)
        for item in body.members
    )
    await validate_rules(db, revision.company_id, rules, allow_empty=True)
    prior = {row.definition_id: row for row in old}
    proposed = {
        item.definition_id: {"revision_id": revision.id, **item.model_dump()}
        for item in body.members
    }
    changed: frozenset[str] = frozenset()
    individual_changes: dict[uuid.UUID, frozenset[str]] = {}
    for definition_id in prior.keys() | proposed.keys():
        before = values(prior[definition_id], context) if definition_id in prior else {}
        after = proposed.get(definition_id, {})
        difference = frozenset(
            key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
        )
        context.assert_writable(difference, before=before, after=after, checked=checks)
        individual_changes[definition_id] = difference
        changed |= difference
    if not changed:
        return changed
    # A complete bounded replacement makes position swaps atomic without violating
    # the unique position key temporarily. Existing draft member identities survive.
    snapshots = {
        row.definition_id: {
            "id": row.id,
            "created_at": row.created_at,
            "created_by": row.created_by,
            "updated_at": row.updated_at,
            "updated_by": row.updated_by,
        }
        for row in old
    }
    for row in old:
        await db.delete(row)
    await db.flush()
    for definition_id, after in proposed.items():
        previous = snapshots.get(definition_id)
        unchanged = previous is not None and not individual_changes[definition_id]
        db.add(
            AttributeSetMember(
                id=previous["id"] if previous else uuid7(),
                tenant_id=actor.tenant_id,
                company_id=revision.company_id,
                created_at=previous["created_at"] if previous else utcnow(),
                created_by=previous["created_by"] if previous else actor.user_id,
                updated_at=previous["updated_at"]
                if unchanged and previous is not None
                else utcnow(),
                updated_by=previous["updated_by"]
                if unchanged and previous is not None
                else actor.user_id,
                **after,
            )
        )
    await db.flush()
    return changed


async def publish_members(
    db: AsyncSession,
    actor: Actor,
    revision: AttributeSetRevision,
    checks: FieldWriteChecks | None = None,
) -> frozenset[str]:
    context = await load_field_context(
        db,
        actor,
        revision.company_id,
        "catalog.attribute_set_member",
        permission="attribute_set.publish",
    )
    rows = await members(db, revision)
    await validate_rules(
        db,
        revision.company_id,
        tuple(
            MemberRule(row.definition_id, row.position, row.is_required, row.allow_variant_axis)
            for row in rows
        ),
        allow_empty=False,
    )
    changed = frozenset(context.native.fields)
    for row in rows:
        native = values(row, context)
        context.assert_writable(changed, before=native, after=native, checked=checks)
    return changed


async def authorize_member_replay(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    changed: frozenset[str],
    *,
    publishing: bool,
    checks: FieldWriteChecks | None = None,
) -> None:
    context = await load_field_context(
        db,
        actor,
        company,
        "catalog.attribute_set_member",
        permission="attribute_set.publish" if publishing else "attribute_set.manage",
    )
    if checks is not None:
        checks.recheck(context)
    else:
        # A receipt cannot bypass new conditional denies when a former draft member
        # has since been replaced or removed; use conservative predicate evaluation.
        assert_fields_writable(changed, rules=context.rules(), target=ScopePath(company_id=company))


async def list_members(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    attribute_set_id: uuid.UUID,
    revision_id: uuid.UUID,
    query: AttributeMemberQuery,
    secret: bytes,
) -> Page[AttributeMemberListItem]:
    context = await load_field_context(db, actor, company, "catalog.attribute_set_member")
    readable = context.readable() | {"id"}
    if "revision_id" not in readable:
        raise PermissionDeniedError("member browsing requires readable revision membership")
    parent_context = await load_field_context(db, actor, company, "catalog.attribute_set_revision")
    if "attribute_set_id" not in parent_context.readable():
        raise PermissionDeniedError("member browsing requires readable template membership")
    revision = await company_object(db, AttributeSetRevision, revision_id, company_id=company)
    if revision.attribute_set_id != attribute_set_id:
        raise PermissionDeniedError("revision belongs to another attribute set")
    model = AttributeSetMember
    stmt = select(*(getattr(model, field) for field in readable)).where(
        model.company_id == company, model.revision_id == revision_id
    )
    filters = {
        key: FilterColumn(key, getattr(model, key))
        for key in ("definition_id", "is_required", "allow_variant_axis")
    }
    stmt = apply_filters(
        stmt,
        query.model_dump(exclude_none=True, include=set(filters)),
        filters=filters,
        readable=readable,
    )
    if query.q is not None:
        raise ValidationFailedError("template members support typed filters, not text search")
    terms = resolve_sort(
        query.sort,
        default="position" if "position" in readable else "id",
        columns={
            "id": SortColumn(model.id, "uuid"),
            "position": SortColumn(model.position, "integer"),
        },
        readable=readable,
        supported=frozenset((key,) for key in ("id", "-id", "position", "-position")),
    )
    codec = cursor_codec(
        secret, actor, company, "catalog.attribute_set_member:" + str(revision_id), context, query
    )

    def project(native: Mapping[str, Any]) -> AttributeMemberListItem:
        return AttributeMemberListItem.model_validate(native)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)


async def validate_type_binding(
    db: AsyncSession, company: uuid.UUID, revision_id: uuid.UUID | None
) -> None:
    if revision_id is None:
        return
    revision = await company_object(db, AttributeSetRevision, revision_id, company_id=company)
    template = await company_object(db, AttributeSet, revision.attribute_set_id, company_id=company)
    if revision.published_at is None or not template.is_active:
        raise ConflictError("product types require an active published attribute template")
    rows = await members(db, revision)
    await validate_rules(
        db,
        company,
        tuple(
            MemberRule(row.definition_id, row.position, row.is_required, row.allow_variant_axis)
            for row in rows
        ),
        allow_empty=False,
    )
