"""Signed lean child pages with explicit owner checks before detail lookup."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page, SortColumn, fetch_page, resolve_sort
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.product_definitions import (
    FamilyAttribute,
    FamilyAttributeOption,
    FamilyCategory,
    FamilyGroupAssignment,
    FamilyManufacturer,
    ItemAttributeValue,
    ItemBarcode,
    ItemUnitBinding,
    ItemUnitRevision,
    ProductConfigurationAdoption,
    ProductConfigurationAdoptionSource,
    ProductDefinitionRow,
)
from catalog.models.products import Item, ProductFamily
from catalog.schemas import product_definition_reads as schemas
from catalog.schemas.product_authoring import AuthoringQuery
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.listing import cursor_codec


@dataclass(frozen=True)
class Resource:
    model: type[ProductDefinitionRow]
    owner_field: str
    owner_model: type[Any]
    item: type[BaseModel]
    detail: type[BaseModel]


RESOURCES = {
    model.__name__: Resource(
        model,
        field,
        owner,
        getattr(schemas, model.__name__ + "ListItem"),
        getattr(schemas, model.__name__ + "Detail"),
    )
    for model, field, owner in (
        (FamilyGroupAssignment, "family_id", ProductFamily),
        (FamilyCategory, "family_id", ProductFamily),
        (FamilyManufacturer, "family_id", ProductFamily),
        (FamilyAttribute, "family_id", ProductFamily),
        (FamilyAttributeOption, "family_id", ProductFamily),
        (ItemAttributeValue, "item_id", Item),
        (ItemUnitBinding, "item_id", Item),
        (ItemBarcode, "item_id", Item),
        (ProductConfigurationAdoption, "item_id", Item),
        (ItemUnitRevision, "binding_id", ItemUnitBinding),
        (ProductConfigurationAdoptionSource, "adoption_id", ProductConfigurationAdoption),
    )
}


async def owner(access: ConfigurationAccess, resource: Resource, object_id: uuid.UUID) -> None:
    row = await access.reference(resource.owner_model, object_id)
    if isinstance(row, Item):
        await access.reference(ProductFamily, row.family_id)
    elif isinstance(row, ItemUnitBinding | ProductConfigurationAdoption):
        item = await access.reference(Item, row.item_id)
        await access.reference(ProductFamily, item.family_id)
    context = await access.context(resource.model)
    if resource.owner_field not in context.readable():
        raise PermissionDeniedError("product child membership is protected")


async def read(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    object_id: uuid.UUID,
    record_id: uuid.UUID,
    resource: Resource,
) -> BaseModel:
    access = ConfigurationAccess(db, actor, company)
    await owner(access, resource, object_id)
    row = await company_object(db, resource.model, record_id, company_id=company)
    if getattr(row, resource.owner_field) != object_id:
        raise PermissionDeniedError("definition belongs to another product owner")
    context = await access.context(resource.model)
    values = await access.values(row)
    result = {
        "id": row.id,
        "company_id": company,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        **{
            key: value
            for key, value in values.items()
            if key in context.readable(values) and key in resource.detail.model_fields
        },
    }
    return resource.detail.model_validate(result)


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    object_id: uuid.UUID,
    resource: Resource,
    query: AuthoringQuery,
    secret: bytes,
) -> Page[BaseModel]:
    access = ConfigurationAccess(db, actor, company)
    await owner(access, resource, object_id)
    context = await access.context(resource.model)
    readable = context.readable() | {"id"}
    selected = readable & resource.item.model_fields.keys()
    model = resource.model
    stmt = select(*(getattr(model, key) for key in selected)).where(
        model.company_id == company, getattr(model, resource.owner_field) == object_id
    )
    if query.q is not None:
        raise ValidationFailedError("product child lists do not support text search")
    if query.as_of is not None:
        if not issubclass(
            model, FamilyGroupAssignment | FamilyCategory | FamilyManufacturer | ItemUnitRevision
        ):
            raise ValidationFailedError("this definition has no effective-date filter")
        if not {"valid_from", "valid_to"} <= readable:
            raise PermissionDeniedError("effective-date fields are protected")
        dated_model = model
        stmt = stmt.where(
            dated_model.valid_from <= query.as_of,
            or_(dated_model.valid_to.is_(None), dated_model.valid_to >= query.as_of),
        )
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(model.id, "uuid")},
        readable=readable,
        supported=frozenset({("id",), ("-id",)}),
    )
    codec = cursor_codec(
        secret,
        actor,
        company,
        "catalog." + model.__tablename__ + ":" + str(object_id),
        context,
        query,
    )

    def project(values: Mapping[str, Any]) -> BaseModel:
        return resource.item.model_validate(values)

    return await fetch_page(db, stmt, query=query, terms=terms, codec=codec, project=project)
