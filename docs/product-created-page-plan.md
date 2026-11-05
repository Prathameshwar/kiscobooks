> Current UI (2026-11-04): [Simple Product creation](simple-product-ready-plan.md) is available at `/masters/items/new`. Product edit/detail, advanced creation and batch/serial pages remain retired. The implementation below is historical.

# Product creation completion

Requested on 2026-11-02: finish Simple Product and Product Profile / SKU creation on a dedicated page with clear next steps.

1. **Completion and navigation.** Add `/masters/items/{id}/created`, verify the current company-owned product, and redirect successful creation there. Preserve optional initial tracking and price references through a bounded, one-use, tab-local handoff scoped to organisation, user, company and product. Updates and embedded reference creation keep their existing behavior.
2. **Next actions and presentation.** Provide product list, new product, view / activation, and an additional SKU action in advanced mode. Show opening stock, batches, serials and warehouses using current company features, published or activated inventory configuration and permissions. Retain native opening and tracking workflows; no automatic activation or posting.
3. **Verification and final fixes.** Test creation, navigation, ownership, protected fields, feature / permission combinations, recovery and both modes. Inspect desktop, tablet, mobile, themes and keyboard layout. Review simplicity and security against CLAUDE.md §§5–6, fix findings and record validation here.

The existing Catalog and Accounting APIs provide the required workflows. This change needs no database, migration, model or generated API changes.

Decision: a newly created draft remains a draft. Inventory actions explain activation requirements and open the product readiness section. The completion page never grants authority from URL parameters or retained browser data. A handoff is consumed before any tracking command, so refreshing cannot replay partial tracking preparation.

## Delivery and review

All three phases implemented. Simple creation and profile creation redirect to the created product's completion route; explicit variant creation does the same after confirming the native company and family. The advanced-mode SKU action opens the native variant form after checking its current configuration and permissions.

Inventory availability is shared with the existing product action menu, avoiding a second interpretation of company features and activated profiles. Warehouses require the multiple-warehouse feature and warehouse read permission. Opening quantity and value remain in the existing company opening-stock workflow. Initial prices remain drafts in a collapsed section.

Manual equivalents of `/simplify` and `/security-review` were performed because those commands are not available in this session. Findings fixed: duplicate action logic, unsupported secondary-button styling, accumulated page spacing, duplicated product-details cards, protected status inferred as Draft, malformed variant receipts preventing safe recovery, navigation guards during the successful handoff, and the storage-blocked completion address. The address regression was reproduced with a failing test before correction. No unresolved security findings remain in this change.

Verification:

- Product creation / navigation / access regression suites: 272 tests passed across 14 files, including the final completion-address regression. Combined with the opening / tracking suites and browser test below: 350 Console tests across 21 files.
- New completion page and handoff: 100% statements, lines and functions; 91.40% branch coverage (page 88.57%, handoff 94.82%).
- Browser: 36 combinations of Simple / advanced modes, active / draft states, widths 1440 / 768 / 390 / 320 and light / dark / ledger themes, plus 200% zoom and keyboard focus checks. Final screenshots in `.tools/product-created-review/`.
- Native opening-stock and tracking navigation regression suites: 77 tests passed.
- Shared card, navigation, layout, token and style-contract suites: 74 tests passed.
- Console and shared UI TypeScript passed. Offline frozen workspace installation passed. Shared UI bumped to 0.1.53 and the new stylesheet is exported by its package.
- No API, model, migration or database changes were required.

Retained tracking input is tab-local and expires after 30 minutes. It is consumed once. If a browser blocks tab storage, the completion screen keeps the entered tracking mounted and changes the address to the saved product's completion route. Refresh therefore opens the saved product rather than the creation form. The page explains reviewing saved tracking records after refresh.
