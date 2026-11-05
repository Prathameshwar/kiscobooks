# Product opening creation review - 2026-11-02

1. Review Simple and Product Profile/SKU completion, opening entry, quantity/unit conversion, cost modes, tracking and worksheet saving. Reproduce defects with failing tests.
2. Fix lost or reinterpreted drafts, stale calculated values and applicable navigation/access defects. Preserve exact decimals, native unit/profile authority, books-begin dates, tenant boundaries and explicit worksheet/posting review.
3. Verify the affected creation and stock-opening suites, backend regressions, responsive layouts and types. Complete simplify/security review and record evidence. Keep database, scripts and models aligned if a native contract change is required.

The review continues through the existing product completion page and company opening worksheet; it does not introduce a separate opening balance on the product master.

## Completed phases

### 1. Review and reproduce

Reviewed the Simple and Product Profile/SKU completion paths, opening quantity and unit selection, total value and unit cost capture, batch/serial eligibility, worksheet editing, and saving/replay. Added failing regressions for cost-mode changes, stale previews, incomplete tracking settings, unfinished entry navigation, worksheet pagination, and tracking carried between product completion pages.

### 2. Fixes

- Total value and unit cost retain separate entered amounts. Changing modes cannot reinterpret the same number. Discarding or adding an allocation resets both amounts, the cost mode, and cost-per quantity.
- A calculated preview is bound to the exact company, opening date, currency, product, unit, quantity, and cost inputs. Changed inputs invalidate it immediately; an older asynchronous response cannot authorize adding an allocation. Unit selection is revalidated when the company, product, or opening date changes.
- Calculation and unit lookup prevent duplicate actions and step navigation while pending. Accounting treatment cannot change while an allocation has unfinished input.
- Missing or protected tracking flags block entry instead of behaving like disabled tracking. Serial lookup uses the existing tracking request wrapper, preserving native product/lot scope and active, unheld, receipt-eligible filters.
- Removing the only allocation on the last worksheet page returns to the preceding valid page.
- Completion handoffs belong to the current actor scope, company, and product. Switching products clears prior transient tracking state and waits for the matching product record.
- Desktop opening steps use a compact horizontal layout. Existing shared responsive styles stack complete labels on narrow screens. No new shared UI styles or library version changes were required.

### 3. Verification and final review

- **189 Console tests passed across 17 files:** 59 entry/workspace/completion tests, 99 related domain, policy, proxy, creation, and continuation tests, 29 product inventory action tests, and 2 browser layout tests.
- **96 browser layouts checked:** 60 opening layouts covering five stages/cost variants and 36 product completion layouts covering Simple, Profile/SKU, and draft products. Both suites cover 1440, 768, 390, and 320 pixel widths in three themes, plus zoom checks. Opening checks also cover keyboard focus, readable step labels, compact desktop progress, and horizontal overflow. Final desktop cost and mobile tracking screenshots were visually reviewed.
- Scoped coverage of the three changed components: **96.16% lines/statements, 98.48% functions, 86.05% branches**, passing the configured aggregate thresholds.
- **47 backend tests passed:** 45 Accounting calculation, API, review-fix, and cohort tests; 2 Catalog opening-unit-fact tests. These use the existing test fixtures, including SQLite, rather than applying DDL to a live database.
- **9 shared UI stepper/setup layout tests passed.** Console TypeScript and whitespace checks passed.

The final simplify review retained the existing worksheet and request flow, consolidated serial reads through the existing tracking wrapper, and reused the shared responsive step styling. No unresolved findings remained.

The final security review checked company/product receipt ownership, exact decimal strings, native calculation and effective-unit authority, fail-closed tracking flags, batch/serial ownership and eligibility, books-begin validation, access restrictions, explicit posting review, and existing immutable worksheet replay and native audit behavior. No unresolved findings remained.

The native API contracts, SDK schemas, database models, and migration scripts remain aligned: this review changes UI state and validation only. No schema, SDK, migration, automatic activation, or automatic posting changes were needed. Screenshots and scoped coverage are available in the ignored `.tools/product-opening-review`, `.tools/product-created-review`, and `.tools/product-opening-review-coverage` directories.
