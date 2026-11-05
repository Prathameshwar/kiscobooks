# Tenant administrator UI fixes, 30 October 2026

All 12 bugs from the UI review have local fixes and passing affected regressions.
Three UI gaps are implemented locally; two have supported partial implementations.
Goods/statutory Purchase, native physical counts and real invitation receipt remain
open prerequisites. The [20-row results CSV](tenant-admin-ui-fixes-results-2026-10-30.csv)
keeps these states separate from live acceptance. Historical findings and failed
evidence have not been rewritten.

## Delivered behavior

Shared search, dropdown, lookup and native date controls now use the same outer
height; hints stay below and multi-select chips can grow. Money/related forms and
saved workflow actions use shared fieldgroups, grids and wrapping action groups.
Account-only entry hides item controls. Purchase validation associates errors with
controls and focuses a correction point. Audit failures no longer display an empty
count, and fixed security exclusions use readable text.

Saved vouchers load verified readable capture automatically, including revision,
native dates, source identities and configured money/quantity display. Back returns
to the voucher directory. The new scoped directory offers review and permitted
draft editing. The first editor supports ordinary money and untaxed account Purchase;
it preserves captured source versions, pins dates/type, refuses unsupported or
protected replacement shapes and retains exact same-key retry for uncertain saves.
It does not reopen submitted/posted records as editable drafts.

Customer ledger links now open PARTY_LEDGER with a company-verified reference.
Selected report definitions, sources and history load automatically without creating
a run. History has timestamps/full identities and wraps at phone width. Source
labels expose native ledger coverage and explicitly leave stock compatibility to
native admission. The designer uses a wrapping toolbar and one compact panel at
tablet/phone widths, with Escape dismissal and focus return.

## Verification and final review

- Affected Console suite: **182 passed**, including financial capture, permissions,
  failed reads, native designer restore/controls and new draft routes.
- Shared-control suite: **197 passed**, including eight actual Edge geometry checks
  at 1440/768/390px and multi-chip growth/focus.
- Final focused summary/editor/report/reference checks: **52 passed**. Three new
  common-label boundary/scope/abort tests also pass. These overlap earlier suites;
  their totals are assertion executions, not unique end-to-end scenarios.
- The last draft review reproduced a Purchase save dropping unrelated captured
  references/parties. Replacement now preserves them and existing line evidence;
  **25 final draft/directory/summary/reference assertions passed**, including cleared
  declared total, invalidated calculation acceptance and pinned source versions.
- Six final designer/history geometry assertions passed. The combined report also
  retained two helper-test cleanup fixture failures; the fixture was corrected and
  all three helper tests then passed in a separate final report.
- Console and shared UI TypeScript checks passed. Reusable Node runners passed
  syntax checks; offline acceptance records all 20 findings as **NOT_RUN**.

Bug regressions were reproduced before their fixes. Final review found an additional
report form-handler bypass of the disabled button when reference ownership failed:
the failing regression was recorded, both submission paths now share the guard,
and the test passes. Phone clipping in the longer history labels was reproduced and
fixed with shared wrapping styles. Duplicate scoped master-label readers were
consolidated and verified with bounded reads, company/identity checks and aborts.
The Purchase replacement correction was tested against a retained full capture,
including an unrelated external reference and party; their data remains present
after the versioned save.
Readable tax-context dates also remain pinned; this retains an existing untaxed
capture and does not implement an additional statutory profile.

Equivalent manual simplification and security/correctness review covered routes,
permissions, captured source versions, full-replacement refusal, uncertain replay,
scope changes, native decimal data and audit feedback. Named `/simplify` and
`/security-review` commands are unavailable here. No further defect was found in
the supported changed slice after the corrections. Native posting/release and
unimplemented profiles are not certified by that conclusion.

## Pending scope

| Finding | Remaining work |
|---|---|
| G01 | Dedicated editing for goods/tax, Sales, stock and other native captures; richer date/type changes. |
| G03 | Native generation metadata for full stock capability and source creation time. READY financial coverage alone cannot prove stock completeness. |
| G05 | Native goods/statutory capture, owner posting/bridges and legal artifacts under B15-B19/D05/C2. Country plus tax type controls supported behavior. |
| G06 | B25 native count model/API/migrations, concurrency/review/cost owner effect and C3 acceptance. Both policy questions are resolved: movements continue against a recorded cutoff; surplus uses current verified native cost or mandatory review. |
| G07 | Controlled provider/SMTP and mailbox configuration, followed by real invitation delivery and acceptance. |

The user shut down the VM during this work. Local implementation and verification
continued; no VM restart, live login, three-company post-fix acceptance or application
database changes were attempted afterward. The reusable [local checks](testing/tenant-admin/test-ui-fixes.ps1)
and [live recheck](testing/tenant-admin/verify-ui-fixes.cjs) are documented in the
[testing README](testing/tenant-admin/README.md). Live rechecking still requires
running services and the retained protected QA credentials/fixtures.
