# Account and party creation UI review - 2026-11-02

1. Review account, customer/party, and supplier creation, including address/contact, tax details, and both opening modes. Capture desktop, tablet, and phone layouts in all three themes; check spacing, labels, field alignment, keyboard focus, and overflow.
2. Fix verified presentation issues through shared token styles, preserving existing fields, native configuration, validation, drafts, creation requests, and opening behavior.
3. Run affected creation, opening, retry, access, edit, and browser checks plus TypeScript. Review final screenshots and record test/coverage evidence and simplify/security findings.

## Completed fixes

- Browser regressions reproduced 24-pixel header-to-content gaps on account, party, and supplier creation. Desktop screenshots also showed narrow three-column identity fields.
- Creation pages now use 16-pixel spacing between related page blocks and the shared token rhythm within sections. Fields use two columns on desktop/tablet and one on phones; full-width descriptions retain their layout.
- Phone progress steps stack with readable labels. Desktop progress remains horizontal. Address/contact, tax, simple opening, and bill-wise opening were reviewed in both party/customer and supplier contexts.
- Account setup now explains that opening is optional, belongs in the final step, and is reviewed in the financial year's opening worksheet.
- Styling is limited to creation roots. Native fields, role/account creation, requiredness, permissions, exact decimal values, opening dates, draft protection, and save/retry requests are preserved. Existing edit, quick-create, opening, product creation, and completion behavior was verified.
- Stabilized a navigation regression by waiting for its existing asynchronous URL update before asserting that the protected relationship filter remains present. No directory behavior changed.

## Validation

- **561 Console tests passed across 23 files:** 554 regression tests across 19 files, plus seven browser tests across four files.
- **312 layout checks passed:** 144 account/party/supplier creation layouts, 36 existing opening layouts, and 132 product creation/completion layouts. The new creation checks use the actual Console stylesheet order and self-hosted Inter font at 1440, 768, 390, and 320 pixels in light, dark, and ledger themes. Checks cover 200% zoom, overflow, keyboard focus, header spacing, field columns, mobile progress labels, retained drafts, and visible bill totals.
- Scoped coverage for the two changed editors passes every configured threshold: **97.60% lines/statements, 94.73% functions, and 92.18% branches**.
- **57 shared UI tests passed across five files.** Console and shared UI TypeScript, UTF-8, and whitespace checks passed.
- Final desktop account identity, phone address/contact, and dark bill-wise opening screenshots were visually reviewed. Artifacts and logs are in ignored `.tools/account-party-creation-ui-review`, `.tools/account-party-creation-ui-coverage`, and `.tools/account-party-creation-ui-*.log` paths.

Shared creation styling reuses the existing stylesheet rather than adding app-local CSS. The UI package is bumped from 0.1.55 to 0.1.56; both consuming apps retain their workspace links and pnpm verified the unchanged lockfile. No database, API, model, migration, SDK, or new dependency changes were required.

Manual simplify and security reviews found no unresolved issues. Native company ownership, field access, opening validation, immutable retries, and audit/posting boundaries remain intact. No callable `/simplify` or `/security-review` command was available, so these reviews were performed manually.
