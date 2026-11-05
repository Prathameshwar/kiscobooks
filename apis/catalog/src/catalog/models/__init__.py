"""Catalog-owned materializations of shared infrastructure and reference models."""

from billing_platform.db.language import Language
from billing_platform.db.platform_models import IdempotencyKey, Outbox, ProcessedMessage
from billing_platform.db.reference_management import (
    ReferenceRevision as ReferenceRevision,
)
from billing_platform.db.reference_management import (
    ReferenceSyncState as ReferenceSyncState,
)
from billing_platform.db.reference_models import Country, Currency, State

from catalog.models.advanced_product_creation import AdvancedProductCreation
from catalog.models.advanced_product_draft import AdvancedProductDraft
from catalog.models.attributes import (
    AttributeDefinition,
    AttributeOption,
    AttributeSet,
    AttributeSetMember,
    AttributeSetRevision,
)
from catalog.models.boms import (
    BOM_MODELS,
    Bom,
    BomAssignment,
    BomComponent,
    BomDraft,
    BomOutput,
    BomRevision,
)
from catalog.models.bulk import (
    BulkChangeSet,
    BulkChangeSetEffect,
    BulkImportArtifact,
    BulkJob,
    BulkJobDependency,
    BulkJobRecord,
)
from catalog.models.classification import (
    CatalogPolicyState,
    CategoryScheme,
    ItemCategory,
    ItemGroup,
    ItemGroupParent,
)
from catalog.models.commercial import (
    Brand,
    BrandManufacturer,
    BrandSeries,
    Manufacturer,
    ManufacturerSite,
    ProductType,
    ProductTypeRevision,
)
from catalog.models.configuration import (
    CONFIGURATION_MODELS,
    CatalogDefaultProfile,
    ProductConfigurationDraft,
    ProductConfigurationRevision,
    ProductConfigurationScope,
    ProductEntryOptionPolicy,
    ProductNumericDefault,
    ProductPricingPolicy,
)
from catalog.models.custom_fields import (
    CustomFieldSequence,
    CustomFieldUniqueClaim,
    CustomFieldValueIndex,
    CustomFieldValueMember,
)
from catalog.models.field_adoption import CustomFieldAdoption
from catalog.models.field_indexes import FieldIndexState, FieldRebuildJob
from catalog.models.handling import HandlingProfile, HandlingProfileRevision
from catalog.models.identifier_masters import (
    IDENTIFIER_MASTER_MODELS,
    IdentifierNamespace,
    IdentifierType,
)
from catalog.models.inventory_templates import (
    InventoryProfileTemplate,
    InventoryProfileTemplateRevision,
)
from catalog.models.manufacturing_operations import (
    ManufacturingOperation,
    ManufacturingOperationRevision,
)
from catalog.models.manufacturing_routes import (
    ManufacturingRoute,
    ManufacturingRouteRevision,
    ManufacturingRouteStep,
)
from catalog.models.master_references import MasterAlias, MasterExternalKey
from catalog.models.product_authoring import (
    CompanyProductAuthoringConfiguration as CompanyProductAuthoringConfiguration,
)
from catalog.models.product_definitions import (
    PRODUCT_DEFINITION_MODELS,
    FamilyAttribute,
    FamilyAttributeOption,
    FamilyCategory,
    FamilyGroupAssignment,
    FamilyManufacturer,
    ItemAttributeValue,
    ItemBarcode,
    ItemUnitBinding,
    ItemUnitRevision,
    ItemVariantKey,
    ProductConfigurationAdoption,
    ProductConfigurationAdoptionSource,
)
from catalog.models.products import Item, ProductFamily
from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement
from catalog.models.projections import (
    CompanyCurrencyAllowanceProjection,
    CompanyFeatureProjection,
    CompanyProjection,
    CustomerPricingProjection,
    CustomerTypeProjection,
    CustomFieldDefinitionProjection,
    FieldConfigProjection,
    FieldPolicyProjection,
    PartyProjection,
    ProjectionCheckpoint,
    RoleAssignmentProjection,
    RoleProjection,
    SourceEventBuffer,
    UserGroupMemberProjection,
    UserGroupProjection,
    UserProjection,
)
from catalog.models.promotion_authoring import (
    PROMOTION_AUTHORING_MODELS as PROMOTION_AUTHORING_MODELS,
)
from catalog.models.promotion_authoring import (
    PromotionStackDraft as PromotionStackDraft,
)
from catalog.models.promotion_authoring import (
    PromotionStackDraftGroup as PromotionStackDraftGroup,
)
from catalog.models.promotion_authoring import (
    PromotionStackDraftPermission as PromotionStackDraftPermission,
)
from catalog.models.promotion_limits import (
    PROMOTION_LIMIT_MODELS as PROMOTION_LIMIT_MODELS,
)
from catalog.models.promotion_limits import (
    PromotionLimitDefinition as PromotionLimitDefinition,
)
from catalog.models.promotion_limits import (
    PromotionLimitRevision as PromotionLimitRevision,
)
from catalog.models.promotions import (
    PROMOTION_MODELS,
    Promotion,
    PromotionBenefit,
    PromotionPriceLevelTarget,
    PromotionRevision,
    PromotionSkuTarget,
    PromotionStackGroup,
    PromotionStackPermission,
    PromotionStackPolicy,
)
from catalog.models.regulatory import ItemRegulatoryClassification
from catalog.models.releases import (
    RELEASE_MODELS,
    CatalogPolicyConsumerAck,
    CatalogPolicyRelease,
)
from catalog.models.returns import ReturnPolicy, ReturnPolicyCondition, ReturnPolicyRevision
from catalog.models.sales_channel import SALES_CHANNEL_MODELS, SalesChannel
from catalog.models.simple_product_creation import SimpleProductCreation
from catalog.models.stock_source import StockSourceFence as StockSourceFence
from catalog.models.tax import (
    CatalogTaxBinding,
    CatalogTaxScope,
    ItemActivation,
    ItemActivationSource,
    ItemInventoryProfile,
    TaxCategory,
    TaxClassification,
    TaxHistoryAction,
    TaxRate,
    TaxRateComponent,
    TaxRateSeries,
    TaxRelease,
    TaxRule,
    TaxRuleApplicability,
)
from catalog.models.units import (
    CompoundUnitComponent,
    PackType,
    UnitConversion,
    UnitOfMeasure,
    UnitTaxCode,
)
from catalog.models.warehouse_groups import (
    WAREHOUSE_GROUP_MODELS,
    WarehouseGroup,
    WarehouseGroupAssignment,
    WarehouseGroupParent,
)
from catalog.models.warehouse_policies import (
    WAREHOUSE_POLICY_MODELS,
    ItemReplenishmentPolicy,
    ItemWarehousePermission,
    ItemWarehousePolicy,
)
from catalog.models.warehouses import (
    DEFAULT_POINTERS,
    WAREHOUSE_MODELS,
    CompanyWarehouseConfiguration,
    Warehouse,
    WarehouseBin,
    WarehouseOperationPolicyRevision,
)
from catalog.models.warranties import WarrantyPolicy, WarrantyPolicyRevision

__all__ = [
    "CONFIGURATION_MODELS",
    "PRODUCT_DEFINITION_MODELS",
    "AttributeDefinition",
    "AttributeOption",
    "AttributeSet",
    "AttributeSetMember",
    "AttributeSetRevision",
    "Brand",
    "BrandManufacturer",
    "BrandSeries",
    "CatalogDefaultProfile",
    "CatalogPolicyState",
    "CategoryScheme",
    "CompanyCurrencyAllowanceProjection",
    "CompanyFeatureProjection",
    "CompanyProductAuthoringConfiguration",
    "CompanyProjection",
    "Country",
    "Currency",
    "CustomFieldDefinitionProjection",
    "CustomFieldSequence",
    "CustomFieldUniqueClaim",
    "CustomFieldValueIndex",
    "CustomFieldValueMember",
    "CustomerPricingProjection",
    "CustomerTypeProjection",
    "FamilyAttribute",
    "FamilyAttributeOption",
    "FamilyCategory",
    "FamilyGroupAssignment",
    "FamilyManufacturer",
    "FieldConfigProjection",
    "FieldIndexState",
    "FieldPolicyProjection",
    "FieldRebuildJob",
    "HandlingProfile",
    "HandlingProfileRevision",
    "IdempotencyKey",
    "IdentifierProfile",
    "IdentifierProfileRequirement",
    "InventoryProfileTemplate",
    "InventoryProfileTemplateRevision",
    "Item",
    "ItemAttributeValue",
    "ItemBarcode",
    "ItemCategory",
    "ItemGroup",
    "ItemGroupParent",
    "ItemRegulatoryClassification",
    "ItemUnitBinding",
    "ItemUnitRevision",
    "ItemVariantKey",
    "Language",
    "Manufacturer",
    "ManufacturerSite",
    "MasterAlias",
    "MasterExternalKey",
    "Outbox",
    "PackType",
    "PartyProjection",
    "ProcessedMessage",
    "ProductConfigurationAdoption",
    "ProductConfigurationAdoptionSource",
    "ProductConfigurationDraft",
    "ProductConfigurationRevision",
    "ProductConfigurationScope",
    "ProductEntryOptionPolicy",
    "ProductFamily",
    "ProductNumericDefault",
    "ProductPricingPolicy",
    "ProductType",
    "ProductTypeRevision",
    "ProjectionCheckpoint",
    "ReturnPolicy",
    "ReturnPolicyCondition",
    "ReturnPolicyRevision",
    "RoleAssignmentProjection",
    "RoleProjection",
    "SourceEventBuffer",
    "State",
    "UnitConversion",
    "UnitOfMeasure",
    "UnitTaxCode",
    "UserGroupMemberProjection",
    "UserGroupProjection",
    "UserProjection",
    "WarrantyPolicy",
    "WarrantyPolicyRevision",
]

from catalog.models.pricing import (
    CommercialGuardRule,
    CommercialPolicyScope,
    CompanyPricingPolicy,
    DiscountCeiling,
    ItemCommercialPolicy,
    ItemMrp,
    ItemPrice,
    ItemPriceDraft,
    ItemPriceFormula,
    ItemPriceNumericRevision,
    ItemPriceScope,
    ItemPriceSeries,
    ItemPriceTier,
    ItemReferenceCost,
    PriceLevel,
    PriceLevelAssignment,
    PriceLevelAssignmentScope,
    PricePlan,
    PurchasePriceTerm,
)
from catalog.models.product_stock_choice import ItemStockChoice

__all__ += [
    "CommercialGuardRule",
    "CommercialPolicyScope",
    "CompanyPricingPolicy",
    "DiscountCeiling",
    "ItemCommercialPolicy",
    "ItemMrp",
    "ItemPrice",
    "ItemPriceDraft",
    "ItemPriceFormula",
    "ItemPriceNumericRevision",
    "ItemPriceScope",
    "ItemPriceSeries",
    "ItemPriceTier",
    "ItemReferenceCost",
    "ItemStockChoice",
    "PriceLevel",
    "PriceLevelAssignment",
    "PriceLevelAssignmentScope",
    "PricePlan",
    "PurchasePriceTerm",
]


__all__ += [
    "CatalogTaxBinding",
    "CatalogTaxScope",
    "ItemActivation",
    "ItemActivationSource",
    "ItemInventoryProfile",
    "TaxCategory",
    "TaxClassification",
    "TaxRate",
    "TaxRateComponent",
    "TaxRateSeries",
    "TaxRule",
]


__all__ += ["CustomFieldAdoption", "TaxHistoryAction", "TaxRelease", "TaxRuleApplicability"]

from catalog.models.tax_governance import TaxImpactFinding, TaxImpactReview  # noqa: E402

__all__ += ["TaxImpactFinding", "TaxImpactReview"]

__all__ += [
    "BulkChangeSet",
    "BulkChangeSetEffect",
    "BulkImportArtifact",
    "BulkJob",
    "BulkJobDependency",
    "BulkJobRecord",
]

__all__ += [
    "DEFAULT_POINTERS",
    "WAREHOUSE_GROUP_MODELS",
    "WAREHOUSE_MODELS",
    "WAREHOUSE_POLICY_MODELS",
    "CompanyWarehouseConfiguration",
    "Warehouse",
    "WarehouseBin",
    "WarehouseGroup",
    "WarehouseGroupAssignment",
    "WarehouseGroupParent",
    "WarehouseOperationPolicyRevision",
]

__all__ += [
    "ItemReplenishmentPolicy",
    "ItemWarehousePermission",
    "ItemWarehousePolicy",
]

__all__ += ["RELEASE_MODELS", "CatalogPolicyConsumerAck", "CatalogPolicyRelease"]
__all__ += ["SALES_CHANNEL_MODELS", "SalesChannel"]
__all__ += ["IDENTIFIER_MASTER_MODELS", "IdentifierNamespace", "IdentifierType"]
__all__ += ["CompoundUnitComponent", "ManufacturingOperation", "ManufacturingOperationRevision"]
__all__ += [
    "PROMOTION_MODELS",
    "Promotion",
    "PromotionBenefit",
    "PromotionPriceLevelTarget",
    "PromotionRevision",
    "PromotionSkuTarget",
    "PromotionStackGroup",
    "PromotionStackPermission",
    "PromotionStackPolicy",
]


__all__ += [
    "AdvancedProductCreation",
    "AdvancedProductDraft",
    "ManufacturingRoute",
    "ManufacturingRouteRevision",
    "ManufacturingRouteStep",
    "SimpleProductCreation",
]
__all__ += [
    "BOM_MODELS",
    "Bom",
    "BomAssignment",
    "BomComponent",
    "BomDraft",
    "BomOutput",
    "BomRevision",
]
