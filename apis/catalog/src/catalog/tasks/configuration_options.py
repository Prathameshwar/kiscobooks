"""Bounded searchable native references with current company and field admission."""

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page, SortColumn, apply_search, fetch_page, resolve_sort
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models import Currency
from catalog.models.attributes import AttributeSet, AttributeSetRevision
from catalog.models.commercial import ProductType, ProductTypeRevision
from catalog.models.products import Item, ProductFamily
from catalog.models.profiles import IdentifierProfile
from catalog.schemas.configuration import (
    ConfigurationOptionItem,
    ConfigurationOptionQuery,
    ConfigurationOptionSource,
)
from catalog.tasks.field_context import load_field_context
from catalog.tasks.listing import cursor_codec
from catalog.tasks.profile_bindings import BINDINGS


async def options(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    source: ConfigurationOptionSource,
    query: ConfigurationOptionQuery,
    secret: bytes,
    *,
    owner_permission: str = "product_configuration.read",
    owner_entity: str = "catalog.product_configuration_scope",
    active_items_only: bool = False,
) -> Page[ConfigurationOptionItem]:
    actor.require_scope(owner_permission, target=ScopePath(company_id=company))
    context = await load_field_context(
        db, actor, company, owner_entity, permission=owner_permission
    )
    models: dict[str, Any] = {
        "items": Item,
        "identifier-profiles": IdentifierProfile,
        "currencies": Currency,
        "product-type-revisions": ProductTypeRevision,
        "attribute-set-revisions": AttributeSetRevision,
    }
    parents: dict[str, tuple[Any, str]] = {
        "product-type-revisions": (ProductType, "product_type_id"),
        "attribute-set-revisions": (AttributeSet, "attribute_set_id"),
    }
    for source_key, binding in zip(
        (
            "inventory-template-revisions",
            "warranty-revisions",
            "return-policy-revisions",
            "handling-revisions",
        ),
        BINDINGS,
        strict=True,
    ):
        models[source_key] = binding.model
        parents[source_key] = (binding.parent, binding.parent_field)
    model = models[source]
    parent = parents.get(source)
    if source == "items":
        parent = (ProductFamily, "family_id")
    if source != "currencies":
        context = await load_field_context(db, actor, company, "catalog." + model.__tablename__)
    label_model = parent[0] if parent else model
    code = model.sku if source == "items" else label_model.code
    name = model.name if source == "items" else label_model.name
    identity = model.code if source == "currencies" else model.id
    required = (
        {"sku", "name", "status", "family_id"}
        if source == "items"
        else {"published_at", "revision", parent[1]}
        if parent
        else {"code", "name", "is_active"}
    )
    if source != "currencies" and not required <= context.readable():
        raise PermissionDeniedError(
            "configuration choices require readable labels and lifecycle fields"
        )
    selected = [identity.label("id"), code.label("code"), name.label("name")]
    if source in parents:
        selected.append(model.revision.label("revision"))
    if parent:
        selected.append(getattr(model, parent[1]).label("parent_id"))
    stmt = select(*selected)
    if source != "currencies":
        stmt = stmt.where(model.company_id == company)
    if parent:
        parent_model, parent_field = parent
        parent_context = await load_field_context(
            db, actor, company, "catalog." + parent_model.__tablename__
        )
        parent_keys = (
            {"code", "name", "status"} if source == "items" else {"code", "name", "is_active"}
        )
        if not parent_keys <= parent_context.readable():
            raise PermissionDeniedError(
                "configuration choices require readable parent labels and lifecycle"
            )
        stmt = stmt.join(parent_model, getattr(model, parent_field) == parent_model.id).where(
            parent_model.company_id == company
        )
        if source == "items":
            stmt = stmt.where(
                model.status.in_(["DRAFT", "ACTIVE"]), parent_model.status.in_(["DRAFT", "ACTIVE"])
            )
            if active_items_only:
                stmt = stmt.where(model.status == "ACTIVE", parent_model.status == "ACTIVE")
        else:
            stmt = stmt.where(model.published_at.is_not(None), parent_model.is_active.is_(True))
    elif source != "currencies":
        stmt = stmt.where(model.is_active.is_(True))
    if query.kind:
        owner = parent[0] if source == "items" and parent else model
        kind_field = "kind"
        if not hasattr(owner, kind_field):
            raise ValidationFailedError("this configuration choice does not support a kind filter")
        kind_context = await load_field_context(
            db, actor, company, "catalog." + owner.__tablename__
        )
        if kind_field not in kind_context.readable():
            raise PermissionDeniedError("configuration choice kind is protected")
        stmt = stmt.where(getattr(owner, kind_field).in_([query.kind, "BOTH"]))
    if query.value:
        try:
            exact = query.value if source == "currencies" else uuid.UUID(query.value)
            if source == "currencies" and (
                len(query.value) != 3
                or not query.value.isascii()
                or not query.value.isupper()
                or not query.value.isalpha()
            ):
                raise ValueError("invalid currency")
            stmt = stmt.where(identity == exact)
        except ValueError as error:
            raise ValidationFailedError("invalid configuration choice identifier") from error
    stmt = apply_search(
        stmt, query.q, columns={"code": code, "name": name}, readable=frozenset({"code", "name"})
    )
    terms = resolve_sort(
        query.sort,
        default="code",
        columns={
            "id": SortColumn(identity.label("id"), "text" if source == "currencies" else "uuid"),
            "code": SortColumn(code.label("code"), "text"),
            "name": SortColumn(name.label("name"), "text"),
        },
        readable=frozenset({"id", "code", "name"}),
        supported=frozenset((key,) for key in ("id", "-id", "code", "-code", "name", "-name")),
    )
    codec = cursor_codec(
        secret,
        actor,
        company,
        "catalog.configuration-options:"
        + source
        + ":"
        + owner_entity
        + ":"
        + str(active_items_only),
        context,
        query,
    )

    def project(row: Any) -> ConfigurationOptionItem:
        suffix = " (revision " + str(row["revision"]) + ")" if "revision" in row else ""
        return ConfigurationOptionItem(
            value=str(row["id"]),
            code=row["code"],
            label=row["name"] + suffix,
            parent_id=row.get("parent_id"),
        )

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)
