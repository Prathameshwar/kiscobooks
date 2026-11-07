# Advanced product creation and management: VM review

Advanced mode is **not fully working end to end**. Goods creation, explicit batch and nonbatch openings, accounting effects, and several native management/pricing operations passed. Three reproducible defects prevent sign-off, and the product and tracking management UI remains intentionally retired.

Verified on 2026-11-06 at https://kisco.cloud, VM `201.18.205.54` (`srv2111154`, root), release `/opt/kiscobooks/releases/product-purchase-20261106-1837`. Tests used the existing **Demo Tenant1 / E2E Batch Goods** company, code `KISCO-E2E-BATCH-3BXK`, ID `01a1b12c-b4fb-71fc-9006-3891ad1cb076`.

## Verification results

Browser tests used a real authenticated session and the normal Console proxy. Native API tests reused that session's existing access token against the VM gateway. Database queries were read-only and verified the resulting stock/voucher/journal records. Native API success does not imply a corresponding UI exists.

| Area | Result | Observed behavior |
|---|---|---|
| VM prerequisites | Pass | Eight APIs, Auth/Console, and relevant workers running; no failed systemd units. Migration heads: Catalog 0223, Accounting 0235, Identity 0100, Vouchers 0116. |
| Advanced Goods creation | Pass | Product Profile and SKU created, unit binding and GST classification/treatment saved, SKU activated. |
| Private draft recovery | Pass | Save/reload/open-latest preserved the requested opening quantity. |
| Batch opening through UI | Pass | Batch expiry saved; 10.0000 units at INR 80.2500 produced INR 802.5000 FIFO stock value. |
| Explicit nonbatch opening through UI | Pass | Checking then unchecking batch tracking produced 4.0000 units at INR 10.1250, total INR 40.5000, without a lot. |
| Untouched optional batch checkbox | **Fail** | UI displays Off, setup inherits a batch-tracked profile, opening submits no batches and fails after activation. |
| Opening accounting and replay | Pass | Both successful openings have POSTED vouchers, matching stock/posting dates, balanced debit/credit amounts, and one movement each. Advancing the completed batch opening again retained its voucher and quantity 10.0000. |
| Purchase reference | Pass | INR 91.2500 persisted independently of the batch opening cost INR 80.2500. |
| Default selling-price capture in Advanced UI | **Fail** | Sale prices are OPTIONAL and default PRICE1 exists, but no selling-price field appears when multiple levels are disabled. This also affects batch sale-price capture. |
| Native price publication | Pass | Batch sale price INR 123.4500 and nonbatch sale price INR 31.2500 published. Same-key replays returned the same price IDs with `Idempotency-Replayed: true`. |
| Default nonbatch price resolution | Pass | PRICE1 resolved INR 31.2500 per 1.0000 unit; quantity 4.0000 gave exact consideration INR 125, no fallback. |
| Batch price resolution | **Fail** | SALE and PURCHASE resolution through the live gateway returned 401, missing verified company context. |
| Current pricing-policy behavior | Pass, limited scope | Missing regular price rejected with 409; ineffective unit revision rejected with 409; unknown price level returned 404. Default level selection passed. |
| Native Product Profile/SKU management | Pass | Name edits persisted; SKU edit replay reused the result, stale edit returned 409. Cross-company item read returned 403. |
| Native batch management | Pass | Prepared an unreceived batch, corrected expiry, held/released it, and read four history actions. Create/correction replay passed; stale correction returned 409. Changing posted-batch dates correctly returned 409 and left expiry unchanged. |
| Product/batch/serial management pages | Retired | Fourteen authenticated detail/edit/tracking URLs returned 404. These workflows cannot be signed off through the UI. |

## Defects and reproduction

### 1. An untouched batch checkbox disagrees with the effective inventory profile

In this company, batch tracking is available but optional; the published inventory template tracks lots. Create a Goods SKU, leave **Enable batch tracking for this SKU** untouched, enter an ordinary opening, and submit. Creation/setup/activation complete, but opening preflight returns **“Opening batches must match the SKU inventory profile.”** The receipt remains OPENING and no stock movement is created.

The checkbox starts with `batch_enabled: null` and renders unchecked. `setupBody` omits the setting for null, so native setup inherits lot tracking. Opening entry treats null as off and submits the nonbatch shape. Recovery still displays **Batch: Off** and ordinary quantity/cost fields, with the saved opening decision locked.

Relevant implementation: `mfes/apps/console/app/lib/advanced-product-business.ts:9`, `app/lib/advanced-product-api.ts:124`, `app/components/AdvancedSetupStep.tsx:36`, and `app/components/AdvancedOpeningReviewStep.tsx:17` (paths relative to `mfes/apps/console`). The effective tracking decision must agree across checkbox, setup, review, and opening preparation.

The control test explicitly checked then unchecked the checkbox and completed successfully. This isolates null/inheritance handling from a company-wide inability to create nonbatch stock.

### 2. Default sale price is omitted when multiple price levels are disabled

The company's sale-price mode is OPTIONAL, multiple price levels are DISABLED, and an active default PRICE1 sales plan exists. Advanced options return `sale_price_levels: []`. Business setup and batch opening render sale fields only by mapping that array, leaving no place to enter the ordinary default sale price.

`apis/catalog/src/catalog/tasks/simple_sale_prices.py:31` returns no choices when multiple levels are disabled. Advanced options reuse that helper at `advanced_product_options.py:156`; the Advanced UI has no single-level field fallback (`AdvancedSetupStep.tsx:39`, `AdvancedOpeningReviewStep.tsx:27`). The replacement wizard must expose the permitted default plan even in single-level mode.

Native publication/resolution succeeded for the nonbatch control, establishing that the price book itself works. API-created test prices were necessary to verify that backend path; they were not captured by the wizard.

### 3. Batch pricing cannot verify the batch through the live gateway

Call `POST /catalog/v1/companies/{company}/prices/resolve` with the created batch SKU, its valid lot, unit revision, INR, date 2026-11-06, and exact quantity. SALE and PURCHASE return **401 / authentication_required / “verified actor and company context are required.”** Ordinary item reads and price publication in the same authenticated session succeed. Nonbatch resolution succeeds.

Catalog's `verified_batch` calls Accounting through `CreationOwners` (`apis/catalog/src/catalog/api/pricing.py:40`). Identity's company-context gateway branch includes Catalog creation/import paths, but excludes pricing paths (`apis/identity/src/identity/api/login.py:366`). The nested Accounting request consequently lacks required verified company context. Repair and test that forwarding path with genuine session authorization.

## Retired pages

The following UI was intentionally removed on 2026-11-04; its native APIs and records remain:

- Product/SKU detail, edit, and former creation-completion pages: `/masters/items/{id}`, `/{id}/edit`, `/{id}/created`.
- Former Product Profile create, detail, edit, and completion pages: `/masters/product-families/new`, `/{id}`, `/{id}/edit`, `/{id}/created`.
- Standalone attribute/variant authoring.
- Every standalone batch and serial list, create, detail, edit, and history page under `/inventory/batches` and `/inventory/serials`.

Product and Product Profile directories remain. The replacement Simple/Advanced creation entry is `/masters/items/new`; Advanced creation is restored on the tested release. Stock summaries, movements, opening-stock entry, and tracking selections within stock/voucher workflows remain. The opening paragraph of `docs/product-ui-removal.md` is stale about Advanced creation.

Direct authenticated HTTP checks confirmed all four tested product/profile detail/edit routes and ten batch/serial routes return 404. Source confirms the other retired product routes (`ProductCatalogPage.tsx:29`); `retired-product-ui.test.tsx` documents tracking route and navigation removal.

## Scope and retained evidence

This is a live Goods/stock review under the selected company's existing policy. Variants, serial tracking, MRP, multiple levels, tiers, formulas, channel/unit prices, and additional currencies were disabled; their end-to-end behavior is unverified. Service creation, multiple SKUs, pricing-policy authoring, buyer-specific assignment/fallback policies, permission-denial matrices, source-change races, and full voucher sales/purchase consumption were not exercised. The native whole-draft preview, readable published policy terms, and carrying-value preview remain open in `docs/advanced-product-creation-todo.md`.

Test fixtures were retained for review; no application fixes, configuration changes, deployment, or repository publication were performed.

| Test SKU / batch | ID | Retained state |
|---|---|---|
| `QA-ADV-0611-B-SKU` | `01a1b181-56ea-724d-9328-47bab103c9ee` | ACTIVE; opening 10.0000 / INR 802.5000; batch sale price INR 123.4500 published. |
| `QA-ADV-0611-BATCH-A` | `01a1b181-89d1-765c-9a26-d5723d9c0b1d` | ACTIVE, not held, expiry 2027-11-06; posted stock dates protected. |
| `QA-ADV-0611-P-SKU` | `01a1b186-84c0-706f-8195-ca8585326afe` | ACTIVE; receipt `01a1b186-8585-7610-837c-842d2089a297` blocked at OPENING; no stock effect. |
| `QA-ADV-0611-N-SKU` | `01a1b18a-95b6-707d-80f0-937c96ed369e` | ACTIVE; opening 4.0000 / INR 40.5000; default sale price INR 31.2500; profile/SKU labels edited to include Managed. |
| `QA-ADV-0611-UNRECEIVED` | `01a1b18f-162a-7557-97fc-6866fd323092` | ACTIVE, not held, no receipt/stock effect, corrected expiry 2027-11-07. |

Local evidence is in `.tools/advanced-product-vm-review-20261106/`; VM browser evidence is in `/tmp/kisco-advanced-review-20261106/`. Canonical pricing/management evidence is in `price-publication-checks.json`, `policy-management-checks.json`, and the successful cases of `final-checks.json`; stock/voucher/journal evidence is in `accounting-evidence.json`. Browser events and screenshots retain the recovery state and successful explicit nonbatch completion.

Initial harness assumptions incorrectly expected replay 200 instead of 201, POST instead of GET for draft preview, MISSING/200 instead of the resolver's 409 contract, 403 instead of unknown-level 404, and ordinary correction of posted batch dates. Those raw assertion failures remain in the evidence for transparency. Corrected checks passed and are not application defects. The batch resolver 401 and two wizard defects remain unresolved.
