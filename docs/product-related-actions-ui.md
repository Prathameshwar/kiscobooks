> UI retired on 2026-11-04. See [product UI removal](product-ui-removal.md) for the current scope. This document records the previous implementation.

# Product related actions

## Plan

1. Review product detail, native supplementary workflows, scoped permissions and return navigation.
2. Add a shared split button using the existing Button and portalled Menu. Keep keyboard navigation, safe links, permission filtering and disabled explanations.
3. Connect SKU and product-family views to their setup areas, related records, attributes and configuration. Preserve native validation and confirmations; protect dirty and pending setup work.
4. Review access, navigation and accessibility; fix findings, run affected tests and type checks, inspect desktop/mobile themes and build Console.

## Scope

SKU: edit, selling/purchasing units, barcodes, readiness, family, base unit, attributes/variants and product configuration. Family: edit, categories, groups, manufacturers, SKUs, linked brand/series and effective configuration. SKU shortcuts also open the owning family's categories/groups/manufacturers. Section-aware return links restore the selected supplementary area; history links open permitted assigned masters. Show only authorised destinations and verified visible references. Existing APIs provide these operations; reuse them.

## Validation

Implemented the reusable control and connected product/SKU and product-family views.

First review: fixed return links that lost the chosen supplementary area, added direct SKU-to-family section links, protected both category and setup drafts, and linked permitted assigned masters in setup history.

Second review: desktop/browser checks exposed mobile menu overflow for a left-side trigger. Added three failing placement regressions, then fixed intrinsic menu measurement and viewport bounds. All three now pass. A failing discard regression also exposed duplicate browser warnings from nested draft guards; product navigation now has one owner, while standalone setup/category forms retain their own guards. Hidden references, rejected metadata, read-only/active products, draft discards and native pending saves are covered.

Shared control regression suite: 171 tests passed, including Menu, SplitButton, placement, SearchSelect and ExportMenu. Console: 121 tests passed across product actions, classification, server routes, master navigation and menu cleanup. Browser: 117 checks passed across 1440px/390px and light/dark/ledger, with zero page errors, business writes or duplicate browser warnings. Reviewed both screenshots. Shared UI, Auth and Console type checks passed.

Final Console production build passed and the managed Console restarted successfully on port 4320. Review findings are fixed. `@janso/ui` is version 0.1.20; both workspace consumer lock entries still use `link:../../packages/ui`, so the version update requires no dependency or lockfile replacement.
