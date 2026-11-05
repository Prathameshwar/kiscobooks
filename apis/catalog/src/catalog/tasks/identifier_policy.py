"""Immutable identifier requirements authored with their master in one transaction."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
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

from catalog.models.classification import ClassificationMaster
from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement
from catalog.schemas.profiles import (
    IdentifierProfileCreate,
    IdentifierRequirementListItem,
    IdentifierRequirementQuery,
)
from catalog.tasks.field_context import load_field_context
from catalog.tasks.listing import cursor_codec


async def initialize_requirements(
    db: AsyncSession, actor: Actor, row: IdentifierProfile, incoming: Any
) -> frozenset[str]:
    body = IdentifierProfileCreate.model_validate(
        {"code": row.code, "name": row.name, "requirements": incoming}
    )
    context = await load_field_context(
        db,
        actor,
        row.company_id,
        "catalog.identifier_profile_requirement",
        permission="identifier_profile.manage",
    )
    changed = frozenset(context.native.fields)
    for requirement in body.requirements:
        values = {"profile_id": row.id, **requirement.model_dump()}
        context.assert_writable(changed, before={}, after=values)
        db.add(
            IdentifierProfileRequirement(
                tenant_id=actor.tenant_id,
                company_id=row.company_id,
                created_by=actor.user_id,
                updated_by=actor.user_id,
                **values,
            )
        )
    await db.flush()
    return changed


async def authorize_requirements_replay(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    profile_id: uuid.UUID,
    changed: frozenset[str],
) -> None:
    context = await load_field_context(
        db,
        actor,
        company,
        "catalog.identifier_profile_requirement",
        permission="identifier_profile.manage",
    )
    # These rows are immutable, so current values are also the original command's
    # values. Re-evaluate predicates against them instead of treating every
    # conditional deny as active during initial receipt rendering and retries.
    rows = list(
        await db.scalars(
            select(IdentifierProfileRequirement)
            .where(
                IdentifierProfileRequirement.company_id == company,
                IdentifierProfileRequirement.profile_id == profile_id,
            )
            .limit(3)
        )
    )
    if not 1 <= len(rows) <= 2:
        raise ConflictError("identifier profile requirements are unavailable")
    for row in rows:
        values = {field: getattr(row, field) for field in context.native.fields}
        context.assert_writable(changed, before={}, after=values)


async def validate_identifier_header(
    db: AsyncSession, row: ClassificationMaster, before: Mapping[str, Any]
) -> None:
    if not isinstance(row, IdentifierProfile) or not before:
        return
    if row.code != before["code"]:
        used = await db.scalar(
            select(IdentifierProfileRequirement.id)
            .where(
                IdentifierProfileRequirement.company_id == row.company_id,
                IdentifierProfileRequirement.profile_id == row.id,
            )
            .limit(1)
        )
        if used is not None:
            raise ConflictError(
                "identifier profile identity is immutable; create a replacement profile"
            )


async def list_requirements(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    profile_id: uuid.UUID,
    query: IdentifierRequirementQuery,
    secret: bytes,
) -> Page[IdentifierRequirementListItem]:
    context = await load_field_context(db, actor, company, "catalog.identifier_profile_requirement")
    readable = context.readable() | {"id"}
    if "profile_id" not in readable:
        raise PermissionDeniedError("requirement browsing needs readable profile membership")
    await company_object(db, IdentifierProfile, profile_id, company_id=company)
    model = IdentifierProfileRequirement
    stmt = select(*(getattr(model, field) for field in readable)).where(
        model.company_id == company, model.profile_id == profile_id
    )
    filters = {
        field: FilterColumn(field, getattr(model, field))
        for field in ("identifier_type", "namespace_rule")
    }
    stmt = apply_filters(
        stmt,
        query.model_dump(exclude_none=True, include=set(filters)),
        filters=filters,
        readable=readable,
    )
    if query.q is not None:
        raise ValidationFailedError(
            "identifier requirements support typed filters, not text search"
        )
    terms = resolve_sort(
        query.sort,
        default="identifier_type" if "identifier_type" in readable else "id",
        columns={
            "id": SortColumn(model.id, "uuid"),
            "identifier_type": SortColumn(model.identifier_type, "text"),
        },
        readable=readable,
        supported=frozenset((key,) for key in ("id", "-id", "identifier_type", "-identifier_type")),
    )
    codec = cursor_codec(
        secret,
        actor,
        company,
        "catalog.identifier_profile_requirement:" + str(profile_id),
        context,
        query,
    )

    def project(native: Mapping[str, Any]) -> IdentifierRequirementListItem:
        return IdentifierRequirementListItem.model_validate(native)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)
