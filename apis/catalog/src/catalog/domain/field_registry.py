"""Catalog native field descriptors; only migrated entities are registered."""

from billing_platform.fields import EntityFields, FieldRegistry, NativeField

registry = FieldRegistry()


def fixed(order: int) -> NativeField:
    return NativeField(
        required=True, hideable=False, reason="native quantity or identity contract", order=order
    )


registry.register(
    EntityFields(
        "catalog.item_stock_choice",
        "ItemStockChoice",
        {
            "item_id": fixed(10),
            "batch_enabled": fixed(20),
            "row_version": fixed(30),
        },
    )
)


registry.register(
    EntityFields(
        "catalog.company_product_authoring_configuration",
        "CompanyProductAuthoringConfiguration",
        {
            "product_family_sku_enabled": fixed(10),
            "row_version": fixed(20),
            "change_reason": fixed(30),
        },
    )
)


for limit_entity, limit_model, limit_fields in (
    (
        "promotion_limit_definition",
        "PromotionLimitDefinition",
        (
            "code",
            "name",
            "is_active",
            "row_version",
            "scope_kind",
            "metric",
            "period_basis",
            "timezone",
            "currency",
            "unit_id",
        ),
    ),
    (
        "promotion_limit_revision",
        "PromotionLimitRevision",
        (
            "definition_id",
            "revision",
            "row_version",
            "published_at",
            "published_source_version",
            "publication_generation",
            "change_reason",
            "maximum_count",
            "maximum_quantity",
            "maximum_amount",
        ),
    ),
):
    registry.register(
        EntityFields(
            "catalog." + limit_entity,
            limit_model,
            {
                key: NativeField(required=False, order=(index + 1) * 10)
                if key
                in {
                    "currency",
                    "unit_id",
                    "maximum_count",
                    "maximum_quantity",
                    "maximum_amount",
                    "published_at",
                    "published_source_version",
                    "publication_generation",
                }
                else fixed((index + 1) * 10)
                for index, key in enumerate(limit_fields)
            },
        )
    )


for stack_entity, stack_model, stack_fields in (
    (
        "promotion_stack_draft",
        "PromotionStackDraft",
        (
            "code",
            "maximum_applied",
            "change_reason",
            "row_version",
            "status",
            "group_count",
            "permission_count",
            "published_policy_id",
        ),
    ),
    (
        "promotion_stack_draft_group",
        "PromotionStackDraftGroup",
        ("draft_id", "position", "stage", "selection", "changes_basket"),
    ),
    (
        "promotion_stack_draft_permission",
        "PromotionStackDraftPermission",
        ("draft_id", "earlier_group_id", "later_group_id", "include_reward_units"),
    ),
    (
        "promotion_stack_policy",
        "PromotionStackPolicy",
        ("code", "version", "maximum_applied", "published_at", "source_sha256"),
    ),
    (
        "promotion_stack_group",
        "PromotionStackGroup",
        ("policy_revision_id", "position", "stage", "selection", "changes_basket"),
    ),
    (
        "promotion_stack_permission",
        "PromotionStackPermission",
        ("policy_revision_id", "earlier_group_id", "later_group_id", "include_reward_units"),
    ),
):
    registry.register(
        EntityFields(
            "catalog." + stack_entity,
            stack_model,
            {key: fixed((index + 1) * 10) for index, key in enumerate(stack_fields)},
        )
    )

for bom_entity, bom_model, bom_fields in (
    ("bom", "Bom", ("code", "name", "is_active", "row_version")),
    (
        "bom_draft",
        "BomDraft",
        (
            "bom_id",
            "draft_number",
            "row_version",
            "status",
            "published_revision_id",
            "specification",
            "change_reason",
            "definition_date",
            "route_revision_id",
            "batch_minimum",
            "batch_maximum",
            "batch_multiple",
            "component_count",
            "output_count",
        ),
    ),
    (
        "bom_revision",
        "BomRevision",
        (
            "bom_id",
            "revision",
            "draft_id",
            "row_version",
            "status",
            "published_at",
            "specification",
            "change_reason",
            "definition_date",
            "route_revision_id",
            "batch_minimum",
            "batch_maximum",
            "batch_multiple",
            "component_count",
            "output_count",
            "policy_generation",
            "source_version",
            "content_sha256",
            "dependency_manifest",
        ),
    ),
    (
        "bom_component",
        "BomComponent",
        (
            "draft_id",
            "revision_id",
            "line_key",
            "sequence",
            "item_id",
            "unit_revision_id",
            "quantity",
            "basis",
            "loss_fraction",
            "timing",
            "route_step_id",
        ),
    ),
    (
        "bom_output",
        "BomOutput",
        (
            "draft_id",
            "revision_id",
            "line_key",
            "sequence",
            "item_id",
            "unit_revision_id",
            "nominal_quantity",
            "yield_fraction",
            "role",
        ),
    ),
    (
        "bom_assignment",
        "BomAssignment",
        (
            "row_version",
            "bom_revision_id",
            "item_id",
            "warehouse_id",
            "valid_from",
            "valid_to",
            "is_active",
            "change_reason",
        ),
    ),
):
    registry.register(
        EntityFields(
            "catalog." + bom_entity,
            bom_model,
            {
                key: fixed((index + 1) * 10)
                if key
                in {
                    "code",
                    "name",
                    "row_version",
                    "status",
                    "bom_id",
                    "draft_id",
                    "revision_id",
                    "line_key",
                    "sequence",
                    "component_count",
                    "output_count",
                }
                else NativeField(
                    required=key
                    in {
                        "specification",
                        "change_reason",
                        "definition_date",
                        "item_id",
                        "quantity",
                        "basis",
                        "loss_fraction",
                        "timing",
                        "nominal_quantity",
                        "yield_fraction",
                        "role",
                        "valid_from",
                        "bom_revision_id",
                    },
                    order=(index + 1) * 10,
                )
                for index, key in enumerate(bom_fields)
            },
        )
    )


for entity, model, extra in (
    ("identifier_type", "IdentifierType", {"is_barcode": fixed(50)}),
    ("identifier_namespace", "IdentifierNamespace", {}),
):
    registry.register(
        EntityFields(
            "catalog." + entity,
            model,
            {
                "code": fixed(10),
                "name": fixed(20),
                "is_active": fixed(30),
                "row_version": fixed(40),
                **extra,
            },
        )
    )


registry.register(
    EntityFields(
        "catalog.manufacturing_operation",
        "ManufacturingOperation",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.manufacturing_operation_revision",
        "ManufacturingOperationRevision",
        {
            "operation_id": fixed(10),
            "revision": fixed(20),
            "row_version": fixed(30),
            "status": fixed(40),
            "published_at": NativeField(order=50),
            "specification": fixed(60),
            "change_reason": fixed(70),
            "service_item_id": NativeField(order=80),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.unit_of_measure",
        "UnitOfMeasure",
        {
            "code": fixed(10),
            "symbol": fixed(20),
            "name": fixed(30),
            "dimension": fixed(40),
            "decimal_places": fixed(50),
            "quantity_increment": fixed(60),
            "is_active": fixed(70),
            "row_version": fixed(80),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.pack_type",
        "PackType",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.unit_conversion",
        "UnitConversion",
        {
            "from_unit_id": fixed(10),
            "canonical_unit_id": fixed(20),
            "numerator": fixed(30),
            "denominator": fixed(40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.unit_tax_code",
        "UnitTaxCode",
        {
            "unit_id": fixed(10),
            "jurisdiction": fixed(20),
            "official_code": fixed(30),
            "valid_from": fixed(40),
            "valid_to": NativeField(hideable=False, reason="effective mapping boundary", order=50),
        },
    )
)

for entity, model, extra in (
    ("item_group", "ItemGroup", {"allowed_kind": fixed(50)}),
    ("category_scheme", "CategoryScheme", {"membership_mode": fixed(50), "is_required": fixed(60)}),
    (
        "item_category",
        "ItemCategory",
        {"scheme_id": fixed(50), "parent_id": NativeField(order=60)},
    ),
):
    registry.register(
        EntityFields(
            "catalog." + entity,
            model,
            {
                "code": fixed(10),
                "name": fixed(20),
                "is_active": fixed(30),
                "row_version": fixed(40),
                **extra,
            },
        )
    )
registry.register(
    EntityFields(
        "catalog.item_group_parent",
        "ItemGroupParent",
        {
            "group_id": fixed(10),
            "parent_group_id": NativeField(order=20),
            "valid_from": fixed(30),
            "valid_to": NativeField(order=40),
        },
    )
)

# These identities are adopted contracts; absent models are not runtime registrations.
CUSTOM_ENABLED_ENTITIES = frozenset(
    {
        "catalog.product_family",
        "catalog.item",
        "catalog.item_group",
        "catalog.item_category",
        "catalog.product_type",
        "catalog.brand",
        "catalog.manufacturer",
        "catalog.price_plan",
        "catalog.tax_rule",
        "catalog.campaign",
        "catalog.promotion",
    }
)

# Commercial masters and their dated/revision children.
registry.register(
    EntityFields(
        "catalog.brand",
        "Brand",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
            "parent_brand_id": NativeField(order=50),
            "owner_party_id": NativeField(order=60),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.manufacturer",
        "Manufacturer",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
            "party_id": NativeField(order=50),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.brand_series",
        "BrandSeries",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
            "brand_id": fixed(50),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.manufacturer_site",
        "ManufacturerSite",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
            "manufacturer_id": fixed(50),
            "country_code": fixed(60),
            "state_code": NativeField(order=70),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.product_type",
        "ProductType",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
            "kind": fixed(50),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.brand_manufacturer",
        "BrandManufacturer",
        {
            "brand_id": fixed(10),
            "manufacturer_id": fixed(20),
            "production_role": fixed(30),
            "valid_from": fixed(40),
            "valid_to": NativeField(order=50),
            "row_version": fixed(60),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.product_type_revision",
        "ProductTypeRevision",
        {
            "product_type_id": fixed(10),
            "revision": fixed(20),
            "row_version": fixed(30),
            "kind": fixed(40),
            "inventory_modes": fixed(50),
            "tracking_modes": fixed(60),
            "unit_dimensions": fixed(70),
            "allow_variants": fixed(80),
            "require_brand": fixed(90),
            "require_manufacturer": fixed(100),
            "require_expiry": fixed(110),
            "published_at": NativeField(order=120),
            "attribute_set_revision_id": NativeField(order=130),
            "inventory_template_revision_id": NativeField(order=140),
            "warranty_revision_id": NativeField(order=150),
            "return_policy_revision_id": NativeField(order=160),
            "handling_revision_id": NativeField(order=170),
        },
    )
)

# Native typed attributes and reusable templates.
registry.register(
    EntityFields(
        "catalog.attribute_definition",
        "AttributeDefinition",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
            "value_type": fixed(50),
            "measurement_dimension": NativeField(order=60),
            "is_variant_capable": fixed(70),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.attribute_option",
        "AttributeOption",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
            "definition_id": fixed(50),
            "value_type": fixed(60),
            "value_text": NativeField(order=70),
            "value_integer": NativeField(order=80),
            "value_decimal": NativeField(order=90),
            "value_boolean": NativeField(order=100),
            "value_date": NativeField(order=110),
            "unit_id": NativeField(order=120),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.attribute_set",
        "AttributeSet",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.attribute_set_revision",
        "AttributeSetRevision",
        {
            "attribute_set_id": fixed(10),
            "revision": fixed(20),
            "row_version": fixed(30),
            "published_at": NativeField(order=40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.attribute_set_member",
        "AttributeSetMember",
        {
            "revision_id": fixed(10),
            "definition_id": fixed(20),
            "position": fixed(30),
            "is_required": fixed(40),
            "allow_variant_axis": fixed(50),
        },
    )
)


registry.register(
    EntityFields(
        "catalog.identifier_profile",
        "IdentifierProfile",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
            "normalization_version": fixed(50),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.identifier_profile_requirement",
        "IdentifierProfileRequirement",
        {
            "profile_id": fixed(10),
            "identifier_type": fixed(20),
            "namespace_rule": fixed(30),
            "min_count": fixed(40),
            "max_count": fixed(50),
            "requires_slot": fixed(60),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.inventory_profile_template",
        "InventoryProfileTemplate",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.inventory_profile_template_revision",
        "InventoryProfileTemplateRevision",
        {
            "template_id": fixed(10),
            "revision": fixed(20),
            "row_version": fixed(30),
            "published_at": NativeField(order=40),
            "identifier_profile_id": NativeField(order=50),
            "lot_tracking": fixed(60),
            "serial_tracking": fixed(70),
            "expiry_required": fixed(80),
            "manufacture_date_required": fixed(90),
            "shelf_life_days": NativeField(order=100),
            "minimum_remaining_life_days": NativeField(order=110),
            "issue_strategy": fixed(120),
            "valuation_method": fixed(130),
            "negative_stock_policy": fixed(140),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.warranty_policy",
        "WarrantyPolicy",
        {"code": fixed(10), "name": fixed(20), "is_active": fixed(30), "row_version": fixed(40)},
    )
)
registry.register(
    EntityFields(
        "catalog.warranty_policy_revision",
        "WarrantyPolicyRevision",
        {
            "policy_id": fixed(10),
            "revision": fixed(20),
            "row_version": fixed(30),
            "published_at": NativeField(order=40),
            "duration": fixed(50),
            "duration_unit": fixed(60),
            "start_trigger": fixed(70),
            "coverage_description": NativeField(order=80),
        },
    )
)


registry.register(
    EntityFields(
        "catalog.return_policy",
        "ReturnPolicy",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.return_policy_revision",
        "ReturnPolicyRevision",
        {
            "policy_id": fixed(10),
            "revision": fixed(20),
            "row_version": fixed(30),
            "published_at": NativeField(order=40),
            "returns_allowed": fixed(50),
            "window_days": NativeField(order=60),
            "condition_count": fixed(70),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.return_policy_condition",
        "ReturnPolicyCondition",
        {
            "revision_id": fixed(10),
            "condition_code": fixed(20),
        },
    )
)


registry.register(
    EntityFields(
        "catalog.handling_profile",
        "HandlingProfile",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.sales_channel",
        "SalesChannel",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.handling_profile_revision",
        "HandlingProfileRevision",
        {
            "profile_id": fixed(10),
            "revision": fixed(20),
            "row_version": fixed(30),
            "published_at": NativeField(order=40),
            "temperature_min": NativeField(order=50),
            "temperature_max": NativeField(order=60),
            "temperature_unit": NativeField(order=70),
            "fragile": fixed(80),
            "keep_dry": fixed(90),
            "keep_upright": fixed(100),
            "instructions": NativeField(order=110),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.master_alias",
        "MasterAlias",
        {
            "entity_type": fixed(10),
            "target_id": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
            "alias": fixed(50),
            "canonical_value": fixed(60),
            "normalization_version": fixed(70),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.master_external_key",
        "MasterExternalKey",
        {
            "entity_type": fixed(10),
            "target_id": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
            "source_namespace": fixed(50),
            "external_key": fixed(60),
        },
    )
)


# Native product identities are registered with their paired migrations.
registry.register(
    EntityFields(
        "catalog.product_family",
        "ProductFamily",
        {
            "code": fixed(10),
            "name": fixed(20),
            "kind": fixed(30),
            "structure_mode": fixed(40),
            "product_type_revision_id": fixed(50),
            "brand_id": NativeField(order=60),
            "series_id": NativeField(order=70),
            "model_code": NativeField(order=80),
            "description": NativeField(order=90),
            "status": fixed(100),
            "row_version": fixed(110),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.item",
        "Item",
        {
            "family_id": fixed(10),
            "default_slot": NativeField(order=20),
            "sku": fixed(30),
            "name": fixed(40),
            "base_unit_id": fixed(50),
            "sellable": fixed(60),
            "purchasable": fixed(70),
            "min_sale_quantity": NativeField(order=80),
            "status": fixed(90),
            "row_version": fixed(100),
        },
    )
)


# Reviewed statutory classifications are typed data, never item custom fields.
registry.register(
    EntityFields(
        "catalog.item_regulatory_classification",
        "ItemRegulatoryClassification",
        {
            "item_id": fixed(10),
            "valid_from": fixed(20),
            "valid_to": NativeField(order=30),
            "product_kind": fixed(40),
            "licence_class": NativeField(order=50),
            "prescription_schedule": NativeField(order=60),
            "food_category_code": NativeField(order=65),
            "source_reference": fixed(70),
            "source_url": fixed(80),
            "source_sha256": fixed(90),
            "review_reason": fixed(100),
            "reviewed_at": fixed(110),
            "reviewed_by": fixed(120),
            "row_version": fixed(130),
        },
    )
)

# Native configuration values and immutable publication sources.
registry.register(
    EntityFields(
        "catalog.product_configuration_scope",
        "ProductConfigurationScope",
        {
            "scope_kind": fixed(10),
            "owner_id": fixed(20),
            "product_type_id": NativeField(order=30),
            "group_id": NativeField(order=40),
            "family_id": NativeField(order=50),
            "item_id": NativeField(order=60),
            "row_version": fixed(70),
            "latest_revision": fixed(80),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.product_configuration_draft",
        "ProductConfigurationDraft",
        {
            "scope_id": fixed(10),
            "status": fixed(20),
            "row_version": fixed(30),
            "effective_from": fixed(40),
            "change_reason": fixed(50),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.product_configuration_revision",
        "ProductConfigurationRevision",
        {
            "scope_id": fixed(10),
            "source_draft_id": fixed(20),
            "revision": fixed(30),
            "effective_from": fixed(40),
            "published_at": fixed(50),
            "change_reason": fixed(60),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.product_entry_option_policy",
        "ProductEntryOptionPolicy",
        {
            "variants_mode": fixed(10),
            "variants_default": NativeField(order=20),
            "barcode_mode": fixed(30),
            "barcode_default": NativeField(order=40),
            "brand_mode": fixed(50),
            "brand_default": NativeField(order=60),
            "model_mode": fixed(65),
            "model_default": NativeField(order=66),
            "category_mode": fixed(70),
            "category_default": NativeField(order=80),
            "manufacturer_mode": fixed(90),
            "manufacturer_default": NativeField(order=100),
            "alternate_units_mode": fixed(110),
            "alternate_units_default": NativeField(order=120),
            "compound_units_mode": fixed(130),
            "compound_units_default": NativeField(order=140),
            "measured_units_mode": fixed(150),
            "measured_units_default": NativeField(order=160),
            "draft_id": NativeField(order=170),
            "revision_id": NativeField(order=180),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.product_numeric_default",
        "ProductNumericDefault",
        {
            "dimension": fixed(10),
            "quantity_decimal_places": NativeField(order=20),
            "quantity_increment": NativeField(order=30),
            "price_decimal_places": NativeField(order=40),
            "price_increment": NativeField(order=50),
            "currency": NativeField(order=60),
            "price_basis_quantity": NativeField(order=70),
            "draft_id": NativeField(order=80),
            "revision_id": NativeField(order=90),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.catalog_default_profile",
        "CatalogDefaultProfile",
        {
            "goods_type_revision_mode": fixed(10),
            "goods_type_revision_id": NativeField(order=20),
            "service_type_revision_mode": fixed(30),
            "service_type_revision_id": NativeField(order=40),
            "inventory_template_revision_mode": fixed(50),
            "inventory_template_revision_id": NativeField(order=60),
            "warranty_revision_mode": fixed(70),
            "warranty_revision_id": NativeField(order=80),
            "return_policy_revision_mode": fixed(90),
            "return_policy_revision_id": NativeField(order=100),
            "handling_revision_mode": fixed(110),
            "handling_revision_id": NativeField(order=120),
            "identifier_profile_mode": fixed(130),
            "identifier_profile_id": NativeField(order=140),
            "draft_id": NativeField(order=150),
            "revision_id": NativeField(order=160),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.product_pricing_policy",
        "ProductPricingPolicy",
        {
            "purchase_reference_mode": fixed(10),
            "sale_price_mode": fixed(20),
            "mrp_mode": fixed(30),
            "sale_level_count": NativeField(order=40),
            "draft_id": NativeField(order=50),
            "revision_id": NativeField(order=60),
            "unit_prices_mode": fixed(70),
            "quantity_tiers_mode": fixed(80),
            "channel_prices_mode": fixed(90),
            "additional_currencies_mode": fixed(100),
            "formula_prices_mode": fixed(110),
            "multiple_price_levels_mode": fixed(120),
        },
    )
)


registry.register(
    EntityFields(
        "catalog.family_group_assignment",
        "FamilyGroupAssignment",
        {
            "row_version": fixed(10),
            "family_id": fixed(20),
            "group_id": fixed(30),
            "valid_from": fixed(40),
            "valid_to": NativeField(order=50),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.family_category",
        "FamilyCategory",
        {
            "row_version": fixed(10),
            "family_id": fixed(20),
            "scheme_id": fixed(30),
            "category_id": fixed(40),
            "is_primary": fixed(50),
            "primary_slot": NativeField(order=60),
            "valid_from": fixed(70),
            "valid_to": NativeField(order=80),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.family_manufacturer",
        "FamilyManufacturer",
        {
            "row_version": fixed(10),
            "family_id": fixed(20),
            "manufacturer_id": fixed(30),
            "site_id": NativeField(order=40),
            "production_role": fixed(50),
            "valid_from": fixed(60),
            "valid_to": NativeField(order=70),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.family_attribute",
        "FamilyAttribute",
        {
            "row_version": fixed(10),
            "family_id": fixed(20),
            "definition_id": fixed(30),
            "is_axis": fixed(40),
            "is_required": fixed(50),
            "position": fixed(60),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.family_attribute_option",
        "FamilyAttributeOption",
        {
            "row_version": fixed(10),
            "family_id": fixed(20),
            "definition_id": fixed(30),
            "option_id": fixed(40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.item_attribute_value",
        "ItemAttributeValue",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "definition_id": fixed(30),
            "option_id": NativeField(order=40),
            "value_type": fixed(50),
            "value_text": NativeField(order=60),
            "value_integer": NativeField(order=70),
            "value_decimal": NativeField(order=80),
            "value_boolean": NativeField(order=90),
            "value_date": NativeField(order=100),
            "unit_id": NativeField(order=110),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.item_variant_key",
        "ItemVariantKey",
        {
            "row_version": fixed(10),
            "family_id": fixed(20),
            "item_id": fixed(30),
            "combination_hash": fixed(40),
            "canonical_combination": fixed(50),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.item_unit_binding",
        "ItemUnitBinding",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "code": fixed(30),
            "unit_id": fixed(40),
            "usage_role": fixed(50),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.item_unit_revision",
        "ItemUnitRevision",
        {
            "row_version": fixed(10),
            "binding_id": fixed(20),
            "revision": fixed(30),
            "pack_type_id": NativeField(order=40),
            "conversion_mode": fixed(50),
            "numerator": NativeField(order=60),
            "denominator": NativeField(order=70),
            "nominal_ratio": NativeField(order=80),
            "secondary_unit_id": NativeField(order=90),
            "quantity_decimal_places": fixed(100),
            "quantity_increment": fixed(110),
            "fractional_entry": fixed(120),
            "valid_from": fixed(130),
            "valid_to": NativeField(order=140),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.item_barcode",
        "ItemBarcode",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "binding_id": NativeField(order=30),
            "value": fixed(40),
            "symbology": fixed(50),
            "is_active": fixed(60),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.product_configuration_adoption",
        "ProductConfigurationAdoption",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "revision": fixed(30),
            "effective_on": fixed(40),
            "product_type_revision_id": fixed(50),
            "group_assignment_id": NativeField(order=60),
            "source_version": fixed(70),
            "policy_generation": fixed(80),
            "preview_hash": fixed(90),
            "resolution_version": fixed(100),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.product_configuration_adoption_source",
        "ProductConfigurationAdoptionSource",
        {
            "row_version": fixed(10),
            "adoption_id": fixed(20),
            "scope_id": fixed(30),
            "revision_id": fixed(40),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.price_level",
        "PriceLevel",
        {
            "row_version": fixed(10),
            "code": fixed(20),
            "name": fixed(30),
            "ordinal": fixed(40),
            "is_active": fixed(50),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.price_plan",
        "PricePlan",
        {
            "row_version": fixed(10),
            "code": fixed(20),
            "name": fixed(30),
            "purpose": fixed(40),
            "price_level_id": NativeField(order=50),
            "currency": fixed(60),
            "tax_basis": fixed(70),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.company_pricing_policy",
        "CompanyPricingPolicy",
        {
            "row_version": fixed(10),
            "default_level_id": fixed(20),
            "missing_price_policy": fixed(30),
            "fallback_level_id": NativeField(order=40),
            "purchase_plan_id": NativeField(order=50),
            "sale_unit_mode": fixed(60),
            "purchase_unit_mode": fixed(70),
            "valid_from": fixed(80),
            "valid_to": NativeField(order=90),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_price_scope",
        "ItemPriceScope",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "subject_kind": fixed(30),
            "lot_id": NativeField(order=40),
            "lot_mrp": NativeField(order=50),
            "lot_currency": NativeField(order=60),
            "lot_unit_id": NativeField(order=70),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_price_numeric_revision",
        "ItemPriceNumericRevision",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "unit_revision_id": fixed(30),
            "currency": fixed(40),
            "price_decimal_places": fixed(50),
            "price_increment": NativeField(order=60),
            "valid_from": fixed(70),
            "valid_to": NativeField(order=80),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_price_series",
        "ItemPriceSeries",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "unit_revision_id": fixed(30),
            "currency": fixed(40),
            "plan_id": fixed(50),
            "price_scope_id": fixed(60),
            "audience_kind": fixed(70),
            "channel_code": fixed(80),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_price_draft",
        "ItemPriceDraft",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "unit_revision_id": fixed(30),
            "currency": fixed(40),
            "numeric_revision_id": fixed(50),
            "series_id": fixed(60),
            "valid_from": fixed(70),
            "valid_to": NativeField(order=80),
            "price_method": fixed(90),
            "amount": NativeField(order=100),
            "price_basis_quantity": fixed(110),
            "status": fixed(130),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_price",
        "ItemPrice",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "unit_revision_id": fixed(30),
            "currency": fixed(40),
            "numeric_revision_id": fixed(50),
            "series_id": fixed(60),
            "valid_from": fixed(70),
            "valid_to": NativeField(order=80),
            "price_method": fixed(90),
            "amount": NativeField(order=100),
            "price_basis_quantity": fixed(110),
            "source_draft_id": fixed(130),
            "supersedes_id": NativeField(order=140),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_price_tier",
        "ItemPriceTier",
        {
            "row_version": fixed(10),
            "draft_id": NativeField(order=20),
            "price_id": NativeField(order=30),
            "min_quantity": fixed(40),
            "max_quantity": NativeField(order=50),
            "amount": fixed(60),
            "currency": fixed(70),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.purchase_price_term",
        "PurchasePriceTerm",
        {
            "row_version": fixed(10),
            "draft_id": NativeField(order=20),
            "price_id": NativeField(order=30),
            "gross_amount": fixed(40),
            "discount_kind": fixed(50),
            "discount_value": fixed(60),
            "currency": fixed(70),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_reference_cost",
        "ItemReferenceCost",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "unit_revision_id": fixed(30),
            "currency": fixed(40),
            "numeric_revision_id": fixed(50),
            "valid_from": fixed(60),
            "valid_to": NativeField(order=70),
            "amount": fixed(80),
            "price_basis_quantity": fixed(90),
            "tax_basis": fixed(100),
            "source_reference": fixed(110),
            "estimate_kind": fixed(120),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_mrp",
        "ItemMrp",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "unit_revision_id": fixed(30),
            "currency": fixed(40),
            "numeric_revision_id": fixed(50),
            "valid_from": fixed(60),
            "valid_to": NativeField(order=70),
            "amount": fixed(80),
            "price_basis_quantity": fixed(90),
            "tax_basis": fixed(100),
            "source_reference": fixed(110),
            "jurisdiction": fixed(120),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_price_formula",
        "ItemPriceFormula",
        {
            "row_version": fixed(10),
            "draft_id": NativeField(order=20),
            "price_id": NativeField(order=30),
            "recipe": fixed(40),
            "percentage": fixed(50),
            "estimate_kind": NativeField(order=60),
            "jurisdiction": NativeField(order=70),
            "rounding_mode": fixed(80),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.commercial_policy_scope",
        "CommercialPolicyScope",
        {
            "row_version": fixed(10),
            "owner_kind": fixed(20),
            "owner_id": fixed(30),
            "group_id": NativeField(order=40),
            "family_id": NativeField(order=50),
            "item_id": NativeField(order=60),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.commercial_guard_rule",
        "CommercialGuardRule",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "unit_revision_id": fixed(30),
            "currency": fixed(40),
            "numeric_revision_id": fixed(50),
            "valid_from": fixed(60),
            "valid_to": NativeField(order=70),
            "rule_kind": fixed(80),
            "amount": NativeField(order=90),
            "percentage": NativeField(order=100),
            "price_basis_quantity": fixed(110),
            "tax_basis": fixed(120),
            "estimate_kind": NativeField(order=130),
            "severity": fixed(140),
            "source_reference": fixed(150),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.discount_ceiling",
        "DiscountCeiling",
        {
            "row_version": fixed(10),
            "scope_id": fixed(20),
            "max_discount_pct": fixed(30),
            "valid_from": fixed(40),
            "valid_to": NativeField(order=50),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_commercial_policy",
        "ItemCommercialPolicy",
        {
            "row_version": fixed(10),
            "item_id": fixed(20),
            "free_sale_allowed": fixed(30),
            "valid_from": fixed(40),
            "valid_to": NativeField(order=50),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.tax_classification",
        "TaxClassification",
        {
            "jurisdiction": fixed(10),
            "code_system": fixed(20),
            "code": fixed(30),
            "item_kind": fixed(40),
            "description": fixed(50),
            "valid_from": fixed(60),
            "valid_to": NativeField(order=70),
            "source_reference": fixed(80),
            "source_url": fixed(90),
            "source_sha256": fixed(100),
            "row_version": fixed(110),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.tax_category",
        "TaxCategory",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.tax_rule",
        "TaxRule",
        {
            "source_reference": fixed(100),
            "source_url": fixed(110),
            "source_sha256": fixed(120),
            "code": fixed(10),
            "name": fixed(20),
            "tax_system": fixed(30),
            "jurisdiction": fixed(40),
            "item_kind": fixed(50),
            "treatment": fixed(60),
            "classification_scope": fixed(65),
            "tax_category_id": fixed(70),
            "is_active": fixed(80),
            "row_version": fixed(90),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.tax_rate_series",
        "TaxRateSeries",
        {
            "rule_id": fixed(10),
            "applicability": fixed(20),
            "row_version": fixed(30),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.tax_rate",
        "TaxRate",
        {
            "series_id": fixed(10),
            "valid_from": fixed(20),
            "valid_to": NativeField(order=30),
            "supersedes_id": NativeField(order=40),
            "source_reference": fixed(50),
            "source_url": fixed(60),
            "source_sha256": fixed(70),
            "row_version": fixed(80),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.tax_rate_component",
        "TaxRateComponent",
        {
            "rate_id": fixed(10),
            "component_key": fixed(20),
            "component": fixed(30),
            "kind": fixed(40),
            "percentage": NativeField(order=50),
            "amount": NativeField(order=60),
            "currency": NativeField(order=70),
            "unit_id": NativeField(order=80),
            "basis_quantity": NativeField(order=90),
            "rounding_mode": fixed(100),
            "position": fixed(110),
            "row_version": fixed(120),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.catalog_tax_scope",
        "CatalogTaxScope",
        {
            "owner_kind": fixed(10),
            "owner_id": fixed(20),
            "group_id": NativeField(order=30),
            "family_id": NativeField(order=40),
            "item_id": NativeField(order=50),
            "row_version": fixed(60),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.catalog_tax_binding",
        "CatalogTaxBinding",
        {
            "scope_id": fixed(10),
            "jurisdiction": fixed(20),
            "direction": fixed(30),
            "bundle": fixed(40),
            "mode": fixed(50),
            "classification_id": NativeField(order=60),
            "treatment": NativeField(order=70),
            "exemption_reason": NativeField(order=80),
            "tax_category_id": NativeField(order=90),
            "rule_id": NativeField(order=100),
            "item_kind": fixed(105),
            "valid_from": fixed(110),
            "valid_to": NativeField(order=120),
            "row_version": fixed(140),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_activation",
        "ItemActivation",
        {
            "item_id": fixed(10),
            "adoption_id": fixed(20),
            "activated_on": fixed(30),
            "source_version": fixed(40),
            "policy_generation": fixed(50),
            "preview_hash": fixed(60),
            "row_version": fixed(70),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_activation_source",
        "ItemActivationSource",
        {
            "activation_id": fixed(10),
            "entity_type": fixed(20),
            "entity_id": fixed(30),
            "entity_version": fixed(40),
            "row_version": fixed(50),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.item_inventory_profile",
        "ItemInventoryProfile",
        {
            "item_id": fixed(10),
            "base_unit_id": fixed(20),
            "template_revision_id": fixed(30),
            "identifier_profile_id": NativeField(order=40),
            "lot_tracking": fixed(50),
            "serial_tracking": fixed(60),
            "expiry_required": fixed(70),
            "manufacture_date_required": fixed(80),
            "shelf_life_days": NativeField(order=90),
            "minimum_remaining_life_days": NativeField(order=100),
            "issue_strategy": fixed(110),
            "valuation_method": fixed(120),
            "negative_stock_policy": fixed(130),
            "row_version": fixed(140),
        },
    )
)


# Job metadata exposes status and identity; domain payloads use protected previews.
_BULK_FIELDS = {
    "bulk_job": (
        "BulkJob",
        [
            "actor_user_id",
            "kind",
            "mode",
            "atomicity",
            "on_error",
            "state",
            "revision",
            "schema_version",
            "input_hash",
            "selection_digest",
            "policy_generation",
            "source_version",
            "record_count",
            "completed_count",
            "invalid_count",
            "expires_at",
            "row_version",
        ],
    ),
    "bulk_change_set": (
        "BulkChangeSet",
        [
            "job_id",
            "logical_key",
            "ordinal",
            "record_count",
            "action_hash",
            "state",
            "error_code",
            "row_version",
        ],
    ),
    "bulk_job_record": (
        "BulkJobRecord",
        [
            "job_id",
            "change_set_id",
            "logical_key",
            "ordinal",
            "resource",
            "action",
            "source_sheet",
            "source_row",
            "state",
            "error_code",
            "row_version",
        ],
    ),
    "bulk_change_set_effect": (
        "BulkChangeSetEffect",
        [
            "job_id",
            "change_set_id",
            "logical_key",
            "accepted_revision",
            "action_hash",
            "row_version",
        ],
    ),
    "bulk_job_dependency": (
        "BulkJobDependency",
        ["job_id", "parent_record_id", "child_record_id", "row_version"],
    ),
    "bulk_import_artifact": (
        "BulkImportArtifact",
        ["job_id", "content_type", "content_sha256", "byte_count", "expires_at", "row_version"],
    ),
}
for _entity, (_model_name, _keys) in _BULK_FIELDS.items():
    registry.register(
        EntityFields(
            "catalog." + _entity,
            _model_name,
            {key: NativeField(order=(index + 1) * 10) for index, key in enumerate(_keys)},
        )
    )

registry.register(
    EntityFields(
        "catalog.tax_rule_applicability",
        "TaxRuleApplicability",
        {
            "rule_id": fixed(10),
            "code_system": fixed(20),
            "code": fixed(30),
            "match_kind": fixed(40),
            "row_version": fixed(50),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.tax_release",
        "TaxRelease",
        {
            "change_reason": fixed(10),
            "business_date": fixed(20),
            "input_digest": fixed(30),
            "change_count": fixed(40),
            "row_version": fixed(50),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.tax_history_action",
        "TaxHistoryAction",
        {
            "resource": fixed(10),
            "target_id": fixed(20),
            "action": fixed(30),
            "previous_id": fixed(40),
            "previous_valid_to": fixed(50),
            "release_id": fixed(60),
            "reason": fixed(70),
            "business_date": fixed(80),
            "row_version": fixed(90),
        },
    )
)

registry.register(
    EntityFields(
        "catalog.warehouse",
        "Warehouse",
        {
            "code": fixed(10),
            "name": fixed(20),
            "kind": fixed(30),
            # System provisioning is a schema fact tied to the reserved codes; hiding it
            # would let a form present a built-in location as an ordinary one.
            "is_system": fixed(40),
            "is_active": fixed(50),
            "row_version": fixed(60),
            "department_id": NativeField(order=70),
            "timezone": NativeField(order=80),
            "address_line1": NativeField(order=90),
            "address_line2": NativeField(order=100),
            "city": NativeField(order=110),
            "postal_code": NativeField(order=120),
            "country_code": NativeField(order=130),
            "state_code": NativeField(order=140),
            "tax_registration_id": NativeField(order=150),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.company_warehouse_configuration",
        "CompanyWarehouseConfiguration",
        {
            "main_warehouse_id": fixed(10),
            "transit_warehouse_id": fixed(20),
            "default_sale_warehouse_id": NativeField(order=30),
            "default_purchase_warehouse_id": NativeField(order=40),
            "default_customer_return_warehouse_id": NativeField(order=50),
            "default_opening_warehouse_id": NativeField(order=60),
            "source_version": fixed(70),
            "row_version": fixed(80),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.warehouse_operation_policy_revision",
        "WarehouseOperationPolicyRevision",
        {
            "warehouse_id": fixed(10),
            "revision": fixed(20),
            "effective_from": fixed(30),
            "effective_to": fixed(40),
            # Every flag is fixed. These are the location's permissions, so a hidden one is
            # a permission the reviewer approving the policy never saw
            # (docs/catalog-warehouses.md §2).
            "allow_sale_issue": fixed(50),
            "allow_purchase_receipt": fixed(60),
            "allow_transfer_in": fixed(70),
            "allow_transfer_out": fixed(80),
            "allow_customer_return_receipt": fixed(90),
            "allow_supplier_return_issue": fixed(100),
            "allow_opening_stock": fixed(110),
            "allow_adjustment": fixed(120),
            "row_version": fixed(130),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.warehouse_group",
        "WarehouseGroup",
        {
            "code": fixed(10),
            "name": fixed(20),
            "is_active": fixed(30),
            "row_version": fixed(40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.warehouse_group_parent",
        "WarehouseGroupParent",
        {
            "group_id": fixed(10),
            "parent_group_id": NativeField(order=20),
            "valid_from": fixed(30),
            "valid_to": NativeField(order=40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.warehouse_group_assignment",
        "WarehouseGroupAssignment",
        {
            "warehouse_id": fixed(10),
            # Fixed: a rollup that cannot see which group a location reports to is a rollup
            # nobody can check (docs/catalog-warehouses.md §3).
            "group_id": fixed(20),
            "valid_from": fixed(30),
            "valid_to": NativeField(order=40),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.warehouse_bin",
        "WarehouseBin",
        {
            "code": fixed(10),
            "name": fixed(20),
            # A bin's location is its identity: `A1` means nothing without the godown it
            # sits in, and the code is only unique within one.
            "warehouse_id": fixed(30),
            "is_active": fixed(40),
            "row_version": fixed(50),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.item_warehouse_policy",
        "ItemWarehousePolicy",
        {
            "item_id": fixed(10),
            # The mode decides how the membership rows read: hiding it would leave a form
            # showing locations with no way to tell an allowlist from a baseline.
            "selection_mode": fixed(20),
            "default_sale_warehouse_id": NativeField(order=30),
            "default_purchase_warehouse_id": NativeField(order=40),
            "default_customer_return_warehouse_id": NativeField(order=50),
            "default_opening_warehouse_id": NativeField(order=60),
            "row_version": fixed(70),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.item_warehouse_permission",
        "ItemWarehousePermission",
        {
            "item_id": fixed(10),
            # Deniable on purpose, and the one field a scoped reader is restricted by: a
            # field policy denying it hides the whole entry from the policy read, so a
            # store manager cannot enumerate the company's other stores through a product
            # (docs/field-permissions.md §6).
            "warehouse_id": NativeField(order=20),
            "is_active": fixed(30),
            # Every flag is fixed, as on the location's own revision: a hidden one is a
            # permission the reviewer approving the policy never saw.
            "allow_sale_issue": fixed(40),
            "allow_purchase_receipt": fixed(50),
            "allow_transfer_in": fixed(60),
            "allow_transfer_out": fixed(70),
            "allow_customer_return_receipt": fixed(80),
            "allow_supplier_return_issue": fixed(90),
            "allow_opening_stock": fixed(100),
            "allow_adjustment": fixed(110),
            "row_version": fixed(120),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.item_replenishment_policy",
        "ItemReplenishmentPolicy",
        {
            "item_id": fixed(10),
            # The scope key, and the location reference the band applies at. The key is
            # never presented on its own: it carries the item-wide sentinel.
            "scope_warehouse_id": fixed(20),
            "warehouse_id": NativeField(order=30),
            "purchase_binding_id": fixed(40),
            # Quantities are fixed: every one of them shapes a suggested order, and a
            # hidden band is a band nobody reviewed.
            "safety_quantity": fixed(50),
            "reorder_quantity": fixed(60),
            "target_quantity": fixed(70),
            "min_order_quantity": fixed(80),
            "max_order_quantity": fixed(90),
            "order_multiple": fixed(100),
            "lead_time_days": NativeField(order=110),
            "is_active": fixed(120),
            "row_version": fixed(130),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.catalog_policy_release",
        "CatalogPolicyRelease",
        {
            # Every field is fixed. A release is the record a consumer and an auditor read
            # to answer "which policy is in force, and does what I enforce match it" — a
            # deniable field there would produce a release nobody could verify
            # (docs/catalog-warehouses.md §5).
            "revision": fixed(10),
            "effective_date": fixed(20),
            "published_at": fixed(30),
            "change_reason": fixed(40),
            "policy_generation": fixed(50),
            "source_version": fixed(60),
            "location_count": fixed(70),
            "default_count": fixed(80),
            "manifest_digest": fixed(90),
            "row_version": fixed(100),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.catalog_policy_consumer_ack",
        "CatalogPolicyConsumerAck",
        {
            # Also all fixed, and for a sharper reason: this row is the *only* evidence that
            # anything enforces a published policy. A tenant field policy that hid the
            # result or the reason would leave a reader unable to tell an enforced location
            # policy from a refused one — and the deactivation fence reads the same row.
            "release_id": fixed(10),
            "release_revision": fixed(20),
            "consumer": fixed(30),
            "aggregate": fixed(40),
            "aggregate_id": fixed(50),
            "enforced_revision": fixed(60),
            "result": fixed(70),
            "reason_code": fixed(80),
            "source_message_id": fixed(90),
            "acknowledged_at": fixed(100),
            "row_version": fixed(110),
        },
    )
)


registry.register(
    EntityFields(
        "catalog.manufacturing_route",
        "ManufacturingRoute",
        {"code": fixed(10), "name": fixed(20), "is_active": fixed(30), "row_version": fixed(40)},
    )
)
registry.register(
    EntityFields(
        "catalog.manufacturing_route_revision",
        "ManufacturingRouteRevision",
        {
            "route_id": fixed(10),
            "revision": fixed(20),
            "row_version": fixed(30),
            "status": fixed(40),
            "published_at": NativeField(order=50),
            "specification": fixed(60),
            "change_reason": fixed(70),
            "step_count": fixed(80),
        },
    )
)
registry.register(
    EntityFields(
        "catalog.manufacturing_route_step",
        "ManufacturingRouteStep",
        {
            "revision_id": fixed(10),
            "sequence": fixed(20),
            "operation_revision_id": fixed(30),
            "setup_minutes": fixed(40),
            "run_minutes": fixed(50),
            "lead_time_minutes": fixed(60),
            "time_basis": fixed(70),
            "quantity_basis": fixed(80),
        },
    )
)
