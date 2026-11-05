# Product master experience review (2026-10-27)

User scope: deeply review product master UI, styling, layout, validation, navigation,
messages and controls. Preserve native company/field permissions, exact quantities,
immutable definitions, idempotency and activation readiness.

## Delivery phases

1. Review the native family/SKU flows, existing tests and live tenant3 screens.
   Restore current source authority for authenticated verification if needed.
2. Improve metadata-driven create/edit forms, product directory and detail navigation,
   context, field guidance, responsive section grouping and recovery messages. Reuse
   shared UI components and token CSS. Add failing regressions before fixing defects.
3. Verify focused UI/API checks and TypeScript; exercise real create, edit, validation,
   readiness and navigation with tenant3. Review desktop/mobile in all three themes.
4. Review implementation for accessibility, permissions, safe navigation and exact
   retries; fix findings and rerun affected checks. Record evidence and limitations.

No new product business semantics, schema or permission widening is planned.

## Delivered behavior and review findings

The directory keeps search, status and sorting in a compact toolbar. Related-master
filters use the shared Disclosure and open automatically when those filters arrive
in the URL. Status uses labelled badges. Reads wait for native field metadata;
failures and pending reads never imply an empty catalogue. Discontinued products
have no edit shortcut. Company mismatches in returned rows fail closed.

Creation has one form card with named family and default-SKU sections and an attached
FormActions footer. Configured defaults and setup guidance sit in the shared context
card. A product family and its first SKU are still created atomically through the
existing native endpoint. Creation waits for verified defaults instead of allowing a
premature save to show a configuration-loading validation error. Codes, references,
required fields and exact quantities retain native validation and field authority.

A definitive 409 during creation retains the draft and permits correcting a conflicting
value. Editing clears only that failed command receipt; the next save obtains a new
idempotency key. An uncertain 5xx keeps its frozen body/key and prevents edits until
its exact retry resolves. Existing-record conflicts retain the reload/review path.

Product details show readable facts, preserving code/name casing, configured quantity
formatting and explicit Yes/No values. Internal slots and concurrency counters no
longer occupy the main facts list. Readable native reference controls still resolve
linked records. Routed product-area styling marks the current area. Section shortcuts
preserve return chains, company/related permissions and unsaved-setup protection.
Readiness translates native reasons into instructions with authorised repair links;
it never decides activation eligibility or hides unknown native reasons. Protected
status is described as protected rather than guessed to be Draft.

First review covered create/edit/readiness, scope, field authority, conflicts and
retries. Fixes: metadata-before-list reads, failed-list/empty-state separation,
returned-company validation, discontinued-edit shortcut removal, correctable create
conflicts, verified-default save gating and setup-history failure presentation.
Second review covered presentation, navigation and accessibility. Fixes: a single
form card/footer, contextual defaults, active routed links, readable detail facts,
readiness instructions/repair navigation, protected-status messaging and textarea /
checkbox help associations. Failing regressions preceded each defect correction.

Manual equivalents of the unavailable simplify/security-review commands checked
CLAUDE.md sections 5 and 6: native company grants and field metadata remain the
boundary; links use validated master navigation; no permission, business lifecycle,
quantity, transaction, audit or publication semantics were widened. No new CSS,
dependency, API contract, model or migration was needed for this UI change.

## Verification

- 157 focused Console tests across ten files passed, including twenty new experience
  regressions and fifteen readiness-message cases. Existing publication, activation,
  variant navigation, denied fields and uncertain-save regressions remain green.
- Console TypeScript passed.
- 15 native Catalog tests passed across classification UI workflows, definition
  mutations, field security and product authoring (276.74 seconds).
- The live tenant3 flow in Catalog enrollment verification created family/SKU
  `UI-MVQQ6FGI`, validated invalid code and excessive quantity precision, edited its
  SKU name and verified the saved detail. Readiness and activation review correctly
  block the incomplete group/base-unit setup. This test product remains a draft;
  no stock, price, tax or voucher execution was performed.
- The stopped local Catalog Identity source worker was restarted through its normal
  launcher; all three enrolled company source leases became current. This was an
  operational prerequisite, with no relaxation of source-authority checks.

Final live browser review: 30 responsive checks passed across directory, create,
SKU detail, edit and family detail at 1440/390 px in Light/Dark/Ledger themes.
No page/card overflow or browser errors were found, and screenshots were inspected.
A real duplicate create returned 409; the form retained values, accepted a corrected
code, and confirmed discarding on Cancel without creating a duplicate. The final
post-fix run used live application/auth/API/CSS; no business responses were mocked.
Private browser evidence is kept in ignored .tools/extension-masters artifacts.
All four phases of this product-experience refinement are complete locally.
