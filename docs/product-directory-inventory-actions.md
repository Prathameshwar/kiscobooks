# Product directory inventory actions

## Phases

1. Reuse the shared kebab Menu and effective product configuration/published
   inventory-profile reads. Load only on opening a product row's menu; verify
   company, record and published revision identities. Reuse company capability
   verification from the party actions, with independently scoped read grants.
2. Add Product ledger (disabled), Manage stock, Manage batches and Manage serials
   to product/SKU and family menus. Hide inapplicable operations for services,
   disabled company features and profiles without the corresponding tracking.
   There are no stock/batch/serial management screens or operational APIs to
   invoke: applicable entries explain that limitation and have no destination.
3. Test lazy reads, configuration/profile/permission combinations and failures,
   retained existing links, keyboard opening and desktop/mobile presentation.
   Review correctness and security without changing stock facts or balances.

No stock, costing, reconciliation or posting design decision is made here. No
new API, model, migration or stock authorization is introduced. No API response
or list projection is widened to include per-row configuration.

## Verification and review (2026-10-27)

All three phases are complete. Products/SKUs and product families reuse the same
Menu, styles, published-profile resolver and verified company feature reader.
Company configuration, effective product settings and inventory-profile reads
require their existing company-scoped grants. Unknown/protected settings never
enable or infer tracking. Reopening refreshes settings; services and disabled
inventory hide the inventory entries. Product ledger remains explicitly disabled.
Applicable stock, batch and serial entries remain disabled because their native
operational management is not implemented, rather than pointing at profile editors.

Focused Console verification passed 191 tests across eight suites. Shared menu,
placement, search-select, select and context-switcher suites passed 243 tests.
TypeScript and whitespace checks passed. Native API/schema/client contracts are
unchanged; no backend test run is required for this navigation-only change.
The UI workspace consumers use workspace links, so the 0.1.25 version bump does
not change their lockfile resolution.

The live read-only tenant3 run covered Products/SKUs and Product families at
1440px/390px in light/dark/ledger themes (12 checks). It waited for current native
configuration, verified horizontal and vertical menu bounds, disabled destinations
and Escape focus, and recorded no browser/API failures or writes. The existing
verification product has no batch/serial tracking; positive tracking combinations
and disabled/mismatched/protected configurations are covered by component tests.

Presentation review found keyboard focus could open a mobile menu before its row
scrolled into view, producing a negative bottom offset. A failing unit regression
confirmed the issue; shared placement now clamps the anchor to viewport edges and
uses only available height. The live review passed after the fix.

Manual simplification and security reviews covered CLAUDE.md sections 5 and 6;
slash-command review tools are unavailable. Shared readers replace duplicated
verification, lazy reads preserve lean lists, and no money/audit/tenant boundary
was changed. No remaining issue was found within this navigation scope.

## Deferred merge button (2026-10-27)

At the user's request, product/SKU and product-family detail headers show a
disabled Merge products button beside the existing primary action. Its accessible
description explains that merging duplicate products is planned for a future
update. It is available as a placeholder on verified read-only and editable detail
views, but not on classification details. No handler, dialog, link, permission or
API is introduced; no consolidation or stock/history rewrite is implemented.
