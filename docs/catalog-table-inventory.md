# Final Catalog table inventory

**Status:** Revised design list, 2026-09-19; **142 tables materialized through migration 0154**,
including reviewed native attributes, identifier/inventory/warranty/return/handling profiles with
product-type bindings, pricing, GST, bulk jobs, the stock-location definitions
(0132–0143) and the v1 completion phases — party/customer-type/customer-pricing projections,
price-level assignment/assignment-scope, sales channel + item_price_series channel FK,
identifier_type + identifier_namespace masters + widening of `item_barcode`, and
`compound_unit_component` (0144–0154); remaining implementation is the v1.1 rename of
`item_barcode` → `product_identifier` and the deferred BOM/promotions/governance rows.
**Scope:** Catalog database only. Base: 122 owned domain/job + 31 support = **153 tables**.
**Optional BOM:** 20 more owned tables; **173 total** (142 owned + 31 support) with the extension.
**Read with:** [Schema](catalog-schema.md),
[stock integration contract](catalog-inventory-integration.md), [complete pricing design](catalog-pricing-design.md),
[optional manufacturing design](catalog-manufacturing-design.md).

This is the final logical table inventory for the current Catalog proposal, not a claim that
all migrations exist. Initial Catalog revisions 0001-0006 cover outbox, processed_message,
idempotency_key, currency, country and state. Revisions 0007-0010 add units/packs, 0011 adds language, and 0012-0015 add custom uniqueness, sequences and typed scalar/member indexes. The list excludes other services' source tables and their replicated copies
of Catalog data. Schema/constraint review still occurs in C0 before implementation.

Customer/party source masters, actual stock, physical batches/devices, transfer/damage/count/
adjustment documents, product stock ledger, runtime coupons, sales and financial journals are
not Catalog tables. External references use minimal read-only projections; Catalog owns only
the customer-to-price-level mapping. Definition of a capability does not implement its runtime.

## 1. Products and classification

| Table | Description / purpose |
|---|---|
| `product_family` | Goods/service model shared by its SKUs. |
| `item` | Individual SKU or service offering used by commercial documents. |
| `simple_product_creation` | Durable single-Save request, reserved code, execution lease and native owner receipts; no stock balances. Added in 0218. |
| `item_group` | Primary group/subgroup master. |
| `item_group_parent` | Dated parent relationships preserving historical group hierarchy. |
| `family_group_assignment` | Dated primary-group assignment for a product family. |
| `category_scheme` | Independent classification axis with single/multiple membership rules. |
| `item_category` | Categories and subcategories within a classification scheme. |
| `family_category` | Family category memberships and primary choices. |
| `product_type` | Reusable native type such as phone, medicine or consultancy. |
| `product_type_revision` | Published type requirements and profile/attribute references. |
| `brand` | Brand and sub-brand hierarchy. |
| `brand_series` | Series or collections belonging to a brand. |
| `manufacturer` | Manufacturer identity as a Catalog master, not a supplier account. |
| `manufacturer_site` | Actual manufacturing plant or production site. |
| `brand_manufacturer` | Dated production relationships between brands and manufacturers. |
| `family_manufacturer` | Approved manufacturers/sites for a family. |
| `item_relationship` | Alternative, accessory, replacement and supersession links. |

## 2. Attributes and variants

| Table | Description / purpose |
|---|---|
| `attribute_definition` | Native typed product attribute definition. |
| `attribute_option` | Controlled typed choice for an attribute. |
| `attribute_set` | Reusable named attribute template. |
| `attribute_set_revision` | Published immutable version of an attribute template. |
| `attribute_set_member` | Template members, requiredness and variant eligibility. |
| `family_attribute` | Applicable family attributes and variant axes. |
| `family_attribute_option` | Allowed variant choices for a family. |
| `item_attribute_value` | Actual typed attribute values for a SKU. |
| `item_variant_key` | Canonical unique variant combination within a family. |

## 3. Units, packs and product identifiers

| Table | Description / purpose |
|---|---|
| `unit_of_measure` | Unit master with accepted quantity precision and increments. |
| `unit_conversion` | Exact conversion between compatible units. |
| `unit_tax_code` | Effective official unit-code mappings by jurisdiction. |
| `pack_type` | Packaging type such as box, strip, bottle or carton. |
| `item_unit_binding` | Stable SKU base/sale/purchase/pack unit identity. |
| `item_unit_revision` | Historical pack conversion and quantity-entry rules. |
| `compound_unit_component` | Components of supported compound-unit entry. |
| `item_barcode` | Product/pack barcodes, GTINs and part codes; widened v1 with `identifier_type_code`/`namespace_code` for non-barcode identifier types (v1.1 renames the table to `product_identifier`). |
| `identifier_type` | Mastered identifier-type codes (BARCODE, GTIN, MPN, SKU, …). |
| `identifier_namespace` | Mastered identifier namespaces grouping codes across the same type. |
| `identifier_profile` | Supported physical-identifier profile definition. |
| `identifier_profile_requirement` | Identifier types, required counts and slots, including multiple IMEIs. |

## 4. Product Configuration and reusable profiles

| Table | Description / purpose |
|---|---|
| `product_configuration_scope` | Typed company/type/group/family/SKU configuration owner. |
| `product_configuration_draft` | Editable proposed product configuration. |
| `product_configuration_revision` | Published configuration version and effective terms. |
| `product_pricing_policy` | Typed pricing requirements, unit/scope/recipe/source modes and defaults under Product Configuration. |
| `product_entry_option_policy` | Native enabled/disabled/optional/required product-entry controls. |
| `product_numeric_default` | Defaults for quantity/rate decimals, increments and price basis. |
| `product_configuration_adoption` | Pinned configuration/profile choices adopted by a SKU. |
| `product_configuration_adoption_source` | Which source populated each adoption row (bulk, native, inherited). |
| `catalog_default_profile` | Typed reusable creation defaults under Product Configuration. |
| `inventory_profile_template` | Reusable inventory/tracking/valuation default template. |
| `inventory_profile_template_revision` | Immutable published revision of an inventory template. |
| `warranty_policy` | Reusable warranty-policy identity. |
| `warranty_policy_revision` | Published warranty duration, triggers and supported terms. |
| `return_policy` | Reusable product return-policy identity. |
| `return_policy_revision` | Published return-window and native eligibility conditions; no disposition or refund execution. |
| `return_policy_condition` | Supported conditions attached to a return-policy revision. |
| `handling_profile` | Reusable product handling/storage profile. |
| `handling_profile_revision` | Published handling requirements and measurement bounds. |

## 5. Warehouses, groups and product inventory controls

| Table | Description / purpose |
|---|---|
| `warehouse` | Physical stores/godowns, permanent Main and protected internal-transit location definitions. |
| `warehouse_group` | Non-stockholding region, zone or other warehouse grouping. |
| `warehouse_group_parent` | Dated warehouse-group hierarchy without cycles. |
| `warehouse_group_assignment` | Dated assignment of a physical warehouse to one primary reporting group. |
| `company_warehouse_configuration` | Permanent Main identity and company activity defaults. |
| `warehouse_operation_policy_revision` | Published sale/purchase/transfer/return/opening/adjustment controls. |
| `warehouse_bin` | Optional bins/racks within an actual warehouse. |
| `item_warehouse_policy` | SKU location-selection mode and activity defaults. |
| `item_warehouse_permission` | Explicit restrictive SKU/location/operation permissions. |
| `item_inventory_profile` | SKU stock, batch, expiry, serial and requested valuation configuration. |
| `item_replenishment_policy` | Default/location safety stock, reorder targets, MOQ and ordering multiples. |
| `item_supplier_term` | SKU supplier references and purchasing terms using external party identity. **Blocked:** no table, and none until Billing publishes an authoritative party projection — a supplier reference to nothing verifiable is a free-text field pretending to be a foreign key. |

## 6. Prices and commercial policies

| Table | Description / purpose |
|---|---|
| `sales_channel` | Native channel master for price and promotion context. |
| `price_level` | PRICE1, optional PRICE2/PRICE3 and further configurable levels. |
| `price_plan` | Currency-specific SALE, PURCHASE or REFERENCE_RETAIL book with immutable published terms. |
| `company_pricing_policy` | Dated default level and explicit missing-price fallback. |
| `price_level_assignment_scope` | Stable customer/customer-type mapping scope against external identity. |
| `price_level_assignment` | Dated assignment of a customer or pricing type to a price level. |
| `item_price_scope` | Stable SKU, verified lot or stock-declaration pricing subject; no physical stock ownership. |
| `item_price_series` | Stable purpose/audience/channel/unit/stock-scope price-history identity. |
| `item_price_numeric_revision` | Dated SKU/unit/currency rate precision and increment rules. |
| `item_price` | Published price history and declared per-N quantity basis. |
| `item_price_tier` | Quantity-based volume-price slabs. |
| `purchase_price_term` | Supplier gross quote and unconditional trade discount explaining the net purchase reference. |
| `item_reference_cost` | Dated standard, replacement or service cost estimates; never actual inventory cost. |
| `item_price_formula` | Typed MRP/cost markup or margin recipe with source and rounding requirements. |
| `item_commercial_policy` | SKU participation/free-sale policy; monetary floors belong to commercial_guard_rule. |
| `commercial_policy_scope` | Company/group/family/SKU scope for commercial restrictions. |
| `commercial_guard_rule` | Dated fixed floors/ceilings and minimum-margin/markup requirements with explicit source/basis. |
| `discount_ceiling` | Effective maximum combined discount restrictions. |
| `item_mrp` | Product/pack/jurisdiction MRP declaration history and future defaults; cannot relabel physical stock. |
| `item_price_draft` | Editable staged price row before publication. |

## 7. Tax definitions

| Table | Description / purpose |
|---|---|
| `tax_category` | Native tax applicability category, distinct from merchandising category. |
| `tax_classification` | Jurisdiction-specific goods/service classification and validity. |
| `tax_rule` | Named native tax-rule identity. |
| `tax_rate_series` | Stable applicability context for tax-rate history. |
| `tax_rate` | Effective published tax-rate definition. |
| `tax_rate_component` | Typed components and calculation dependencies within a rate. |
| `catalog_tax_scope` | Company/group/family/SKU tax-configuration scope. |
| `catalog_tax_binding` | Dated inheritance, overrides, exemptions and explicit-rule requirements. |
| `tax_rule_applicability` | Applicability rows narrowing when a tax rule applies. |
| `tax_history_action` | Dated changes recorded against a tax rate/rule history. |
| `tax_release` | Published tax bundle release evidence. |
| `item_activation` | Per-item activation-state row. |
| `item_activation_source` | Which source made an item active (bulk, product, native). |

## 8. Governance, aliases and policy publication

| Table | Description / purpose |
|---|---|
| `master_alias` | Alternative names/codes resolving to an existing Catalog master. |
| `master_external_key` | External source identifiers for exact matching and import deduplication. |
| `master_change_job` | Reviewed hierarchy/default/master changes and their outcomes. |
| `catalog_hierarchy_state` | Stable concurrency boundary for group and assignment changes. |
| `catalog_policy_state` | Configuration generation invalidating stale impact previews. |
| `catalog_policy_release` | Complete published configuration/dependency release. |
| `catalog_policy_consumer_ack` | Trusted external-consumer activation/rejection evidence; not a stock balance. |

## 9. Schemes, promotions and coupon-program definitions

| Table | Description / purpose |
|---|---|
| `campaign` | Stable grouping for related promotions and shared definitions. |
| `campaign_draft` | Editable campaign proposal. |
| `campaign_revision` | Published campaign terms and schedule. |
| `promotion` | Stable automatic offer, scheme or coupon-triggered promotion identity. |
| `promotion_draft` | Editable promotion proposal. |
| `promotion_revision` | Published immutable promotion terms. |
| `promotion_condition_group` | Bounded AND/OR grouping of native conditions. |
| `promotion_condition` | Typed eligibility operand/reference/range; no executable expression. |
| `promotion_target` | Explicit native inclusion/exclusion target. |
| `target_manifest` | Reviewed target selection and source-version evidence. |
| `promotion_benefit` | Percent/fixed/bundle/free-quantity/gift benefit definition. |
| `promotion_sku_target` | Scoped exact SKU target in the bounded same-item publication subset. |
| `promotion_price_level_target` | Scoped eligible price level in the bounded same-item publication subset. |
| `benefit_component` | Qualifying/reward components for multi-part schemes. |
| `promotion_stack_policy` | Immutable versioned ordered benefit selection and combination policy. |
| `promotion_stack_group` | Ordered group within one published stack policy revision. |
| `promotion_stack_permission` | Scoped, explicit allowed interaction between two groups in one policy. |
| `promotion_limit_definition` | Stable count/quantity/budget limit definitions; no consumed counters. |
| `coupon_program` | Coupon distribution and eligibility definition linked to a promotion. |
| `coupon_program_revision` | Published code-mode, binding, validity and policy terms; no issued codes. |

## 10. Catalog bulk operations

| Table | Description / purpose |
|---|---|
| `bulk_job` | Catalog-owned import/update request, reviewed settings and progress. |
| `bulk_job_record` | Staged source record, normalized action and validation result. |
| `bulk_change_set` | Bounded dependent changes committed in one Catalog transaction. |
| `bulk_change_set_effect` | Durable evidence preventing duplicate execution after retries. |
| `bulk_job_dependency` | Prerequisite graph between staged changes. |
| `bulk_import_artifact` | Private bounded source/error/result artifact with retention. |

## 11. Read-only external source projections in Catalog

| Table | Description / purpose |
|---|---|
| `inventory_lot_projection` | Minimal verified Billing lot identity for pricing references; no quantity/cost or master CRUD. |
| `stock_price_declaration_projection` | Read-only physical pack/MRP declaration evidence and lot/unit-context linkage from Billing. |
| `party_projection` | Minimal authoritative external party identity/status for supplier and other references. |
| `customer_type_projection` | External customer pricing-type identity/status. |
| `customer_pricing_projection` | External customer role/type membership needed for price-level mapping. |
| `company_projection` | Authoritative company scope and required common configuration. |
| `company_feature_projection` | Authoritative company capabilities and use restrictions. |
| `custom_field_definition_projection` | Identity-owned field definitions copied for local validation. |
| `field_config_projection` | Identity-owned field presentation configuration. |
| `field_policy_projection` | Identity-owned field-level access rules. |
| `fiscal_year_projection` | Optional authoritative fiscal-year source for custom-number reset. |
| `user_projection` | Minimal authoritative user status for original-actor field policy; no credentials or PII. |
| `user_group_projection` | Current group activity for field-policy subject resolution. |
| `user_group_member_projection` | Authoritative user/group relationships; gateway-supplied group IDs do not override this source. |
| `role_projection` | Minimal active/inactive role identity, including published system roles. |
| `role_assignment_projection` | Dated, scoped subject/role assignments for field-policy evaluation. |
| `source_event_buffer` | Authenticated durable changes, exact payload digest and contiguous versions while snapshots bootstrap or gaps recover. |
| `projection_checkpoint` | Source snapshot/replay barrier, freshness and readiness. |

## 12. Catalog custom-field persistence

| Table | Description / purpose |
|---|---|
| `custom_field_value_index` | Typed searchable custom-field values for Catalog entities. |
| `custom_field_value_member` | Multi-select membership index without multiplied query rows. |
| `custom_field_unique_claim` | Transactional logical-field uniqueness claims. |
| `custom_field_sequence` | Scoped/reset-cycle auto-number allocation for Catalog entities. |
| `field_index_state` | Custom-field index generation and query readiness. |
| `field_rebuild_job` | Resumable Catalog custom-index rebuilding. |
| `custom_field_adoption` | Per-entity adoption evidence for tenant custom fields. |

## 13. Shared platform tables materialized in Catalog

| Table | Description / purpose |
|---|---|
| `outbox` | Events/jobs recorded atomically with Catalog mutations. |
| `processed_message` | Deduplication of consumed source events. |
| `idempotency_key` | Safe replay of Catalog API requests. |
| `country` | Shared country reference data. |
| `state` | Shared state/province reference data. |
| `currency` | Shared currency reference data. |
| `language` | Shared language reference data. |

## 14. Optional BOM and manufacturing definitions

These 20 tables are added only by the selected M0-M4 extension. Shared units, products,
attributes, warehouses, reference costs, audit/outbox, jobs and releases are reused. This is
a definition/estimate module; no production execution tables are included.

| Table | Description / purpose |
|---|---|
| `product_manufacturing_policy` | Typed Product Configuration revision child controlling optional BOM structure, estimation and change requirements. |
| `item_manufacturing_profile` | Dated SKU make/buy eligibility, manufacturing roles and default-BOM requirement; preserves goods/service and inventory boundaries. |
| `manufacturing_operation` | Reusable named operation master without machines, capacity or actual work records. |
| `manufacturing_operation_revision` | Reviewed operation specifications and optional service reference with immutable published content. |
| `manufacturing_route` | Stable reusable route identity for an ordered manufacturing definition. |
| `manufacturing_route_revision` | Versioned route with setup/run/batch conventions; no live schedule. |
| `manufacturing_route_step` | Ordered steps pinning operation revisions and estimated timing/batch requirements. |
| `bom` | Stable named manufacture/phantom BOM identity; supports alternative definitions. |
| `bom_draft` | Version-checked authoring document staged for full validation and publication. |
| `bom_revision` | Immutable published BOM specification and exact product/unit/route/dependency references. |
| `bom_component` | Distinct material/subassembly/phantom input lines, quantities, losses and operation requirements. |
| `bom_component_substitute` | Explicit approved per-line alternate SKUs, replacement ratios, validity and authorization constraints. |
| `bom_output` | Primary, co-product, by-product and recoverable-scrap output definitions and expected quantities. |
| `bom_assignment` | Dated exact-SKU/location applicability and deterministic default-revision selection. |
| `bom_location_default` | Issue/output/WIP/scrap location hints subject to real location and consumer policies. |
| `bom_quality_requirement` | Native input/output/step inspection specifications; excludes measurements and quality-release execution. |
| `bom_cost_policy` | Revision-owned estimate source, currency/basis and multi-output allocation policy. |
| `bom_cost_charge` | Explicit operation/service/setup/overhead estimate charges with nonrecursive calculation bases. |
| `bom_cost_estimate` | Immutable manufacturing-estimate request/result and complete source/dependency manifest. |
| `bom_cost_estimate_line` | Traceable component/operation/charge/output estimate detail with quantities, sources and reconciled allocations. |

## Ownership exclusions

| Required capability | Owning API | Catalog contribution |
|---|---|---|
| Customer/party/supplier master and customer-type membership | Billing | Read-only references and dated price-level assignments |
| Opening stock and physical lots/serials/IMEIs | Billing | Product tracking/unit/location definitions |
| Store/bin transfers and transit discrepancies | Billing | Locations/groups/flags, immutable product profiles and consumer acknowledgement |
| Damaged stock, quarantine, write-down and disposal | Billing | Tracking/handling/return/location policy definitions |
| Stock adjustment and physical-count/recount | Billing | Exact unit rules and appropriate native product/location configuration |
| Product stock ledger, cost and inventory balances | Billing; Reports for analytical projections | Stable product identifiers and source histories |
| Basket quotes, issued coupons, holds, usage and redemption | Billing | Promotion/program/limit/stack definitions |
| Company capabilities and custom-field definitions/policies | Identity | Local projections and policy enforcement |
| Production/work orders, WIP, consumption/output, subcontract custody and actual manufacturing cost | Billing/inventory execution, under a separate plan | Optional BOM/route/specification revisions and estimates |
| Work centres, capacity, actual inspections and batch genealogy | Execution owner; Reports for large analytics | Operation/quality definitions and protected dependency manifests only |

There is no Catalog party/customer master, stock-transfer table, damage-balance table,
physical-count table or product-ledger table. In particular, `product_identifier` identifies
the product/pack; a specific phone's two IMEIs belong to Billing's physical-unit identity.

## Decision log

- 2026-11-04: Removed location from the planned price-series identity; regular
  pricing has no warehouse override. Stock locations and valuation retain their own models.

- 2026-09-11: Materialized four planned unit/pack tables in revisions 0007-0010. Total proposal remains 147 base plus 20 optional; ten tables now have matching Catalog models and migrations.

- 2026-09-11: Materialized six shared support/reference tables in the independent Catalog chain;
  147 base/167 extended remains the planned total, not the implemented table count.

- 2026-09-11: Added 20 optional BOM/configuration/routing/estimate tables; 147 base or 167
  including manufacturing definitions. No production-order, WIP, genealogy or actual-cost source table added.

- 2026-09-11: Added six Catalog pricing/configuration tables and two minimal external projections,
  for 147 total. Price scopes cover units/lots/declarations while actual cost and physical source
  records remain in Billing. Monetary minimum-price authority is commercial_guard_rule.

- 2026-09-11: Finalized the current Catalog-only inventory after the explicit ownership correction.
  Added warehouse grouping, immutable inventory-template revisions, typed promotion conditions,
  minimal party/fiscal projections and trusted consumer acknowledgement.
- 2026-09-11: Kept operational stock/financial design in the separate integration contract.
  Removed the earlier implication that Billing tables would be implemented as part of Catalog.

- 2026-09-11: Source implementation required five explicit subject relation projections and
  one durable event buffer missing from the earlier logical inventory. Base inventory is now
  153 (122 owned + 31 support), or 173 with optional BOM. Catalog has 27 model/migration pairs;
  these source tables do not add Identity or Billing authoring to Catalog.
