# Catalog schema and API contracts

Current Simple Product delivery (2026-11-04): see [ready on Save](simple-product-ready-plan.md), [Simple imports](simple-product-import-plan.md) and [batch creation](simple-product-batch-opening-plan.md). Catalog owns creation progress, product definitions, GST and prices; Vouchers numbers and posts openings through Accounting. Local Catalog head is 0221 (184 tables); Accounting head is 0235. Batch additions retain an immutable product tracking choice, verified lot price scopes and Accounting-owned initial physical MRP. Older proposal status below is historical.

**Ownership amendment, 2026-10-10:** Under the [Vouchers plan](vouchers-plan.md), future
Billing/Payments APIs are replaced by Vouchers workflows and Accounting posting authority.
Accounting is the party source; stock/value posting there remains proposed. Older Billing
ownership below is superseded by that mapping. This changes the plan, not existing schema,
source-service identifiers, consumer allowlists or event contracts. Payroll/HR is excluded.

**Status:** Working Catalog schema: 130 tables through 0143, including native pricing, GST,
activation, six private bulk-job tables and the twelve stock-location definition tables
(0132–0143). Native MySQL 9.6 verifies model parity and the complete
upgrade/downgrade/upgrade chain.
**Bulk administration:** See [API, storage and recovery](catalog-v15-api.md).

**Generic tax templates, 2026-10-31:** Catalog 0215 adds immutable
`tax_rule.classification_scope VARCHAR(8) NOT NULL DEFAULT 'SPECIFIC'`, constrained
to `SPECIFIC`/`ANY`. Existing classification restrictions retain their meaning.
Explicitly selected generic GST templates use `ANY`; a product still needs its
HSN/SAC classification, kind and treatment. Empty specific applicability still
blocks completion. Online downgrade refuses while generic templates exist.
See [company tax defaults](company-tax-defaults.md) for provisioning and backfill.

**Adoption schema amendment, 2026-10-30:** Catalog 0214 adds non-null
`product_configuration_adoption.resolution_version` with server default 1.
Existing adoption records retain version 1 semantics. Native reviewed adoption
and activation write version 2 to preserve Company-only precedence. This field
is server controlled and protected by native field policy; unsupported versions
fail closed. No historical rows are rewritten. Apply this additive revision
before deploying the matching Catalog API. Downgrade requires online validation
and is refused when any version other than 1 exists; removing the marker would
reinterpret retained pins. Offline downgrade is intentionally unavailable.

**Schema amendment, 2026-10-30:** Catalog 0211-0213 remove `source_reference`
from `catalog_tax_binding`, `item_price_draft` and `item_price`. The product
creation tax/price note is permanently retired. No replacement text is collected
or synthesized. Official tax definitions retain their evidence columns; scoped
IDs, amounts, dates, publication lineage and immutable audit history remain.
Downgrade recreates non-null columns with empty defaults for compatibility but
cannot reconstruct deleted text. Recover old notes from a pre-upgrade backup.
Restore that text before reverting to an API release requiring non-empty notes;
column-shape rollback alone does not restore old price-definition validation.
**Table inventory:** [153 base Catalog tables + 20 optional BOM tables = 173 with the extension](catalog-table-inventory.md).
**V1 selection:** [Per-company products/services, prices and India GST](catalog-v1-scope.md).
The inventory below describes the full design; it is not a requirement to build all 173 tables for v1.
**External stock contract:** [Transfers, damage, counts, adjustments and product ledger](catalog-inventory-integration.md).
**Ownership:** Customer/party source and operational stock/financial APIs remain Billing-owned and outside Catalog implementation.
**Companions:** [Product rules](catalog-product-design.md).
**Bulk and pricing contract:** [Workflows, modes and examples](catalog-bulk-pricing.md).
**Price/cost model:** [Product, unit, batch, MRP, formulas and guards](catalog-pricing-design.md).
**Promotion schema and workflows:** [Schemes, coupons, holds and redemption](catalog-promotions.md).
**Product Configuration and numeric schema:** [Defaults, overrides and precision](catalog-product-configuration.md).
**Warehouse contract:** [Main, location policies and stock transfers](catalog-warehouses.md).

## 1. Database conventions

Use the existing platform mixins and naming: singular tables, UUIDv7 BINARY(16) IDs,
tenant_id, UTC DATETIME(6) audit timestamps, DATE business dates, VARCHAR validated enums,
and row_version on mutable aggregates. Money and quantities use DECIMAL(19,4); money has
an explicit currency. Percentages and exact conversion numerator/denominator are not money.
Use positive BIGINT rational terms with overflow checks and arbitrary-precision intermediate
arithmetic; validate representability before persisting converted quantities.

Company-owned rows carry company_id. Scope-check every parent; enforce same-company
composite FKs/unique parent keys locally where feasible. Cross-service IDs reference local
projections, never another database. Master codes are bounded strings, normalized explicitly;
barcode/serial values preserve leading zeros and use documented canonical/binary equality.
Referenced rows are retained. One lifecycle mechanism per entity.

Published revisions and posting snapshots preserve history. expected_version guards
updates; domain/date/stock operations lock stable aggregate parents in canonical order.
Uniqueness is enforced by constraints/claims, not a check-then-insert race.

Money, price, unit, tracking, tax and stock-control fields are native columns/child rows.
JSON is reserved for descriptive custom values, immutable transport/document snapshots
and non-queryable job payloads; query-critical dimensions stay typed and indexed.
Small bounded enum sets in native immutable revision documents are also permitted when
the native schema validates every value and no SQL filtering uses their contents; see the
[commercial revision storage decision](catalog-commercial-masters-api.md).

## 2. Catalog tables and key constraints

All tables below include tenant/company scope and audit fields where applicable.
An item is a SKU; a product_family is its descriptive and variant-definition parent.

### Product, classification and attributes

| Table | Essential fields | Constraints / lifecycle |
|---|---|---|
| item_group | code, name, allowed_kind, custom_fields, row_version | Unique company/code; is_active; parent belongs to dated edge table; subgroup uses the same master |
| item_group_parent | group_id, parent_group_id?, valid_from/to | One parent/root per date, same company; reject overlapping edges, cycles and depth >8 over every affected date interval |
| category_scheme | code, name, membership_mode single/multiple | Unique company/code; is_active; independent classification axis |
| item_category | scheme_id, code, name, parent_id?, custom_fields, row_version | Unique company/scheme/code; acyclic same-scheme tree; is_active |
| product_type; product_type_revision | code/name/kind/custom_fields on master; revision, allowed dimensions/modes, attribute_set_revision_id, inventory_template_revision_id, warranty_revision_id, return_policy_revision_id and handling_revision_id on revision | Unique company/code and type/revision; master is_active; published requirements immutable and code-validated |
| brand | code, name, parent_brand_id?, optional owner-party reference, custom_fields | Unique company/code; same-company acyclic sub-brand hierarchy; is_active; no tax inheritance through brand |
| manufacturer | code, name, optional party reference, custom_fields | Unique company/code; is_active; manufacturer is not a supplier account |
| brand_series | brand_id, code, name | Unique brand/code; optional series grouping; is_active |
| brand_manufacturer | brand_id, manufacturer_id, production_role, valid_from/to | Many-to-many production relationship; does not assert legal brand ownership |
| manufacturer_site | manufacturer_id, code, country/state, name | Unique manufacturer/code; is_active; actual production site, not a second supplier account |
| product_family | code, name, kind GOODS/SERVICE, product_type_revision_id, brand_id?, series_id?, model_code?, description?, custom_fields | Unique company/code; status draft/active/discontinued; group/category relationships are explicit below |
| family_group_assignment | family_id, group_id, valid_from/to | One primary group per date; required on activation, real General default available; family lock |
| family_category | family_id, scheme_id, category_id, is_primary | Unique family/category; enforce scheme cardinality and at most one primary per scheme |
| family_manufacturer | family_id, manufacturer_id, site_id?, role, valid_from/to | Approved product sources; same manufacturer/site; actual receipt producer stored on lot |
| item | family_id, sku, name, base_unit_id, sales_unit_binding_id?, purchase_unit_binding_id?, sellable, purchasable, min_sale_quantity?, warranty_revision_id?, return_policy_revision_id?, handling_revision_id?, origin_country_code?, custom_fields | Unique company/sku; status; family kind/group inherited; unit/profile/variant structure frozen on activation; quantity increment comes from the selected unit revision |
| attribute_set; attribute_set_revision; attribute_set_member | Reusable template code/name; immutable revision; definition/options, requiredness and axis eligibility per member | Unique template/revision/definition; references the existing typed attribute definitions/options |
| attribute_definition | code, name, value_type, measurement_dimension?, is_variant_capable | Unique company/code; typed native domain definition, no executable expressions |
| attribute_option | definition_id, code/name, value_type, exactly one typed value, unit_id?, private value_hash/canonical_value | Unique company/definition/code and canonical value; referenced definition semantics immutable; is_active |
| family_attribute | family_id, definition_id, is_axis, is_required, position | Unique family/definition; activated axes immutable; axis values use explicit options |
| family_attribute_option | family_id, definition_id, option_id | Allowed axis values; composite parent checks |
| item_attribute_value | item_id, definition_id, option_id? or typed scalar/unit | Unique item/definition; exactly the valid representation for the type |
| item_variant_key | family_id, item_id, combination_hash, canonical_combination | Unique family/hash and item; compare canonical bytes on collision; family lock on variant creation |

A non-variant family has exactly one default SKU. Variant signatures include sorted axis IDs
and option IDs, never mutable labels. Required variant values are checked on activation.
Primary groups are operational hierarchy; categories are scheme-qualified parallel classification.
Neither category membership nor type/brand adds an implicit competing tax-inheritance path.
Many-category joins use EXISTS/unique membership projections so list/report totals are not multiplied.
General goods/service type revisions and a General group are separately seeded, not implicit nulls.
Descriptions, physical dimensions and warranty use bounded native shapes: dimension values
have units; duration has an allowed unit/start trigger. No physical-stock fields on services.

### Reusable profiles and master governance

| Table / owned structure | Contract |
|---|---|
| pack_type | Company/code/name, e.g. box/bottle/strip; FK from unit revision; no global conversion factor |
| inventory_profile_template; inventory_profile_template_revision | Stable code plus separately stored immutable revisions of supported tracking/valuation defaults; instantiate item_inventory_profile at activation |
| warranty_policy; warranty_policy_revision | Stable code; duration/unit/start trigger and supported terms, immutable referenced revision |
| return_policy; return_policy_revision; return_policy_condition | Stable code; return window, server-maintained condition count and fixed eligibility conditions; Billing owns dispositions and refunds |
| handling_profile; handling_profile_revision | Native temperature bounds/unit and storage labels; metadata validation; specialist compliance execution separately gated |
| catalog_default_profile | Typed template/lead-time references owned by Product Configuration revisions; existing company/group default routes delegate to this same authority; creation defaults remain distinct from live tax bindings |
| sales_channel | Company/code/name, fixed channel kind; is_active; price context uses the stable ID |
| tax_category | Jurisdiction/code/allowed kind and supported applicability class; distinct from merchandising category; referenced by native tax context |
| item_relationship | Source/target SKU, supported relation kind and validity; no self-link; supersession cycles rejected; alternative links never auto-substitute a transaction |
| master_alias; master_external_key | Registered entity/owner, scoped normalized alias or source/external ID; unique namespace mapping; owner/tenant validation |
| master_change_job | Proposed dated move/default update, reviewed source-version vector, impact counts/errors, checkpoint and result; publication rechecks versions |
| catalog_hierarchy_state | Company PK and row_version; stable lock/version boundary for dated hierarchy and family-assignment changes |
| catalog_policy_state | UUID row identity, unique tenant/company key and generation; increment on every inheritance-impacting binding, assignment or descendant create/change so new rows also invalidate a preview |
| catalog_policy_release | Company/revision/effective date, published_at and bounded dependency manifest; only validated complete releases can be consumed for the effective interval |
| catalog_policy_consumer_ack | Company, trusted consumer, release/aggregate and source event identity, acknowledged/enforced version, applied/rejected result and safe reason; idempotent source-only ingestion, scoped read; older acknowledgement cannot regress current enforcement |

Do not build a universal master-value JSON/EAV table. Share descriptor, lookup, import and
change-impact mechanisms while preserving typed domain rows. Optional party roles such as
brand owner/importer/marketer reference the party owner; no duplicated balances, tax registration
or legal addresses. SKU/lot origin uses the shared ISO country reference and recorded evidence.

Hierarchy history is authoritative in item_group_parent and family_group_assignment.
Resolve a bounded ancestor walk as of posting_date; cache by dated release/version. Derived
closure indexes may accelerate subtree queries, but never replace dated source edges.
Bulk reparent validation checks every affected validity boundary, including future edges;
concurrent group edits lock catalog_hierarchy_state. Reset/inherit/reparent operations
are first-class audited actions with impact preview, not unrestricted parent_id PATCH.
Publication compares catalog_policy_state as well as the reviewed dependency versions;
checking only previously read rows would miss a newly created descendant or tax override.
Ordinary moves affect today/future dates. Historical corrections use a separate controlled
action and retain prior release/edge records so old snapshots remain addressable.

### Product Configuration (C6ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œC8)

Add typed product_configuration_scope, draft/revision, entry-option policy, numeric defaults
and product_configuration_adoption records as specified in the configuration companion.
Reuse existing tracking/commercial/profile authorities and catalog policy releases; do not
duplicate native feature values in a generic JSON/EAV settings store. Scope FKs for family/SKU
arrive with C7. Native metadata exposes enabled/required/locked states and authorized provenance.
New defaults affect activation; adoption of existing SKUs uses reviewed C10 domain jobs.

### Pricing configuration and verified price subjects

| Table | Essential fields and constraints |
|---|---|
| product_pricing_policy | Product Configuration draft/revision child; sale/purchase/MRP requiredness, required sale-level coverage, and explicit gates for extra levels, unit prices, tiers, channels, currencies and formulas; no price amounts or actual cost |
| item_price_scope | Item, subject kind SKU/LOT/STOCK_DECLARATION and exact matching projected references; unique company/item/normalized subject; immutable identity, same-item local ownership checks |
| purchase_price_term | One optional PURCHASE item_price child; gross quote, NONE/PERCENT/FIXED_PER_BASIS trade discount and pinned basis; net reference deterministically reconciles, no independent contradictory edits |
| item_reference_cost | Item/unit revision/currency/basis, STANDARD_ESTIMATE/REPLACEMENT_ESTIMATE/SERVICE_ESTIMATE, amount, validity, numeric revision and evidence; nonoverlap under stable item lock; never an actual-cost cache |
| item_price_formula | One derived item_price child; fixed native source/recipe, percent, source-reference kind and output rounding; no arbitrary expressions, price recursion or simultaneous fixed/tier amount |
| commercial_guard_rule | Dated commercial_policy_scope and optional item_price_scope; FIXED_MIN/FIXED_MAX/MIN_MARGIN/MIN_MARKUP, compatible basis, cost source and BLOCK/REQUIRE_APPROVAL; fixed amounts require an SKU/stock scope; mandatory restrictions combine, not override |
| inventory_lot_projection | Read-only Billing lot/item/manufacturer/date/status/version; no quantity, actual cost or physical-master write API |
| stock_price_declaration_projection | Read-only Billing declaration identity, item/lot/pack linkage, MRP/currency/jurisdiction/tax basis/source revision; exact reference does not prove allocation or availability |

The [pricing contract](catalog-pricing-design.md) defines fixed ranking, required-scope filtering,
same-lot multiple declarations, unit-rate independence and NEEDS_ALLOCATION/NEEDS_COST/
NEEDS_TAX_CONTEXT resolution. Physical declaration/cost/posting ownership remains Billing.

### Units, packs and identifiers

| Table | Essential fields | Constraints / lifecycle |
|---|---|---|
| unit_of_measure | code, symbol, name, dimension, decimal_places, quantity_increment | Unique company/code; decimal_places 0ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ4; is_active; referenced definition immutable |
| unit_conversion | from_unit_id, canonical_unit_id, numerator, denominator | Positive reduced ratio, same dimension; one canonical relation; immutable referenced row |
| unit_tax_code | unit_id, jurisdiction, official_code, valid_from/to | Effective mapping, sourced separately from unit name |
| item_unit_binding | item_id, code, unit_id, role | Stable identity for base/sale/purchase/pack; unique item/code; numerical rules live only in revisions |
| item_unit_revision | binding_id, revision, pack_type_id?, conversion_mode, numerator/denominator?, nominal_ratio?, secondary_unit_id?, quantity_decimal_places, quantity_increment, dimensions/weight?, valid_from/to | Unique binding/revision; effective history; precision 0ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ4 within unit bounds; exact increments; no retrospective ratio overwrite |
| compound_unit_component | compound_revision_id, position, component_revision_id | Acyclic same-SKU components pinned to revisions; quantities supplied structurally per request |
| product_identifier | item_id, unit_binding_id?, unit_revision_id?, type, namespace, value, canonical_value | Unique company/namespace/canonical_value; is_active; retained ownership; one barcode cannot drift across pack ratios |
| identifier_profile | code, name, normalization_version, row_version | Company-unique code; normalization version 1; is_active; requirement structure and identity immutable after creation |
| identifier_profile_requirement | profile_id, identifier_type, namespace_rule, min_count, max_count, requires_slot | One SERIAL/IMEI row per profile; scoped FK; bounded 0..8 counts; multiple values require slots; IMEI uses COMPANY namespace |

Unit bindings refer to revision IDs for new usage; documents preserve the exact used revision.
The earlier item.quantity_increment shorthand is an optional derived API alias of the base
unit revision, not a second writable column. Company quantity_precision is not stock quantization.
Model the item/unit circular relationship with table creation first and one FK ALTER per
later revision where necessary. Never use a cross-service FK to simplify that ordering.
Barcode reuse across pack changes is rejected if a scan cannot identify the intended pack.

Identifier namespace keys are explicit: common scan namespace for internal/GTIN product
codes; manufacturer or supplier context for their part codes. GTIN canonicalization follows
its standard. Supplier references require an authoritative party projection before activation.
Scanning an unqualified part code may return ambiguity, never an arbitrary match.

### Stock-control masters

| Table | Essential fields | Constraints / lifecycle |
|---|---|---|
| warehouse | code, name, kind STORE/GODOWN/INTERNAL_TRANSIT, department_id?, timezone, native address/tax-location facts | Unique company/code; is_active; reserved MAIN cannot be deleted/deactivated; internal transit is non-selectable |
| warehouse_group | Company/code/name and lifecycle; non-stockholding region/zone/group; cannot be a stock allocation or expand actor scope |
| warehouse_group_parent | Group/parent and validity; one dated parent/root, same-company, no cycles/depth overflow; changes use reviewed policy/hierarchy publication |
| warehouse_group_assignment | Warehouse/group and validity; one primary group per warehouse/date; authorized rollups deduplicate warehouses and preserve historical membership |
| company_warehouse_configuration | company PK, immutable main_warehouse_id and transit_warehouse_id, current activity-default references with audited history, source_version | Main plus configuration provision atomically; defaults are explicit and scoped; multi_godown remains Identity-owned |
| warehouse_operation_policy_revision | warehouse_id, revision, UTC validity, sale/purchase/transfer-in/out/customer-return/supplier-return/opening/adjustment flags | Typed operation controls; acknowledged live activation in Billing; main identity does not bypass policy |
| item_warehouse_policy; item_warehouse_permission | Item allocation mode ALLOW_ALL_ACTIVE/ALLOW_LIST, activity defaults and explicit warehouse/operation restrictions | Same-company FKs; narrows location policy/permission only; exact source/destination persisted |
| warehouse_bin | warehouse_id, code, name | Unique warehouse/code; is_active; optional feature, same-company checks |
| item_inventory_profile | item_id, base_unit_id, lot_tracking, serial_tracking, identifier_profile_id?, expiry_required, manufacture_date_required, shelf_life_days?, minimum_remaining_life_days?, issue_strategy, valuation_method | Unique item; goods-only; structural settings immutable after activation |
| item_replenishment_policy | item_id, warehouse_id?, safety_quantity, reorder_quantity, target_quantity, min_order_quantity, max_order_quantity?, order_multiple, lead_time_days, purchase_binding_id | Unique item/scope_warehouse; non-null normalized scope key for the product-wide band; versioned explicit overrides |
| item_supplier_term | item_id, supplier_ref, supplier_sku?, purchase_binding_id, lead_time_days, MOQ, order_multiple, priority | Native reference, effective history; only with party producer |
| item_commercial_policy | item_id, participation/override eligibility, free_sale_allowed, valid_from/to | Effective SKU participation; minimum-price amounts move to commercial_guard_rule and combined discount percentages remain in discount_ceiling; no competing writable floor |
| commercial_policy_scope; discount_ceiling | Typed company/group/family/SKU owner; max_discount_pct and valid_from/to | Effective constraints combine by minimum ceiling; explicit local FKs and owner checks; no amount inherited across incompatible units |
| item_mrp | item_id, unit_revision_id, amount/basis, currency, jurisdiction, tax_basis, numeric_revision, source evidence, valid_from/to | Effective product/pack declaration/default; physical stock declarations remain Billing-owned and cannot be rewritten by a later product MRP |

No on_hand/opening_qty/current_cost column on item. Warehouse activation does not create a
physical stock balance. Expiry/serial profiles require the corresponding company capabilities.
Valuation/account mappings used for posting are authoritative in Billing; Catalog publishes
the selected method as configuration and cannot change it through an unrestricted PATCH.

### Commercial price and tax histories

| Table | Essential fields | Constraints / lock boundary |
|---|---|---|
| price_level | code, name, row_version | Unique company/code; is_active; seed PRICE1 and optionally PRICE2/PRICE3; no fixed three-column SKU layout |
| price_plan | code, name, purpose SALE/PURCHASE/REFERENCE_RETAIL, price_level_id?, currency, tax_basis, custom_fields | Unique company/code; SALE requires level and unique level/currency; other purposes reject sale-level semantics; published purpose/currency/level/tax basis immutable |
| company_pricing_policy | default_level_id, missing_price_policy ERROR/FALLBACK, fallback_level_id?, valid_from/to | Non-overlap per company; lock catalog_policy_state; no recursive/self fallback |
| price_level_assignment_scope | subject_kind CUSTOMER/PRICING_TYPE, customer_ref? or pricing_type_ref?, row_version | Exactly matching subject; local projection references; unique company/kind/subject; stable lock |
| price_level_assignment | scope_id, price_level_id, valid_from/to | Non-overlap per subject; effective history and source provenance |
| party_projection | Minimal authoritative party identity/roles/status/source version for supplier/manufacturer/brand-owner references; source-only writes and protected reads; never Catalog party CRUD |
| customer_type_projection; customer_pricing_projection | Authoritative customer/type IDs, dated pricing-type memberships, status, source version and completeness | Read-only source contracts; one pricing type per customer/date; not a marketing-group union or login role |
| item_price_series | plan_id, item_id, price_scope_id, unit_revision_id, audience_kind/ref, channel_key, row_version | Unique normalized complete context; native audience/stock/unit ranking, no arbitrary priority winner; stable lock before first price |
| item_price_numeric_revision | item_id, unit_revision_id, currency, valid_from/to, price_decimal_places, price_increment? | Non-overlapping scoped policy under stable item lock; precision 0ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ4; positive exact increment; existing prices retain their original revision |
| item_price | series_id, valid_from/to, price_method, amount?, currency, quantity_basis, price_basis_quantity, price_numeric_revision_id, source snapshots, supersedes_id? | Exactly fixed amount/volume tiers OR typed formula; PURCHASE terms reconcile reference amount; positive exact basis; immutable published terms and numeric/source evidence |
| item_price_tier | price_id, min_qty, max_qty?, amount, currency | Disjoint [min,max) ranges; volume semantics; inherit parent pricing unit/basis/numeric policy; no gaps in supported quantity interval |
| promotion / promotion_revision | Stable rule identity plus immutable native benefit/target/stack terms | Unified automatic discount/scheme model below; replaces the proposed item_discount_rule table |
| tax_classification | jurisdiction, code_system, code, item_kind, description, valid_from/to, source | Official/native classification; effective code validity |
| tax_rule | code, name, tax_system, jurisdiction, classification_scope, custom_fields | Unique company/code; is_active; immutable system/jurisdiction/scope; SPECIFIC restrictions or explicitly selected ANY template |
| tax_rate_series | rule_id, typed applicability key, row_version | Unique rule/context; stable lock |
| tax_rate | series_id, valid_from/to, source_reference, supersedes_id? | Effective component set; no arbitrary value PATCH |
| tax_rate_component | rate_id, key, kind, percentage? or amount/currency/unit?, basis_key, position, rounding_rule | Unique rate/key; dependency DAG; correct shape per kind |
| catalog_tax_scope | company_id, owner_kind COMPANY/GROUP/FAMILY/SKU, group_id?, family_id?, item_id?, row_version | Exactly the owner FK required by kind; same-company composite FKs; unique normalized owner key; stable lock before first binding |
| catalog_tax_binding | scope_id, direction, jurisdiction, bundle CLASSIFICATION/TREATMENT/RULE, mode INHERIT/OVERRIDE/REQUIRE_EXPLICIT, classification_id?, treatment?, exemption_reason?, tax_category_id?, rule_id?, item_kind?, valid_from/to | Strict typed shape per bundle/mode; non-overlap per scope/direction/jurisdiction/bundle/item_kind; item_kind GOODS/SERVICE or NULL (all kinds); no opaque JSON |
| tax_impact_review | actor_user_id, change_reason, input_digest, request JSON, change_count, policy_generation, source_version, business_date, status PENDING/COMPLETE/STALE/FAILED, checkpoint_id?, item/checked/finding/blocking counts, reason_code?, completed_at? | Chunked background release review; poll index (company, status, id); a release publishes only against a matching COMPLETE, unblocked row |
| tax_impact_finding | review_id, item_id, direction, as_of, status MISSING/REQUIRE_EXPLICIT/INVALID, missing JSON, blocking | Same-company FK to its review; unique review/item/direction/date; page index (review, id); derived report rows, not audited individually |

catalog_tax_binding replaces the earlier item-only tax-assignment table. The item endpoint
is an adapter to SKU scope, not a duplicate source. Resolve each complete bundle as
SKU > family > nearest group > ancestors > company, using dated membership/edges. An
explicit zero/exemption is a value; REQUIRE_EXPLICIT is a blocking configuration state.
Missing/INHERIT continues to the next ancestor; invalid overrides fail instead of falling back.
Classification and inherited rule/treatment must pass joint jurisdiction validation.

Resolved output includes effective value, owner, binding/release revision and inheritance path
per bundle. Company tax fallback is Catalog-owned, never Identity's default_tax_system.
Lock tax scope and hierarchy release before overlap/impact publication; activation validates
all referenced scopes. Billing needs the complete dated hierarchy and binding dependency set.

item_price has either a flat amount, volume-tier children or one supported formula. Zero is permitted only by explicit policy;
negative/nonfinite/overflow/excess-scale values are rejected. Currency/unit/tax basis are
explicit. Resolve SALE level from authorized customer/type/company assignment, then currency plan;
filter required scopes and apply fixed audience -> stock scope -> unit ranking and
original-line quantity tier. PURCHASE uses configured book and supplier -> standard audience;
REFERENCE_RETAIL is queried explicitly, never a sale fallback. Contract-agreement contexts remain
unsupported until their authoritative source/rules exist. Ordinary callers cannot bypass
this by supplying a cheaper plan ID. No custom-field input enters selection.

Company capability multi_price_levels is proposed, not present in the current code catalogue.
Off pins new sales to baseline PRICE1; an alternate default requires the capability.
Enabling creates additional level definitions, not prices.
Missing coverage fails unless an explicit one-level fallback applies; stale/ambiguous/denied
context never triggers fallback. Relevant mappings/levels/plans must share company scope.

Price/tax effective DATE ranges are inclusive, consistent with the existing helper. Replacing a row
at date D ends its predecessor at D-1. Keep replaced values and revision links addressable;
retroactive corrections are controlled and audited. Posted Billing snapshots are immutable.
Lock series/tax scope before overlap checks; for cross-series audience ambiguity enforce precedence
and fail resolution on equal-rank matches. Membership changes cannot silently select a winner.

### Promotions and coupon-program definitions (P1)

The [promotion schema](catalog-promotions.md) specifies candidate fields and constraints for
campaign/draft/revision, promotion/draft/revision, typed condition/target/manifest children,
benefit/component, stack policy/permissions, limit definitions and coupon program/revisions.
Native requiredness depends on mechanic: percentage, amount, bundle components or paid/reward
quantities. Money has currency/basis; quantity has exact unit semantics. No JSON expressions
or custom-field operands drive calculation. Descriptive campaign/promotion custom values are allowed.

Published windows use UTC [starts_at, ends_at) and a recorded scheduling timezone; they do not
reuse inclusive DATE price-history logic. Mutable drafts use workflow status; published revisions
use validity windows. Revision changes preserve the stable identity used by live usage limits.
Catalog publishes complete rule/dependency releases. Runtime coupon codes and counters are Billing data.

### Optional BOM and manufacturing definitions (M0-M4)

Use the [manufacturing contract](catalog-manufacturing-design.md) for quantity/loss/estimate
semantics and optional enablement. These are 20 Catalog definition/estimate tables. No production
order, work centre, WIP, actual-inspection, genealogy or actual-manufacturing-cost source is added.
All references below enforce tenant/company compatibility with local composite constraints.

| Table | Key native shape and constraints |
|---|---|
| product_manufacturing_policy | One typed child per Product Configuration revision; supported structure/estimate/requiredness options; no arbitrary rules or amounts duplicated from BOMs. |
| item_manufacturing_profile | Item, sourcing/role flags, default-BOM requirement, effective range and version; nonoverlapping dated profiles; MAKE output requires stock-enabled goods. |
| manufacturing_operation | Company/code unique stable identity; scoped name/lifecycle/annotations; no actual machine or worker assignment. |
| manufacturing_operation_revision | Operation/revision unique; typed specification, optional service SKU; editable DRAFT then immutable PUBLISHED content; retirement preserves referenced rows. |
| manufacturing_route | Company/code unique stable identity; no production order/scheduling fields. |
| manufacturing_route_revision | Route/revision unique; declared timing/batch basis; draft/publish/retire with complete pinned step set. |
| manufacturing_route_step | Route revision/step key unique; ordered position, operation revision, nonnegative setup/run times and positive time/output basis; sequential route only. |
| bom | Company/code unique; kind MANUFACTURE/PHANTOM; stable primary SKU for MANUFACTURE, null for PHANTOM; no pseudo-stock output. |
| bom_draft | BOM, base revision, row_version and typed authoring payload; whole-document validation; publish normalizes children atomically. |
| bom_revision | BOM/revision unique; immutable content/hash, batch/config/route rules and publication evidence; manufacture basis/yield/unit derive from primary bom_output; phantom-only positive logical count basis; effective selection uses dated assignments. |
| bom_component | Revision/line key unique; physical item XOR phantom revision; physical mode STOCK_INPUT/EXPLODE_CHILD with conditional child FK; exact quantity/unit/loss/run semantics and optional valid route step. |
| bom_component_substitute | Component/alternate key unique; exact positive ratio, compatible unit/profile, validity and approval constraint; whole-line replacement only; no implicit inverse/transitive selection. |
| bom_output | Revision/output key unique; actual goods SKU, kind, positive nominal quantity, expected yield, unit revision and estimate allocation share; exactly one primary matching bom.primary_item for manufacture, no outputs for phantom; primary row owns manufacture basis/yield/unit. |
| bom_assignment | Item, optional warehouse, revision, default/applicability role and effective range; revision primary output must match exact item; serialize date-overlap/default selection checks. |
| bom_location_default | Revision plus issue/output/WIP/scrap role, optional component/output binding, warehouse/bin; bin belongs to location and scope; defaults never authorize stock posting. |
| bom_quality_requirement | Revision/check key, input/output/step scope, pinned native attribute/unit constraints and inspection-required behavior; no actual result or arbitrary expression. |
| bom_cost_policy | One per BOM revision; estimate currency/basis, material-source choices and PRIMARY_ONLY/EXPLICIT_PERCENT allocation; unsupported source combinations rejected. |
| bom_cost_charge | Revision/charge key; fixed/run/time/output/allowed-direct-cost-percent basis, manual estimate or pinned service reference, optional exact route step; no recursive overhead. |
| bom_cost_estimate | BOM revision, immutable scenario/date/currency/quantity/run/substitution/source manifest, completeness/result/hash and actor evidence; refresh inserts a new estimate. |
| bom_cost_estimate_line | Estimate/path/line identity, source type/revision, quantity/unit, exact basis, rounded amount and output allocation; preserves repeated paths and reconciled totals. |

Cross-row rules (one primary output, percent totals, graph cycles, assignment overlap and full
dependency publication) require locked aggregate transactions as well as row CHECK/FK/unique
constraints. Reuse catalog_policy_state for the scoped graph generation/lock, releases/acks,
bulk jobs and audit/outbox. Publishing a replacement does not mutate older parents or estimates.
Phantom revisions allow variable component groups only, with no physical outputs, own routing,
fixed/run charges or output-cost policy. New MAKE activation can publish against finalized draft
SKU profiles before atomically activating the SKU/default assignment; consumers require active
products and the complete release, avoiding circular activation prerequisites.
Adopted estimates reference item_reference_cost as STANDARD_ESTIMATE with exact output/run/source
provenance; actual-cost scalars never enter these tables. Native policy cannot come from custom fields.

Indexes include company/BOM/revision, component item and child revision for reverse where-used,
assignment item/warehouse/validity, route revision/step position and estimate source/date/ID.
Graph queries retain distinct line paths; security filtering must not present hidden requirements
or costs as a complete public aggregate. Full API actions and optional phases live in the companion.

## 3. External owners and integration contracts

No Billing tables are created by this Catalog schema. The current Catalog-only phase plan
supersedes the earlier integrated source/stock/sales candidate inventory.

| External owner/capability | Required Catalog integration |
|---|---|
| Billing party/customer/type source | party_projection, customer_type_projection and customer_pricing_projection; complete versioned source, known-empty membership and tombstones |
| Billing lot and physical price declarations | inventory_lot_projection and stock_price_declaration_projection; minimal verified references for Catalog-owned prices, no availability/actual-cost/source writes |
| Billing fiscal-year source | Optional fiscal_year_projection for custom-number reset; unavailable until real source readiness |
| Billing stock/physical units | Publish product/unit/tracking/location definitions; no on-hand/opening/current-cost or physical serial source in Catalog |
| Billing transfers/damage/counts/adjustments | Publish complete location/product/configuration releases; consume trusted activation/deactivation acknowledgements |
| Billing product stock ledger | Stable SKU/group/unit history; ledger and balances come from Billing's posted movement evidence |
| Billing promotion execution/sales/credits | Publish native promotion/program/limit/stack/price/tax releases; no codes/counters/holds/redemptions in Catalog |
| Reports analytics | Versioned scoped source contracts; Reports owns its read models and analytical exports |

The [inventory integration contract](catalog-inventory-integration.md) defines immediate/transit
transfers, discrepancies, freight allocation, damage custody/write-down/disposal, blind counts,
reviewed adjustments and pinned ledger semantics. These are requirements for Billing's plan,
not Catalog migration or API tasks. Missing owner APIs are explicit dependencies.

## 4. Catalog support stores and Identity dependencies

### Catalog-owned bulk-job storage

| Table | Essential contract |
|---|---|
| bulk_job | Actor/tenant/company, kind IMPORT/UPDATE, intent, schema/config revisions, selection digest, job revision, atomicity/error mode, state and counts; versioned preview/commit |
| bulk_job_record | Job/revision/source row key, registered entity/target ID or external key, expected_version, typed normalized action, safe validation outcome and change_set_id |
| bulk_change_set | Ordered bounded transaction unit and request hash; includes all dependent SKU fields or selected price-level series for one SKU |
| bulk_change_set_effect | Unique job/stable logical change-set key; records accepted revision/action hash, committed entity/result versions and audit references; atomic with domain effects |
| bulk_job_dependency | Parent/child record/change-set edges; bounded acyclic graph, failed prerequisite blocks dependent |
| bulk_import_artifact | Private bounded source/error artifact, content hash/type, retention deadline and bytes/chunks; excluded from normal SELECT/list; no new datastore |

Shared engine/helpers belong in libs/platform; these rows/migrations/domain handlers belong
to Catalog. Other services may reuse the mechanisms through their own implementation plans. Staging/action payload JSON is non-queryable transport intent, not commercial
source of truth. Normalize fields/indexes used for scheduling/filtering. Commit uses ordinary
typed domain logic, expected versions, policies and uniqueness constraints.

The idempotency key prevents duplicate submission; the change-set effect marker prevents
duplicate execution after worker redelivery. Source external keys prevent duplicate creates
across jobs. Publication stores the accepted immutable revision/digest; changed input needs
a fresh preview. Worker leases/checkpoints do not substitute for DB effect uniqueness.
Completed change sets are sealed across job revisions; revalidating failed records cannot
reapply successful changes. New job dispatch is committed through the owning outbox.
Track approved in-job source changes in the dependency/effect records so later records use
their planned resulting versions; unrelated edits still conflict. This cannot refresh a
percentage-price baseline or broaden a frozen selection without a new reviewed revision.

Price batch actions lock selected series in canonical order and compute changes from the
reviewed baseline. All requested levels for a SKU can form one transaction; larger jobs may
partially finish across SKUs. Explicit atomic mode is bounded to one company/database.
Tax-policy releases and master hierarchy moves keep their own domain-level transaction/publication
rules. Stock opening and other Billing jobs are not submitted through Catalog bulk APIs. Rollback of a failed job is not an automatic business reversal.

### Existing platform/configuration stores

| Store | Required contract |
|---|---|
| outbox, processed_message, idempotency_key | Existing platform shapes plus transactional executors/transport; one set per service |
| company_projection, company_feature_projection | Minimal authoritative scope/config; source version and receipt freshness; preserve feature usage locks |
| custom_field_definition_projection, field_config_projection, field_policy_projection | Identity IDs, logical keys/scope, versions, lifecycle/tombstones and typed configuration |
| fiscal_year_projection | Optional read-only Billing fiscal-year identity/calendar/state/source revision for Catalog auto-number reset; not a Catalog fiscal source or financial posting API |
| projection_checkpoint | Source barrier, snapshot/replay state, last applied metadata; UUIDv7/time is not a commit watermark |
| custom_field_value_index | Entity/definition/company, exactly one typed representation; currency sibling for currency_amount |
| custom_field_value_member | Entity/definition/member rows; multi-select membership via EXISTS, not duplicate-producing joins |
| custom_field_unique_claim | Tenant, normalized company scope, entity type, logical field key, canonical value hash, canonical bytes, owner |
| custom_field_sequence | Entity/definition/scope/reset-cycle key, next value; same transaction as entity, no gap-free guarantee |
| field_index_state; field_rebuild_job | Definition/version/generation, pending/building/ready/failed, checkpoint/error; partially built index is unavailable |

Claim uniqueness is scoped by logical field key, including overrides. Null/unset do not
claim; strings use explicit normalization/case rules; numbers canonicalize Decimal; currency
amount includes currency. Unique multi-select sets are rejected initially unless an explicit
whole-set canonical contract is added. Retained historical entities retain claims.
Compare bytes on hash collision and fail safely; reserve/release claims in canonical order
within the entity transaction. Protect claim values like their source custom fields.

Identity already owns definition/config/policy/index/sequence source tables. Any missing source
version, job or capability-transition support is an Identity dependency under its own plan;
Catalog implementation does not add Identity migrations or rewrite its 0001ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ0034 chain.
Pure registry contributions live in the shared contract package; Identity must not import
Catalog ORM or run Catalog queries.

Custom-enabled entities: catalog.product_family, catalog.item, catalog.item_group,
catalog.item_category, catalog.product_type, catalog.brand, catalog.manufacturer,
catalog.price_plan, catalog.tax_rule, catalog.campaign and catalog.promotion.
Native metadata/policies additionally register promotion/program/limit/stack/issuance/hold/
approval/redemption actions and sale/credit fields, product-configuration drafts/publication/
adoption/effective reads, price-numeric revisions and warehouse/default/operation-policy/transfer actions, plus category
schemes, profiles, price levels/assignments, bulk actions, hierarchy/tax-scope actions, catalog.unit_of_measure,
catalog.item_unit_revision, catalog.item_inventory_profile, catalog.item_price,
catalog.tax_rate, billing.party, billing.customer_pricing_type and exposed inventory actions/fields.
Billing source entities start with native metadata/policies; custom values require a separate
explicit registration. Child-list mutation semantics
must be explicit; policy checking only top-level JSON keys is insufficient.

## 5. API surface

Paths are relative to each service's existing versioned API prefix. Company context is
explicit and checked against every object. Mutation action permissions are distinct where
stock posting, overrides or historical changes need stronger authority.

### Catalog domain routes

| Routes | Behavior | Permission family |
|---|---|---|
| GET /product-configuration, /product-configuration/options; POST/PATCH drafts; POST draft validate/preview/publish | Typed scoped defaults/requirements and numeric profile references with dependencies/readiness | Explicit configuration read/manage/publish plus field policies |
| GET /items/{id}/effective-configuration; POST /product-configuration-adoptions/preview; POST /{id}/commit | Pinned structural and dated commercial rules; reviewed existing-SKU adoption | Configuration read/adopt plus underlying item/profile authority |
| GET/POST /items/{id}/price-numeric-revisions | Dated rate-entry precision/increments for SKU/unit/currency | Price configuration authority; existing published values remain unchanged |
| POST/GET /product-families; GET/PATCH /product-families/{id}; POST activate/discontinue | Family and variant definition | Explicit item.* mappings |
| POST/GET /items; GET/PATCH /items/{id}; POST activate/discontinue | SKU; nested metadata validated through domain | Existing item.* catalogue |
| GET/PUT /product-families/{id}/attributes; GET/PUT /items/{id}/attributes | Native axis/options/values and exact variant combination | item.update plus scope/field policies |
| CRUD /item-groups; GET /item-groups/{id}/children; POST /item-groups/{id}/reparent | Group/subgroup master, bounded tree reads and dated move | Separate group read/manage/move; tax-impact changes also require tax authority |
| CRUD /category-schemes, /item-categories, /product-types, /brands, /brand-series, /manufacturers, /manufacturer-sites | Typed business masters and lifecycle; type changes publish revisions | Explicit resource-specific master permissions |
| CRUD /attribute-sets, /attribute-definitions, /attribute-options, /pack-types, /sales-channels | Reusable typed lookup masters | Explicit master read/manage permissions |
| CRUD /warranty-policies, /return-policies, /handling-profiles, /inventory-profile-templates | Supported native profiles with immutable revisions | Explicit profile read/manage; capability checks |
| GET/PUT /product-families/{id}/categories; GET/PUT /product-families/{id}/manufacturers; POST /product-families/{id}/assign-group | Category/approved-source links and dated primary-group assignment | Family update plus relevant scope/tax-impact authority |
| GET/PUT /catalog-defaults; GET/PUT /item-groups/{id}/defaults | Typed creation defaults and explicit revisions | Master-default management; field policies |
| GET/POST /items/{id}/relationships | Alternative/accessory/supersession links | Item relationship management; both objects scoped |
| GET /masters/{entity_type}/{id}/usage; POST /master-changes/preview; POST /master-changes/{id}/publish; GET /master-changes/{id} | Allowlisted registry, impact and version-bound publication | Underlying resource grants plus change/publish permissions; no generic unscoped CRUD |
| CRUD /units; POST /units/convert | Unit metadata and exact/compound conversion validation | Read/manage unit permissions |
| GET/POST /items/{id}/unit-bindings; POST /unit-bindings/{id}/revisions | Packs and measured quantity profiles | item read/update and protected-field checks |
| GET/POST /items/{id}/identifiers; POST /product-identifiers/{id}/deactivate | Product/pack codes | Item read/manage |
| POST /barcode/resolve | Bounded product-code/GS1 parser; optional explicit namespace | Item read; scoped, no URL fetch |
| GET/PUT /items/{id}/inventory-profile; CRUD /identifier-profiles | Native tracking/cost method definitions | Explicit inventory configuration permission |
| CRUD /warehouses, /warehouse-bins, /warehouse-groups; reviewed group reparent/assignment | Physical location and non-stockholding group definitions with dated hierarchy | Explicit warehouse/group read/manage/move; actor location scope never expands through a group |
| GET /warehouse-configuration; preview/publish defaults; warehouse operation-policy history/preview/publish | Built-in Main, activity defaults and independent native flags; Billing activation status | Warehouse configuration authority plus field policies; capability changes remain Identity actions |
| GET/PUT /items/{id}/warehouse-policy | Restrictive product-location allowlist/defaults and operation permissions | Item/location policy authority; cannot expand actor scope |
| GET/PUT /items/{id}/replenishment-policies; CRUD /item-supplier-terms | Thresholds and terms | Explicit replenishment management |
| CRUD /price-plans; GET/POST /item-price-series; GET /item-price-series/{id}/history; POST publish/supersede | SALE/PURCHASE/REFERENCE_RETAIL, dated fixed/tier/recipe rates and typed purchase terms | Purpose-specific price read/manage plus publication authority |
| GET/POST /items/{id}/price-scopes; GET /pricing-reference-options | Verified SKU/lot/declaration price subjects and minimal allowed source references | Scoped price-subject/reference access; no physical lot/declaration CRUD |
| GET/POST /items/{id}/reference-costs; POST publish/supersede | Dated standard/replacement/service estimates with source evidence | Separate reference-cost read/manage/publish |
| GET/POST /commercial-guard-rules; POST validate/publish; GET history | Fixed min/max and margin/markup definitions with source/basis and approval requirements | Separate guard manage/publish and protected cost-derived reads |
| GET /items/{id}/price-matrix | Authorized purpose/level/unit/scope prices, coverage and missing-source states | Per-purpose/field permissions; no supplier/customer/cost leakage |
| CRUD /price-levels; GET/PATCH /pricing-policy | At least three configurable levels and dated default/fallback policy | Price-level/policy manage; company capability gate |
| GET/PUT /customer-type-price-levels; GET/PUT /customer-price-levels | Dated typed commercial assignment | Price-assignment manage plus customer/company scope |
| POST /prices/resolve | Purpose, trusted audience, item/date/unit/currency and enabled stock scope; complete regular reference or NEEDS_ALLOCATION/NEEDS_COST/NEEDS_TAX_CONTEXT | Purpose-specific price read; explicit level/plan override needs authority; untrusted cost/availability assertions rejected |
| CRUD /tax-rules; GET/POST /tax-rate-series; GET history; POST publish/supersede | Native effective tax definitions/components | Existing tax_rule.* with explicit history actions |
| GET/PUT /catalog-tax-defaults; GET/PUT /item-groups/{id}/tax-assignments; GET/PUT /product-families/{id}/tax-assignments; GET/PUT /items/{id}/tax-assignments | Dated typed bundles at explicit owner scope; reset-to-inherit is an explicit action | Tax configuration permission plus owner scope/field policy |
| POST /tax-configurations/resolve; GET /tax-classifications; CRUD /tax-categories | Inherited definition context with source path; native classifications and tax-category master | Tax read/manage as applicable; mask denied ancestors; invoice tax calculation stays in Billing |
| GET/PUT /items/{id}/commercial-policies; GET/POST /items/{id}/mrp | Participation/free-sale and product/pack/jurisdiction MRP history; monetary guards use their own API | Explicit commercial-policy/MRP permission; physical declarations are source-owned |
| CRUD /campaigns, /promotions, /coupon-programs; POST /promotions/{id}/validate, /preview, /publish | Typed drafts, impact and immutable published revisions | Separate promotion read/manage/publish; no runtime redemption here |
| GET/POST /promotion-stack-policies, /promotion-limits | Dated combination/cap policy; reviewed changes preserve consumed/held capacity | Explicit stack/limit administration and field policies |
| GET /catalog-import-templates; POST /catalog-imports; POST /catalog-imports/{id}/validate; GET /catalog-imports/{id}/preview; POST commit/cancel; GET job/records/errors | Versioned upload, reviewed selection and resumable execution | Import plus every underlying resource/action grant |
| POST /catalog-bulk-updates/preview; POST /catalog-bulk-updates/{id}/commit; POST cancel; GET job/records/errors | Frozen file/filter selection and typed version-aware changes | Bulk-update plus underlying resource/action grants; worker uses original actor authority |

CRUD here means explicit create/detail/patch/list and permitted lifecycle routes, not generic
hard delete. API implementations must enumerate each operation/permission in OpenAPI before
the phase closes. Currency/amount history and immutable attributes are never arbitrary PATCHes.

### Optional manufacturing routes

When M0-M4 is selected, register the [BOM/route/estimate endpoint families](catalog-manufacturing-design.md#8-api-bulk-and-persistence)
with explicit read/manage/publish/estimate/reference-cost-adopt permissions. Reuse configuration,
bulk, revision history and release APIs. Explosion returns a requirement definition, not availability;
estimates return protected references, not actual production cost. Production commands remain external.

### External API boundaries

Catalog exposes no party/customer CRUD, inventory documents, transfers, damage cases, stock
counts/adjustments, stock ledger, pricing-quotes, coupon issuance/holds/redemption or sales/
credit posting routes. Their contracts are owned by Billing. The [inventory companion](catalog-inventory-integration.md)
records proposed external operations; the [promotion companion](catalog-promotions.md) records
runtime integration requirements. They are not Catalog OpenAPI operations.

### Identity, metadata and service contracts

- Identity-owned dependencies: definition/config/policy source APIs, registry/type/source discovery
  and configuration-job status; Catalog consumes supported contracts and implements no source CRUD.
- Catalog: GET /entities/{entity_type}/field-set, resolved /custom-fields, registered options
  with pagination, /field-policy for the current actor, and /field-index-jobs/{id}.
- Catalog: narrowly authorized /internal/replication/{entity_type}/snapshot;
  schema/aggregate versions and source barrier, never ordinary user's unmasked export.
- Internal capability transition endpoints require explicit service principals, idempotency
  and version checks; arbitrary headers cannot claim system authority.
- Catalog: explicit public health/live and health/ready with no sensitive details.
- Catalog release consumer status: scoped read of catalog_policy_consumer_ack; acknowledgement
  ingestion requires a trusted consumer, source version and idempotent event identity.

## 6. Requests, queries and indexes

- Require Idempotency-Key for creates, publication/history actions and job submissions; bind to
  tenant/company/route/canonical body/caller authority. Validate auth before replay and serialize
  the original effect under current read policy. Reject mismatched reuses.
- expected_version is mandatory on mutable aggregates/actions. PATCH omission means unchanged;
  explicit null clears only nullable fields. A custom_fields map patches named keys.
- Lists: default 50/max 200, stable signed keyset cursor bound to scope/filter/search/sort,
  bounded typed allowlists, lean ListItem schemas, no automatic exact count or JSON selection.
- Custom filters require resolved readable/search-ready definitions; member queries use EXISTS.
  Denied fields are unavailable to search/filter/order and derived resolution outputs.
- Catalog reference/acknowledgement responses must not expose external stock, cost or physical
  identifiers beyond the caller's scope; operational reads remain in their owner API.
- Suggested access indexes: tenant/company/status/name/id for masters; company/family for variants;
  group/validity and parent/validity for dated edges; family/validity for group assignment;
  scheme/category/family for membership; tax scope/context/bundle/date for inherited bindings;
  company/identifier namespace/canonical value for scans; series/effective dates for history;
  warehouse/group/validity for location membership; source identity for imports;
  tenant/definition/company/typed value for cf; consumer/release/version for acknowledgement.
- FK/unique indexes are additional to access indexes. Verify advertised filter combinations
  with MySQL EXPLAIN and actual query count; do not promise arbitrary combinatorial filtering.

Return structured codes such as unsupported_capability, invalid_unit_conversion,
quantity_not_representable, ambiguous_price, missing_tax_context, tracking_required,
duplicate_identifier, stale_projection, consumer_not_ready and version_conflict.
Field errors must not reveal denied values, raw SQL or another tenant's identifiers.

## 7. Events, bootstrap and deployment

Versioned snapshot families cover company/config, groups/dated edges/assignments, category/type,
brand/manufacturer/profile, family/item, unit, warehouse/group/bin, price level/assignment/plan/series,
customer-pricing projections, tax scopes/bindings, promotion/program/stack/limit revisions and
policy-release manifests. Catalog consumes only necessary party/fiscal/configuration source facts
and trusted consumer activation/deactivation acknowledgements. Billing owns inventory, sale,
coupon and financial events under its separate contracts. No raw runtime coupon codes or
physical-unit identifiers are copied into Catalog's ordinary source projections.
Envelope includes source, schema_version, aggregate ID/version, tenant/company, message_id,
occurred_at and trace_id. Audit and projection payloads are separate contracts.

Version each true aggregate independently. If an item snapshot carries child mappings, it
must carry their complete authoritative set; unrelated child deltas must not be discarded
by sharing an inappropriate version cursor. Chunk oversized snapshots with a manifest/version
protocol; do not truncate. Projection exports exclude raw custom/physical identifiers unless
the consumer has an explicit need and protection contract.

Start durable change capture before snapshot, merge only newer versions, retain tombstones,
then catch up to an explicit source barrier including in-flight outbox work. Publish readiness
only after dependencies are complete. Ack after local commit; retries preserve message_id.

Catalog migration order: platform/reference tables -> company/field/party projections and owned
job stores -> units/groups/categories/types/brands/attributes/profile revisions -> Product
Configuration -> families/SKUs/assignments and deferred local FKs -> packs/identifiers ->
warehouses/groups/bins/location policies -> price/tax scopes/histories -> release acknowledgements
-> promotion definitions and bulk adapters. Model/migration parity and one-DDL revisions apply
throughout. Source dependencies do not add migrations to another service's database.

Optional BOM migration ordering: manufacturing policy/profile -> operation/revisions ->
route/revisions/steps -> BOM/draft/revision -> components/substitutes/outputs/assignments/location/
quality/cost policy/charges -> saved estimates/lines. Add deferred local FKs in separate DDL
revisions where cycles require it. Reuse support tables. Publish operation/route/child dependencies
before complete parent manifests; no consumer acknowledges a partially received BOM closure.

Set and test bounded cursor/idempotency/replay retention, event sizes, import document sizes,
security freshness and job batches. APIs expose job progress/failure; restart is resumable.
Rebuild Catalog-derived indexes from owned records and validate against their source generation.
Stock/financial rebuilds remain Billing obligations under the external contract.

## Decision log

2026-11-04: Catalog 0220 stores one immutable `item_stock_choice` per product.
0221 adds `lot_id`, generated `lot_key` and the physical MRP mirror to
`item_price_scope`, preserving existing SKU scope uniqueness. These definitions
do not store stock balances; Accounting 0235 owns physical declarations and its
existing lot positions/cost layers own opening effects.

- 2026-11-04: Catalog 0216 adds six INHERIT/DISABLED/ENABLED pricing controls to
  `product_pricing_policy` in one additive ALTER. Legacy rows retain INHERIT;
  downgrade requires an online check and refuses authored settings.

- 2026-11-04: Removed planned warehouse references, location ranking and location
  scope from regular pricing. Stock-location and valuation contracts remain separate.

- 2026-10-31: Added revision 0215 for explicit generic tax-rule classification
  scope. Version-two India GST defaults use business-neutral names and distinct
  nil/exempt/non-GST choices. Existing restrictions and dated financial history
  remain unchanged; scope is native policy rather than a custom-field convention.

- 2026-10-10: Replaced the planned Billing/Payments service boundary with Vouchers workflows
  and Accounting party/posting authority. Schema and wire changes remain future explicit work.

- 2026-10-05 (tax-accounting Phase 2): revision 0155 adds nullable `catalog_tax_binding.item_kind`
  (GOODS/SERVICE, check-constrained) so a company or BOTH-group scope keeps separate goods and
  services defaults; history keys include it and resolution prefers the product's kind, then NULL.
  No index revision was added: binding lookups already filter on the existing scope/direction/bundle
  index, and the extra column only narrows those rows. Revisions 0156/0157 create
  `tax_impact_review` and `tax_impact_finding` (plan decision 3: chunked background impact review
  that publication references). Each is one literal statement with a DROP/column-drop downgrade.
  Also corrected pre-existing model/migration drift in 0150, 0153 and 0154 and `metadata.TABLES`.

- 2026-09-11: Added paired unit_of_measure, unit_conversion, unit_tax_code and pack_type models and revisions 0007-0010, native quantity rules and wire/list schemas. Unit CRUD/publication and authoritative field/source integration remain pending; no live database was migrated.

- 2026-09-11: Implemented Catalog foundation revisions 0001-0006 using shared models and
  filtered service metadata. Registered the scoped implementation-readiness endpoint with
  existing item.read authority; remaining proposed domain routes are not implemented.

- 2026-09-11: Added 20 optional BOM/routing/configuration/estimate structures and their native
  constraints/routes; inventory is 147 base or 167 with M0-M4. Execution sources stay outside Catalog.

- 2026-09-11: Added typed purchase terms, estimates, pricing configuration/scopes/recipes/guards
  and minimal lot/declaration projections. Catalog inventory is 147 tables. Removed duplicate
  minimum-price storage and arbitrary series priority; actual costs and declarations stay external.

- 2026-09-11: User corrected scope to Catalog only. Removed Billing source/stock/sales table and
  route deliverables from this schema; linked their integration contracts. Added the final owned
  inventory, warehouse groups, typed profile revisions, minimal source projections and consumer acknowledgement.

- 2026-09-11: Added Main/bootstrap and warehouse/default/operation-policy contracts, product
  location restrictions, Billing activation guards and explicit immediate/transit transfer legs.
- 2026-09-11: Added Product Configuration table/API contracts, explicit unit precision,
  price numeric revisions and rate-basis quantities. Removed duplicate item-level increment
  storage; selected unit revision is authoritative. Storage remains DECIMAL(19,4).
- 2026-09-11: Detailed execution planning made the C11 Billing fiscal source/Catalog reset
  readiness explicit and bound P2 approval to quotes with unique actual-sale consumption in P4.
- 2026-09-11: Replaced item_discount_rule with the unified native promotion model; added
  Catalog definitions and Billing quote/code/quota/redemption plus sale/credit table families.
  Linked detailed P0ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œP5 constraints and expanded metadata/API registration obligations.
- 2026-09-11: Added the minimal Billing commercial-party source, aligned the C2/C5/C8
  dependency chain and C11ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œC14 stock phases, pinned published plan terms, and specified
  how bulk dependencies advance only through approved effects of their own job.
- 2026-09-11: Added currency-independent price levels, dated customer/type assignments and
  shared-shaped bulk-job storage. Replaced earlier shorthand import routes with staged
  upload/validate/preview/commit and separate bulk-update contracts.
- 2026-09-11: Expanded explicit master inventory and replaced item-only tax assignment with
  typed company/group/family/SKU scopes, dated inheritance and dependency-safe publication.
- 2026-09-11: Expanded the candidate schema for native family/SKU, units/conversions, tracking,
  tiered pricing, tax and required Billing inventory records.
- 2026-09-11: Replaced the earlier 29-table/simple-master estimate with an ownership-grouped
  inventory. Exact revision counts follow finalized DDL; no misleading fixed count is promised.

- 2026-09-11: Added literal one-DDL revisions 0011-0015 with matching models for shared
  language and Catalog-owned custom claims/sequences/typed scalar/member values. Scalar
  timestamp storage is value_datetime_at. Unique values use explicit canonicalization and
  hash-collision checks; text/member keys use binary MySQL collation. No live DB migrated.


### Identity source materialization decision, 2026-09-11

The authorized Identity implementation publishes `identity.catalog_context.v2` from its own
native tables. Catalog projections are partitioned by `(tenant_id, company_id, source_id)`;
v2 adds the company currency allowance projection so foreign price authoring uses Identity's
reviewed company currency policy. The v2 source and consumer require a complete new snapshot.
source identities shared across companies receive separate local UUIDv7 row identities.
Projection checkpoints pin complete snapshot identity/digest, source generation and lease.
Subject projections include only status/activity and relationships. Snapshot replacement,
contiguous buffered-event merge and checkpoint activation commit atomically. Every allocated
source generation has an event, including empty snapshot barriers. A missing version marks
context stale until caught up or replaced by a complete newer snapshot. Events never extend
the completeness lease. Default 60-second leases are initial engineering configuration, not
an agreed production freshness SLA. The inventory increases by six missing support structures.

The checkpoint stores `snapshot_source_version` separately from the applied event watermark.
A new complete snapshot may start before events already applied while its pages were in flight;
activation merges those buffered events and must reach at least the old watermark before commit.
Replaying the same snapshot does not extend its lease. Reusing a baseline version with another
snapshot identity or content is rejected. This closes the event-before-snapshot refresh race.

- 2026-09-11: Classification increment uses the common UUID identity plus a unique company
  policy-state key, allowing the shared atomic insert-claim mechanism; the logical company
  aggregate and generation remain the same authority.

Decision 2026-09-11: classification history dates use the documented MySQL DATE floor 1000-01-01; the separately seeded GENERAL root begins at that floor. Category trees retain same-scheme composite parent references. General cannot change code/kind/lifecycle or parent. Classification HTTP workflows are detailed in catalog-classification-api.md.


### Index-generation increment (2026-09-12)

Catalog head 0034 adds the planned field_index_state and field_rebuild_job models/tables,
for 34 materialized tables. Each revision contains one CREATE/DROP. No deployed DDL was changed.
The unpublished 0033 state constraints enforce ready/building order and prevent retiring the
active generation. The public/job contracts are in [index rebuild API](catalog-index-rebuild-api.md).
Source definitions remain Identity-owned; unique claims are not reused as speculative staging.


Decision 2026-09-12 (C6.07, review in progress): added the closed polymorphic master_alias and
master_external_key identity stores in 0060/0061, including binary identity collation, retained
claims and scoped owner indexes. The [governance contract](catalog-master-governance-api.md)
defines normalization, permission boundaries and the limited direct-local usage query. These
working additions do not change the reviewed baseline until all milestone gates pass.

Decision 2026-09-12: product_family and item are now paired native tables (0062/0063) for atomic draft goods/service creation. The initial API exposes SIMPLE only; configuration/variants/activation remain open. See catalog-products-api.md for tested scope.


## V1.5 implemented bulk storage (2026-09-13)

| Revision/table | Durable responsibility |
|---|---|
| 0111 `bulk_job` | Original actor, fixed modes, state/counts, input/review hashes, source/policy pins, expiry |
| 0112 `bulk_change_set` | Stable logical key, order, action hash and atomic group status |
| 0113 `bulk_job_record` | Source coordinates, exact normalized command, private review/dependency evidence and safe result code |
| 0114 `bulk_change_set_effect` | Unique logical effect identity and accepted revision, committed with native writes |
| 0115 `bulk_job_dependency` | Unique directed edges; both endpoints constrained to the same tenant/company/job |
| 0116 `bulk_import_artifact` | Private bounded MEDIUMBLOB, content hash and seven-day expiry |

Each revision has one literal CREATE statement and one DROP downgrade. Composite foreign
keys prevent cross-company and cross-job references. Actor/work/order/expiry indexes support
bounded list and worker reads. Private JSON/BLOB columns, selected IDs and semantic Identity
digests are excluded from field metadata and public response schemas. Retention erases private
payloads while keeping job/effect identity. Decision: these are administration records, not
new product domain state or external-owner replicas.


## Product custom-field adoption (15 September 2026)

Migration 0129 adds `requires_adoption TINYINT(1) NOT NULL DEFAULT 0` to
`custom_field_definition_projection`, retaining the source definition's adoption gate.
Migration 0130 creates `custom_field_adoption`:

| Column | Contract |
|---|---|
| `id`, `tenant_id`, audit columns | Standard scoped master identity and audit timestamps |
| `company_id BINARY(16)` | Company owner; SCOPE_ALL reserves the tenant uniqueness registry |
| `entity_type VARCHAR(80)` | `catalog.product_family` or `catalog.item` |
| `definitions JSON` | Accepted validation contracts; on SCOPE_ALL, retained tenant uniqueness contracts |
| `row_version BIGINT` | Positive optimistic version, guarded against exhaustion |

Unique `(tenant_id, company_id, entity_type)` prevents duplicate acceptance state. The tenant
row serializes every product claim writer with adoption. Company policy generation changes
on acceptance, invalidating old bulk evidence. Values stay on product JSON; derived indexes
and unique claims remain transactional. The adoption table is included in metadata head 0130.
Both new revisions refuse downgrade to avoid silently discarding adoption gates/contracts.
See [custom-fields.md](custom-fields.md) for review tokens, permissions, bounds and deployment.


### Native measured integer attributes (0131)

Revision 0131 replaces `ck_item_attribute_value_p76_scalar_type` with one atomic ALTER.
INTEGER and DECIMAL scalar SKU attributes can carry `unit_id`; TEXT, BOOLEAN and DATE
scalars require no unit. The existing exclusive option/scalar and typed-value checks still
apply. Domain authoring additionally enforces the attribute's measurement dimension and unit
quantity grid. Downgrade requires explicit data reconciliation and is refused automatically.


## Implemented stock-location definitions (0132-0143, 18 September 2026)

| Revision / table | Durable responsibility |
|---|---|
| 0132 `warehouse` | Company/code/name, kind STORE/GODOWN/INTERNAL_TRANSIT, optional department, timezone and native address/tax-location facts; paired checks tie `is_system` to the reserved MAIN code and the transit kind to TRANSIT, so a built-in identity cannot be forged by a direct write |
| 0133 `company_warehouse_configuration` | One row per company, immutable `main_warehouse_id`, the four current activity-default pointers and the provisioning source version; Main and transit must differ |
| 0134 `warehouse_operation_policy_revision` | Per-location revision number, UTC validity window and the eight typed operation booleans as columns; unique revision per location and per scope, window closed at one instant by its successor |
| 0135 `warehouse_group` | Non-stockholding region/zone identity, company-unique code, `is_active` lifecycle and the scoped id key its dated children reference |
| 0136 `warehouse_group_parent` | Dated parent interval per group, unique `(group_id, valid_from)`, no self-parent; a NULL parent is a root interval, not a missing one |
| 0137 `warehouse_group_assignment` | Dated primary group per location, unique `(warehouse_id, valid_from)`; append-only, so a March rollup still answers for March |
| 0138 `warehouse_bin` | Physical subdivision, unique `(warehouse_id, code)` — `A1` in two godowns is two bins — and a parent that never changes |
| 0139 `item_warehouse_policy` | One row per SKU: selection mode ALLOW_ALL_ACTIVE / ALLOW_LIST and the four product activity-default pointers, each a same-company location FK |
| 0140 `item_warehouse_permission` | Explicit per-location operation restrictions, keyed to the policy's scoped item key rather than to `item`, so a restriction without a selection mode cannot be stored |
| 0141 `item_replenishment_policy` | Safety / reorder / target / MOQ / maximum / multiple as `NUMERIC(19,4)`, lead time, purchase unit binding; the product-wide band stores the nil UUID in `scope_warehouse_id` tied by check to a NULL `warehouse_id`, which makes "one product-wide band" a unique constraint instead of a convention |
| 0142 `catalog_policy_release` | Company/revision/effective date, `published_at`, bounded manifest counts, manifest digest and the generation plus source version the release was validated against |
| 0143 `catalog_policy_consumer_ack` | Trusted consumer, release/aggregate and source-event identity, enforced revision, APPLIED/REJECTED with an allowlisted safe reason; a reason is required exactly when the result is a rejection, and the subject of a release-level ack must be that release |

Each revision is one literal CREATE statement with a DROP downgrade. Every foreign key is
composite and same-company; nothing references another service's table. All quantities are
`NUMERIC(19,4)`, enums are `VARCHAR` with checks, and no operation flag is JSON. Catalog stores
no balance, movement, transfer or count: those remain Billing's, and a location's stock half of a
deactivation is fenced behind its acknowledgement rather than inferred here.
## Live product authoring singleton - decision 2026-10-28

Migration 0210 adds `company_product_authoring_configuration`: tenant/company unique,
UUID identity, `product_family_sku_enabled` boolean, integer `row_version`,
`change_reason` and standard audit fields. It includes the inherited tenant index.
Absent configuration resolves to simple mode without a row insert on read.
The compatibility roster is seeded separately from DDL. This current control does
not alter dated configuration revisions, product adoption or stock storage.
See [the simple product API](simple-product-api.md) for contracts and rollout.

## Simple creation receipts and Model control - decision 2026-11-04

0217 adds the typed `model_mode` Product Configuration option with INHERIT for
historical rows and DISABLED in new-company starter configuration. 0218 adds
`simple_product_creation`, unique by tenant/company/command key and product code.
Its request hash, step, pending native command, owner receipts and bounded lease
allow one Save to resume through activation, pricing and opening posting. It
stores no stock balance. Accounting owns per-product opening controls (0232),
quantities, valuation and financial effects. Populated receipt rollback is refused
to preserve recovery links. See [delivery and review evidence](simple-product-ready-plan.md).
