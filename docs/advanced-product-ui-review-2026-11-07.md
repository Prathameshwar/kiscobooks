# Advanced Product Profile / SKU creation UI review

Local fixes and verification are recorded in [advanced-product-ui-fixes-todo.md](advanced-product-ui-fixes-todo.md). The findings below retain the review baseline; they are not a claim that the issues remain in the updated source.

Review requested on 2026-11-07. Scope: current local source, all four creation steps, overall layout, dropdown refresh behavior, and pricing compared with Simple creation. No application changes or deployment performed.

Browser validation could not start: Vitest configuration loading failed with `spawn EPERM` when starting esbuild. Findings below are source/CSS findings; exact rendered geometry, live dropdown network behavior, and end-to-end price persistence are not verified by this review.

## Confirmed layout and label issues

- Shared `.janso-field + .janso-field` adds a 1rem top margin. The wizard's `.product-wizard__fields` grid does not reset it, unlike the shared `.janso-form-grid`. Adjacent shared fields therefore receive inappropriate stacked-form spacing.
- Wizard native selects have a 2.7rem minimum height; shared inputs and search selects use the 2.25rem control token. Label weights, backgrounds, and borders also differ.
- Field metadata labels are used verbatim. When metadata supplies `brand_id`, `series_id`, `model_code`, or `base_unit_id`, the readable fallback does not apply.
- Selected values without a retained label become `Selected choice`. Defaults, restored drafts, and remounts need readable label resolution.

## Step-by-step findings

1. Product Profile: mixed controls and uneven field margins; `Change Product Type` is awkward in creation; Description is single-line; raw metadata labels and unresolved selected names need correction.
2. SKUs and units: outer sidebar plus inner SKU list, editor padding, and nested attribute/unit cards reduce editing width. The inner list/editor remain side by side at 601–900px. Binding and conversion labels need explanations; SKU names truncate.
3. Business setup: policy facts show identifiers instead of names/terms. Separate price grids have inconsistent group spacing. Long price labels combine name, currency, tax basis, and required status.
4. Opening and review: nested batch/serial cards compound padding. Opening errors can repeat inline and in notices. Review displays identifiers for classification and master selections. Variant summary reads `option_id`, omitting typed scalar values.

Overall design recommendations: reduce repeated titles/introduction text; make long step names readable at intermediate widths; keep actions accessible on long forms; verify narrow-width SKU editing, long labels, conditional controls, and error states in a browser.

## Dropdown refresh / perceived postback

`AdvancedProductWizard` reloads options when Product kind, Product group, or Product Type revision changes. It sets `loading=true`; each step is rendered only when `!loading`. Consequently the active form unmounts during the request, losing focus and component-local label caches. This is a React options refresh, not an explicit document reload in the inspected code.

Selecting Product Type clears the revision; when a revision was already selected this also reloads options. Published revisions load through a separate request. Automatically filling an empty default Group or Type revision can cause additional options requests.

Brand, Series, Manufacturer, Category, and Base unit do not directly trigger this outer options effect. Dependent choices and per-unit pricing defaults have their own refreshes.

Recommendation: retain the form and its labels/focus while refreshing dependent options; indicate pending state locally. Review default application and request sequencing before calling any particular request unnecessary.

## Pricing compared with Simple creation

| Input | Advanced | Simple |
|---|---|---|
| Purchase reference | Per SKU in Business setup when purchasable and configured; amount plus source reference | Nonbatch Prices group or batch row; simpler amount input |
| Sale price | Per SKU by accessible configured plan, including default single-level plan | Selling price in single-level mode, named levels in multiple-level mode |
| MRP | Goods when configured; amount, jurisdiction, and source reference | Nonbatch Prices group or batch row |
| Batch pricing | Opening batch rows capture opening unit cost, separate purchase reference, sale prices, and physical MRP | Batch entry has separate price/cost columns |
| Opening valuation | Separate opening unit cost and quantity | Separate opening unit cost and quantity |

Important: purchase reference is an estimate/reference, not an opening valuation cost or a complete purchase price-book editor.

Current `advanced_product_options.py` calls `sale_choices(..., include_default=True)`. The missing single-level sale input described in the 2026-11-06 VM review is addressed in current local source, assuming an accessible configured default plan. Deployment/live behavior was not reverified. Optional sale pricing with unavailable defaults/access can still produce no inputs without an explanatory notice; required mode has a warning or API rejection.

Remaining pricing UI concerns:

- Amounts use `TextField` with decimal keyboard hints rather than the shared numeric input behavior. Validation checks decimal strings on continue/submit.
- Advanced requires purchase source reference when an amount is entered; MRP requires jurisdiction and source reference. These conditional requirements lack field-level required markers/hints. Errors combine multiple missing values under the amount field.
- Validation allows up to four decimals; the header separately reports configured price precision. The UI should clearly explain allowed entry precision and publication rules.
- The batch sale labels omit the inclusive/exclusive tax basis shown for SKU-level sale inputs.
- Final review omits batch purchase reference and physical MRP, despite capturing them.
- Batch price capture in Advanced is inside opening stock entry; there is no standalone initial batch price-entry section when opening is skipped.

Per-SKU submission does re-fetch unit-specific defaults in `AdvancedCreationProgress.skuOptions` before `setupBody`, so the initial options' missing price defaults alone do not establish an incorrect submitted basis/precision.

Relevant source: `AdvancedProductWizard.tsx`, `AdvancedProfileStep.tsx`, `AdvancedSkuStep.tsx`, `AdvancedSkuUnits.tsx`, `AdvancedSetupStep.tsx`, `AdvancedOpeningReviewStep.tsx`, `AdvancedCreationProgress.tsx`, `advanced-product-business.ts`, `advanced-product-api.ts`, `SimpleProductCreate.tsx`, `SimpleProductBatches.tsx`, shared `product-wizard.css`/`janso-ui.css`, Catalog `advanced_product_options.py`/`simple_sale_prices.py`.
