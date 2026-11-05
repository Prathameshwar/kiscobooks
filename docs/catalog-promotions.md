# Catalog promotions, schemes, discounts and coupons

**Ownership amendment, 2026-10-10:** [Vouchers](vouchers-plan.md) replaces future Billing
and Payments APIs. Catalog retains promotion definitions; Vouchers prepares documents and
requests evaluation. If enabled, authoritative eligibility, live quotas/holds, redemption,
gift-stock and financial effects must commit together in Accounting's proposed posting
extension. Older Billing runtime references below mean that split, not a new service.
Promotions remain separately phased; this amendment implements no runtime or wire rename.

**Status:** P0 definition/owner contracts frozen and typed validation implemented, 2026-09-11.
The bounded automatic same-item B15 preflight validates only the currently supported
evaluator shape. Eight scoped tables at Catalog revisions 0161-0168, with two
scoped promotion-to-stack foreign-key revisions 0169-0170, retain dormant
same-item and stack-policy publication facts; they do not publish or activate a promotion. P1/P5 authoring/publication
APIs and the Vouchers/Accounting runtime remain pending.
The stored-fact reader can reconstruct the bounded same-item mechanic and reject
missing or inconsistent rows. It has no release, source-readiness or execution authority.
**Scope correction:** Only P0/P1/P5 definition work is part of the Catalog plan. Billing runtime
schemas/routes below are external owner references, not Catalog migrations or endpoint tasks.
The authoritative Catalog inventory is [Catalog tables](catalog-table-inventory.md).
**Read with:** [Product rules](catalog-product-design.md),
[schema](catalog-schema.md) and [bulk/pricing](catalog-bulk-pricing.md).
**Numeric and enablement contract:** [Product Configuration](catalog-product-configuration.md).
**Regular-price sources and guards:** [Product/unit/batch pricing design](catalog-pricing-design.md).
**Stock location contract:** [Stores/godowns, defaults and operation controls](catalog-warehouses.md).

**Voucher configuration integration (planned):** The [commercial configuration contract](voucher-commercial-configuration.md)
binds enabled mechanics and price-level/stack/free-sale guards to native Sales/Purchase/type/
class restrictions. Recording authorized manual bonus quantities does not imply automatic
rule evaluation. Automatic 10+1 must use the single evaluator and authoritative Accounting
consumption; source-scoped reward claims survive lot splits and partial fulfillment.
Purchase supplier terms do not consume sales promotions; procurement scheme automation
remains outside this sales scope. CAL17-CAL28 supplement the existing promotion gates.

## 1. Requirement and boundaries

Include sales promotions as a first-class part of the commercial model: schemes, coupons,
automatic/manual discounts, customer price-level interaction, bulk administration, limits,
stock effects and returns. This supersedes the earlier blanket deferral of advanced promotions.
The terms below describe different responsibilities; a coupon is not another price column.

| Concept | Responsibility |
|---|---|
| Price level/book/tier | Establish the customer's regular price for the currency, unit and quantity |
| Promotion | A versioned native eligibility rule and benefit; automatic or coupon-triggered |
| Scheme | A promotion mechanic such as buy X/get Y, quantity benefit or bundle price |
| Campaign | Group related promotions for dates, shared caps and reporting; no extra discount by itself |
| Coupon program | Define code distribution, binding, validity and usage policy for one promotion |
| Coupon instance | A public shared code or a unique issued token; selects its program, never contains a trusted amount |
| Manual discount | An authorized document action with reason and limits, evaluated in the same calculation pipeline |
| Commercial guardrail | Mandatory ceilings, price floors, MRP, free-sale and approval rules applying to the combined result |

Catalog owns authoring and published commercial definitions. Billing owns the **single basket
promotion evaluator**, quotes, coupon issuance, live limits/holds, redemptions and sale/return
effects. Billing consumes complete local Catalog projections; no remote call inside posting.
Catalog can statically validate definitions; transaction simulation uses Billing's quote API.
There is no second item-discount engine or coupon microservice.

A standing MRP/cost-based regular-price recipe is distinct from a promotional benefit. Resolve
the recipe against the actual supported allocation/declaration/cost context before applying
benefits. Preserve original-line tier quantities through stock splitting. Billing then checks
combined net consideration against commercial_guard_rule and applicable declaration/tax limits.
Do not award the same intended MRP reduction twice or expose protected cost through explanations.

Reuse libs/platform for Decimal/rational arithmetic, allocation primitives, tenant sessions,
auth/field policy, idempotency, jobs and events. Promotion eligibility/selection stays in
Billing domain; Catalog ORM and commercial policy do not move into the shared library.
Campaign descriptions can use registered custom fields; eligibility and money never can.

## 2. Supported benefits and targeting

| Mechanic | Native contract and important limits |
|---|---|
| Line percentage / fixed amount | Explicit per-unit or per-line basis; maximum benefit; no negative net line |
| Basket percentage / fixed amount | Minimum eligible spend; eligible line set; allocated to those lines, never a detached discount total |
| Quantity scheme | Buy quantity threshold for a declared SKU/pack or compatible pool, benefit and repeat cap; distinct from the base price tier |
| Buy X get Y / free quantity | Same or separate qualifying/reward pools, buy quantity, reward quantity, reward percentage, repeat limit |
| Mix-and-match / bundle price | Explicit component quantities or choose-N pool, target bundle price, deterministic allocation; no BOM/assembly implied |
| Conditional gift | Spend/quantity threshold and exact eligible gift SKU choices; explicit customer selection where required |
| Coupon offer | Activate one of the above mechanics with shared, unique, customer-bound or single-use codes |
| Manual line / document discount | Fixed or percentage; authorized amount, reason, actor and any native approval reference |
| Lot clearance | Optional verified lot/expiry selector; only after real lot allocation is available |

Supported native conditions: company, customer/customer pricing type, price level, sales channel,
authorized selling location, currency, item kind/type, SKU/family, group/subgroup, category,
brand, approved manufacturer, native option-valued attributes, dates/time windows and eligible
quantity/spend. Distinguish approved product manufacturer from actual lot manufacturer.
Exclude selectors override includes. Values within one selector are OR; selector dimensions
are AND. A bounded list of alternative condition groups permits OR, without arbitrary scripts.
Require an explicit eligible price-level set on publication; the authoring default is PRICE1.
Applying an offer to wholesale/dealer levels or all levels is a deliberate native selection.

Group/category/attribute selection declares SNAPSHOT_ON_PUBLISH or CURRENT_AT_EVALUATION.
Default to a frozen eligible-SKU manifest. The live mode explicitly includes future matching
products and uses the complete current source generation; quotes record that generation and
matched SKUs. Historical quotes/returns never resolve today's category membership.
A category can explicitly target a promotion without becoming an implicit tax/price ancestor.

Published benefit currency must match the transaction; no implicit FX. Quantity pools declare
compatible unit dimensions and exact conversions. Counting a piece, box and service hour as
one common quantity is invalid. Services can receive discounts or defined free service units,
but never generate stock movements. Stock gifts must be sellable and satisfy their usual
tracking, expiry, lot, serial/IMEI and location rules.

For "buy 10, get 2" define **10 paid + 2 reward**, not 10 total. SAME_ITEM quantities are
partitioned into disjoint paid/reward units; CROSS_ITEM pools cannot reuse an allocated unit.
Repeat count, per-order maximum and choice ordering are explicit. Default reward selection
is lowest eligible regular unit price, then SKU/line identity; customer-choice schemes require
an explicit eligible selection. Reward quantities do not trigger another reward recursively.
Serial-tracked rewards require whole physical units. A missing gift is reported; it is never
silently substituted or charged. Posting must confirm a revised quote if the gift cannot be supplied.
Separate qualifying and reward allocations before testing a scheme's spend threshold. Added
reward lines never increase qualifying spend; later basket rules exclude allocated reward units
by default. A caller cannot mark an ordinary line as a gift to change eligibility or stock cost.

Exclude stored-value gift cards, wallet credit, loyalty points, cashback, referral payouts,
payment-method-funded offers, vendor rebate settlements, cumulative turnover incentives and
purchase-side supplier schemes from this sales delivery. They need their own liability,
settlement or procurement source and workflows. Do not accept their configuration as if supported.
First-ever-purchase targeting also waits for an authoritative, concurrency-safe customer sales
history/cutover contract; per-customer promotion usage limits are included now.

## 3. One deterministic calculation contract (Billing-owned)

1. Validate scoped customer, native memberships, capabilities, currency, units and freshness.
   Resolve Price 1/2/3 (or another level), book, customer/channel exception and volume tier.
   Record this regular-price baseline before promotions; never compare everything with Price 1.
   Preserve price_basis_quantity, exact quantity and numeric/config revisions. Normalize amounts
   for comparison/calculation at sufficient precision; never round a per-unit rate prematurely.
2. Resolve the transaction's tax context locally. Build explicit eligible amount and quantity
   bases. Spend thresholds declare NET_EXCL_TAX or GROSS_INCL_TAX; exclude ineligible lines,
   charges and settlement instruments. The default threshold basis is the regular-price
   eligible subtotal, before promotions. Later discounts never cause eligibility to oscillate.
3. Match published automatic rules and supplied coupon programs. Coupon validation is scoped
   and rate-limited. Validate dates, selectors, units and usage policy; a quote does not claim
   to have reserved the final coupon, budget or gift.
4. Select compatible offers using the stacking contract below; allocate scheme quantities.
   Apply product/scheme benefits, then basket/coupon benefits, then authorized manual discounts.
   A coupon's benefit participates in its declared stage, rather than creating a second discount.
5. Allocate every benefit to lines/units, enforce combined guards and calculate tax using the
   selected jurisdiction adapter. Persist separate regular amount, each benefit, taxable basis,
   components, final amount and rounding. Do not equate a zero selling price with zero tax.
6. Return selected/skipped offer explanations, reward lines, source/rule/engine versions,
   cart digest, expiry and exact totals. Mask commercially restricted explanations.
   Hold/post revalidates current authority, source readiness and the supported quote policy.

Percentages use the remaining eligible consideration in their stage: 10% then 10% is 19%
off the same original baseline, not 20%. A fixed benefit declares per-unit/per-line/basket
scope, currency and NET_EXCL_TAX or GROSS_INCL_TAX amount basis. Inclusive-price extraction,
gross-discount inversion and mixed-tax allocations require an adapter that implements those
operations; unsupported tax contexts fail publication/quote rather than using a guessed formula.
Taxes, freight and payment charges are not implicitly coupon-eligible.

Allocate basket/bundle discounts pro rata against eligible remaining line value, then
distribute currency rounding residuals by largest remainder and stable line identity.
Cap each line at its permitted remaining benefit; redistribute only to eligible capacity.
Track discount amounts attributable to reward units so partial returns are reproducible.
Use exact Decimal calculations and DECIMAL(19,4) storage; retain calculation/rounding versions.
A basket allocation must exactly equal its declared applied benefit. A bundle target above
the regular component sum is ineligible, not a surcharge.

### Stacking, priority and mandatory guards

- Default: one promotion per order. Combining offers requires an explicit versioned policy
  allowing their stack groups and stages. A public code does not automatically combine with
  every existing sale price or automatic promotion.
  Combining manual benefits with promotions also requires an explicit permission in that policy.
  Two codes for the same promotion cannot apply it twice; repeats follow its native repeat rule.
- Within each exclusive group use configured PRIORITY or BEST_SINGLE. PRIORITY sorts by
  explicit priority then immutable promotion ID. BEST_SINGLE compares individually feasible
  offers by final customer payable on the same stage baseline/tax context and resulting basket,
  then uses that stable tie-break. Different gift/bundle baskets require PRIORITY or an explicit
  customer choice; do not invent a cash equivalent to promise a universal best deal.
- Evaluate groups in the published order; this is deterministic, not a promise to solve a
  global cheapest combination. Overlapping bundle/quantity allocations consume disjoint units.
  Whether a later ordinary percentage may discount those units is an explicit stack permission.
- Proposed limits: 5 submitted codes, 100 candidate promotions, 20 condition groups per revision,
  10 applied benefits and 500 basket lines. Reject excess work with a clear error; never silently
  ignore remaining eligible offers. Measure limits in P5 before adopting production defaults.
- Apply company/group/family/SKU discount ceilings restrictively to **total** benefit, including
  schemes, coupons and manual reductions, against the resolved regular price. Floors and MRP
  use their declared unit/currency/tax basis; inventory cost/margin checks use authoritative Billing.
- A gift needs free_sale_allowed and an explicit native commercial-policy allowance for its
  full benefit. A campaign cannot override a restrictive group ceiling by itself. Explicit,
  dated gift allowances are reviewed policy changes and cannot waive statutory obligations.
- Discounts beyond the actor's delegated authority require a separate authorized approval.
  Store a native approval bound to immutable quote ID/cart digest, amount, currency, expiry and
  reason; P4 binds it to the actual sale revision and consumes it once under a unique claim.
  Maker cannot approve their own request. Editing the cart invalidates approval. This bounded
  approval contract does not pretend the general approval_workflow routing engine already exists.
- A candidate that violates a hard guard is infeasible. Automatic offers may be skipped with
  a reason; a specifically requested coupon/manual benefit must report the conflict. Never
  silently clip an advertised fixed/bundle benefit into a different offer.

## 4. Authoring, publication and suspension

Use mutable promotion_draft rows with row_version and workflow status. Publishing creates
immutable promotion_revision, typed targets/conditions/benefits and a dependency manifest.
A promotion is a stable code/identity; changing its revision does not reset usage or budgets.
Same promotion cannot have overlapping applicable revision windows. Different promotions
may overlap only under the explicit selection policy.

Commercial publication and validity are distinct: drafts use status; published revisions
use dated validity and do not also carry is_active or an independently maintained ACTIVE flag.
Promotion/coupon eligibility instants use UTC [starts_at, ends_at), with the company's IANA
timezone recorded for scheduled windows. Persist expansion of local/DST windows explicitly.
These instants differ from inclusive DATE ranges used for price/tax histories.
Use trusted sale/acceptance time for coupon eligibility, not a caller-backdated posting_date;
tax/fiscal validity still follows the native posting-date contract.

Preview publication shows sample eligible SKUs, overlap/stack conflicts, baseline price levels,
free-sale/floor failures and projected exposure. Publication validates referenced definitions,
not a guarantee of future cost/stock/budget. Catalog publishes a complete immutable release;
Billing activates it only after dependencies arrive. Source gaps/staleness fail closed for new
holds/posts. Replication readiness is explicit in API responses, not assumed after an event send.

Operational suspension uses a dated Billing redemption_block over a company/campaign/
promotion/program/code scope. It immediately governs that Billing authority, including outstanding
holds, and emits an outbox event for Catalog visibility. No is_active edit to historical terms.
An emergency-stop request is acknowledged only after the block commits; event propagation alone
is not an immediate stop. Resumption is a new dated control action. Remaining budgets and posted
redemptions survive pause, revision and resume.
Stable redemption_scope_guard rows cover every enclosing scope, including currently unblocked
ones. Holds/posts take shared guard locks; block/resume takes the corresponding exclusive lock.
Use one tested order across guards, documents/holds, quotas and stock/cost locks. Thus a sale
committed before the stop remains valid; one following the acknowledged stop cannot consume it.

## 5. Coupons, budgets and concurrent redemption (external Billing contract)

A coupon program declares SHARED_PUBLIC or UNIQUE_ISSUED, code canonicalization, redemption
window, optional customer binding, total/per-customer/per-order limits and promotion identity.
Single-use is a limit of one; redemption counts belong to Billing, not to a coupon boolean.
Guest use is allowed only for programs without customer identity requirements. IP/device data
is not proof of a unique customer; named-customer limits require the authoritative party ID.

Generate unpredictable unique codes; public vanity codes are intentionally shareable.
Preserve leading zeros and define case rules. Lookup uses company-scoped keyed code hashes;
retain key version, rotate through explicit lookup aliases and enforce unique canonical claims
across active key versions. Never log raw coupon codes, expose them in audit or use them in URLs.
Keep required old lookup keys while their codes remain usable; new issuance checks/claims all
retained key versions under a fenced key-generation contract. Rotation cannot require recovering
plaintext from an old hash or create a duplicate canonical code through two concurrent writers.
Protected issuance output is available only to authorized issuers via short-lived private
artifacts; store encrypted delivery material only for that bounded retrieval period.
Generic validation failures do not reveal another customer's binding or usage.

Limits can apply independently to campaign, promotion, program, coupon and customer:
redemption count, reward-unit count and discount budget. Count one configured redemption
per promotion/order; repeats consume separately declared reward units. Budgets use explicit
currency buckets and a declared NET benefit basis, not inventory cost or guessed gross totals.
Higher caps never override a tighter enclosing cap. Budget increases preserve prior consumption;
reductions below committed plus held amounts are rejected.
Catalog limit revisions are requests until Billing activates them under the same quota locks
and acknowledges the enforced version. Report PENDING/APPLIED/REJECTED delivery evidence;
publication alone cannot claim a lower live cap. Limit cutover must not race another reservation.

Quote is read-only. An explicit checkout hold atomically reserves all needed usage/budget
buckets; it can also reserve the selected stock/gift through the existing inventory kernel.
Use a bounded TTL (proposed 15 minutes), customer/order-scoped hold limits and request throttling.
For limited physical gifts, only a successful inventory reservation can promise availability.

- Create/lock stable quota bucket rows even when their counters are initially zero. Under a
  canonical lock order enforce committed + live-held + requested <= limit across all scopes.
  Counter arithmetic, reservations and reservation entries commit in one Billing transaction.
- Bind a hold to actor/customer/company, cart digest, quote, rule/source versions, amounts and
  server expiry. Changing quantity/customer/code/date requires explicit replacement/revalidation.
  Replace atomically under the same locks; do not lose a valid hold merely because replacement fails.
- Posting locks and validates the live hold, suspension/capability state and current document.
  Commit redemption, quota consumption, allocated benefits, financial entries, stock movement,
  audit and outbox together. A public standalone "mark coupon used" endpoint is forbidden.
- Hold expiry/release and posting serialize on the same rows; one outcome wins. Database UTC time
  governs expiry. An expiry worker is cleanup, not the correctness boundary.
- Quota holds guarantee capacity only. Default quote policy is REVALIDATE_ON_POST: source/price/
  tax changes require a fresh quote and explicit acceptance; they never silently change the charge.
  Reuse or replace the existing hold under the same limits. No unimplemented locked-price promise.
- Idempotency guards issuance, holds, posting, release and reversals. Also enforce unique
  document/promotion/application identity and original-document return references; a new request
  key cannot redeem twice. A committed effect survives a crash before response/acknowledgement.

## 6. Financial posting, cancellation and returns (external Billing contract)

This request adds a **bounded Billing sales-document integration** to the earlier stock-only
scope: native sale/credit-note header and lines, draft/quote binding, post, reversal/return,
numbering, receivable/revenue/tax and stock/COGS mappings as applicable.
Payment collection, full order management and general invoice lifecycle automation remain
separate. Coupon delivery is incomplete until this actual posting path exists; a simulated
redemption against an arbitrary external invoice ID is insufficient.

A zero-price stock reward still issues its actual lot/serial units and records inventory cost.
Separate promotional benefit reporting from the jurisdiction/accounting policy used for
revenue reduction or promotional expense. Never book both as duplicate expense. Account mappings
and gift/tax treatment must pass the supported adapter; no statutory treatment is assumed here.

Before posting, cancellation releases a hold. After posting, correction is a linked financial
reversal/credit in an open period, retaining original pricing/tax/benefit/cost evidence.
Returns allocate the original benefits to the returned quantities; never run today's promotion
rules on the return. Use cumulative returned quantities and allocate the final rounding residual
on the last return, preventing repeated partial refunds from exceeding the original amount.

Default return behavior: refund the original net paid amount of returned units; do not silently
reprice retained units or recover a free gift's list price. A different gift-recovery policy needs
explicit, disclosed native terms and supported jurisdiction validation. Track outstanding/returned
gifts as evidence without inventing an automatic customer debt.
Default coupons are not reissued and budgets are not replenished by a refund; audited replacement
issuance or allowed restoration is an explicit policy action. Record gross redeemed, reversed,
restored and net measures separately. Restore only the original amount once, never more than its
remaining reversible allocation; usage and money restoration are separate policy choices.

## 7. Catalog schema and external runtime references

All tables use company/tenant scope, existing IDs/money types and local composite ownership
constraints. Cross-service references point to local projections. Keep queryable business
conditions typed; bounded immutable calculation snapshots may be JSON.

| Owner / table family | Essential fields and invariants |
|---|---|
| Catalog campaign; campaign_draft / campaign_revision | Stable code; published date window, purpose SALE, currency and limit definitions; draft status separate from dated revision |
| Catalog promotion; promotion_draft / promotion_revision | Campaign reference, version, trigger, mechanic, priority/stack group, windows, target mode, return-policy reference; immutable published terms |
| Catalog promotion_condition_group / promotion_condition | Native operand types and typed references/ranges; bounded AND/OR contract; one valid operand shape per row, no executable expression |
| Catalog promotion_target / target_manifest | Typed include/exclude owner refs and selected SKU/source-generation evidence; same-company FKs, exact scope cardinality |
| Catalog promotion_benefit / benefit_component | Percent/fixed/bundle/buy/reward quantities, units, currency, amount basis, cap/repeat rules; mechanic-specific requiredness/checks |
| Catalog promotion_stack_policy / stack_permission | Versioned ordered groups, selection mode and allowed pair/stage interactions; no implicit stacking |
| Catalog coupon_program / coupon_program_revision | Promotion identity, code mode, customer-binding requirement, date/limit/restore policy; version never resets usage |
| Catalog promotion_limit_definition | Typed campaign/promotion/program scope; count/reward/amount limits, currency and period basis; no nullable pseudo-unique scope key |
| Billing promotion_release and projection children | Immutable Catalog payload/dependency versions and complete activation barrier |
| Billing coupon_issue_job / coupon_instance / coupon_code_claim | Program/revision, optional customer, issuance source, validity; canonical keyed claims unique per company across key rotations |
| Billing redemption_scope_guard | Stable company/campaign/promotion/program/code scope rows; shared hold/post versus exclusive stop/resume locks |
| Billing redemption_block | Typed scope and effective suspension interval; append-only control evidence, no rewrite of historical revisions |
| Billing promotion_quota_bucket | Stable scope/customer/period/currency keys, configured limit/version, committed and held measures, row_version; locks before changes |
| Billing promotion_quota_entry | Append-only reserve/consume/release/restore deltas with source effect ID; rebuild/reconciliation basis |
| Billing pricing_quote / quote_line / quote_benefit | Immutable cart/customer/source/engine hashes, expiry, chosen/failed benefits, per-line allocations, exact tax/totals |
| Billing promotion_hold / hold_entry | Lifecycle status HELD/CONSUMED/RELEASED/EXPIRED; expires_at is a deadline, not a second manually set lifecycle; exact quota/stock references |
| Billing discount_approval | Quote ID/cart digest, optional sale revision until P4 binding, actor/approver, amount/currency/reason, expiry and workflow state; no self-approval, unique one-sale consumption |
| Billing sale_document / sale_line; credit_note / credit_line | Real dated/numbered posting source with original-line links; typed monetary and quantity facts plus immutable calculation snapshots |
| Billing promotion_redemption / redemption_allocation / redemption_reversal | Original document/line/unit provenance and quantities/amounts, coupon/program/revision, source idempotency, append-only reversal links |

Shared/public codes consume shared buckets; unique codes additionally consume their own bucket.
Bucket identity includes stable promotion/program identity, not revision ID. Period limits use
explicit timezone-derived period keys; lifetime limits remain lifetime across revisions.
Immutable issuance validity is date-based; exhaustion is derived from counters and revocation
uses redemption_block, not a competing coupon.used/is_active status.
Mutable quota counters must reconcile to entry history plus active holds. Index by scoped
code hash, eligibility selector, quote/document identity, quota scope, hold expiry and source effect.

| Service / API family | Contract |
|---|---|
| Catalog CRUD /campaigns, /promotions, /coupon-programs | Scoped authoring/history; edits use expected_version |
| Catalog POST /promotions/{id}/validate, /preview, /publish | Static validation, reviewed impact/dependency digest and immutable publication |
| Catalog /promotion-stack-policies; /promotion-limits | Dated policy management and reviewed exposure/cap updates |
| Billing POST /pricing-quotes; GET /pricing-quotes/{id} | One basket evaluator; regular price, benefits, gifts, tax and masked explanations |
| Billing POST /coupon-issuance-jobs; GET job/results | Reviewed unique-code generation/import; protected output, durable per-code effects |
| Billing POST /promotion-holds; POST /promotion-holds/{id}/replace, /release | Explicit capacity reservation; idempotency, scope, current cart/version |
| Billing POST /redemption-blocks | Scoped immediate stop/resume evidence; applies to new and held redemptions |
| Billing /discount-approvals | Request/approve/reject the exact bounded document discount |
| Billing /sales-documents; POST /{id}/post; /credit-notes | Real posting and original-allocation reversal through owned domain handlers |
| Billing GET /promotion-redemptions and bounded usage summary | Authorized operational evidence; heavy campaign analytics use Reports projections |

Exact permission keys are added to the existing catalogue/roles/seeds during implementation:
separate read/manage/publish, coupon issue/export, suspension, quote, hold, discount apply/approve,
sale post and credit post. Bulk permission never implies those underlying grants.
Native field policies apply to rules, costs, budgets, customer assignments and exports.
Security logs identify program/reference and failure class, not plaintext token or customer details.
Events include published definitions, issued/revoked instances, holds, redemptions and reversals;
raw codes never appear in events. All state changes use atomic audit/outbox.

## 8. Bulk work, capabilities and operational evidence

Reuse the staged import/update contract: template -> validate -> preview -> explicit commit,
frozen IDs/versions, dependency ordering and one effect per stable logical change set.
Catalog imports campaigns, draft rules, targets and program definitions. Publishing is a
separate authorized action over the reviewed revision. Typed bulk updates can schedule dates,
change future benefit/cap revisions or target sets; they never edit consumed counters.

Billing owns unique-code generation/import jobs. Prevalidate exact external identity, duplicate
canonical codes, customer binding, windows and per-batch limits. Retry resumes the same code
effects and protected artifact, not another batch of usable codes. Expired code-output artifacts
return an explicit expiry result; retry never regenerates a new usable batch. Authoring publication
emits proposed limits; issuance/sale activation requires Billing's acknowledged enforced version.
Definition publication and issuance are separate jobs with explicit readiness/partial results.
Do not offer global atomic import across Catalog/Billing or direct redemption-history updates.

Proposed capabilities: sales_promotions (locks_on=sales_promotion_posted);
coupons (requires sales_promotions, locks_on=coupon_redemption_posted).
Free physical goods additionally require inventory and their actual tracking features.
Simple permissioned manual discounts remain baseline commercial functionality.
Catalog activation requires compatible registry, Identity source, projections and Billing first-use
handshake. Each owner implements its part in its own plan; Catalog cannot claim runtime readiness
from definition publication. Catalog permissions/metadata and scoped consumer acknowledgements ship here.
Disabling before first use coordinates pending holds; after financial use the ratchet preserves
history. Stopping a live offer uses redemption_block, not disabling an irreversible feature.

Reconcile committed/held/restored counts and amounts, code issuance, sales/credit allocations,
gift stock/cost and ledger totals. Export outbox events to Reports for campaign sales, benefits,
redemptions and reversal metrics; operational counters are not an analytics warehouse.
Alert on projection gaps, quota drift, stuck holds/jobs, unusually frequent failed codes and
excessive reservation attempts. Recovery rebuilds from retained immutable facts and source barriers.

## 9. Owned delivery phases and external acceptance

The revised Catalog-only plan includes these phases:

| Phase | Catalog work and dependencies | Exit evidence |
|---|---|---|
| P0 | Adopt definition/mechanic/stack/tax/return/owner contracts with C0 | Native requiredness and external prerequisites are explicit |
| P1 | Author/publish campaigns, schemes, typed conditions, targets, benefits, stack/limit and program definitions; P0/C5/C6/C8/C9 | Catalog model/migration parity, validation, protected history and complete releases |
| P5 | Catalog definition bulk adapters and consumer handoff; P1/C10 | Reviewed job effects, safe publication and truthful activation status |
| C15 | Catalog security/recovery/performance evidence | Owned release verified; external runtime readiness explicitly reported |

Legacy P2 (quotes/evaluator), P3 (issuance/quotas/holds) and P4 (sales/credits/redemption) belong
to Billing's separate plan. Do not implement or check them off under Catalog. C11-C14 inventory/
fiscal work likewise remains external. Catalog tests its contracts; an unavailable consumer is
reported as a dependency, not replaced by a second evaluator.

Billing integration acceptance includes A/B/C regular prices, supported stacking (10% then 10%
is 19%), tracked buy-10/get-2, exact mixed-tax allocations, last-use races, immutable limit
identity, quote-bound approvals, actual gift availability and bounded original-allocation
returns. Only tests against the actual Billing service establish those runtime behaviors.
Catalog's definition tests must reject malformed or unsupported versions of those mechanics.

## Decision log

- 2026-10-11: Added the bounded same-item stack-policy storage at Catalog 0166-0168
  and scoped promotion-revision foreign keys at 0169-0170. Policy, group and pair
  facts are immutable through the Catalog ORM; publication must still validate
  ordered stages and complete source versions. A pre-existing dormant revision
  with an invalid stack reference will make the FK migration fail for reviewed
  repair; no data is silently rewritten. The disposable MySQL promotion verifier
  passed upgrade, scoped schema/FK checks, isolation and downgrade/re-upgrade.

- 2026-10-10: Mapped old Billing runtime ownership to Vouchers preparation and proposed
  Accounting atomic hold/redemption/stock/financial effects. Definition/runtime phasing is preserved.

- 2026-09-11: Integrated typed regular-price recipes and lot/declaration contexts with the sole
  Billing evaluator; final floor/margin/MRP checks apply after benefits with original source evidence.

- 2026-09-11: Scope correction limits Catalog delivery to definitions, publication, owned bulk
  and consumer status. P2-P4/runtime candidate tables remain Billing integration references.
  Named promotion_condition as the typed Catalog condition table; no executable JSON rules.

- 2026-09-11: Added the shared warehouse policy/default contract for quote, gift allocation,
  reservation and posting; an applied location sale-disable also blocks existing held sales.
- 2026-09-11: Linked independent quantity/rate/amount precision and Product Configuration;
  quotes/posts enforce exact price basis, effective participation and original revision evidence.
- 2026-09-11: Recorded the user's request for schemes, coupons, discounts and promotions.
  Added a finite native sales-promotion system and P0–P5 workstream, replacing blanket deferral.
- 2026-09-11: Chose Catalog definition ownership and one Billing evaluator/redemption authority.
  Expanded the delivery boundary to the minimum real sales/credit posting needed for safe usage,
  gifts and returns; no new service or UI. This remains a plan, not implemented functionality.
- 2026-09-11: Detailed execution planning binds P2 approval to an immutable quote/cart, then
  P4 binds/consumes it on one real sale, avoiding a dependency on an unbuilt sales-document API.

- 2026-09-11: Froze P0 scope/mechanics/native targeting/stacking/owner/return/guard contracts.
  Added Catalog-only typed DTOs for percent/fixed/quantity/buy-get/bundle/mix-match/gift,
  explicit price levels/currency/UTC intervals/IANA timezone, ordered stack permissions,
  return-policy references and coupon-program count/budget definitions. Structural tests
  do not validate live quota capacity, gift stock, tax adapters or published dependencies.
  Runtime, scheduled local-window expansion, authoring tables/APIs and complete publication
  remain their subsequent phases. IANA fallback data is pinned for Windows portability.

### Sales commercial-configuration review - 2026-10-10

Linked native voucher policy restrictions and manual versus automatic free-quantity
semantics to existing Catalog definitions and future Vouchers/Accounting execution. Existing
stack, gift-return, capability and publication/runtime boundaries remain authoritative.
