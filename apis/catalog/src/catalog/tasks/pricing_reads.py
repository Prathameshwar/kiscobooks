"""Signed lean pricing pages, with purchase costs excluded before paging."""

import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page, SortColumn, apply_search, fetch_page, resolve_sort
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import ItemGroup
from catalog.models.pricing import (
    PRICING_MODELS,
    CommercialPolicyScope,
    ItemPrice,
    ItemPriceDraft,
    ItemPriceSeries,
    PricePlan,
    PricingRow,
)
from catalog.models.products import Item, ProductFamily
from catalog.schemas import pricing_reads
from catalog.schemas.pricing import PricingQuery
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.listing import cursor_codec
from catalog.tasks.pricing_commands import product, protected, purpose_access, row

MODELS = {model.__tablename__: model for model in PRICING_MODELS}


async def dependencies(access: ConfigurationAccess, value: Any) -> None:
    if hasattr(value, "price_id"):
        parent = await row(
            access,
            ItemPrice if value.price_id else ItemPriceDraft,
            value.price_id or value.draft_id,
        )
        await dependencies(access, parent)
        return
    await purpose_access(access, value)
    if hasattr(value, "item_id") and value.item_id is not None:
        await product(access, value.item_id)
    scope = None
    if isinstance(value, CommercialPolicyScope):
        scope = value
    elif hasattr(value, "scope_id"):
        scope = await row(access, CommercialPolicyScope, value.scope_id)
    if scope is not None:
        if scope.group_id:
            await access.reference(ItemGroup, scope.group_id)
        if scope.family_id:
            await access.reference(ProductFamily, scope.family_id)
        if scope.item_id and scope is not value:
            await product(access, scope.item_id)


async def read(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    model: type[PricingRow],
    object_id: uuid.UUID,
) -> BaseModel:
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(model)
    if model is PricePlan and "purpose" not in context.readable():
        raise PermissionDeniedError("price purpose is protected")
    value = await company_object(db, model, object_id, company_id=company)
    await dependencies(access, value)
    native = await access.values(value)
    schema: type[BaseModel] = getattr(pricing_reads, model.__name__ + "Detail")
    result = schema.model_validate(
        {
            "id": value.id,
            "company_id": company,
            "created_at": value.created_at,
            "updated_at": value.updated_at,
            **{key: entry for key, entry in native.items() if key in context.readable(native)},
        }
    )

    if isinstance(value, PricePlan):
        custom = value.custom_fields or {}
        readable = context.readable(
            {**native, **{"custom_field:" + key: entry for key, entry in custom.items()}}
        )
        result = result.model_copy(
            update={
                "custom_fields": {
                    key: entry for key, entry in custom.items() if "custom_field:" + key in readable
                }
            }
        )
    return result


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    model: type[PricingRow],
    query: PricingQuery,
    secret: bytes,
) -> Page[BaseModel]:
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(model)
    readable = context.readable() | {"id"}
    schema: type[BaseModel] = getattr(pricing_reads, model.__name__ + "ListItem")
    selected = readable & schema.model_fields.keys()
    native_model: Any = model
    stmt = select(*(getattr(model, key) for key in selected)).where(model.company_id == company)
    # Owner fields are checked once before the lean query. Conditional denies are
    # conservatively excluded by FieldContext.readable() without loading detail rows.
    if hasattr(model, "item_id") or hasattr(model, "price_id"):
        await protected(access, Item)
        await protected(access, ProductFamily)
    if hasattr(model, "scope_id") or model.__tablename__ == "commercial_policy_scope":
        for owner_model in (CommercialPolicyScope, ItemGroup, ProductFamily, Item):
            await protected(access, owner_model)
    # Joining mapped classes preserves session-level tenant criteria on every participant.
    priced = model is ItemPriceSeries or hasattr(model, "series_id") or hasattr(model, "price_id")
    if model is PricePlan or priced:
        await protected(access, PricePlan)
        plans = select(PricePlan.id).where(
            PricePlan.company_id == company, PricePlan.tenant_id == actor.tenant_id
        )
        if not actor.allows_scope("purchase_price.read", target=ScopePath(company_id=company)):
            plans = plans.where(PricePlan.purpose != "PURCHASE")
        if model is PricePlan:
            stmt = stmt.where(PricePlan.id.in_(plans))
        else:
            await protected(access, ItemPriceSeries)
            series = select(ItemPriceSeries.id).where(
                ItemPriceSeries.company_id == company,
                ItemPriceSeries.tenant_id == actor.tenant_id,
                ItemPriceSeries.plan_id.in_(plans),
            )
            if model is ItemPriceSeries:
                stmt = stmt.where(model.id.in_(series))
            elif hasattr(model, "series_id"):
                stmt = stmt.where(model.series_id.in_(series))
            else:
                for parent in (ItemPrice, ItemPriceDraft):
                    await protected(access, parent)
                prices = select(ItemPrice.id).where(
                    ItemPrice.company_id == company,
                    ItemPrice.tenant_id == actor.tenant_id,
                    ItemPrice.series_id.in_(series),
                )
                drafts = select(ItemPriceDraft.id).where(
                    ItemPriceDraft.company_id == company,
                    ItemPriceDraft.tenant_id == actor.tenant_id,
                    ItemPriceDraft.series_id.in_(series),
                )
                stmt = stmt.where(
                    or_(native_model.price_id.in_(prices), native_model.draft_id.in_(drafts))
                )
    for key, value in query.model_dump(exclude_none=True).items():
        if key in {"q", "limit", "cursor", "sort", "as_of"}:
            continue
        if key not in context.native.fields:
            raise ValidationFailedError("unsupported pricing list filter")
        if key not in readable:
            raise PermissionDeniedError("pricing filter is protected")
        stmt = stmt.where(getattr(model, key) == value)
    if query.as_of is not None:
        if not hasattr(model, "valid_from"):
            raise ValidationFailedError("this resource has no dated filter")
        if not {"valid_from", "valid_to"} <= readable:
            raise PermissionDeniedError("pricing dates are protected")
        stmt = stmt.where(
            model.valid_from <= query.as_of,
            or_(native_model.valid_to.is_(None), native_model.valid_to >= query.as_of),
        )
    if query.q is not None:
        if not hasattr(model, "code"):
            raise ValidationFailedError("this pricing resource does not support text search")
        stmt = apply_search(
            stmt,
            query.q,
            columns={"code": model.code, "name": native_model.name},
            readable=readable,
        )
    columns = {"id": SortColumn(model.id, "uuid")}
    supported: set[tuple[str, ...]] = {("id",), ("-id",)}
    if hasattr(model, "code"):
        columns["code"] = SortColumn(model.code, "text")
        supported |= {("code",), ("-code",), ("code", "id"), ("-code", "-id")}
    terms = resolve_sort(
        query.sort, default="id", columns=columns, readable=readable, supported=frozenset(supported)
    )
    codec = cursor_codec(secret, actor, company, "catalog." + model.__tablename__, context, query)

    def project(values: Mapping[str, Any]) -> BaseModel:
        return schema.model_validate(values)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)
