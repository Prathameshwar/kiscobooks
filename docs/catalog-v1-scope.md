# Catalog v1 scope

**Decision date:** 2026-09-12. **Scope:** API/database, workers and required shared mechanisms; no UI.
This document records the selected release scope and service boundaries. API behavior is
documented in the [Catalog service guide](../apis/catalog/README.md).

**2026-10-10 ownership amendment:** The [Vouchers plan](vouchers-plan.md) replaces the
planned Billing and Payments APIs. Vouchers owns transaction documents; Accounting supplies
parties and authoritative posting. Its proposed stock/value extension remains future work.
Catalog's implemented release scope is unchanged; payroll and related work are excluded.

## Confirmed decisions and workload interpretation

| Topic | v1 decision |
|---|---|
| Business scope | Products/services, commercial prices and tax rules; inventory transactions later |
| Ownership | Separate catalog per company; no shared tenant-wide product or price master |
| Jurisdiction | India GST |
| Workload | User answered "2000" to the combined product/import-size question. Working interpretation: 2,000 items/SKUs per company and 2,000 input rows per import |
| Identity dependency | Explicit approval to implement the minimal Identity-owned company, feature and field-policy sources required by Catalog |

The two workload numbers are initial benchmark targets, not verified capacity or hard-coded
business limits. Variant expansion, historical price/tax rows and reference records add to the
SKU count and must appear in benchmark fixtures. Concurrency, maximum file bytes, retention and
latency objectives still need measured engineering bounds; 2,000 does not specify those values.

## Company isolation

Every company owns its products, groups/categories/types, brands/manufacturers, units/packs,
configuration, price books, tax assignments, aliases and import jobs. Codes may repeat in two
companies; references, lookup candidates and uniqueness checks must use the complete owning
scope. A tenant-level role still needs authority for the company addressed by the operation.

Keep tenant filtering in libs/platform and enforce company/object/field access in each workflow.
Same-company composite foreign keys protect local references. Lists, options, search, cursors,
bulk previews/errors, history and idempotency replay must not reveal another company's records.
Tenant field definitions can remain Identity-owned reusable metadata; company values remain
isolated. Shared read-only statutory/ISO references do not make business catalogs shared.

## Included capabilities

| Area | Deliverable |
|---|---|
| Masters and configuration | Existing unit conversions/packs, groups/subgroups, categories, product types, manufacturers/brands, attributes and reusable profiles; complete aliases/external keys/usage and native Product Configuration needed by the product workflow |
| Products/services | Families, simple SKUs and variants; goods/service validation, unit bindings, product/pack barcodes, descriptive custom fields, lifecycle and immutable activated structure |
| Product inventory definitions | Optional tracking/expiry/serial/IMEI requirements and existing profile bindings; these describe a product and do not create a physical batch, device or balance |
| Stock-location definitions | Permanent Main and protected internal-transit identity, stores/godowns, non-stockholding groups and bins, typed operation-policy revisions, company activity defaults, restrictive SKU location policies and per-location replenishment targets, published releases and trusted consumer acknowledgement. Definitions only: no balance, movement, transfer or count. Phased in [catalog-warehouse-plan.md](catalog-warehouse-plan.md) |
| Pricing | Retain the earlier requested purchase reference, MRP, PRICE1/2/3+, explicit unit/pack prices, quantity tiers, dated history, price precision and minimum selling-price controls; bounded reference-cost recipes must name their source |
| Customer pricing | Catalog owns price-level mappings; authoritative party identity/type membership comes from Accounting. Company-level prices work independently; customer/supplier-specific resolution requires the implemented, verified source adapter |
| Tax | India GST classifications, dated rule/component revisions, company/group/family/SKU assignment and inherited resolution; explicit treatment and price tax basis |
| Bulk | Company-scoped product/master/price/tax/stock-location create/update/upsert, validation and preview, version checks, resumable jobs, current actor/field authority and protected results. A quantity, transfer, count or trading party has no importable resource at all |
| API quality | Typed filters, indexed search, stable sorting, signed keyset paging (50 default/200 maximum), lean lists, optimistic concurrency, idempotency and transactional audit/outbox |

Actual costs, lot/declaration prices and any rule needing physical allocation stay unavailable
without authoritative Accounting posting facts. Missing or denied facts never become zero cost, an invented
customer, an arbitrary fallback price or an assertion of available stock.

## India GST implementation boundary

Model HSN goods and SAC service classification explicitly, with source/version evidence.
The official [CBIC classification explanation](https://cbic-gst.gov.in/pdf/press-release/Press-release-HSN-code-SAC-issue.pdf)
describes these classification systems; its historical invoice thresholds are not v1 constants.

Provide native CGST, SGST, UTGST and IGST component definitions and dated applicable cess rules
where the supported notification requires them. Keep component applicability separate from a
product's classification. CBIC describes GST's component structure and place-of-supply basis in
[its GST overview](https://cbic-gst.gov.in/about-gst.html); transaction-specific selection remains
the Accounting posting owner's responsibility, using the Vouchers document's supplier/recipient,
registration, location and supply facts, with local validated definitions.

The design must distinguish taxable, nil-rated, exempt and non-GST configuration from missing
configuration. Zero-rated supply and reverse-charge applicability require explicit transaction
context; neither is inferred from a generic zero product rate. Tax-inclusive/exclusive price
bases and effective dates must be explicit in previews, published definitions and history.

Use reviewed, effective-dated official notifications when loading real classifications/rates.
Do not hard-code a universal slab list or treat an old FAQ/ready reckoner as current authority.
The [GST Council services reference](https://gstcouncil.gov.in/gst-rates-services) contains dated
historical documents; each imported rule must identify the actual applicable notification and
period. Choosing India GST resolves the jurisdiction question, not rate-dataset validation.

Catalog publishes reproducible tax definitions and their provenance. Invoice tax determination,
GST returns, e-invoicing, e-way bills, statutory posting and payment remain outside Catalog.

## Deferred release work

Opening stock, receipts/issues, transfers, damaged stock, adjustments, counts, physical
batches/serials/IMEIs, product stock ledgers and actual valuation remain later work in the
Vouchers plan: Vouchers workflows and proposed Accounting stock/value posting.
Operational multi-store enforcement and stock-dependent pricing wait for those real contracts:
Catalog's v1 location definitions publish policy and report it as pending until a trusted consumer
acknowledges an enforced version, and a non-Main deactivation stays unavailable until that fence
exists. `item_supplier_term` waits for the authoritative Accounting party projection adapter.
The design is [warehouse definitions](catalog-warehouses.md); the phasing is
[catalog-warehouse-plan.md](catalog-warehouse-plan.md).

Campaign/scheme/coupon administration and optional BOM/manufacturing are scheduled after this
core v1 release. Their requirements remain in the [promotion](catalog-promotions.md) and
[manufacturing](catalog-manufacturing-design.md) design contracts.
Basic regular-price tiers and commercial discount limits remain part of pricing.

Also deferred to v1.1 (2026-09-19 decision, see
[completion plan](catalog-v1-completion-plan.md) §2):

- **Governance rows `catalog_hierarchy_state` and `master_change_job`.** Reparent locking rides
  `catalog_policy_state` today; the reviewed impact-preview workflow those two rows enable is v1.1.
  Schema-doc references to them are pruned in the same sweep.
- **Table rename `item_barcode` → `product_identifier`.** v1 widens the existing table with
  `identifier_type_code` / `namespace_code` columns bound to the new `identifier_type` and
  `identifier_namespace` masters. The rename waits until every consumer is off the older client.

## Decision log

- 2026-10-10: Replaced future Billing/Payments dependencies with Vouchers document workflows
  and Accounting party/posting authority. Stock/value posting remains proposed, not delivered.
  Existing wire identities/consumer allowlists need explicit compatibility work in V0.

- 2026-10-05: Reverse-charge applicability is a stored, dated rule fact; the transaction context
  still decides whether RCM applies to a document. See [tax-accounting-plan](tax-accounting-plan.md).
- 2026-09-12: User selected products/services, prices and tax rules for v1 and deferred inventory
  transactions; selected separate catalogs per company and India GST; explicitly approved the
  minimal Identity sources. Earlier pricing requirements remain applicable.
- 2026-09-12: Interpreted the single workload answer "2000" as both 2,000 SKUs/company and
  2,000 rows/import; recorded it as a working benchmark assumption, not a hard limit or proof.
- 2026-09-13: Removed execution tracking and retained the release scope, ownership and
  workload decisions in this document. API contracts remain in the linked service guides.
- 2026-09-17: Added Catalog-owned stock-location definitions to v1 on the user's decision.
  Operational multi-store enforcement stays deferred to Billing; publication reports a pending
  enforced version rather than claiming a stop in another database.
