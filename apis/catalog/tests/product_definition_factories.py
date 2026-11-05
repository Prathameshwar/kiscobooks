"""Native fixtures include every configuration and product definition table."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.product_authoring import variant_identity
from catalog.models import (
    CatalogDefaultProfile,
    CategoryScheme,
    FamilyAttribute,
    FamilyAttributeOption,
    FamilyCategory,
    FamilyGroupAssignment,
    FamilyManufacturer,
    Item,
    ItemAttributeValue,
    ItemBarcode,
    ItemCategory,
    ItemGroup,
    ItemGroupParent,
    ItemUnitBinding,
    ItemUnitRevision,
    ItemVariantKey,
    Manufacturer,
    ProductConfigurationAdoption,
    ProductConfigurationAdoptionSource,
    ProductConfigurationDraft,
    ProductConfigurationRevision,
    ProductConfigurationScope,
    ProductEntryOptionPolicy,
    ProductFamily,
    ProductNumericDefault,
    ProductPricingPolicy,
)
from catalog.schemas.configuration import EntryOptions, PricingRequirements, ProfileDefaults
from tests.attribute_factories import seed_attributes
from tests.product_factories import setup_product


async def seed_definitions(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, *, with_barcode: bool = True
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    company, user, _, body = await setup_product(factory, tenant)
    attributes = await seed_attributes(factory, tenant, company)
    result = {**attributes, "actor_user": user}
    common: dict[str, Any] = {"tenant_id": tenant, "company_id": company}
    date = dt.date(2090, 1, 1)
    with tenant_scope(tenant):
        async with factory.begin() as db:

            async def save(model: type[Any], **values: Any) -> Any:
                row = model(**common, **values)
                db.add(row)
                await db.flush()
                result[model.__tablename__] = row.id
                return row

            family = await save(
                ProductFamily,
                code="FAMILY",
                name="Family",
                kind="GOODS",
                product_type_revision_id=uuid.UUID(body["product_type_revision_id"]),
                structure_mode="VARIANT",
                status="DRAFT",
            )
            item = await save(
                Item,
                family_id=family.id,
                default_slot=1,
                sku="SKU",
                name="SKU",
                base_unit_id=uuid.UUID(body["default_item"]["base_unit_id"]),
                sellable=True,
                purchasable=True,
                status="DRAFT",
            )
            group = await save(ItemGroup, code="GROUP", name="Group", allowed_kind="GOODS")
            await save(ItemGroupParent, group_id=group.id, parent_group_id=None, valid_from=date)
            assignment = await save(
                FamilyGroupAssignment, family_id=family.id, group_id=group.id, valid_from=date
            )
            scheme = await save(
                CategoryScheme, code="SCHEME", name="Scheme", membership_mode="SINGLE"
            )
            category = await save(
                ItemCategory, code="CATEGORY", name="Category", scheme_id=scheme.id
            )
            await save(
                FamilyCategory,
                valid_from=dt.date(1000, 1, 1),
                valid_to=None,
                family_id=family.id,
                scheme_id=scheme.id,
                category_id=category.id,
                is_primary=True,
                primary_slot=1,
            )
            manufacturer = await save(Manufacturer, code="MAKER", name="Maker")
            await save(
                FamilyManufacturer,
                family_id=family.id,
                manufacturer_id=manufacturer.id,
                production_role="MANUFACTURER",
                valid_from=date,
            )
            definition, option = attributes["attribute_definition"], attributes["attribute_option"]
            await save(
                FamilyAttribute,
                family_id=family.id,
                definition_id=definition,
                is_axis=True,
                is_required=True,
                position=0,
            )
            await save(
                FamilyAttributeOption,
                family_id=family.id,
                definition_id=definition,
                option_id=option,
            )
            await save(
                ItemAttributeValue,
                item_id=item.id,
                definition_id=definition,
                option_id=option,
                value_type="TEXT",
            )
            digest, canonical = variant_identity(
                {definition: frozenset({option})}, {definition: option}
            )
            await save(
                ItemVariantKey,
                item_id=item.id,
                family_id=family.id,
                combination_hash=digest,
                canonical_combination=canonical,
            )
            binding = await save(
                ItemUnitBinding,
                item_id=item.id,
                unit_id=item.base_unit_id,
                code="BASE",
                usage_role="BASE",
            )
            await save(
                ItemUnitRevision,
                binding_id=binding.id,
                revision=1,
                conversion_mode="FIXED",
                numerator=1,
                denominator=1,
                quantity_decimal_places=0,
                quantity_increment="1",
                fractional_entry=False,
                valid_from=date,
            )
            if with_barcode:
                await save(
                    ItemBarcode,
                    item_id=item.id,
                    binding_id=binding.id,
                    value="000abc",
                    symbology="CODE128",
                    is_active=True,
                )
            scope = await save(
                ProductConfigurationScope, scope_kind="COMPANY", owner_id=company, latest_revision=1
            )
            draft = await save(
                ProductConfigurationDraft,
                scope_id=scope.id,
                status="PUBLISHED",
                effective_from=date,
                change_reason="Initial",
            )
            await save(ProductEntryOptionPolicy, draft_id=draft.id, **EntryOptions().model_dump())
            await save(
                ProductNumericDefault,
                draft_id=draft.id,
                dimension="COUNT",
                quantity_decimal_places=0,
                quantity_increment="1",
            )
            await save(CatalogDefaultProfile, draft_id=draft.id, **ProfileDefaults().model_dump())
            await save(
                ProductPricingPolicy, draft_id=draft.id, **PricingRequirements().model_dump()
            )
            revision = await save(
                ProductConfigurationRevision,
                scope_id=scope.id,
                source_draft_id=draft.id,
                revision=1,
                effective_from=date,
                change_reason="Initial",
                published_at=utcnow(),
            )
            await save(
                ProductEntryOptionPolicy, revision_id=revision.id, **EntryOptions().model_dump()
            )
            await save(
                ProductNumericDefault,
                revision_id=revision.id,
                dimension="COUNT",
                quantity_decimal_places=0,
                quantity_increment="1",
            )
            await save(
                CatalogDefaultProfile, revision_id=revision.id, **ProfileDefaults().model_dump()
            )
            await save(
                ProductPricingPolicy, revision_id=revision.id, **PricingRequirements().model_dump()
            )
            adoption = await save(
                ProductConfigurationAdoption,
                item_id=item.id,
                resolution_version=1,
                revision=1,
                effective_on=date,
                product_type_revision_id=family.product_type_revision_id,
                group_assignment_id=assignment.id,
                source_version=1,
                policy_generation=1,
                preview_hash=bytes(32),
            )
            await save(
                ProductConfigurationAdoptionSource,
                adoption_id=adoption.id,
                scope_id=scope.id,
                revision_id=revision.id,
            )
    return company, result
