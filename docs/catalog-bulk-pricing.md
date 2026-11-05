# Catalog bulk operations and customer price levels

**Status:** Catalog-owned implementation design, 2026-09-11; API/DB only.
**Scope:** Customer/party masters remain Billing-owned. Catalog stores pricing mappings and
minimal read-only source projections. Catalog imports never create customers or post stock.
See [final Catalog inventory](catalog-table-inventory.md) and [inventory integration](catalog-inventory-integration.md).
**Read with:** [Product design](catalog-product-design.md) and [schema](catalog-schema.md).
**Promotion composition:** [Schemes, coupons, limits and returns](catalog-promotions.md).
**Numeric/product controls:** [Precision, price basis and configuration](catalog-product-configuration.md).
**Expanded pricing authority:** [Purchase, MRP, unit/batch prices, estimates, recipes and guards](catalog-pricing-design.md).
**Location controls:** [Main, warehouse policies and stock allocation](catalog-warehouses.md).

## 1. At least three configurable customer price levels

A company can enable the proposed multi_price_levels capability. Price 1 is the ordinary
default; enabling the capability idempotently creates Price 2 and Price 3 definitions.
Names are editable (Retail, Wholesale, Dealer, for example), and more levels can be added.
There are no price1/price2/price3 columns on item and no hard-coded A/B/C customer logic.

| Example customer pricing type | Assigned level | Example price for the same SKU/unit |
|---|---|---|
| A / Retail | Price 1 | INR 100.0000 |
| B / Wholesale | Price 2 | INR 90.0000 |
| C / Dealer | Price 3 | INR 85.0000 |

Amounts are illustrative, all on the same tax-exclusive basis. Seeding levels does not invent
prices. Missing-price coverage is reported before a level is used for a customer.

A price_level is a company master independent of currency. Existing price_plan remains the
currency/purpose/tax-basis book under that level. Each sale level has at most one plan per
currency; item_price_series and its effective rows/tiers supply SKU/unit/channel prices.
Thus Retail INR and Retail USD share a level identity without any implicit FX conversion.
Purchase plans retain their own supplier/purpose rules.

Customer pricing type is a native, dated commercial-party attribute, separate from product
type, login role and many-valued marketing groups. Accounting now owns the live
`party_commercial_type` and dated `party_commercial_type_membership` masters; Catalog owns
type-to-level and customer-to-level commercial assignments. Catalog's customer/type/membership
projections still lack a live Accounting producer/consumer handoff, so buyer-specific lookup
fails closed until those source facts are populated and verified. The older Billing ownership
references in source contracts are historical and require replacement in that handoff.

### Selection and safeguards

1. Verify company/customer scope, feature state, authoritative customer pricing type and date.
   A sale `/prices/resolve` or `/prices/coverage` request may supply `party_id`; Catalog uses
   its active dated customer-pricing projection, never a caller-supplied type. Missing or
   ambiguous membership, inactive/ambiguous type, overlapping assignments, expired company
   policy or inactive resolved level fails closed. Omitting `party_id` is the declared walk-in
   path and uses the company default. Buyer-specific lookup requires `customer_pricing.read`.
2. Resolve level: permissioned explicit override with reason > customer-specific level assignment
   > customer-pricing-type assignment > company default. There is one applicable pricing type
   per customer/date. Walk-in/no-type customers use the declared default; stale/missing source
   data is an error, not proof that the customer has no type.
3. Resolve that SALE level's plan for the exact transaction currency. Filter required stock
   scopes, then use the fixed audience > stock scope > unit ranking in the pricing
   companion. Customer audience outranks channel/standard; equal-rank matches fail. PURCHASE
   resolves a configured purchase book and supplier audience; REFERENCE_RETAIL is explicit only.
   Contract-agreement contexts remain unavailable until their own source/rules exist.
4. Apply the declared quantity tier to establish the regular-price baseline. Quantity tiers
   are independent of customer price levels. Validate pack/unit and effective-date context.
   Preserve price amount, positive price_basis_quantity and numeric revision. Calculate with
   the exact declared basis; do not round a normalized unit rate before multiplying quantity.
   Lot splitting preserves the original compatible billed-line tier quantity. A supported recipe
   requiring actual cost/allocation/tax returns an explicit incomplete reference state until its
   owner supplies those facts. Billing applies schemes/coupons/manual benefits and final guards;
   Catalog price resolution does not run a second basket discount calculator.
5. Return source customer/type/assignment/level/plan/series/tier IDs and versions, currency,
   unit basis, tax basis and any fallback/override reason. Billing revalidates authoritative
   context and snapshots the selected commercial facts when posting.
   The current Catalog price response exposes `buyer_party_id`, `buyer_price_level_id`,
   `buyer_pricing_chain` and source IDs so a caller can explain the selected level. Voucher
   invoice capture still accepts an entered rate; authoritative buyer-price snapshot and
   posting-time revalidation require a separate Catalog-to-Vouchers source/evidence contract.
   Until that contract is implemented, this lookup is a price suggestion, not proof that a
   posted invoice used the buyer's assigned price.

Ordinary callers cannot choose an arbitrary cheaper plan/level or spoof customer type.
An administrative quote/override endpoint requires its own permission. Customer-facing
responses expose their authorized result, not every customer's price table.

The default missing-price policy is ERROR. A company may explicitly configure one fallback
level, using the same currency and compatible declared unit basis; record its use in the
result. Fallback applies only to absent price coverage, never to ambiguity, invalid data,
scope failure, stale context or a violated price floor. Zero is a price, not a missing value.
There is no recursive fallback chain or cheapest-price selection.

When multi_price_levels is off, only the baseline PRICE1 sale level is eligible for new
transactions; setting another default or requesting an alternate level requires the capability.
The feature key does not exist in current code: activation requires compatible registry,
Identity management and Billing use contracts under their owner plans; Catalog supplies its
consumer/configuration checks and tests. Apply the existing irreversible-use policy
after a customer-price-level posting; historical assignments/prices remain readable.
Mapping changes and retiring a level are effective/controlled operations, not history deletion.

## 2. Bulk import workflow

**Template/upload → stage → validate → preview → explicit commit → results.**

- Inputs: UTF-8 CSV, a versioned XLSX workbook, or the equivalent JSON batch. Workbook sheets
  represent typed resources: groups, units, manufacturers, families, SKUs, packs, identifiers,
  category links and prices. Opening stock uses a separate Billing import endpoint.
- Templates come from the code registry plus authorized effective custom-field definitions.
  Include schema version, documented identifiers, required/optional columns, units/currency,
  mode and examples. Layout-hidden fields remain governed by actual field policy.
- Bind a job to one tenant/company and mode: CREATE_ONLY, UPDATE_ONLY or explicit UPSERT.
  Cross-company files must be split; there is no cross-service atomic upload.
- Match by immutable ID, or exact company-scoped stable code/external key. Display names do
  not identify records. When both ID and code are supplied they must agree. Repeated target
  keys inside a file are rejected, not resolved by row order.
- Resolve declared master references and staged dependencies in topological order. Missing
  masters fail by default; masters included on explicit workbook sheets can be created first.
  Do not silently create a new group, manufacturer, unit or custom-field definition from a typo.
- Validate types, native requirements, company features, permissions, custom fields, variants,
  conversions, identifiers, tax/price intervals and duplicate values using the ordinary domain
  handlers. Validate concurrent uniqueness again during commit.
- Produce counts and record-level actions: create, update, unchanged, invalid or blocked by
  dependency. For updates show permitted before/after values, versions and downstream impact.
  Error output identifies sheet/row/column/code with safe messages.
- Default: validation errors prevent commit. The caller may explicitly accept the independent
  valid subset, producing a new reviewed selection digest. Dependants of excluded/failed
  records are blocked; silently skipping bad rows is not a successful full import.
- Commit references the reviewed job revision/digest. Changed input, definitions, relevant
  company policy or target versions requires revalidation. No modifications occur during preview.
  During execution, approved earlier change sets may create planned masters or advance their
  versions. Advance dependent expectations only from those recorded job effects; do not treat
  them as outside edits or silently accept an unrelated concurrent change. Preserve the frozen
  selection and revalidate against exact approved resulting definitions where required.

Raw uploads are private, bounded, short-lived artifacts in the owning service's MySQL-backed
staging storage for this delivery; no new datastore is required. Workers read normalized staged
records. Set upload, expanded-XLSX, row/column/cell and concurrency limits before release;
reject macros, external links and formula cells. Preserve codes/GTIN/IMEI as text and parse
money/quantities from decimal lexical values without a float intermediary. Return safe
CSV/XLSX error reports with spreadsheet formula-injection protection.

### Transaction and retry contract

Use a reusable bulk-job engine in libs/platform, with Catalog/Billing-specific validators
and writers. Long work executes in existing workers; the API returns 202 and a job URL.

- The default large-job unit of commit is a bounded change set for a domain aggregate,
  not an arbitrary SQL row. A SKU with its attributes/identifiers is committed together.
  Price changes may group all selected levels for one SKU into one same-DB transaction.
- Small batches can request ATOMIC mode within documented limits (proposed: 100 root
  aggregates / 1,000 child records, one company/database). Reject oversized atomic requests.
  No cross-service atomic mode, and no promise that a 50,000-row job is one transaction.
- Large jobs report per-change-set results. on_error defaults to STOP; CONTINUE_INDEPENDENT
  is explicit. Earlier successful change sets remain committed when a later one fails.
  Final states distinguish SUCCEEDED, PARTIAL, FAILED and CANCELLED.
- Store each change-set effect marker, result versions, audit/outbox and business mutation
  in the same transaction. Redelivery/resume must not reapply an increase or create a duplicate.
  Source-system/external identity also prevents a new upload/request key duplicating a create.
- Cancellation stops new change sets; it does not undo committed work. Retrying reuses immutable
  recorded actions for unapplied records. Editing a failed row creates a new validation revision.
  Completed change sets stay sealed across revisions; a requested correction is a new job.
  Effect uniqueness uses job plus stable logical change-set ID, not a retry/revision ID that
  would allow an already committed percentage adjustment to run again.
- There is no universal undo. A permitted master correction is a new version-aware job;
  effective prices/tax require correction history, and posted stock requires Billing reversal.

Opening imports keep each complete document, tracking allocations and financial posting atomic.
Catalog master-import success never implies that a related Billing opening document posted.

## 3. Bulk update workflow

Two entry points share the same preview/commit job contract:

| Entry point | Selection and intent |
|---|---|
| UPDATE_ONLY file / JSON batch | Per-record ID/code, expected_version and only the fields/actions to change |
| Filter-based bulk action | Authorized typed filters (group/subtree, brand, type, etc.) plus allowlisted operation; materialize exact IDs/versions at preview |

Freeze the selected IDs at preview; never rerun a broad filter during execution and accidentally
include newly created records. Export-for-update includes IDs/versions and only authorized
fields. expected_version is required for update files; a missing version must trigger an
explicit fresh preview, never a blind overwrite.

Supported operations include set field, set-if-empty, category add/remove, profile assignment,
lifecycle action, dated group reassignment, reset tax override to inheritance and effective
price replacement. Changes to immutable kind/base unit/tracking cannot be forced through a job.
A group tax/default update uses its native impact/publish action and does not rewrite every SKU.

- Omitted/blank update cells mean unchanged. Clearing a nullable value requires explicit
  clear_fields; clearing an inheritance override uses its reset action. Zero and false are
  explicit values. Create-mode blanks follow defaults/requiredness.
- Child collections are patched by stable keys. Omitted children are retained; removals and
  full replacements require explicit actions and all relevant permissions.
- Custom fields use registered keys and their effective validators/policies. Definitions
  must already exist in Identity; bulk data import cannot become an admin-definition bypass.
- Percentage/fixed price adjustments are allowlisted domain actions with explicit level(s),
  currency/unit scope, effective date and rounding. Compute old/new values during preview.
  Never accept arbitrary formulas, Python, SQL or spreadsheet expression evaluation.
- Recheck actor authority and relevant configuration before each change-set transaction;
  record-level conflicts are reported without overwriting another user's intervening edit.
  Original submitter authority is used, not unrestricted worker credentials.
- Persist before/after evidence and source versions safely. Reports and previews enforce read
  policies; a user with write-only authority must not receive a leaked old value.

Example: increase Price 2 by 5% for all active Phone SKUs from a selected future date.
The preview freezes eligible SKUs and existing price-series versions, shows rounded old/new
prices, and checks discount/MRP constraints. Commit creates effective history. Existing posted
invoices and Price 1/Price 3 remain unchanged. If a selected price changed after preview, that
change set conflicts; the system does not apply 5% to an unexpected new baseline.

## 4. Importing and updating the three prices

Canonical price records are long-form:

| sku | price_level | currency | unit_code | amount | valid_from |
|---|---|---|---|---|---|
| PHONE-001 | PRICE1 | INR | PCS | 100.0000 | 2026-10-01 |
| PHONE-001 | PRICE2 | INR | PCS | 90.0000 | 2026-10-01 |
| PHONE-001 | PRICE3 | INR | PCS | 85.0000 | 2026-10-01 |

An optional convenient workbook sheet may have price_1/price_2/price_3 columns. Its template
pins those columns to actual level IDs and the plan's unit/currency/tax-basis contract,
then normalizes them into the same records. Renaming levels cannot redirect an old workbook.
Omitted level columns mean no change; blank is not zero and does not delete a price.

Group requested levels for the same SKU into one price change set so a failing Price 3 does
not leave only Price 1 and Price 2 changed for that SKU. Whole-file consistency across many
SKUs requires bounded ATOMIC mode; a large resumable job can finish partially and reports it.
Each selected quantity tier must be explicit; a tiered schedule cannot be flattened accidentally.

Bulk export of all price levels needs price-management/read authority; it is not available
to an ordinary customer who can only see their own resolved price.

## 5. API and persistence requirements

| API | Contract |
|---|---|
| GET /catalog-import-templates | Versioned, authorized CSV/XLSX/JSON schema and column mappings |
| POST /catalog-imports | Stage upload/batch and mode; return job ID |
| POST /catalog-imports/{id}/validate; GET /catalog-imports/{id}/preview | Validate and return bounded reviewed results/digest |
| POST /catalog-imports/{id}/commit; POST /catalog-imports/{id}/cancel | Explicit reviewed execution/cancellation |
| POST /catalog-bulk-updates/preview | Freeze selected IDs/versions and typed operations |
| POST /catalog-bulk-updates/{id}/commit; POST /catalog-bulk-updates/{id}/cancel | Same job semantics and scoped permissions |
| GET job; GET job/records; GET job/errors | Status, paginated outcomes, protected error artifact |
| CRUD /price-levels; GET/PATCH /pricing-policy | Level master and default/fallback policy; company capability managed through Identity |
| GET/PUT /customer-type-price-levels; GET/PUT /customer-price-levels | Effective native assignments against authorized party projections |
| POST /prices/resolve | Customer/context-driven selection; explicit override needs permission |

Route-specific grants accompany underlying item/master/price grants; import access alone
does not authorize every action. Upload, preview and commit carry idempotency/revision
contracts; unchanged replay is safe. Audit records reference the job/change set.

Owned tables are detailed in the schema companion: price_level, company_pricing_policy,
price_level_assignment_scope/history, local customer/type projections; bulk_job,
bulk_job_record, bulk_change_set, bulk_change_set_effect, bulk_job_dependency and
bulk_import_artifact. Common shapes/execution live in libs/platform; service ORM stays local.

## 6. Required acceptance

- Customer A/B/C receives Price 1/2/3 for the same SKU; more than three levels work.
- Disabled capability, unauthorized cheap-level selection, stale membership, missing coverage,
  explicit fallback, zero price, unit/currency and quantity-tier cases are covered.
- Old posted documents retain their resolved level/amount after mapping or price changes.
- Duplicate rows, invalid references, custom-field errors and partial workbook dependencies
  are caught during validation and rechecked on commit.
- Stale versions, permissions revoked after preview and newly matching filter records cannot
  cause unintended updates.
- Creating a group/family and then dependent SKUs in one reviewed import succeeds without
  a false stale-version conflict; an outside group/tax change still requires revalidation.
- A worker crash after DB commit but before acknowledgement creates one effect on retry,
  including percentage changes and all-level price change sets.
- Atomic mode fully rolls back; large-job failure/cancellation exposes precisely what committed.
- Opening imports and master/price changes cannot bypass their ordinary posting/history rules.

## Promotion definition imports and external coupon issuance

P5 reuses these jobs for campaign/promotion/program drafts and future rule/target/cap revisions.
Static validation and publication require the underlying promotion authority; importing a draft
does not publish it. Reviewed publication has its own immutable revision/dependency digest.
Billing owns separate code generation/import jobs, scoped customer binding and protected code
artifacts. A repeated request or worker retry must not issue another usable batch. Exact code
canonicalization, duplicate claims and program readiness are checked before issuance.

Cross-service authoring/publication/issuance is an explicit dependency chain with visible partial
results, never one advertised atomic import. Bulk tools cannot patch redeemed counts, active holds,
posted allocations or original coupon history. Changing future caps cannot reduce capacity below
already committed plus held usage. The [promotion design](catalog-promotions.md) is authoritative
for code security, rule requiredness, calculation, limits and returns.

## Warehouse definition imports and defaults

Use exact company-scoped location IDs/codes. MAIN is reserved: imports may use its ordinary
authorized update/policy paths but cannot create, deactivate or replace it. Additional selectable
locations require multi_godown. Opening/receipt/issue rows retain explicit resolved locations
and validate the matching operation flag, product restrictions and current actor scope.
A default change or master update never moves quantity. Transfers and opening effects use
Billing's native posting handlers, including transit legs and stable source-effect identities.

## Optional BOM and route imports

[M3 manufacturing bulk](catalog-manufacturing-design.md#8-api-bulk-and-persistence) reuses this
pipeline for operation/route revisions, BOM drafts/components/substitutes/outputs and dated
assignments. Freeze line identities and a complete dependency graph; publish children before
parents. Each revision is atomic; cross-BOM jobs are resumable and activate only a complete release.

Quantity/yield/component/route/allocation changes create new revisions and show where-used,
estimate and default-assignment effects. Bulk updates do not edit published BOMs or running
production orders. Revalidate authority, versions and graph generation at commit. Reject actual
production consumption/output, WIP, cost, physical lot/serial and manufacturing-ledger imports.

## Decision log

- 2026-11-04: Removed location-based price ranking and warehouse price scopes from
  the pricing/import plan. Warehouse definition imports and stock allocation remain separate.

- 2026-10-30: Native product tax assignments, price draft imports and price ADJUST
  no longer accept the retired free-text `source_reference`. Reusable templates
  derive required columns from the updated schemas. Previously staged uncommitted
  actions containing the field require a fresh corrected preview; committed
  effects and immutable historical audit records remain retained.

- 2026-10-12: Connected verified party/type assignments to ordinary dated SALE item-price
  resolution, retaining the administrator-only explicit book/level override. Refused missing,
  inactive and ambiguous buyer facts and expired company policies. Preserved a walk-in default
  when no buyer is supplied. Accounting now owns the commercial type master; its Catalog source
  feed and voucher posting-price enforcement remain separate owner boundaries.

- 2026-09-11: Added optional BOM/route bulk definition contracts using existing jobs and releases;
  no parallel import engine or manufacturing execution writes.

- 2026-09-11: Added purchase-term/reference-cost/MRP/guard import contracts and deterministic
  unit/lot/declaration price scopes. Bulk changes cannot create physical lots or update actual cost.

- 2026-09-11: Restricted this implementation to Catalog master/price/configuration/promotion
  definition jobs. Billing customer source, coupon issuance and stock jobs remain external;
  Catalog import permission never authorizes their source writes.

- 2026-09-11: Added location/default import rules and Main protection; warehouse policies
  cannot bypass native stock posting, multi_godown or per-operation authorization.

- 2026-09-11: Added quantity/rate precision and explicit price-basis validation to direct/bulk
  paths. Product Configuration adoption uses reviewed jobs; no silent rounding or field clearing.
- 2026-09-11: Separated regular-price selection from Billing's sole promotion evaluator.
  Extended reviewed jobs to promotion drafts and separate, idempotent Billing code issuance.
- 2026-09-11: Aligned the consolidated sequence: Billing party source in C2/C5, pricing in C8,
  Catalog bulk in C10 and stock bulk in C14. Clarified in-job dependency/version advancement.
- 2026-09-11: Made customer-type pricing with at least three enabled levels explicit, separate
  from quantity tiers. Added concrete import/update workflows, review/version semantics,
  bounded atomicity, durable retry and backend contracts. No runtime implementation claimed.
