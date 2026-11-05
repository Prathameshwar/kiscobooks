"""Code-registered local dependencies; usage is never an external retirement proof."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.base import Base
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import SortColumn, fetch_page, resolve_sort
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog import models
from catalog.domain.field_registry import registry
from catalog.schemas.master_usage import (
    UsageCatalog,
    UsageItem,
    UsagePage,
    UsageQuery,
    UsageRelation,
)
from catalog.tasks.field_context import READ_PERMISSIONS, FieldContext, load_field_context
from catalog.tasks.listing import cursor_codec
from catalog.tasks.master_owners import OWNERS, owner_context


@dataclass(frozen=True)
class Dependency:
    entity: str
    model: type[Base]
    field: str
    polymorphic: bool = False
    discriminator: str = "entity_type"
    discriminator_value: str | None = None

    @property
    def key(self) -> str:
        return self.entity + "." + self.field


def dependencies(entity: str) -> tuple[Dependency, ...]:
    if entity not in OWNERS:
        raise ValidationFailedError("unsupported Catalog usage target")
    table = OWNERS[entity].__table__
    assert isinstance(table, Table)
    target = table.name
    result = []
    for source in registry.entity_types():
        native = registry.get(source)
        model = getattr(models, native.model_name)
        for field in native.fields:
            column = model.__table__.columns[field]
            if any(
                fk.column.table.name == target and fk.column.name == "id"
                for fk in column.foreign_keys
            ):
                result.append(Dependency(source, model, field))
    result.extend(
        (
            Dependency("catalog.master_alias", models.MasterAlias, "target_id", True),
            Dependency("catalog.master_external_key", models.MasterExternalKey, "target_id", True),
        )
    )
    if entity == "catalog.tax_classification":
        result.extend(
            Dependency(
                "catalog.tax_history_action",
                models.TaxHistoryAction,
                field,
                True,
                "resource",
                "tax_classification",
            )
            for field in ("target_id", "previous_id")
        )
    return tuple(sorted(result, key=lambda relation: relation.key))


def readable_membership(context: FieldContext, relation: Dependency) -> bool:
    required = {relation.field} | ({relation.discriminator} if relation.polymorphic else set())
    return required <= context.readable()


async def relation_catalog(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    target: uuid.UUID,
) -> UsageCatalog:
    await owner_context(db, actor, company, entity, target)
    visible = []
    contexts: dict[str, FieldContext] = {}
    for relation in dependencies(entity):
        if not actor.allows_scope(
            READ_PERMISSIONS[relation.entity], target=ScopePath(company_id=company)
        ):
            continue
        if relation.entity not in contexts:
            contexts[relation.entity] = await load_field_context(
                db, actor, company, relation.entity
            )
        if readable_membership(contexts[relation.entity], relation):
            visible.append(
                UsageRelation(
                    key=relation.key, entity_type=relation.entity, field_key=relation.field
                )
            )
    return UsageCatalog(relations=visible)


async def list_usage(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    target: uuid.UUID,
    query: UsageQuery,
    secret: bytes,
) -> UsagePage:
    await owner_context(db, actor, company, entity, target)
    relation = next((row for row in dependencies(entity) if row.key == query.relation), None)
    if relation is None:
        raise ValidationFailedError("unsupported local usage relation")
    context = await load_field_context(db, actor, company, relation.entity)
    if not readable_membership(context, relation):
        raise PermissionDeniedError("usage requires readable reference membership")
    if query.q is not None:
        raise ValidationFailedError(
            "usage pages support relation and lifecycle filters, not text search"
        )
    model = relation.model
    id_column = getattr(model, "id")  # noqa: B009 - attributes of registered ORM types
    stmt = select(id_column).where(
        getattr(model, "company_id") == company,  # noqa: B009 - registered ORM type
        getattr(model, relation.field) == target,
    )
    if relation.polymorphic:
        stmt = stmt.where(
            getattr(model, relation.discriminator) == (relation.discriminator_value or entity)
        )
    for key, value in (("is_active", query.is_active), ("published_at", query.published)):
        if value is None:
            continue
        if key not in context.native.fields:
            raise ValidationFailedError("lifecycle filter is not supported for this relation")
        if key not in context.readable():
            raise PermissionDeniedError("usage filters require readable lifecycle fields")
        column = getattr(model, key)
        if key == "published_at":
            stmt = stmt.where(column.is_not(None) if value else column.is_(None))
        else:
            stmt = stmt.where(column == value)
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(id_column, "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    codec = cursor_codec(
        secret, actor, company, "catalog.master_usage:" + entity + ":" + str(target), context, query
    )

    def project(native: Mapping[str, Any]) -> UsageItem:
        return UsageItem(id=native["id"], entity_type=relation.entity, field_key=relation.field)

    page = await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)
    return UsagePage(items=page.items, page=page.page)
