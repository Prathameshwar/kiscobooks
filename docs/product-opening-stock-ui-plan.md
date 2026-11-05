# Product opening stock UI plan

Status: authorized and implemented; verification and review evidence is recorded in
[the UI delivery record](product-opening-stock-ui-delivery.md).
Date: 2026-10-28. Backend contract: [opening-stock API](product-opening-stock-api.md).

## Starting point and proposed experience

The product Inventory menu already links active SKUs to
`/inventory/stock/opening?item_id=...`. That route currently wraps the generic
VoucherEntry form. Product creation still explains that opening stock follows
activation. Existing controls cover warehouses, batches, serials, total carrying
value and linked opening journals, but do not provide the complete new cutover,
conversion/rate/history, reconciliation and finalization workflow.

Extend these entry points into one company opening-stock workspace with product
shortcuts. One company has one books-begin cutover. A product entry contributes
allocations to that cutover; saving one product never finalizes the whole company.
The worksheet remains editable through the native manifest replacement API before
physical claims exist. Once posting starts, changes follow audited correction.

## Phases and completion criteria

- [x] **1. Workspace, readiness and permission-aware navigation.** Review the
  existing route, company-scoped page gates, same-origin API proxy and download
  allowlists, generated types, product menus and shared form/draft guards. Build
  the landing workspace with company, books-begin date, currency, current cutover,
  progress and specific setup blockers. Link to authorized account mapping,
  financial periods and product activation screens. Distinguish missing setup,
  unavailable services, protected values, legacy history and disabled posting.
  Stock read opens authorized review; individual actions require their own grants.
  Exit: direct links, refresh and company switching retain correct scope and never
  start an independent per-product opening.

- [x] **2. Product entry and creation-wizard integration.** Reuse product-list
  actions, product details and the existing creation wizard's fourth step. After
  successful product creation, offer Continue to opening stock with the verified
  SKU preselected. Retain the ability to create the product from any valid wizard
  step. Require activation before authoritative opening preparation. Display
  product creation, activation and opening as separately confirmed outcomes, with
  retry directed only at the unfinished action. Exit: retry never recreates the
  product; services and non-stock products do not expose physical entry.

- [x] **3. Four-step opening entry.** Reuse the existing stepper, form sections,
  entity searches and action bar:
  1. Product and locations: product, read-only cutover/currency, warehouse/bin,
     entered quantity and effective permitted unit/conversion.
  2. Cost and value: explicit unit-cost or total-value mode, priced quantity,
     authoritative API calculation, normalized base quantity and company rounding.
  3. Tracking and history: configured batches, expiry/manufacture information,
     prepared serial selection, count reconciliation, known original receipt date
     or explicit unknown history, and cohort ordering.
  4. Review: allocation totals, conversion evidence, accounting treatment and GL
     preview, validation issues and the authorized save/continuation action.
  Support multiple warehouses/cohorts for a product. Reuse existing identity
  preparation controls where authorized; preparing an identity creates no stock.
  Hide inapplicable tracking fields and never default missing value to zero.
  Exit: exact decimal text throughout; no calculation from selling price and no
  JavaScript floating-point authority over financial totals.

- [x] **4. Durable worksheet, native drafts and approval handoff.** Integrate
  controller-owned manifest creation/replacement and Stock Operator draft
  preparation. Reuse native voucher lifecycle screens and approval rules. Prefer
  the durable opening-import checkpoint workflow for grouped draft creation,
  including manual worksheet batches, so receipts survive refresh and interrupted
  work. Use stable source keys, versions and idempotency identities. Explain
  worksheet saved, draft created, awaiting approval, posting in progress, posted
  and confirmation pending separately. A changed allocation requires review and
  the appropriate native draft revision. Exit: uncertain responses use owner
  status/same-request recovery; completed work is never presented as rolled back.

- [x] **5. Bulk import workbench.** Reuse file-upload, import history, progress,
  result tables and export controls. Load the versioned template; support
  CSV/TSV/XLSX and typed JSON within backend bounds. Explain native references and
  conversion/history requirements, show validation/chunk issues, review totals,
  create native drafts and resume outstanding chunks. Surface existing jobs when
  content is uploaded again. Cancellation explains retained drafts and effects.
  Exit: Ready to create drafts is never shown as Stock posted; forbidden file
  shapes, duplicate cohorts and stale reviews have actionable messages.

- [x] **6. Reconciliation and company completion.** Display declared/applied
  quantities and carrying values, missing cohorts, physical/GL checks and pending
  confirmations. Provide explicit zero-stock confirmation under its narrow
  permission; keep financial zero opening separate. Provide controller-reviewed
  legacy adoption without interpreting its empty declaration as zero existing
  inventory. Finalization uses the latest version/hash and a confirmation summary.
  Exit: incomplete or unreconciled cutovers cannot finalize; opening a product
  shortcut resumes the existing company workflow.

- [x] **7. History, export and corrections.** Show product/warehouse-filtered
  opening cohorts, known/unknown age, native voucher and movement links, immutable
  manifest revisions and authorized exports. Expose reopen, reversal and
  replacement only when permitted and supported. Explain closed periods and
  downstream dependencies, with links to the native corrective workflow. Exit:
  field-level cost denies also cover summaries, rates, CSV and cached views;
  posted balances are never edited directly.

- [x] **8. Experience verification and two reviews with fixes.** Test loading,
  empty, success, permission/configuration branches, validation, stale edits,
  dependency failures, lost responses, recovery and context changes. Verify the
  full workflow against native APIs, including untracked/batch/serial/both
  products, FIFO/MVA, conversions, multiple warehouses, zero declarations, imports,
  approval handoff, reconciliation and correction. Inspect narrow/mobile and
  desktop layouts, keyboard/focus behavior, accessible errors, and light/dark/
  ledger themes. Review twice, implement each review's fixes and rerun affected
  checks. Keep a delivery checklist and record precise activation/test limits.

## Presentation and behavior rules

Reuse `@janso/ui` PageHeader, PageNavigation, section/form/action components,
SearchSelect, DataTable, notices and confirmations. Any reusable extension belongs
in the shared package and token-based styles. Use company date/quantity/amount
formatters, consistent spacing and alignment, readable compact allocation tables
and a persistent review summary that adapts on small screens. Keep keyboard
navigation and validation focus predictable. Preserve entered work on recoverable
failures and guard unsaved navigation/company changes.

Use business labels such as Unit cost, Total carrying value, Create opening
drafts and Finalize company opening. Show identities, source keys and conversion
revision details only when they help resolve an issue or inspect evidence.

## Authority and activation

Stock Operator may prepare/import drafts; financial-controller authority plus
stock configuration manages a nonzero cutover. Voucher approval remains separate.
Company Administrator's zero declaration does not confer financial management.
The UI reflects these distinctions instead of automatically assigning broader
roles or treating a permission denial as a retryable service error.

Draft preparation remains available when otherwise authorized and ready. Posting
controls reflect the server's admission status and prerequisites. General posting
activation remains a separate release decision; any QA posting uses an explicitly
authorized isolated scope. Schema migrations are not expected solely for this UI.
Any owner API gap discovered during integration must be recorded and resolved
through its owning service, with matching contracts and checks.
