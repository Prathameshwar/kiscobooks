# Product creation UI review - 2026-11-02

1. Review Simple and Product Profile/SKU creation with the existing native field fixtures. Capture each step and optional setup at desktop, tablet, and phone widths in all three themes. Check spacing, label wrapping, field alignment, keyboard focus, and overflow.
2. Fix verified presentation and navigation issues using the shared design system. Keep the existing fields, creation requests, configuration rules, and completion destinations intact.
3. Run affected creation, access, draft, completion, and browser suites plus TypeScript. Review the final screenshots and record findings and validation.

## Completed review and fixes

- Reproduced mobile step labels wrapping across four lines and desktop SKU trading flags interrupting the identity row. Added failing browser and component regressions before making the layout changes.
- Product Profile/SKU identity fields now use the shared two-column form grid, with trading flags together on the following row. Narrow screens keep one field per row.
- Creation steps remain horizontal on desktop and stack with readable labels on phones. Header-to-form spacing is 16 pixels, and related content uses shared spacing tokens.
- Styling is scoped to the creation root. Existing edit, completion, opening, and other master screens retain their own layout. Existing fields, field policy, configuration rules, creation requests, retry keys, and completion destinations are preserved.
- Updated a stale test that expected the older completion-page link. It now verifies the saved SKU's setup destination, defaults acceptance, and one create request.
- Added recovery checks for field/configuration retries, company-defined product and SKU inputs, server validation, latest-revision reference review, and explicit draft-discard confirmation.

## Validation and final review

Browser checks cover 96 creation layouts (two modes, four steps/setup panels, four widths, three themes), 36 completion layouts, and 60 opening layouts. Creation and completion captures use the actual Console stylesheet order, palettes, and self-hosted Inter font. The standalone fixture lets the document scroll for full-page screenshots. Checks include 200% zoom, horizontal overflow, keyboard focus, mobile label wrapping, compact desktop progress, header spacing, and SKU field/flag alignment.

- **351 Console tests passed across 26 files:** the final 348-test regression run across 23 files, plus three browser tests covering 192 layouts. Coverage initially exposed missing recovery-path tests; the final scoped aggregate passes every configured threshold at **93.83% lines/statements, 93.18% functions, and 87.62% branches** for the two changed editors.
- **57 shared UI tests passed across five files**, covering content, form, wizard, stepper, and setup layout.
- **Console and shared UI TypeScript checks passed.** UTF-8 and whitespace checks passed. Scoped coverage and the final regression log are in `.tools/product-creation-ui-review-coverage` and `.tools/product-creation-ui-review-tests.log`.

Final desktop identity, phone tracking/review, Simple setup, and dark completion screenshots were visually reviewed. Artifacts are in the ignored `.tools/product-creation-ui-review`, `.tools/product-created-review`, and `.tools/product-opening-review` directories.

The shared UI package is bumped from 0.1.54 to 0.1.55. Both consuming apps still resolve the package through the existing workspace links; pnpm verified the unchanged lockfile. No new dependencies, API/schema changes, migrations, or database writes were required.

Manual simplify and security reviews found no unresolved issues. These changes use shared token styles and grid classes, preserve native field metadata and company/product ownership checks, and keep existing validation, exact decimal inputs, draft protection, and save/retry behavior. No callable `/simplify` or `/security-review` command was available in this session, so these were manual reviews.
