"""Protected tax detail and bounded lean pages, including owner dependency checks."""

import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page, SortColumn, apply_search, fetch_page, resolve_sort
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models import Item, ItemGroup, ProductFamily, UnitOfMeasure
from catalog.models.pricing import PricingRow
from catalog.models.tax import (
    CatalogTaxBinding,
    CatalogTaxScope,
    ItemActivation,
    ItemActivationSource,
    ItemInventoryProfile,
    TaxCategory,
    TaxClassification,
    TaxRate,
    TaxRateComponent,
    TaxRateSeries,
    TaxRule,
)
from catalog.models.tax_governance import TaxHistoryAction, TaxRelease, TaxRuleApplicability
from catalog.schemas import tax_reads as schemas
from catalog.schemas.tax import TaxQuery
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.listing import cursor_codec
from catalog.tasks.pricing_commands import product, protected, row
from catalog.tasks.tax_commands import component_basis, scope_owner
from catalog.tasks.tax_history import rows


async def dependencies(
    access: ConfigurationAccess, value: Any, *, publication: bool = False
) -> None:
    if isinstance(value, TaxRelease):
        for action in await rows(access, TaxHistoryAction, release_id=value.id):
            if action.release_id == value.id:
                await access.require(action)
                await dependencies(access, action, publication=publication)
    elif isinstance(value, TaxHistoryAction):
        model = {
            entry.__tablename__: entry for entry in (TaxClassification, TaxRate, CatalogTaxBinding)
        }[value.resource]
        await dependencies(
            access, await row(access, model, value.target_id), publication=publication
        )
        if value.previous_id is not None:
            await dependencies(
                access, await row(access, model, value.previous_id), publication=publication
            )
    elif isinstance(value, TaxRuleApplicability):
        await dependencies(access, await row(access, TaxRule, value.rule_id))
    elif isinstance(value, TaxRateComponent):
        await dependencies(
            access, await row(access, TaxRate, value.rate_id), publication=publication
        )
        await component_basis(access, value)
    elif isinstance(value, TaxRate):
        await dependencies(access, await row(access, TaxRateSeries, value.series_id))
        if publication:
            # A publication receipt represents its children as well as the rate header.
            for component in await rows(access, TaxRateComponent, rate_id=value.id):
                await access.require(component)
                if component.unit_id is not None:
                    await access.reference(UnitOfMeasure, component.unit_id)
    elif isinstance(value, TaxRateSeries):
        await dependencies(access, await row(access, TaxRule, value.rule_id))
    elif isinstance(value, TaxRule):
        await row(access, TaxCategory, value.tax_category_id)
    elif isinstance(value, CatalogTaxBinding):
        await dependencies(access, await row(access, CatalogTaxScope, value.scope_id))
        if value.classification_id is not None:
            await row(access, TaxClassification, value.classification_id)
        if value.tax_category_id is not None:
            await row(access, TaxCategory, value.tax_category_id)
        if value.rule_id is not None:
            await dependencies(access, await row(access, TaxRule, value.rule_id))
    elif isinstance(value, CatalogTaxScope):
        await scope_owner(access, value)
    elif isinstance(value, ItemActivationSource):
        await dependencies(access, await row(access, ItemActivation, value.activation_id))
    elif isinstance(value, ItemActivation | ItemInventoryProfile):
        await product(access, value.item_id)


async def read(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    model: type[PricingRow],
    object_id: uuid.UUID,
) -> BaseModel:
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(model)
    value = await company_object(db, model, object_id, company_id=company)
    await dependencies(access, value)
    native = await access.values(value)
    result = {
        "id": value.id,
        "company_id": company,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        **{key: entry for key, entry in native.items() if key in context.readable(native)},
    }
    if isinstance(value, TaxRule):
        custom = value.custom_fields or {}
        readable = context.readable(
            {**native, **{"custom_field:" + key: entry for key, entry in custom.items()}}
        )
        result["custom_fields"] = {
            key: entry for key, entry in custom.items() if "custom_field:" + key in readable
        }
    schema: type[BaseModel] = getattr(schemas, model.__name__ + "Detail")
    return schema.model_validate(result)


async def list_rows(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    model: type[PricingRow],
    query: TaxQuery,
    secret: bytes,
) -> Page[BaseModel]:
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(model)
    for dependent in {
        TaxRateComponent: (TaxRate, TaxRateSeries, TaxRule, TaxCategory, UnitOfMeasure),
        TaxRate: (TaxRateSeries, TaxRule, TaxCategory),
        TaxRateSeries: (TaxRule, TaxCategory),
        TaxRule: (TaxCategory,),
        CatalogTaxBinding: (CatalogTaxScope, ItemGroup, ProductFamily, Item),
        CatalogTaxScope: (ItemGroup, ProductFamily, Item),
        ItemActivationSource: (ItemActivation, Item, ProductFamily),
        ItemActivation: (Item, ProductFamily),
        ItemInventoryProfile: (Item, ProductFamily),
    }.get(model, ()):
        await protected(access, dependent)
    readable = context.readable() | {"id"}
    schema: type[BaseModel] = getattr(schemas, model.__name__ + "ListItem")
    native: Any = model
    stmt = select(*(getattr(model, key) for key in readable & schema.model_fields.keys())).where(
        model.company_id == company
    )
    if model is TaxRate:
        # All native fields of these dependencies were authorized above. Join on
        # tenant/company ownership as well as ID; the lean page needs no per-row lookups.
        stmt = (
            stmt.add_columns(
                TaxRule.code.label("rule_code"),
                TaxRule.name.label("rule_name"),
                TaxRateSeries.applicability.label("applicability"),
            )
            .join(
                TaxRateSeries,
                and_(
                    TaxRateSeries.id == TaxRate.series_id,
                    TaxRateSeries.company_id == TaxRate.company_id,
                    TaxRateSeries.tenant_id == TaxRate.tenant_id,
                ),
            )
            .join(
                TaxRule,
                and_(
                    TaxRule.id == TaxRateSeries.rule_id,
                    TaxRule.company_id == TaxRateSeries.company_id,
                    TaxRule.tenant_id == TaxRateSeries.tenant_id,
                ),
            )
        )
    for key, value in query.model_dump(exclude_none=True).items():
        if key in {"q", "limit", "cursor", "sort", "as_of"}:
            continue
        if key not in context.native.fields:
            raise ValidationFailedError("unsupported tax list filter")
        if key not in readable:
            raise PermissionDeniedError("tax filter is protected")
        stmt = stmt.where(getattr(model, key) == value)
    if query.as_of is not None:
        if not hasattr(model, "valid_from"):
            raise ValidationFailedError("this resource has no dated filter")
        if not {"valid_from", "valid_to"} <= readable:
            raise PermissionDeniedError("tax dates are protected")
        stmt = stmt.where(
            native.valid_from <= query.as_of,
            or_(native.valid_to.is_(None), native.valid_to >= query.as_of),
        )
        if model in {TaxClassification, TaxRate, CatalogTaxBinding}:
            await protected(access, TaxHistoryAction)
            stmt = stmt.where(
                model.id.not_in(
                    select(TaxHistoryAction.target_id).where(
                        TaxHistoryAction.company_id == company,
                        TaxHistoryAction.resource == model.__tablename__,
                        TaxHistoryAction.action == "WITHDRAW",
                    )
                )
            )
    if query.q is not None:
        if not hasattr(model, "code"):
            raise ValidationFailedError("this resource has no text search")
        columns = {"code": native.code}
        if hasattr(model, "name"):
            columns["name"] = native.name
        stmt = apply_search(stmt, query.q, columns=columns, readable=readable)
    sorts = {"id": SortColumn(model.id, "uuid")}
    supported: set[tuple[str, ...]] = {("id",), ("-id",)}
    if hasattr(model, "code"):
        sorts["code"] = SortColumn(native.code, "text")
        supported |= {("code",), ("-code",), ("code", "id"), ("-code", "-id")}
    terms = resolve_sort(
        query.sort, default="id", columns=sorts, readable=readable, supported=frozenset(supported)
    )

    def project(values: Mapping[str, Any]) -> BaseModel:
        return schema.model_validate(values)

    page = await fetch_page(
        db,
        stmt,
        query=query,
        terms=terms,
        codec=cursor_codec(
            secret, actor, company, "catalog." + model.__tablename__, context, query
        ),
        project=project,
    )
    if model in {TaxHistoryAction, TaxRelease, TaxRuleApplicability}:
        for item in page.items:
            await dependencies(access, await row(access, model, item.model_dump()["id"]))
    return page
