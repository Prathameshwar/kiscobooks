"""Exact audit routes; complete domain releases have independent future contracts."""

AUDIT_EVENTS = frozenset(
    {
        "catalog.company_product_authoring_configuration.create",
        "catalog.company_product_authoring_configuration.update",
        "catalog.simple_product_creation.create",
        "catalog.simple_product_creation.revise",
        "catalog.simple_product_creation.complete",
        *(f"catalog.advanced_product_draft.{action}" for action in ("create", "update", "delete")),
        *(f"catalog.advanced_product_creation.{action}" for action in ("create", "update")),
        "catalog.stock_source_fence.acquire",
        "catalog.stock_source_fence.release",
        *(
            f"catalog.promotion_limit_definition.{action}"
            for action in ("create", "update", "activate", "deactivate")
        ),
        *(
            f"catalog.promotion_limit_revision.{action}"
            for action in ("create", "update", "publish")
        ),
        *(
            f"catalog.{entity}.{action}"
            for entity in (
                "promotion_stack_draft",
                "promotion_stack_draft_group",
                "promotion_stack_draft_permission",
                "promotion_stack_policy",
                "promotion_stack_group",
                "promotion_stack_permission",
            )
            for action in ("create", "update", "publish")
        ),
        *(f"catalog.bom.{action}" for action in ("create", "update", "activate", "deactivate")),
        *(f"catalog.bom_draft.{action}" for action in ("create", "update", "publish")),
        *(f"catalog.bom_revision.{action}" for action in ("publish", "retire")),
        *(
            f"catalog.{entity}.{action}"
            for entity in ("bom_component", "bom_output")
            for action in ("create", "update", "publish")
        ),
        *(f"catalog.bom_assignment.{action}" for action in ("create", "update", "deactivate")),
        *(
            f"catalog.manufacturing_route.{action}"
            for action in ("create", "update", "activate", "deactivate")
        ),
        *(
            f"catalog.manufacturing_route_revision.{action}"
            for action in ("create", "update", "publish", "retire")
        ),
        *(
            f"catalog.manufacturing_operation.{action}"
            for action in ("create", "update", "activate", "deactivate")
        ),
        *(
            f"catalog.manufacturing_operation_revision.{action}"
            for action in ("create", "update", "publish", "retire")
        ),
        "catalog.custom_field_adoption.adopt",
        "catalog.item_regulatory_classification.create",
        "catalog.item_regulatory_classification.update",
        "catalog.bulk_job.export",
        *(
            f"catalog.{entity}.{action}"
            for entity in (
                "bulk_job",
                "bulk_change_set",
                "bulk_job_record",
                "bulk_change_set_effect",
                "bulk_job_dependency",
                "bulk_import_artifact",
                "tax_rule_applicability",
                "tax_release",
                "tax_history_action",
                "tax_classification",
                "tax_category",
                "tax_rule",
                "tax_rate_series",
                "tax_rate",
                "tax_rate_component",
                "catalog_tax_scope",
                "catalog_tax_binding",
                "item_activation",
                "item_activation_source",
                "item_inventory_profile",
                "item_stock_choice",
                "price_level",
                "price_plan",
                "company_pricing_policy",
                "item_price_scope",
                "item_price_numeric_revision",
                "item_price_series",
                "item_price_draft",
                "item_price",
                "item_price_tier",
                "purchase_price_term",
                "item_reference_cost",
                "item_mrp",
                "item_price_formula",
                "commercial_policy_scope",
                "commercial_guard_rule",
                "discount_ceiling",
                "item_commercial_policy",
            )
            for action in ("create", "update", "publish", "close")
        ),
        # A future tax definition withdrawn from its history keeps its row; the row records
        # `withdraw` and a `tax_history_action` row records the reason.
        *(
            f"catalog.{entity}.withdraw"
            for entity in ("tax_classification", "tax_rate", "catalog_tax_binding")
        ),
        *(
            f"catalog.{entity}.{action}"
            for entity in (
                "unit_of_measure",
                "pack_type",
                "item_group",
                "category_scheme",
                "item_category",
                "brand",
                "manufacturer",
                "brand_series",
                "manufacturer_site",
                "product_type",
                "attribute_definition",
                "attribute_option",
                "attribute_set",
                "identifier_profile",
                "inventory_profile_template",
                "warranty_policy",
                "return_policy",
                "handling_profile",
                "warehouse",
                "warehouse_group",
                "warehouse_bin",
                # v1 completion — sales_channel and the two identifier masters ride the same
                # create/update/activate/deactivate CRUD as the other classification masters.
                "sales_channel",
                "identifier_type",
                "identifier_namespace",
            )
            for action in ("create", "update", "activate", "deactivate")
        ),
        # The location configuration is a singleton: it is provisioned once and then only
        # repointed, so it has no lifecycle actions of its own.
        "catalog.company_warehouse_configuration.create",
        "catalog.company_warehouse_configuration.update",
        # An operation policy has no draft to publish: a revision is written already in force,
        # so the audited actions are the row's own — `create` for the new revision, `update`
        # for the predecessor whose window it closes.
        "catalog.warehouse_operation_policy_revision.create",
        "catalog.warehouse_operation_policy_revision.update",
        # A product's location policy is stated whole, so one PUT writes a `create` for a row
        # newly named and an `update` for one whose flags changed or that the request dropped.
        # There is no `deactivate`: retirement is an `update` of `is_active` on a row the
        # caller restated by omission, not a lifecycle action aimed at that row.
        *(
            f"catalog.{entity}.{action}"
            for entity in (
                "item_warehouse_policy",
                "item_warehouse_permission",
                "item_replenishment_policy",
            )
            for action in ("create", "update")
        ),
        # A release is written once and never edited, so `publish` is its only action — the
        # word matters here: the audited fact is that a reviewer delivered this policy, not
        # that a row appeared.
        "catalog.catalog_policy_release.publish",
        # An acknowledgement is a trusted consumer's claim, ingested from a signed event:
        # `create` when a consumer first speaks about a release, `update` when it advances
        # what it enforces. There is no user action here at all, which is why these two carry
        # no `actor_user_id` (docs/audit.md §5.2, docs/catalog-warehouses.md §5).
        "catalog.catalog_policy_consumer_ack.create",
        "catalog.catalog_policy_consumer_ack.update",
        *(
            f"catalog.{entity}.{action}"
            for entity in ("master_alias", "master_external_key")
            for action in ("create", "activate", "deactivate")
        ),
        *(
            f"catalog.{entity}.{action}"
            for entity in ("product_family", "item")
            for action in ("create", "update")
        ),
        "catalog.product_configuration_scope.create",
        "catalog.product_configuration_scope.update",
        "catalog.product_configuration_scope.publish",
        "catalog.product_configuration_draft.create",
        "catalog.product_configuration_draft.update",
        "catalog.product_configuration_draft.publish",
        "catalog.product_configuration_revision.create",
        "catalog.product_configuration_revision.update",
        "catalog.product_configuration_revision.publish",
        "catalog.product_entry_option_policy.create",
        "catalog.product_entry_option_policy.update",
        "catalog.product_entry_option_policy.publish",
        "catalog.product_numeric_default.create",
        "catalog.product_numeric_default.update",
        "catalog.product_numeric_default.publish",
        "catalog.catalog_default_profile.create",
        "catalog.catalog_default_profile.update",
        "catalog.catalog_default_profile.publish",
        "catalog.product_pricing_policy.create",
        "catalog.product_pricing_policy.update",
        "catalog.product_pricing_policy.publish",
        "catalog.family_group_assignment.create",
        "catalog.family_group_assignment.update",
        "catalog.family_group_assignment.close",
        "catalog.family_category.create",
        "catalog.family_category.update",
        "catalog.family_category.close",
        "catalog.family_manufacturer.create",
        "catalog.family_manufacturer.update",
        "catalog.family_manufacturer.close",
        "catalog.family_attribute.create",
        "catalog.family_attribute.update",
        "catalog.family_attribute.close",
        "catalog.family_attribute_option.create",
        "catalog.family_attribute_option.update",
        "catalog.family_attribute_option.close",
        "catalog.item_attribute_value.create",
        "catalog.item_attribute_value.update",
        "catalog.item_attribute_value.close",
        "catalog.item_variant_key.create",
        "catalog.item_variant_key.update",
        "catalog.item_variant_key.close",
        "catalog.item_unit_binding.create",
        "catalog.item_unit_binding.update",
        "catalog.item_unit_binding.close",
        "catalog.item_unit_revision.create",
        "catalog.item_unit_revision.update",
        "catalog.item_unit_revision.close",
        "catalog.item_barcode.create",
        "catalog.item_barcode.update",
        "catalog.item_barcode.close",
        "catalog.product_configuration_adoption.create",
        "catalog.product_configuration_adoption.update",
        "catalog.product_configuration_adoption.close",
        "catalog.product_configuration_adoption_source.create",
        "catalog.product_configuration_adoption_source.update",
        "catalog.product_configuration_adoption_source.close",
        "catalog.unit_conversion.create",
        "catalog.unit_tax_code.create",
        "catalog.unit_tax_code.close",
        "catalog.item_group.move",
        "catalog.brand.move",
        "catalog.brand_manufacturer.create",
        "catalog.brand_manufacturer.close",
        "catalog.product_type_revision.create",
        "catalog.product_type_revision.update",
        "catalog.product_type_revision.publish",
        "catalog.attribute_set_revision.create",
        "catalog.attribute_set_revision.update",
        "catalog.attribute_set_revision.publish",
        "catalog.handling_profile_revision.create",
        "catalog.handling_profile_revision.update",
        "catalog.handling_profile_revision.publish",
        "catalog.return_policy_revision.create",
        "catalog.return_policy_revision.update",
        "catalog.return_policy_revision.publish",
        "catalog.warranty_policy_revision.create",
        "catalog.warranty_policy_revision.update",
        "catalog.warranty_policy_revision.publish",
        "catalog.inventory_profile_template_revision.create",
        "catalog.inventory_profile_template_revision.update",
        "catalog.inventory_profile_template_revision.publish",
        "catalog.item_category.move",
        "catalog.item_group_parent.create",
        "catalog.item_group_parent.close",
        "catalog.warehouse_group.move",
        "catalog.warehouse_group_parent.create",
        "catalog.warehouse_group_parent.close",
        # A location's primary group is the location's own dated relation, so the membership
        # row records `create`/`close` and the location records that it was reassigned.
        "catalog.warehouse.assign",
        "catalog.warehouse_group_assignment.create",
        "catalog.warehouse_group_assignment.close",
        *(
            f"catalog.field_rebuild_job.{action}"
            for action in ("start", "cancel", "chunk", "cleanup", "failed")
        ),
        # Background tax impact reports: requested, advanced per chunk, then invalidated by a
        # policy change or stopped by a refused proof or invalid release.
        *(
            f"catalog.tax_impact_review.{action}"
            for action in ("start", "chunk", "stale", "failed")
        ),
    }
)


AUDIT_EVENTS = AUDIT_EVENTS | frozenset(
    f"catalog.import_job.{action}" for action in ("create", "update", "export", "cleanup")
)


def audit_event(entity: str, action: str) -> str:
    """An unknown command cannot commit an audit event the publisher will never select."""
    event = entity + "." + action
    if event not in AUDIT_EVENTS:
        raise ValueError("unregistered Catalog audit event")
    return event
