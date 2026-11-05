> Current UI (2026-11-04): [Simple Product creation](simple-product-ready-plan.md) is available at `/masters/items/new`. Product edit/detail, advanced creation and batch/serial pages remain retired. The implementation below is historical.

# Simple product UI: phased implementation plan

Status: proposed, 2026-10-28. This document authorizes no UI implementation by itself.
API contracts: [simple product API](simple-product-api.md).
API delivery evidence: [API TODO](simple-product-api-todo.md).

## Product experience to deliver

| Area | Simple mode: setting false | Advanced mode: setting true |
|---|---|---|
| Inventory overview/menu | One Products destination | Existing Products / SKUs and Product families destinations |
| Create | One product code and name, with applicable setup | Existing family/default-SKU wizard |
| Product detail/edit | One product identity and one edit form | Existing family and SKU views |
| Specifications | Ordinary attributes and their values | Attributes, variant axes and separate variant SKUs |
| Inventory features | Existing configured stock, batches, serials, warehouses and opening flow | Same capabilities, selecting the specific SKU |
| Imports | One-product template and product results | Existing family/item templates and results |

In simple mode there must be no duplicate family/SKU cards, identity sections,
creation choices or default-SKU confirmation. Feature sections such as pricing and
inventory may have their own panels; they belong to the same product. Product
families remain an internal API ownership detail in this experience.

The user has prioritized clear language, a simple layout and proper shared styling
for ordinary and business users. These are acceptance requirements in every phase,
not a cosmetic pass after functionality is complete.

## Repository findings affecting the plan

- `inventory-navigation.ts` and `InventoryOverview.tsx` currently produce two
  static destinations/cards. Changing only the create form would leave duplication.
- `ProductCatalogDirectory.tsx` routes New from items into family creation;
  `ProductCatalogPage.tsx` also selects the family editor for item creation.
- The existing editor uses four steps and separate family/default-item form state.
  Simple mode should not make the user understand those two identities.
- `product-request-policy.ts` and its delegated policies do not yet allow the new
  product facade and live authoring-mode routes. Proxy support comes first.
- Current configuration screens describe dated drafts/publication. The live mode
  control needs a clearly identified current-company setting, outside that workflow.
- Inventory actions and tracking references use item IDs and SKU-oriented labels.
  They can reuse the same operational IDs with mode-appropriate wording.
- Product imports use the shared `MasterImport` implementation and a product profile.
  Extend that profile and templates instead of creating another import engine.
- `VoucherStock.tsx` already supports opening modes and posted opening-value
  selection. Connect product actions and labels to that flow rather than storing
  opening quantities on the product form.
- Saved family-owned relationship reads can reuse the authorized native item to
  family lookup privately. The simple facade supplies product-oriented write
  adapters; the UI must never assume a family ID equals an item ID.

## Phase 0: readiness, contract mapping and screen specification

Deliver:

1. Confirm migration 0210 and the legacy-company compatibility seed are applied in
   the environment used for live UI testing. Preserve existing companies' mode.
2. Map the generated Catalog product/mode/field-set contracts to the console's
   current API helpers, typed form state, reference sources and retry mechanism.
3. Specify the four main simple-mode screens: directory, create, detail and edit.
   Define their empty, loading, denied, failed and successful states before coding.
4. Inventory every product entry point: menu, overview cards, directory New,
   bookmarks, related links, imports, voucher selectors, stock and tracking pages.
5. Start a UI TODO/evidence log following these phases. Preserve the unrelated
   stock, voucher and UI work already present in the shared workspace.

Exit: each screen/action has a real API contract and a reviewable layout/copy
specification. Missing backend capability is reported explicitly, not simulated.

## Phase 1: company mode loading and safe API access

Deliver:

1. Add typed reads for `/product-configuration/authoring` and the product facade.
   Reuse existing service readers/commands and generated API-client types.
2. Extend the console proxy's closed allowlists for the exact product list/detail,
   field-set, create/update, setup/attribute/category-preview and mode endpoints.
   Validate methods, UUID paths, allowed queries and duplicate parameters.
3. Provide one shared mode source keyed by tenant/company, with explicit loading,
   simple, advanced and error/denied states. Do not interpret an unavailable mode
   response as false or use the separate `variants_default` policy as the switch.
4. Use the same verified mode for shell navigation, overview cards and page dispatch.
   Avoid briefly flashing family/SKU options during initial loading/hydration.
5. Cancel or ignore old-company responses on company change. Invalidate mode,
   navigation and relevant product reads after a successful mode change.
6. Preserve permitted read access when mode cannot be verified; keep mode-dependent
   create/configuration actions unavailable with a clear reason until resolved.

Exit: proxy tests reject unsupported paths/methods, and loading/error/company-switch
tests prove the wrong company's mode never determines the current form or menu.

## Phase 2: Product Configuration setting

Deliver:

1. Add a current-company Product structure section to Product Configuration.
   Label the switch **Use product families and SKUs**. Explain: "Turn this on when
   you manage several variants of a product, such as sizes or colours."
2. Show the saved state as Single products or Families and SKUs. Keep this control
   separate from dated configuration drafts, publication and product adoption.
3. Respect read/manage permissions and native field policies. Read-only users can
   inspect permitted state; the UI must not offer an unauthorized save action.
4. Collect the required change reason, obtain a preview and commit that exact
   reviewed change. Translate blocker codes into plain language without IDs or
   invented affected-product counts.
5. Handle expired/stale previews by refreshing the review. Never silently disable
   required variants, discard pending import work or convert existing records.
6. Refresh the rest of the product experience after success; protect unsaved forms
   against losing their values if the mode changes in another tab/session.

Exit: enable/disable, blockers, stale preview, denied access and retry cases work;
the current setting is visually distinct from the dated-defaults configuration.

## Phase 3: navigation, directory and existing links

Deliver:

1. In simple mode, show one Products card/menu entry and one New product action.
   Hide the separate Product families destination. Retain other classification,
   configuration, inventory, pricing and warehouse destinations as applicable.
2. Retain `/masters/items` as the public product URL to preserve existing links.
   Its simple directory uses `/products`; advanced mode keeps current behavior.
3. Use Product code and Product name columns. Keep useful search/filter/sort,
   cursor paging, lifecycle status and permitted row actions. Hide family-only
   filters and explanatory text about creating a family/default SKU in simple mode.
4. Make both existing New entry URLs resolve to the appropriate mode's editor.
   Preserve validated return links, filters and the current company.
5. Resolve old family detail/edit links in simple mode through an authorized
   one-item lookup before redirecting to the product. If no unique permitted item
   can be resolved, show a useful unavailable/protected state; never guess an ID.
6. Clear obsolete family filters/cursors with a short explanation when changing
   modes, without dropping unrelated useful directory state.

Exit: no duplicate identity cards remain in simple mode; direct links and Back
navigation work; advanced directory/navigation regression tests remain green.

## Phase 4: simple product creation

Deliver:

1. Add a focused simple-product editor selected by the existing page dispatcher.
   Reuse setup/reference/validation helpers; keep the advanced editor intact.
2. Present one form with one primary Product details section: product name, code,
   product type, base unit and applicable purchase/sale choices. Obtain labels,
   visibility, requiredness, controls and allowed edits from the field-set contract.
3. Make Create product available without forcing four wizard steps. Place optional
   groups/units, pricing/tax, specifications, barcodes and tracking setup into clearly
   named expandable sections. Required settings must be visible and identified.
4. Apply reviewed defaults through the existing explicit acceptance flow. If a
   required type/unit/default is unavailable, explain what must be selected or set up.
   Never create hidden replacement masters or silently drop configured requirements.
5. Keep item/shared custom fields in one understandable form, respecting their
   distinct native bindings, conditional visibility, requiredness and read/write rules.
6. Submit one flat product identity to `POST /products`, with the verified authoring
   version and supported initial setup. Keep revision tokens and internal IDs out
   of business-facing copy.
7. Preserve entered values on failure, focus the first failing field, show a concise
   error summary, prevent duplicate submission and retain retry identity for an
   uncertain result. A changed draft starts a new command identity.
8. After success, show one product summary with View product, Finish setup/Review
   activation as applicable, and Create another. Clearly identify draft prices and
   remaining activation requirements. Do not report a draft as ready to transact.

Exit: ordinary users can create a basic product from one form; configured required
features still work; failed/uncertain submissions cannot create duplicate products.

## Phase 5: one-product detail, editing and feature setup

Deliver:

1. Present one product heading and one identity summary. Reuse shared section/tab
   patterns for overview, commercial setup, specifications and inventory where useful.
   Do not reproduce a second family/default-SKU card in any subview.
2. Use the aggregate PATCH contract for ordinary edits. Preserve read-only fields,
   active/discontinued lifecycle restrictions and explicit display label overrides.
3. On a stale revision or changed mode, retain the draft and offer reload/review;
   do not silently overwrite new server values or transform the form into advanced mode.
4. Use the product attribute form and product-oriented setup adapters for ordinary
   specifications, groups, categories and manufacturers. Connect category preview
   and commit to the same reviewed product state.
5. For existing family-owned relationship reads, privately resolve the authorized
   native owner and reuse the current bounded readers. Keep protected ownership
   protected; display neither an editable family identity nor raw IDs.
6. Reuse unit, barcode, tax, pricing, profile, readiness and activation components
   through a small typed adapter. Keep the product ID equal to the operational item ID.
7. Show variant axes and New variant only in advanced mode and only when the type,
   effective settings, lifecycle and permissions also allow them. Ordinary attributes
   remain usable with advanced mode off.

Exit: every existing applicable feature can be opened and saved for a simple
product; edit/activation and all advanced-family/SKU regressions pass.

## Phase 6: stock, tracking, vouchers and opening stock

Deliver:

1. Centralize mode-aware product labels and reference display for stock actions,
   batches/serials, warehouses, vouchers and back links. Show Product in simple mode;
   show the specific product/SKU and variant description in advanced mode.
2. Keep all selections and commands keyed by the same `item_id`. A display adapter
   may map public `code` to legacy selector `sku` locally; never invent another ID.
3. Preserve activated inventory-profile checks, stock/non-stock/service distinctions,
   batch/serial/expiry requirements and warehouse/bin applicability. The authoring
   switch cannot grant these capabilities or erase their requirements.
4. Offer Record opening stock from an eligible saved product and its completion
   screen, connecting to the existing opening voucher workflow. If product prefill
   is missing, add validated selection prefill and recheck it against the current company.
5. Label opening choices plainly: post opening stock and value together, or link
   a previously recorded opening balance. Keep date, quantity/value, currency,
   warehouse, batches/serials and native GL claim requirements visible as needed.
6. Preserve books-begin date rules, multi-location/batch input, duplicate checks,
   preview/post/reversal controls and permissions. Do not auto-post an opening when
   the product is saved. Explain product-save success separately from opening failure.
7. Keep tracking/stock views and voucher item selection consistent after switching
   company or returning from a product, including scans and unit selection.

Exit: simple and advanced goods can use supported opening flows, including both
opening modes; services/non-stock products and unauthorized actions are handled
correctly; existing stock/voucher tests remain green.

## Phase 7: imports, templates and results

Deliver:

1. Extend the existing product import profile and shared MasterImport UI to consume
   mode-appropriate templates. Simple mode starts with the `simple_product` resource.
2. Show one Product code/name in mapping, preview, results and history. Keep shared
   and item custom fields distinguishable without asking for a family/SKU pair.
3. Reuse server-generated CSV/XLSX/other currently supported templates and native
   validation. Do not require authoring versions, aggregate revisions or internal
   family fields as spreadsheet columns.
4. Link successful simple rows to product detail using the returned item ID. Preserve
   duplicate-code errors, row corrections, dependent rows and retry semantics.
5. Handle changed mode/configuration after template/review by asking for a current
   template/review while preserving the uploaded file and explaining the rejected step.
   Retain legacy advanced imports and historical jobs without relabeling their meaning.

Exit: simple file create/update imports, errors/results and advanced import
regressions pass through the existing shared import workflow.

## Phase 8: visual, accessibility and final acceptance

Deliver:

1. Complete responsive checks for directory/create/detail/configuration/import and
   opening entry. Use a readable content width, aligned desktop form columns,
   stacked narrow-screen fields, consistent spacing and clear action hierarchy.
2. Reuse `@janso/ui` form layouts, inputs, SearchSelect, cards, tables, buttons,
   notices, dialogs and loading states. Place any necessary reusable CSS in the
   shared stylesheets, using existing tokens. No page-local copied CSS, ad hoc
   colours or theme-specific hardcoding.
3. Check light/dark/ledger themes, keyboard access, focus after validation, visible
   labels, required markers, screen-reader status/error messages and dialog focus.
   Preserve company-configured amount/date/quantity display and exact decimal input.
4. Add Vitest/Testing Library coverage per delivered page/component/conditional
   branch and proxy policy. Run typechecking and existing product/configuration,
   attributes, imports, navigation and stock/voucher regression suites.
5. Exercise browser journeys for both modes, company switching, permissions,
   stale edits/mode changes, interrupted saves, activation, inventory and opening.
   Capture reviewable desktop/mobile/theme evidence using the repository's tools.
6. Perform two final reviews: first for usability/reuse/correctness, then for
   authorization/proxy boundaries/retries/data preservation. Fix findings, rerun
   affected checks and complete the TODO/evidence log.

Exit: the user-visible experience matches the simple/advanced table above;
advanced mode still works; no unresolved API/UI integration or usability defect
remains. Commit/publishing follows the workspace rules only when authorized.

## Delivery checklist

- [x] Phase 0: readiness and screen/contract specification.
- [x] Phase 1: mode loading and closed proxy access.
- [x] Phase 2: current-company configuration switch.
- [x] Phase 3: navigation, directory and direct links.
- [x] Phase 4: simple product creation.
- [x] Phase 5: detail/edit and feature setup.
- [x] Phase 6: inventory, vouchers and opening stock.
- [x] Phase 7: imports and results.
- [x] Phase 8: visual/accessibility checks and two final reviews performed.

Delivery evidence and the unresolved repository-wide function coverage gate are
recorded in [simple-product-ui-todo.md](simple-product-ui-todo.md). Implementation
and reviews are complete; the coverage gate must not be described as passing.

## Inline master creation decision - 2026-10-30

Product group/type selectors now expose a permission-gated + New action and the
shared right-side Drawer. The existing group/type/requirements forms remain the
owning implementations. Groups select on a compatible save; types select only
after explicit publication and native option verification. The product draft stays
mounted throughout, including cancellation and retry. The same implementation
serves family/SKU creation. See [review](product-reference-create-review-2026-10-30.md)
and [reusable results](product-reference-create-results-2026-10-30.csv).
