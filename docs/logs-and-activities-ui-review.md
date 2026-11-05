# Logs and activities UI review — 2026-10-30

Administer now opens `/logs-and-activities`, with Audit logs and Activities cards.
Both history pages link back, and the sidebar keeps the hub selected. Company
and tenant grants determine each card independently; direct routes remain valid.

Audit logs and Activities now share card gutters, bounded filter controls,
wrapping toolbar actions, table borders and paging presentation. Audit evidence
styles moved from Console CSS to the shared UI library. Long action names,
identifiers, hashes and exact before/after values wrap at narrow widths.
Activities uses readable subject/actor references with full IDs in their titles,
one status-appropriate error state, and retained rows during a normal refresh.
Changing company immediately resets its rows, cursor stack and pending request.

Review found and fixed blank activity reference cells, stale company activity
state, generic/duplicate cursor-error feedback, narrow toolbar overflow, nested
evidence tables inheriting stacked-row styles, and a pinned audit heading escaping
the visually clipped mobile header. The new refresh control returns to the first
audit page while retaining its typed filters and discarding its old cursor.

## Validation

- Console: **135 passed** across 17 affected test files, covering hub branches,
  navigation, audit/activity pages, errors, filters, refresh, signed cursors,
  evidence masking, exports, native BFF authorization and platform reuse.
- Shared UI: **467 passed**, including DataTable, ActionCard, FilterBar, Card,
  column/export controls, content layout and contrast.
- Edge: **3 browser tests passed**, exercising **36 layouts**: three actual
  component surfaces × widths 1440/768/390/320 × light/dark/ledger. Geometry checks
  cover overflow, card placement/focus, filter alignment and evidence headings.
  Screenshots were visually reviewed, including phone audit details and dark
  Activities. Component interactions are covered by React Testing Library;
  browser layout fixtures use rendered component DOM and shared CSS.
- Console `pnpm exec tsc --noEmit`: passed.
- Fail-first reports retained locally for admission, cursor feedback, company
  switching, blank references, toolbar overflow and pinned mobile headings.

An initial parallel run timed out in a platform-history interaction; it passed
alone and the final affected run passed with two workers. Vite's CJS deprecation
notice remains tooling output; the final JSON reports all have `success: true`.

No live tenant-login/API integration run was performed: the VM is shut down.
Browser/component transports were deterministic test fixtures. This report does
not claim a deployed or live-data check.

## Reuse

The cases and findings are in
[CSV results](testing/tenant-admin/logs-and-activities-ui-results.csv).
The page/navigation tests and `activity-feed.test.tsx` are normal Console tests.
Run the affected suite from `mfes/apps/console` with two workers; include
`audit-events`, `audit-event-evidence`, `audit-page`, `activity-page`, `audit-api`,
`audit-proxy`, `platform-audit-events` and administration/navigation suites.

For the layout review, from `mfes/apps/console` in PowerShell:

```powershell
$env:QA_LOGS_BROWSER = '1'
pnpm.cmd exec vitest run tests/logs-and-activities-layout.browser.test.tsx --maxWorkers=1 --minWorkers=1
Remove-Item Env:QA_LOGS_BROWSER
```

The opt-in test uses the existing `.tools/ui-review-runner` Playwright installation
and local Edge. JSON evidence and screenshots live under ignored `.test_artifacts`.

## Final security and simplification review

Walked CLAUDE.md §§5–6 and the final diff. No unresolved findings in this change.
The hub performs no data fetch; route checks fail closed for missing, expired or
other-company grants. Native APIs still authorize each read/export independently.
Evidence masking, exact values and immutable records remain intact. Refresh
reuses no cursor across company/filter changes, and abandoned activity requests
cannot populate a new company. No API/database/grant/data writes were added.
Shared UI is version 0.1.41; consuming apps use unchanged `workspace:*`/`link:`
lock entries. Concurrent local-auth work is outside this delivery.

`/simplify` and `/security-review` are unavailable in this environment; the manual
reviews above were completed instead. The implementation reuses shared controls
and styles; no additional dependency or duplicate app stylesheet was introduced.
