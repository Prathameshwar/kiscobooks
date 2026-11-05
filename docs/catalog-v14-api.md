# Catalog V1.4 tax definitions and activation

The original V1.4 implementation added tax definitions and activation through migration
`0110`. Product Tax corrections add three governance tables; Catalog now has 117 tables
through migration `0124`. OpenAPI and the generated TypeScript client contain the exact schemas.

## Definitions and history

| Resource | Operations | Purpose |
|---|---|---|
| `tax-classifications` | POST, GET list/detail | Dated sourced HSN goods or SAC services classification |
| `tax-categories` | POST, PATCH, GET list/detail | Company category; referenced categories cannot retire |
| `tax-rules` | POST, PATCH, GET list/detail | Immutable jurisdiction/kind/treatment/category and source evidence; descriptive name/custom fields can change |
| `tax-rate-series` | POST, GET list/detail | Stable rule and applicability identity |
| `tax-rates` | POST, GET list/detail | Effective rate publication with an explicit predecessor |
| `tax-rate-components` | GET list/detail | Immutable native components created with the rate |
| `tax-scopes` | POST, GET list/detail | Company, group, family or SKU owner |
| `tax-bindings` | POST, GET list/detail | Dated classification, treatment and rule bundles for sale or purchase |
| `tax-rate-previews` | POST | Validate a proposed rate and its complete affected schedule without saving effects |
| `tax-rule-applicabilities` | POST, GET list/detail | Native HSN/SAC exact or prefix matches; immutable once the rule is used |
| `tax-release-previews`, `tax-releases` | POST preview, POST publication; GET release list/detail | Signed coordinated changes |
| `tax-withdrawals`, `tax-history-actions` | POST withdrawal; GET action list/detail | Retained future withdrawal and predecessor evidence |
| `tax-impact-previews` | POST | Affected products and future date/direction readiness |
| `tax-impact-reviews` | POST start; GET detail; GET `{id}/findings` | Chunked background impact report for releases over the synchronous bound |
| `tax-configurations/resolve` | POST | Resolve an item's effective native bundles and authorized sources |

Definition reads require `tax_rule.read`; changes require `tax_rule.manage` and dated
publication also requires `tax_rule.publish`. Dependency permissions and field policies apply
to referenced products, groups and fixed-cess units. Company administration receives the new
publication permission through shared package 0.20.0.

Every write uses `Idempotency-Key`. Mutable masters require `expected_version`; dated
publications require `expected_generation` and `expected_source_version`. A replacement must
name `supersedes_id` and `expected_previous_version`; publication closes its predecessor in the
same transaction. It rejects overlaps and rewriting past business dates. Rate/release previews
require manage and publish authority, checked before any body validation, exercise the same
validation under the company lock, and roll back their records and audit outbox entries. Rate,
release and impact previews and impact-review starts share the per-user tax write budget of 120
requests a minute per company (429 beyond it), spent before the body is parsed. A supersession
must start strictly after the company business date: a predecessor already in force today is
never shortened (409), matching withdrawal. Publication commands audit as `.publish`; a
withdrawal also audits its target row as `.withdraw`. Publication repeats validation under the lock.

Each classification/rule/rate identifies its reviewed official Indian government HTTPS source,
reference and SHA-256 document fingerprint. The authorized publisher attests applicability;
Catalog does not download or independently verify that source. No production tax rate seed is
installed. Test definitions are explicitly synthetic.

`TAXABLE`, `NIL_RATED`, `EXEMPT` and `NON_GST` remain distinct. The three rate contexts are
`INTRA_STATE` (CGST/SGST), `INTRA_UT` (CGST/UTGST) and `INTER_STATE` (IGST). Components support
exact percentage or fixed INR compensation cess per declared unit/basis. Other cess levies are
outside this adapter. Percentage compensation cess can exceed 100;
stored amounts and percentages retain four decimals. Nil-rated definitions explicitly contain
zero GST and no cess; exempt/non-GST definitions require an explanation and no charged rates.

Resolution selects each bundle from SKU, family, dated nearest group and ancestors, then
company. `INHERIT` continues upward, `OVERRIDE` selects that bundle and `REQUIRE_EXPLICIT`
blocks inherited completion. Missing data and incompatible/denied references never become a
zero rate. Taxable/nil-rated readiness requires all three supply contexts with consistent GST
totals and compensation-cess definitions. Central/state or central/UT percentages and `rounding_mode` must be equal, and rounding is part of
the cross-context signature;
the ceilings are 20% for each component and 40% for IGST. Rule applicability must explicitly
match the selected HSN/SAC code. `transaction_determination_required` is always true: registration, place of supply,
per-document reverse-charge determination, zero-rated supplies, invoices and statutory posting belong to the posting
service (Billing, or Accounting for accounting vouchers). Reverse-charge *applicability* is a dated fact on the rule.

Lists use signed cursors, limits 1–200, default `id` ordering, code ordering/search on resources
with codes, and resource-compatible typed IDs/directions/bundles/date filters. A filter that
does not belong to that resource is rejected. Lean lists exclude source documents and custom
field payloads; field denies also govern filters, search, sorting and dependency resolution.

## Coordinated corrections and administration

POST `tax-release-previews` with `expected_generation`, `expected_source_version`,
`change_reason` and up to 100 ordered `changes`. Each change has a unique `key`, a `kind`
(`CLASSIFICATION`, `RATE`, `BINDING`, `WITHDRAWAL`) and its ordinary `definition`, using
the same generation/source pair. A binding may reference an earlier classification change
as `classification_id: {"key": "newClassification"}`. Publish that exact body with the returned
`preview_token` to `tax-releases` and an idempotency key. The token expires after 15 minutes
and is bound to tenant, company, user, input and company business date. One release advances
the policy generation once. Bulk supports the same native operation as `tax_release/PUBLISH`.

For example, a 5% to 12% change needs three coordinated rate definitions: 6%+6% CGST/SGST,
6%+6% CGST/UTGST, and 12% IGST. A lone inconsistent context is rejected. Replacing a
classification must also close and replace every dependent binding whose interval would
otherwise extend past it. A classification must cover the complete interval of each binding.
Explicit group/family/SKU bindings enforce goods/service compatibility before publication,
including empty groups with a restricted product kind. A company scope or `BOTH` group binding may
carry `item_kind` (`GOODS`/`SERVICE`); each kind keys its own history, so a mixed company has a
goods default and a services default. Resolution prefers the binding keyed to the product's kind,
then the all-kinds (`item_kind` null) binding. On a GOODS/SERVICE-only scope `item_kind` must match
it; the referenced classification and rule must match the binding's kind (422).

Withdrawal accepts a resource, target ID, expected row version, reason, publication versions
and `restore_predecessor`. Only strictly future records can be withdrawn. Original values and
source evidence remain queryable; effective-date lists and resolution exclude withdrawn rows.
Restoration uses recorded predecessor bounds and refuses overlaps or changed successor chains.
Legacy records without publication evidence require `restore_predecessor: false` and an explicit
replacement where needed. A coordinated withdrawal plus replacement permits correction at the
same future start date. Active products must retain complete tax coverage across known dates.
Downgrades never delete evidence: restoring old uniqueness/mapping constraints can fail when
retained corrections or tax mappings use the new capabilities.

`RuleInput.classifications` accepts HSN/SAC `code_system`, `code` and `match_kind` (`EXACT` or
`PREFIX`). HSN matches use 4/6/8 digits and never begin with 99 (chapter 99 is services); exact SAC uses six digits beginning with 99, and SAC
prefixes use 4/6 digits beginning with 99. The set may be extended only before any binding uses
the rule. Used or legacy rules requiring corrected/missing applicability need a replacement rule
and coordinated bindings. No migration guesses legal applicability or installs statutory rates.

Impact preview accepts `resource` (`tax_rule`, `tax_classification`, `catalog_tax_scope`),
`target_id` and `as_of`. It reports affected items and COMPLETE/MISSING/REQUIRE_EXPLICIT/INVALID
results across known date boundaries. Queries follow the affected products' relevant scopes
and current/future dependencies; unrelated company history does not consume their review capacity.
Review bounds are 8,192 rows per dependency query,
256 affected products, 64 dates and 2,048 item/date/direction checks; exceeding a bound fails
explicitly. Large changes require narrower scopes or a background review; the API never reports an unchecked
subset as complete.

POST `tax-impact-reviews` with the exact release body (and an idempotency key) dry-runs it under the
lock and queues a PENDING review bound to the policy generation, Identity source version, business
date and input digest; it requires `tax_rule.manage` and `tax_rule.publish`. The separately run
worker `python -m catalog.tasks.tax_review_worker` advances each review in chunks of at most 16
products, as the requester with fresh Identity proofs, replaying the release in a rolled-back
savepoint. Non-COMPLETE results are stored as findings; INVALID results, and non-COMPLETE results
for ACTIVE products, block. Any Catalog product or tax change moves the generation, so the next
chunk marks the review STALE; a refused proof marks it FAILED. Findings list by `id` with an
optional `blocking` filter, no search, and require `tax_rule.read` plus `item.read`.
`tax-releases` accepts exactly one of `preview_token` or `impact_review_id`; a review publishes only
when COMPLETE, unblocked and still matching input, generation, source version and date (409).

Option sources `catalog.tax_categories`, `catalog.tax_rules` and `catalog.tax_classifications`
support native options. Classification options accept `as_of`, defaulting to the company date.
All three masters support aliases, external keys and usage relations through ordinary master
routes. Metadata mappings may target unexpired future classifications; tax selection still
checks the requested date and withdrawal evidence. Current dependency authority is checked on replay;
rate and release publication receipts also require readable component fields and fixed-cess units.

## Reviewed activation

1. POST `items/{item_id}/activation-preview` with `as_of` equal to the current company business
   date. The result lists missing requirements, source versions and an expiring signed token.
2. Resolve every missing definition. Required checks include configured attributes, variant
   identity, effective units/profiles, required sale levels/unit prices, purchase references,
   MRP and tax bundles for enabled sale/purchase directions.
   Required prices must also pass known commercial BLOCK checks and declared source coverage.
   Derived base prices retain the requested pack's own MRP coverage requirement.
   Scheduled unit revisions are checked at their start dates so activation cannot freeze a
   known future unit change without its required price definitions. Their dependencies join
   the signed source set. Review allows at most 1,024 future unit revisions and 64 dates;
   it does not certify unknown future changes or final transaction tax/approval facts.
   Tax readiness also checks every known future classification, binding, rate and ancestry
   boundary for enabled commercial directions. Missing future coverage blocks eligibility
   and identifies its date/direction. Products with neither direction enabled need no tax review.
3. POST `items/{item_id}/activate` with the preview's `as_of`, `expected_version`,
   `expected_family_version`, `preview_token` and an idempotency key.

Activation requires `item.activate`, product update/adoption authority and readable dependencies.
The token is bound to tenant, company, user and SKU and expires after 15 minutes. The command
rechecks the complete preview under the company lock; a stale or incomplete preview commits
nothing. It records configuration adoption and immutable activation/source rows, freezes the
selected goods inventory profile and activates the SKU. First activation activates its family;
another draft SKU in that active family may subsequently activate.

Missing required MRP remains an explicit eligibility requirement. Activation reuses the
adoption preview freshly validated within that same locked command, avoiding a duplicate
requirements pass. Standalone adoption still revalidates the caller's signed preview.

GET list/detail routes `item-activations`, `item-activation-sources` and
`item-inventory-profiles` expose protected history under item-read authority. They have no
mutation endpoints. Activated structural definitions cannot be edited through draft authoring.
Service activation never creates a stock profile or physical stock. Configuration and
requirements responses now advertise `activation_available: true`; each SKU still needs a
successful eligibility preview. Full consumer release and acknowledgement remain V1.6 work.

## Tax publication to Accounting

Every tax command that changes a classification, rule or rate (publish, correct, withdraw,
restore, rule retire) stages `catalog.tax_classification.changed`, `catalog.tax_rule.changed` or
`catalog.tax_rate.changed` (schema version 1, contracts in `apis/accounting/contracts/`). They
go into the outbox in the same transaction as the change, with
`source_version = CatalogPolicyState.generation` after the bump. A rolled-back command leaves no
event, and previews publish nothing. `catalog.tasks.accounting_publisher` relays only these
events to `platform.sources`, signed for Accounting. `catalog.tasks.tax_backfill` republishes
current state per company, idempotently. No route changed.

`catalog.tasks.charge_tax` produces version-two charge-tax evidence: rate on `posting_date`,
`tax_calc` arithmetic, and the supplier registration valid on `posting_date`. It is a task
function only; its caller is an open item in [tax-accounting-plan](tax-accounting-plan.md) Phase 5.

## Decision log

- 2026-10-30: Removed the product setup free-text `source_reference` from native
  tax assignment input/detail, coordinated release bindings and form metadata;
  Catalog 0211 drops the binding
  column. Official classification/rule/rate evidence and exemption reasons retain
  their separate validation and publication contracts.

- 2026-10-28 product workflow review: activation and configuration-adoption tokens
  bind the resolved configuration and tax values, policy generation, source
  revisions, row/version pins and eligibility. An equivalent Identity refresh may
  advance its transport `source_version` without invalidating that review. Each
  request still requires a fresh verified checkpoint and current actor/field/
  reference authority; actual value or generation changes still reject the token.
  Commit records retain the current source watermark. Existing preview tokens may
  require a fresh review after this change; public request/response schemas and
  stock/financial posting contracts are unchanged.

- 2026-10-05: Reverse-charge applicability is stored on the dated tax rule; per-document RCM
  determination stays with the posting service (Billing or Accounting). Resolves the conflict with
  catalog-product-design §9. See [tax-accounting-plan](tax-accounting-plan.md).
- 2026-09-14 Product Tax review: enforce equal GST splits and statutory ceilings; native HSN/SAC
  applicability; complete cross-context GST/compensation-cess schedules; governed future correction
  with retained evidence; product impact and future activation checks; native master administration.
  Authorization subject lookups are reused only within one access operation and keyed by source
  version and date. New commands/replays revalidate authority; production timeout limits are unchanged.
  Statutory references: [CBIC GST FAQs](https://cbic-gst.gov.in/hindi/sectoral-faq.html) and
  [IGST section 5](https://cbic-gst.gov.in/hindi/IGST-bill-e.html).

- 2026-09-14: Required-price activation uses the same exact commercial assessment as native
  publication and includes scheduled unit revisions in the reviewed dependency set.
- 2026-09-14 review: preserve explicit missing-MRP eligibility and avoid duplicate adoption
  validation inside activation so the command can complete within its existing time budget.
- 2026-10-05 tax-accounting Phase 2: same-day supersession rejected; split GST components share
  rounding; HSN chapter 99 rejected for goods; kind-keyed company/`BOTH`-group bindings; previews
  authorize first and are rate-limited; `.publish`/`.withdraw` audit actions. Decision 3: releases
  over 256 products publish against a chunked background `tax-impact-reviews` report instead of a
  preview token; the 256-product synchronous bound is unchanged.
- 2026-10-06 tax-accounting Phase 5: tax changes publish through the outbox in the command's
  transaction. A command's row carries its strongest action, and rule retirement is a WITHDRAW. A
  withdrawn classification or rate is sent with `valid_to = valid_from` until contract v1 can
  express "never effective". The backfill reuses the current generation and writes no audit
  event. The charge-tax v2 producer fails closed without a supplier registration valid on
  `posting_date`, issues composition supplies untaxed, and refuses foreign currency.
