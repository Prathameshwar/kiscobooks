"""Owner-nested protected mapping browse and exact resolution."""

import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.errors import (
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.gateway import Actor
from billing_platform.listing import (
    FilterColumn,
    ListQuery,
    Page,
    SortColumn,
    apply_filters,
    apply_search,
    fetch_page,
    resolve_sort,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.master_references import external_key, normalized_alias
from catalog.models.master_references import MasterAlias, MasterExternalKey
from catalog.schemas.master_references import AliasListItem, ExternalKeyListItem
from catalog.tasks.field_context import load_field_context
from catalog.tasks.listing import cursor_codec
from catalog.tasks.master_owners import (
    disclosed_fields,
    owner_access,
    owner_available,
    owner_context,
)
from catalog.tasks.master_references import (
    ALIAS,
    Reference,
    detail,
    get_row,
    require_membership,
    require_owner_activity,
    validate_identity,
)
from catalog.tasks.policy_state import policy_state


async def read(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    target: uuid.UUID,
    object_id: uuid.UUID,
    spec: Reference,
) -> BaseModel:
    context = await load_field_context(db, actor, company, spec.entity)
    require_membership(context)
    await owner_context(db, actor, company, entity, target)
    row = await get_row(db, company, entity, target, object_id, spec)
    state = await policy_state(db, actor, company)
    return detail(row, context, spec, state.generation if state else 1)


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    target: uuid.UUID,
    spec: Reference,
    query: ListQuery,
    secret: bytes,
) -> Page[BaseModel]:
    context = await load_field_context(db, actor, company, spec.entity)
    require_membership(context)
    await owner_context(db, actor, company, entity, target)
    readable = disclosed_fields(context) | {"id"}
    model = spec.model
    item = AliasListItem if spec is ALIAS else ExternalKeyListItem
    integrity = (
        {"alias", "canonical_value", "normalization_version"}
        if spec is ALIAS
        else {"source_namespace", "external_key"}
    )
    statement = select(
        *(getattr(model, key) for key in (readable & item.model_fields.keys()) | integrity)
    ).where(
        model.company_id == company,
        model.entity_type == entity,
        model.target_id == target,
    )
    keys = ("is_active",) if spec is ALIAS else ("is_active", "source_namespace", "external_key")
    filters = {key: FilterColumn(key, getattr(model, key)) for key in keys}
    statement = apply_filters(
        statement,
        query.model_dump(exclude_none=True, include=set(keys)),
        filters=filters,
        readable=readable,
    )
    if spec is ALIAS:
        text = normalized_alias(query.q)[1] if query.q is not None else None
        statement = apply_search(
            statement,
            text,
            columns={"canonical_value": MasterAlias.canonical_value},
            readable=readable,
        )
    elif query.q is not None:
        raise ValidationFailedError("opaque external keys use exact namespace/key filters")
    columns = {"id": SortColumn(model.id, "uuid")}
    if spec is ALIAS:
        columns["canonical_value"] = SortColumn(MasterAlias.canonical_value, "text")
    default = "canonical_value" if spec is ALIAS and "canonical_value" in readable else "id"
    terms = resolve_sort(
        query.sort,
        default=default,
        columns=columns,
        readable=readable,
        supported=frozenset((key,) for field in columns for key in (field, "-" + field)),
    )
    codec = cursor_codec(
        secret,
        actor,
        company,
        spec.entity + ":" + entity + ":" + str(target),
        context,
        query,
    )

    def project(native: Mapping[str, Any]) -> BaseModel:
        validate_identity(dict(native), spec)
        return item.model_validate({key: value for key, value in native.items() if key in readable})

    return await fetch_page(db, statement, query=query, terms=terms, codec=codec, project=project)


async def resolve(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    spec: Reference,
    incoming: Mapping[str, str],
) -> BaseModel:
    context = await load_field_context(db, actor, company, spec.entity)
    require_membership(context)
    readable = disclosed_fields(context)
    keys = {"alias", "canonical_value"} if spec is ALIAS else {"source_namespace", "external_key"}
    if not keys | {"is_active"} <= readable:
        raise PermissionDeniedError(
            "reference resolution requires readable identity and activity fields"
        )
    parent_context = await owner_access(db, actor, company, entity)
    require_owner_activity(parent_context)
    model = spec.model
    statement = select(model).where(
        model.company_id == company,
        model.entity_type == entity,
        model.is_active.is_(True),
    )
    if spec is ALIAS:
        statement = statement.where(
            MasterAlias.canonical_value == normalized_alias(incoming["alias"])[1]
        )
    else:
        statement = statement.where(
            MasterExternalKey.source_namespace == incoming["source_namespace"],
            MasterExternalKey.external_key == external_key(incoming["external_key"]),
        )
    row = await db.scalar(statement.limit(1))
    if row is None:
        raise NotFoundError("active master reference is unavailable")
    assert isinstance(row, MasterAlias | MasterExternalKey)
    owner, _ = await owner_context(db, actor, company, entity, row.target_id)
    if not await owner_available(db, actor, company, owner):
        raise NotFoundError("active master reference is unavailable")
    state = await policy_state(db, actor, company)
    return detail(row, context, spec, state.generation if state else 1)
