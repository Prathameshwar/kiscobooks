# Catalog V1.3 pricing API

Implementation scope: company-owned regular price definitions.
All paths below are under `/v1/companies/{company_id}`. The generated
`apis/catalog/openapi.json` is the exact request/response contract.

## Authoring sequence

1. `POST /pricing/bootstrap` creates PRICE1 and, when verified `multi_price_levels` is enabled,
   PRICE2/PRICE3. Bootstrap is idempotent and creates no amounts. Run it after enabling the
   feature; Catalog does not synchronously provision rows inside Identity's feature transaction.
2. Create a `/price-plans` book with SALE, PURCHASE or REFERENCE_RETAIL purpose, explicit
   currency and tax basis. SALE requires a level. Only a book's name and descriptive custom
   fields can be patched; purpose, level, currency and tax basis remain immutable.
3. Publish `/company-pricing-policies` with dated default/fallback levels, optional purchase
   book and separate sale/purchase unit-selection modes. Create the SKU's `/price-scopes`,
   dated `/price-numeric-revisions` and stable `/price-series` for its book and unit revision.
4. `POST /price-drafts` accepts FIXED, TIERS or FORMULA native terms. `PUT /price-drafts/{id}`
   replaces an unpublished draft with `expected_version`. Preview using
   `GET /price-drafts/{id}/preview`; publish using `POST /price-drafts/{id}/publish` with
   the preview's row version, policy generation and Identity source version.
5. Read immutable prices through `/prices` and `/prices/{id}`. Forward replacement names
   `supersedes_id` and `expected_previous_version`; its predecessor closes on D-1. Dates
   are inclusive. New published history cannot begin before the company's current business
   date. Original amount, source, unit and numeric terms remain preserved.

All writes require `Idempotency-Key`. Every mutation uses the company policy lock, current
actor and changed-field authority, transactional audit/outbox, optimistic versions and a
receipt. Replays recheck current authority. There is no posting or fiscal-period mutation.
The in-process limiter allows 120 pricing writes per tenant/company/actor per minute;
deployment must additionally configure the shared gateway limit. This repository does not
yet contain the nginx deployment configuration.

## Resolution and exact quantities

`POST /prices/resolve` requires SKU, currency, unit revision, business date and original
billed quantity. `POST /prices/coverage` uses the same body, returning `MISSING` for absent
coverage. Invalid, stale or denied dependencies are errors; they never trigger fallback.

Ordinary SALE uses the dated company default level. Only configured absence fallback is
allowed. Explicit administrative level/book selection requires `price_plan.override` and
an `override_reason`. PURCHASE uses its configured reference book and additional purchase
read authority. REFERENCE_RETAIL requires its explicit book. No currency conversion occurs.

An explicit unit/pack price takes precedence. With `EXACT_BASE_DERIVATION`, an absent unit
price may use an authoritative fixed conversion from a base price. Independently priced
packs need not equal base price times pack size. A measured conversion never uses nominal
quantity. Fallback levels use the same unit-selection policy.

Rates and quantities are exact decimal strings, persisted as DECIMAL(19,4). A rate amount
has an explicit `price_basis_quantity`; no rounded unit-rate copy is introduced. The result
returns exact consideration as integer-string `numerator`/`denominator`. For example,
0.1000 per 1000 at quantity 10 returns 1/1000. Entry must fit the dated price grid; quantity
must fit the product unit grid. Tiers begin at zero, remain contiguous and end unbounded,
with at most 64 tiers. Boundaries select using the original compatible billed quantity.

FORMULA accepts only MRP less percent, reference estimate plus markup, or reference estimate
target margin, with explicit rounding. References resolve at the requested date; formula
definitions are immutable and source IDs are returned. Markup and margin use different
formulas. No expression language, recursion or caller-provided cost is accepted.

## References and commercial rules

- `/reference-costs`: dated STANDARD_ESTIMATE, REPLACEMENT_ESTIMATE or SERVICE_ESTIMATE,
  tax exclusive, with source evidence. Service estimates require services; goods estimates
  require goods. These are estimates, not inventory valuation or actual purchase costs.
- `/product-mrps`: dated tax-inclusive goods declarations for an explicit unit/pack and
  jurisdiction. No MRP conversion between packs. Required MRP must exist for that pack;
  omitted resolution jurisdiction uses the company's country.
- `/commercial-guard-rules`: fixed minimum/maximum or estimate-based minimum markup/margin,
  with BLOCK or REQUIRE_APPROVAL severity. Multiple applicable minima/maxima combine to
  the strictest bounds; an empty range fails. BLOCK bounds remain independently enforced.
- `/commercial-policy-scopes` and `/discount-ceilings`: company/group ancestry/family/SKU
  limits combine to the strictest percentage. `/item-commercial-policies` explicitly permits
  zero SALE prices where appropriate; missing policy never means a free sale.
- PURCHASE fixed drafts may carry gross quote and unconditional discount terms. The exact
  net must reconcile. SALE rules do not silently constrain purchase or retail references.

Formula evaluation rejects incompatible source/book tax bases. Guard comparisons that need
missing tax context return `NEEDS_TAX_CONTEXT` without an amount or consideration.
Known same-basis BLOCK bounds still apply when another bound needs tax context. For example,
an exclusive floor remains enforceable alongside an inclusive MRP, and an inclusive book
cannot exceed its same-pack MRP merely because an exclusive guard also applies.
Responses identify source, price, numeric/unit, tier and guard IDs and applicable approval
rules. `final_guard_validation_required` is always true: Billing must check actual basket
benefits, tax, allocation, authorization and final consideration before posting. Catalog
does not grant an approval or execute a discount, stock movement or purchase.

## Draft readiness and dated coverage

`GET /price-drafts/{id}/preview` evaluates every tier, fixed rate or live formula against
known applicable BLOCK bounds. Drafts may retain commercial errors for editing, but native
publication, bulk validation/commit and required-price activation reject those errors.
Approval-only bounds remain evidence for Billing and do not become publication blocks.

The preview distinguishes commercial validity from publication-history readiness:

- `valid`, `issues`: commercial/coverage assessment, with issue code, effective date and
  safe explanation. Structural validation and denied dependencies retain their existing
  error responses; they are not silently converted into missing coverage.
- `publishable`, `publication_issues`: whether the assessed draft can enter the current
  history. Same-date overlaps, past publication and already published drafts are explicit.
  `supersedes_id` and `expected_previous_version` suggest the sole eligible predecessor for
  a forward replacement. Publication still rechecks authority, versions and overlap under
  its existing lock; a preview is not a reservation.
- `coverage_valid_to`: latest date covered by the draft interval and its declared mandatory
  unit/reference dependencies; null means no known end. A gap identifies the first missing
  date and blocks publication until the price interval or source schedule is corrected.
  This is coverage evidence, not a guarantee that all commercial checks pass on every date.
- `guard_ids`, `approval_guard_ids`, `source_ids`: the evidence considered, including known
  future dependencies. `transaction_requirements` contains `TAX_CONTEXT` and/or
  `MEASURED_QUANTITY` when static comparison needs transaction facts.
- `final_guard_validation_required` is always true. A valid, publishable definition still
  requires Billing's final tax, discount, measured allocation and approval checks.

Review checks the declared price interval against its pinned unit revision, contiguous
formula references, required MRP and estimate sources used by commercial guards. It evaluates
rates again at known source, guard and free-sale policy boundaries. A dependency history is
bounded to 1,024 rows and a schedule to 64 future review dates; use shorter price intervals
when those bounds are exceeded. Unknown future changes are not predicted, and runtime
resolution continues to validate current dated dependencies. Measured comparisons defer only
at static assessment; runtime never substitutes a nominal conversion for actual allocation.

## Permissions, lists and native storage

Existing `price_plan.read/manage` govern regular definitions. Publishing dated definitions
also requires `price_plan.publish`. PURCHASE data additionally requires
`purchase_price.read/manage`; estimates use `reference_cost.read/manage`. CompanyAdmin
receives these management keys; TenantAuditor receives the two new reads. Sales roles gain
no purchase-cost, estimate or administrative override permission. Field denies apply to
native/custom fields, references, previews, resolution, filters, search and sorting.

Every listed resource has GET collection/detail operations. Child collections are
`/price-tiers`, `/purchase-price-terms` and `/price-formulas`. Growing collections use lean
schemas, signed keyset cursors (50 default, 200 maximum), typed allowlisted filters and
stable ID/code sorting. Code/name search is prefix indexed where supported. Purchase rows
are filtered before paging; list reads do not load full detail/source/custom-field payloads.

| Migration | Table | Purpose |
|---|---|---|
| 0083 | price_level | Stable company level and ordinal |
| 0084 | price_plan | Immutable purpose/level/currency/basis; descriptive custom fields |
| 0085 | company_pricing_policy | Dated defaults, fallback and unit modes |
| 0086 | item_price_scope | Stable SKU-only owner |
| 0087 | item_price_numeric_revision | Dated independent price grid |
| 0088 | item_price_series | Unique book/SKU/unit/currency series |
| 0089 | item_price_draft | Editable native price aggregate |
| 0090 | item_price | Immutable published terms and predecessor |
| 0091 | item_price_tier | Contiguous quantity bands |
| 0092 | purchase_price_term | Gross, unconditional discount and net evidence |
| 0093 | item_reference_cost | Dated explicit estimate |
| 0094 | item_mrp | Pack/jurisdiction declaration |
| 0095 | item_price_formula | Bounded native live-reference recipe |
| 0096 | commercial_policy_scope | Typed company/group/family/SKU owner |
| 0097 | commercial_guard_rule | Fixed or estimate-derived bounds |
| 0098 | discount_ceiling | Dated percentage limit |
| 0099 | item_commercial_policy | Dated explicit free-sale permission |

Each table carries tenant/company scope, row version and audit fields. Composite local FKs
bind owners and price currencies. Draft/published child ownership is exclusive. Each
migration creates one table and supplies its downgrade. No cross-service foreign keys.

Customer/pricing-type assignments, supplier audiences, lot/declaration selection,
actual allocated costs, complete consumer releases/acknowledgements and final Billing execution
remain separate work. Audited withdrawal or replacement starting on the same date needs a
separate publication lifecycle; preview reports the conflict without rewriting immutable history.
Warehouse-specific regular pricing is excluded from the plan, not deferred API work.
Product tax masters and reviewed activation are implemented in [V1.4](catalog-v14-api.md),
and bulk administration in [V1.5](catalog-v15-api.md).

## Decision log

- 2026-11-04: Removed warehouse selection from future pricing scope. Current SKU
  pricing contracts need no API or storage change for this decision.

- 2026-10-30: Removed the product setup free-text `source_reference` from native
  price draft input/replacement and draft/published-price detail. Catalog 0212-0213
  drop the corresponding columns. Publication receipts, source IDs/versions,
  exact calculation and history continue to follow the existing contract.

- 2026-09-14: Unified static commercial checks for draft preview/publication, bulk native
  execution and required-price activation. Enforce every known same-basis BLOCK limit even
  when a different limit needs tax context. Expose bounded declared coverage and publication
  readiness without inventing Billing facts or a withdrawal lifecycle.
- 2026-09-12 follow-up review: direct tier, formula and purchase-term reads require the
  parent price/draft's SKU and family authority, matching the collection-read boundary.
- 2026-09-12: Implemented the authorized V1.3 company/SKU pricing slice with 17 native tables,
  exact rate bases, explicit unit selection, current-authority publication and protected reads.
  Real customer/supplier/physical-stock sources remain prerequisites for their wider design.
- 2026-09-12: Reserved levels are provisioned by the explicit idempotent bootstrap after
  verified feature enablement. Identity retains its transaction boundary and ratchet; no
  invented rates or synchronous cross-service writes are introduced.
- 2026-09-12: Formula recipes use dated live native references. Publication and resolution
  preserve reference IDs; actual cost formulas remain unavailable. Tax-incompatible final
  comparisons fail closed for Billing context. Company timezone governs forward publication.
