# Company edit layout review

Requested scope: align Edit company with the existing create/edit design system.

1. Reproduce the missing shared form/context layout and document-text accessibility
   gaps with regression tests.
2. Reuse FormLayout, one form card, named sections and an attached FormActions
   footer. Provide saved company context and posting/access guidance beside the
   editor. Keep reference loading, field metadata, validation, save concurrency,
   locked fields and draft/discard behavior intact.
3. Run affected company tests and TypeScript; inspect desktop/mobile layouts in
   all themes, including validation, save, cancel and locked-field states.

Decision 2026-10-27: company editing uses the same shared form/context layout as
other routed editors. No new app stylesheet, API contract or database change is
required. Company creation remains its existing guided wizard.

## Completed changes and verification

Edit company now uses FormLayout with one form card, a saved-company context card
and an attached FormActions footer. Named sections use SectionHeader, short fields
use the responsive shared form grid, and document text spans the form width.
Custom-only sections omit empty native-field grids. The details view reuses the
same section hierarchy in one read-only card without editor controls or an aside.

The context card identifies the saved company/code/status and explains posting
locks and save/cancel behavior. Visual review found that ReviewList's fixed label
column left company names too little room in the narrow aside; the shared ListRow
now presents that identity instead. The discard dialog explicitly offers Keep
editing. Document text uses FieldLabel, metadata character limits and associated
hint/error text.

Regression tests reproduced the absent editor layout, document-text description
gap and unsuitable aside review grid before their fixes. All 96 tests across six
affected company/navigation suites passed, including permissions, hidden/locked
fields, exact PATCH payloads, concurrency conflicts, draft protection, save errors
and reference retries. Console TypeScript and changed-file whitespace checks passed.
The pre-existing CompanyConfiguration tests emitted React act/jsdom navigation
warnings while passing; this change did not alter that component.

A browser harness used the real Console shell, CompanyProfile and shared styles
with fixed service responses. Twelve width/theme combinations passed (320, 390,
1024 and 1440 px in Light, Dark and Ledger). Desktop/mobile screenshots were
inspected. It also exercised validation focus, Cancel/Keep editing, save success,
unchanged-save disabling, locked fields, reference outage and the read-only view.
No browser errors or horizontal overflow were found. No live company was changed.

Manual simplification and CLAUDE.md security/correctness review found no remaining
blocking issue. The named simplify/security-review commands are unavailable in this
session. Company field authority, posting protection, API payloads and database
contracts are unchanged. Unrelated workspace changes were preserved.

A subsequent read-only live check under the reported tenant account verified all
48 available controls in seven sections at nine width/theme combinations (320,
390 and 1440 px). The unchanged Save button stayed disabled and the action footer
was reachable. No live company settings were changed.
