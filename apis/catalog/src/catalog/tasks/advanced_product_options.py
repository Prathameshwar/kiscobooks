"""Current native Catalog sources for the advanced wizard; no copied policy."""

import uuid
from typing import Any, Literal

from billing_platform.authz import ScopePath
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.api.field_metadata import field_set
from catalog.models.attributes import AttributeDefinition, AttributeSetMember
from catalog.models.commercial import ProductTypeRevision
from catalog.models.projections import CompanyFeatureProjection, CompanyProjection
from catalog.schemas.advanced_product_creation import (
    AdvancedAttributeMember,
    AdvancedCreationOptions,
    AdvancedDraftContent,
    AdvancedTypeOption,
)
from catalog.schemas.configuration import AuthoringDefaults, AuthoringDefaultsQuery
from catalog.schemas.field_metadata import FieldSet
from catalog.schemas.simple_product_creation import SimpleBatchOptions
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.configuration_authoring import suggestions
from catalog.tasks.pricing_commands import business_date
from catalog.tasks.product_mode import read as read_mode
from catalog.tasks.product_stock_choice import available
from catalog.tasks.simple_classification_details import required_schemes
from catalog.tasks.simple_creation_preparation import default_group
from catalog.tasks.simple_sale_prices import sale_choices
from catalog.tasks.simple_serial_preparation import serial_options


async def fields(
    db: AsyncSession, current: Actor, company: uuid.UUID, request: Request
) -> tuple[FieldSet, FieldSet]:
    clean = Request(dict(request.scope) | {"query_string": b""})
    family = await field_set(company, "catalog.product_family", clean, "create", None, current, db)
    sku = await field_set(company, "catalog.item", clean, "create", None, current, db)
    return family, sku


async def defaults(
    db: AsyncSession,
    current: Actor,
    company: uuid.UUID,
    *,
    kind: Literal["GOODS", "SERVICE"],
    group_id: uuid.UUID | None,
    product_type_revision_id: uuid.UUID | None,
) -> tuple[AuthoringDefaults, uuid.UUID | None, CompanyProjection]:
    access = ConfigurationAccess(db, current, company)
    profile = await db.scalar(
        select(CompanyProjection).where(
            CompanyProjection.company_id == company, CompanyProjection.source_id == company
        )
    )
    if profile is None:
        raise ConflictError("Company product defaults are still being prepared")
    group = group_id or await default_group(access)
    chosen = await suggestions(
        access,
        AuthoringDefaultsQuery(
            as_of=business_date(profile.timezone),
            kind=kind,
            group_id=group,
            product_type_revision_id=product_type_revision_id,
            include_price=False,
        ),
    )
    return chosen, group, profile


async def context(
    db: AsyncSession,
    current: Actor,
    company: uuid.UUID,
    request: Request,
    *,
    kind: Literal["GOODS", "SERVICE"],
    group_id: uuid.UUID | None = None,
    product_type_revision_id: uuid.UUID | None = None,
) -> AdvancedCreationOptions:
    current.require_scope("item.create", target=ScopePath(company_id=company))
    mode = await read_mode(db, current, company)
    if not mode.product_family_sku_enabled:
        raise ConflictError("This company uses Simple Product creation")
    selected, group, company_row = await defaults(
        db,
        current,
        company,
        kind=kind,
        group_id=group_id,
        product_type_revision_id=product_type_revision_id,
    )
    family, sku = await fields(db, current, company, request)
    access = ConfigurationAccess(db, current, company)
    configuration = selected.configuration
    batch = await available(access, configuration, selected.product_type_revision_id, kind)
    serial = await serial_options(access, configuration, kind)
    selected_type = None
    attribute_members: list[AdvancedAttributeMember] = []
    if selected.product_type_revision_id is not None:
        revision = await access.reference(ProductTypeRevision, selected.product_type_revision_id)
        selected_type = AdvancedTypeOption(
            id=revision.id,
            attribute_set_revision_id=revision.attribute_set_revision_id,
            kind=revision.kind,
            unit_dimensions=revision.unit_dimensions,
            inventory_modes=revision.inventory_modes,
            tracking_modes=revision.tracking_modes,
            allow_variants=revision.allow_variants,
            require_brand=revision.require_brand,
            require_manufacturer=revision.require_manufacturer,
            require_expiry=revision.require_expiry,
        )
        if revision.attribute_set_revision_id is not None:
            rows = list(await db.scalars(
                select(AttributeSetMember)
                .where(
                    AttributeSetMember.company_id == company,
                    AttributeSetMember.revision_id == revision.attribute_set_revision_id,
                )
                .order_by(AttributeSetMember.position, AttributeSetMember.id)
                .limit(129)
            ))
            if len(rows) > 128:
                raise ConflictError("Product Type has too many attribute members")
            for row in rows:
                await access.require(row)
                definition = await access.reference(AttributeDefinition, row.definition_id)
                attribute_members.append(AdvancedAttributeMember.model_validate({
                    "definition_id": definition.id, "name": definition.name,
                    "value_type": definition.value_type,
                    "measurement_dimension": definition.measurement_dimension,
                    "position": row.position, "is_required": row.is_required,
                    "allow_variant_axis": row.allow_variant_axis,
                    "is_variant_capable": definition.is_variant_capable,
                }))
    inventory_enabled = (
        await db.scalar(
            select(CompanyFeatureProjection.id)
            .where(
                CompanyFeatureProjection.company_id == company,
                CompanyFeatureProjection.feature_key == "inventory",
                CompanyFeatureProjection.is_enabled.is_(True),
            )
            .limit(1)
        )
        is not None
    )
    price_access = current.allows_scope("price_plan.read", target=ScopePath(company_id=company))
    if configuration.pricing.sale_price_mode == "REQUIRED" and not price_access:
        raise PermissionDeniedError("selling prices require price plan read access")
    levels = (
        await sale_choices(
            access, configuration, business_date(company_row.timezone), include_default=True
        )
        if price_access
        else []
    )
    schemes = (
        await required_schemes(access) if configuration.options.category_mode != "DISABLED" else []
    )
    return AdvancedCreationOptions(
        company_id=company,
        kind=kind,
        today=business_date(company_row.timezone),
        currency=company_row.base_currency,
        mode=mode,
        defaults=selected,
        default_group_id=group,
        selected_type=selected_type,
        attribute_members=attribute_members,
        inventory_enabled=inventory_enabled,
        batch=SimpleBatchOptions.model_validate(batch),
        serial=serial,
        gst_enabled=company_row.default_tax_system == "gst_in",
        price_levels_accessible=price_access,
        family_fields=family,
        sku_fields=sku,
        sale_price_levels=levels,
        required_category_schemes=schemes,
    )


def selected_context(
    content: AdvancedDraftContent,
) -> tuple[Literal["GOODS", "SERVICE"], uuid.UUID | None, uuid.UUID | None]:
    value = content.profile
    kind = value.get("kind", "GOODS")
    if kind not in {"GOODS", "SERVICE"}:
        raise ValidationFailedError("Choose Goods or Service before saving the draft")
    ids = []
    for key in ("group_id", "product_type_revision_id"):
        raw: Any = value.get(key)
        try:
            ids.append(uuid.UUID(str(raw)) if raw is not None else None)
        except (ValueError, TypeError) as exc:
            raise ValidationFailedError(f"{key} must be a real identifier") from exc
    return kind, ids[0], ids[1]


def guard_content(
    content: AdvancedDraftContent,
    family: FieldSet,
    sku: FieldSet,
    *,
    write: bool,
) -> None:
    """A saved snapshot may never bypass a current native/custom field deny."""
    protected = (
        (
            content.profile,
            family,
            frozenset(
                {
                    "code",
                    "name",
                    "kind",
                    "structure_mode",
                    "product_type_revision_id",
                    "brand_id",
                    "series_id",
                    "model_code",
                    "description",
                }
            ),
        ),
        *(
            (
                entry,
                sku,
                frozenset(
                    {"sku", "name", "base_unit_id", "sellable", "purchasable", "min_sale_quantity"}
                ),
            )
            for entry in content.skus
        ),
    )
    for values, field_set_value, direct in protected:
        available = {field.key: field for field in field_set_value.fields}
        for key in direct & values.keys():
            field = available.get(key)
            if field is None or not field.visible or (write and not field.writable):
                raise PermissionDeniedError("product draft contains a protected field")
        custom = values.get("custom_fields")
        if custom is not None:
            if not isinstance(custom, dict) or len(custom) > 128:
                raise ValidationFailedError("custom fields must be a bounded object")
            for key in custom:
                field = available.get(key)
                if (
                    field is None
                    or field.source != "custom"
                    or not field.visible
                    or (write and not field.writable)
                ):
                    raise PermissionDeniedError("product draft contains a protected custom field")
