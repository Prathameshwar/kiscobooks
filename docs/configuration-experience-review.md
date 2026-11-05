# Company configuration experience review

Scope: Company settings and its Financial years, Company configuration, Product
configuration and Account/party/supplier configuration workflows. Reuse existing
shared controls, CSS and layout; preserve native API validation and permissions.

## Delivery plan

1. Review the entry pages, related forms, read-only/loading/error states, navigation,
   validation focus and retained drafts. Identify concrete usability gaps.
2. Add failing regressions, fix the gaps, and run the affected UI suites. Preserve
   company authority, protected fields, exact decimals and uncertain-command recovery.
3. Check the real components with existing CSS at desktop/mobile sizes in the three
   themes; run TypeScript and manually review security, correctness and simplification.

## Findings and verification

- Return paths now retain Company settings, company configuration and filtered
  directories through scopes, drafts, records, editors and related configuration.
  Shared navigation validates each parent, bounds nesting and rejects external,
  encoded traversal and ambiguous duplicate return destinations.
- Saving on the same details page preserves its original parent rather than
  constructing a self-return link. Back labels and settings breadcrumbs identify
  the actual directory, scope, record, effective-settings or adoption destination.
- Financial year generation focuses local/native validation errors. Interrupted
  generation retains the year and request key; an interrupted period transition
  retains its reason/body/key when its review is closed and reopened. New changes
  and refreshes remain disabled until that command is recovered.
- Product inspection and adoption mark and focus missing/invalid dates and owners.
  Source-revision links preserve the originating inspection/review and invoke its
  leave guard. Readable product dates use the company display formatter.
- Empty product/accounting filtered lists offer a clear-filters action. Clearing
  supplier filters retains the fixed supplier-role constraint. Financial period
  statuses use readable labels.
- Existing shared cards, inputs, searchable references, notices, dialogs, table
  layouts and theme CSS are reused. No API, model, migration, permission catalogue
  or dependency change is required.

Verification: the full console run passed **1,727 tests in 134 files**. After the
final source-navigation/date refinements, **423 affected tests in 20 files** passed.
TypeScript and the final production build passed. **128 browser checks** passed
at 1440px/390px across light/dark/ledger themes, using the real console components,
the production layout's CSS and isolated fixture API responses. Browser checks
cover read-only actions, overflow, draft preservation, validation focus, nested
return links and exact recovery; they do not change live business configuration.

Manual CLAUDE.md sections 5/6 and simplification review checked company authority,
read-only and masked fields, safe return navigation, retained drafts, immutable
publication/lifecycle rules and exact command recovery. Backend checks, idempotency,
audit/outbox and decimal storage remain authoritative. The `/simplify` and
`/security-review` commands are unavailable here; the reviews were performed manually.
No unresolved finding remains in the reviewed changes.
