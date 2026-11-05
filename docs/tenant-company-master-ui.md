# Tenant, company and Catalog master UI delivery

Scope agreed by the user's phased UI request on 2026-10-24. Reuse the existing
Console shell, shared CSS, forms, tables, notices and navigation. Group means
Catalog item group/subgroup, consistent with the preceding master inventory.

1. Complete tenant/company validation and error recovery. Preserve current
   creation, invitation, field permissions, concurrency and company selection flows.
   Run the affected tenant/company suites before proceeding.
2. Add company-scoped unit, manufacturer and item-group directories, detail and
   create/edit pages. Use backend field sets, bounded paging, typed wire contracts,
   versioned/idempotent writes, permitted lifecycle actions and guarded navigation.
   Add narrowly allowlisted proxy routes and permission-aware navigation; test them.
3. Run UI tests, TypeScript checks and production build. Review permission/company
   boundaries, field access, exact quantities, failure messages and navigation.
   Record findings and remaining limitations here.

No datastore or backend domain change is planned. Lifecycle/dependency restrictions
continue to be enforced by the existing Catalog APIs.

## Execution and review

All three UI phases are implemented locally and reviewed.

### Phase 1: tenant and company forms

Company forms now check the backend's minimum lengths, patterns and available
choices before saving. Tenant and company forms preserve server field messages
and focus the first invalid control. Existing field access, concurrency,
invitations and company-selection flows remain covered by their existing tests.
Regression tests were confirmed failing before these fixes. The four affected
tenant/company suites passed with 59 tests at the phase boundary.

### Phase 2: company masters

Inventory navigation now opens Units, Manufacturers and Item groups for the
current company, subject to its active permission grants. Each resource has a
searchable, filtered, cursor-paged directory and create, detail and edit screens.
The implementation reuses the Console shell and `@janso/ui` CSS/components;
there are no additional application stylesheets or production dependencies.

Forms render permitted backend field-set metadata, with a native control map
for the Catalog wire types. Manufacturer and group custom fields reuse the
existing custom-field normalization and controls, including dynamic options.
Manufacturer party selections use the Accounting API's `status=ACTIVE` filter.
Unit quantity increments remain decimal strings and must fit the selected
precision; numeric inputs are rejected at the request-construction boundary.

Writes send changed writable fields, expected versions and an idempotency key
retained for unchanged retries. Conflict recovery retains the draft and asks
before replacing it. Pending writes and unsaved navigation are guarded.
Activation/deactivation use existing dependency-checked lifecycle commands.
Group creation takes a dated parent assignment; later moves use the separate
`item_group.move` permission and expected hierarchy generation. Parent history
is paged and respects metadata visibility; an omitted parent is not displayed
as a fabricated top-level assignment.

The proxy addition is limited to these three master namespaces and their field
sets, lifecycle commands and group history/move routes. Unknown methods, routes,
write queries, duplicate query keys and malformed IDs are rejected. Existing
same-origin, authenticated service proxying and backend object authorization
continue to enforce access independently of the UI.

### Phase 3: verification

- Console: **96 test files, 1,043 tests passed**, using
  `pnpm.cmd exec vitest run --coverage --maxWorkers=6 --minWorkers=2`.
  The process exits 1 solely for the existing global coverage thresholds below.
- Production Next.js build passed, including the new master route. The build
  used a separate ignored output directory to preserve the running Console.
  It exposed an existing Next.js page-props type error in the two notification
  index pages; removing their default parameter fixed it, with a regression
  type test confirmed failing first. Their optional search parameters remain.
- TypeScript checking passed.
- Edge/Playwright checked 24 combinations: three resources, directory/create/
  detail/edit, at 1440px and 390px widths. There were no browser errors or
  horizontal document/control overflows. Validation focus and create-to-detail
  navigation passed, and desktop/mobile screenshots were inspected.
- `git diff --check` passed. Build-generated changes to `next-env.d.ts` and
  `tsconfig.json` were restored; no configuration threshold was weakened.

Coverage was compared against unchanged committed source and tests using a
read-only Vitest source loader, without moving or resetting workspace files.
The baseline had 93 passing files and 988 passing tests.

| Console metric | Unchanged baseline | Final implementation | Configured gate |
| --- | ---: | ---: | ---: |
| Statements | 97.47% | 97.48% | 90% |
| Lines | 97.47% | 97.48% | 90% |
| Branches | 83.07% | 83.19% | 85% |
| Functions | 77.54% | 78.42% | 90% |

Overall coverage did not decrease. The repository-wide function and branch
gates still fail and must be addressed before treating the full coverage job
as green; this UI work does not claim that those pre-existing failures are fixed.

### Final review and practical limits

The requested simplification, security and correctness review was performed
manually against CLAUDE.md sections 5 and 6 because `/simplify` and
`/security-review` are not available tools in this session. Review fixes included
the Accounting status filter, ambiguous-save recovery messaging, exact increment
types, omitted parent-history values and distinct filtered/initial empty states.
No remaining security or correctness findings were identified in this task's
changes. Domain audit/outbox emission, field denies, lifecycle restrictions and
hierarchy validation remain the existing backend's responsibility; there are
no backend schema, money-execution or API-contract changes in this delivery.

Browser checks used fixture API responses with the actual shared shell and
styles. They do not establish a live authenticated write to the local database.
Review artifacts and full logs are kept in ignored `.tools/` paths, including
`master-ui-final-coverage.log`, `master-ui-baseline-coverage.log`,
`master-ui-final-build.log` and `master-ui-browser/checks.json`.

The separate sign-in outage was traced to the unavailable Authentik VM/tunnel.
After the user started the VM, its services were verified over SSH and the
managed tunnel was restored. A fresh sign-in request returned HTTP 200 with
the Authentik authorization URL, PKCE, state and nonce. Completing a user
credential login was not part of that probe. The managed tunnel remains running.

## Focused review follow-up (2026-10-24)

Requested by the user after the initial delivery. The review proceeds in two
phases: (1) reproduce and fix editor/detail validation, selection and pending
navigation defects; (2) fix directory and history access/recovery gaps, then run
the affected suites, build and desktop/mobile interaction checks. Existing
styles, API contracts and backend authorization remain the basis of the fixes.

Both fix phases and final verification are complete locally.

| Area | Review finding and fix |
| --- | --- |
| All three directories | Search, filters and sorts were sent before checking field access. Metadata now resolves first; unavailable settings are removed with a visible explanation, and their controls are hidden. Search requires both registered code/name fields, matching the API. |
| Units | Changing an authorized quantity field was blocked when its counterpart was omitted by a read deny. Submitted increments remain exact strings and are validated independently; cross-field precision is checked when readable, and the API checks the protected stored rule. |
| All three editors | Trimming a label or selecting the current integer option could send a redundant update. Native values now normalize before comparison, and an unchanged form says "No changes to save." without writing. |
| Manufacturers | A fabricated `selected` option overwrote a chosen party's cached name with its UUID. The picker now retains its actual option label. Saving is disabled when the only writable field needs unavailable party access. |
| Group creation | Parent identifiers lacked client validation and server parent errors were absent from the picker. Valid IDs are checked; parent errors are attached to the named control and receive focus. |
| Group moves | Parent/date field errors were lost in the generic modal message. They now appear beside each control, focus correctly and clear on edits. Missing or nonpositive hierarchy generations cannot be submitted. |
| Detail actions | Company changes could interrupt open or pending lifecycle/hierarchy actions. They now use the existing context/unload guard. Uncertain results explain recovery and unchanged retries retain their request key; conflicts direct users to cancel and reload. |
| Group parent history | Expired cursors retried the same failing page, and stale metadata could leave Next enabled. Expired-page recovery restarts at the first page; failed responses cannot supply the next cursor. |
| Manufacturer/group custom fields | Invalid custom types produced only a general notice. Per-field errors now identify and focus the invalid control. Immutable and generated values are excluded from edit requests, including dependent values reset by another control. |
| Custom conditions/defaults | Numeric conditions used string comparison during save, unlike the rendered controls, and defaults were resolved too late. One helper now resolves exact numeric conditions, defaults and editable fields for validation, request bodies and save availability. |
| Read-only/empty views | Empty directories suggested creation even without permission. They now direct readers to a company administrator; forms with no editable visible fields disable Save. |

Regression evidence: 25 new regression cases were run and confirmed failing
before the corresponding fixes (12 workflow/value cases, 8 access/recovery
cases, 3 custom-value cases and 2 condition/default cases). An additional passing
contract test verifies an invalid move date is rejected without a request.
The final affected master suites contain **77 passing tests**. An existing
directory test now locates the collection request directly rather than assuming
it precedes metadata: metadata-first admission is the intentional behavior change.

The focused simplification pass shares custom draft resolution between form
validation and Save availability. Security/correctness review rechecked company
grants, field projection, exact quantities, changed-field writes, versions,
idempotent retries and hierarchy dates against CLAUDE.md sections 5 and 6. No
remaining findings were identified in the revised master UI. Existing backend
checks remain authoritative; no API, database, CSS or dependency changes were
needed for this follow-up.

Final verification:

- **96 Console test files, 1,069 tests passed** with coverage, including the
  77 affected master tests. Full-suite output is
  `.tools/master-focus-final-coverage.log`.
- Production Next.js build passed; output is
  `.tools/master-focus-final-build.log`. TypeScript and `git diff --check` passed.
  Only the build's generated `next-env.d.ts`/`tsconfig.json` edits were restored.
- **24 layout checks and 50 focused browser scenarios passed** at 1440px and
  390px. The focused scenarios cover all three resources' validation,
  create/edit, no-change saves, lifecycle failures/retries, restricted fields
  and reader empty states; group parent/date/history failures; and numeric
  custom conditions, defaults, validation focus and confirmed request bodies.
  There were no page errors or horizontal control/document overflows. Mobile
  hierarchy errors, restricted-field views and desktop custom-field errors
  were also inspected visually.
- Browser responses were fixtures, as in the initial delivery. No live
  database write or production publication is claimed. Review screenshots and
  results are in `.tools/master-focus-browser/`; layout results are in
  `.tools/master-ui-browser/`. The temporary preview server was stopped after
  verification; the running application services were preserved.

| Coverage metric | Before focused review | After fixes |
| --- | ---: | ---: |
| Statements/lines | 97.48% | 97.50% |
| Branches | 83.19% | 83.60% |
| Functions | 78.42% | 78.50% |

Every overall metric improved. The existing global branch (85%) and function
(90%) thresholds still fail, so the coverage command exits 1 despite all tests
passing. Those thresholds were retained and this follow-up does not claim a
green repository-wide coverage gate.
