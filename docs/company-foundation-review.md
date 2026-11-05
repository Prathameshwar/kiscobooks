# Company foundation implementation and reviews

Completed 2026-10-23 for priorities 1-4. The four-phase plan and execution checklist are
in [company-foundation-todo.md](company-foundation-todo.md). The proposed future Sales,
Purchases and Inventory page hierarchy remains a later workstream.

## Behavior and usage

### Company context

The selector still reads Identity's authenticated self-read company choices. A switch
verifies the exact company returned by Identity. An explicit financial year also requires
Accounting to return that year under the selected company's scoped path before either
cookie is written. Denials, malformed responses and dependency failures preserve existing
cookies. Step-up remains with Auth. Cookies remain hints: services independently enforce
object scope and document dates.

Rail/directory selection uses a shared in-flight switch guard. A full reload resolves new
permissions and display settings. Providers remount workspace state on company/account/
authority changes; the shell remounts workspace state on year changes. A successful change
therefore discards unsaved transient workspace state; this adds no persistent draft store
or cross-company draft migration. Stale search/readiness responses abort and are ignored.
Calendar controls hide after loss of calendar authority even with a prior context object.

### Settings ownership

- `/settings`: **Company settings**, with readiness and delegated access review for the
  company currently open. Without a company it provides selection guidance.
- `/organisation`: **Organisation administration**, with implemented company, delegated
  role and notification destinations authorised by active tenant-scope grants. Company
  and department grants are not promoted. Denied destinations stay absent.
- `/platform`: platform administration and global reference catalogs. Compatible catalog
  URLs stay at `/settings/{catalog}`, but guards, breadcrumbs and rail identify platform
  ownership. Global catalogs no longer appear as disabled tenant settings cards.
- Tenant notification URLs stay compatible. Their server page uses tenant-scope grants
  for management, matching the API, and returns to Organisation administration. Shared
  providers/recipient policy are not represented as company-owned controls.
- The role directory remains a delegated-access surface. Identity filters records and
  independently rejects out-of-scope role changes and assignments.

### Navigation and direct pages

`navigationFor(session)` is the single resolver for sidebar and command search. It checks
company presence, effective read keys, organisation authority and destination availability,
then removes empty sections. Future invoice/payment/ledger/tax/item/stock links stay hidden
until their pages exist. Existing rail/search/drawer primitives and shared CSS are reused.

Overview/customer loading now waits for company/read authority. Product editor pages have
explicit read gates. Company Audit refuses an explicit company filter that differs from
the company currently open, with instructions to switch first. Missing-company and denied
visits do not mount audit reads. Every API continues to independently enforce authority.

### Company readiness

Open **Company settings > Company readiness** at `/settings/readiness`.

| Check | Existing owner API | Read authority |
|---|---|---|
| Identity/defaults | Identity company detail | `company.read` and field policy |
| Features/locks | Identity `setup-readiness` | `company.read` and protected-input policy |
| Books | Accounting `financial-setup` | `accounting.finance.read` and field policy |
| Selected-year prerequisites | Accounting `fiscal-years/{id}/readiness` | `period.read`, `accounting.finance.read`, `ledger.read` and field policy |

Missing books, unknown calendars, inaccessible inputs, dependency failure, incomplete
openings, unopened/closed periods and configuration reconciliation are distinguished.
There is no global readiness score. A satisfied year check does not authorise a document's
posting. Selected years remain display context; posting dates remain authoritative.

Chart/account mappings, numbering and tax registration/licence applicability remain
explicit responsibilities rather than fabricated automated checks. The screen is read-only:
it does not initialise books, change protected fields, finalise openings, open/close periods
or activate statutory capabilities. Management pages for existing companies remain later work.
The existing new-company wizard still bootstraps books only with tenant-wide authority.

## Review 1: authority, isolation and response handling

Walked repository security/correctness rules, API authority, cookie writing, scoped grants,
field redaction and data-loading gates. Initial regressions reproduced five selection/state
problems before their fixes. This review then reproduced and fixed five more findings:

1. Malformed IDs could throw during selection verification. IDs are now type/shape checked;
   inconsistent company/year responses return 502 and write no cookies.
2. Accounting book facts for another company could render. Owner mismatches are refused
   before facts display.
3. Explicit Audit company links could conflict with the selected-company header. The page
   now asks the user to switch and does not mount mismatched reads.
4. Audit direct visits lacked an explicit page read gate. Denied visits now refuse before
   mounting the Audit component; no-company visits show guidance.
5. Organisation navigation could expose a workspace with no implemented permitted entry.
   The resolver now requires an accessible company/role/notification destination.

All 39 focused review checks passed. Existing API authority was preserved. No permission
catalogue, backend contract/model/migration or broad proxy wildcard was introduced.

## Review 2: navigation, recovery and presentation

Inspected direct visits, role/company/year changes, command/rail consistency, readiness
errors, breadcrumbs, mobile layouts and browser switching. Fixes and verification:

- Overview/customer loaders now check authority before starting. Product editors have
  direct read guards and company-keyed state.
- A deferred-request regression reproduced concurrent selection racing across entry
  points; the shared browser helper now serializes company changes.
- Calendar selectors/chips and readiness do not disclose stale year context after read
  authority is removed.
- Company creation and automatic books bootstrap now require their active tenant-scope
  grants in the wizard and entry controls, matching the API. A current-company grant
  cannot promise administration of a newly created company.
- Reference breadcrumbs/active rail return to Platform administration; tenant notification
  navigation returns to Organisation administration.
- Screenshot inspection found long refresh labels crowded mobile card headings. Labels
  are now short, with descriptive accessible names.
- The browser fixture lacked production's `janso-root` body class. Corrected the fixture
  and tested content-pane width as well as document width to detect internal clipping.
- A repeated company query parameter could crash Audit link handling. A failing regression
  reproduced it; non-scalar filters are now rejected before mounting history reads.
- Updated tests intentionally describing the old Settings/catalog placement. Unrelated
  business implementation was preserved.

## Verification and limits

- Final full Console suite: **905 passed** against frozen application source. Additional
  final readiness checks: **12 passed**, covering frozen features and a satisfied year
  check without posting authority. Console TypeScript passed. The scoped creation/calendar
  follow-up also passed all **38** affected checks.
- Existing affected Identity gateway/session/setup suites: **21 passed**.
- Existing Accounting fiscal/readiness suites: **11 passed**, including owner scope,
  field policy, immutable financial setup and readiness failures.
- Chrome journeys passed company A/B selection, changed navigation permissions, financial
  year selection, workspace reset, denied selection preserving cookies, company-only
  versus tenant administration and limited-read presentation.
- Light/dark/ledger layouts passed document and content-pane overflow checks at 390px;
  desktop/narrow screenshots were inspected. Local ignored artifacts:
  `.tools/company-foundation-browser-57b36d102a594892b985e9d2c8ce1921`.
- Browser fixtures exercise production shell, Providers, readiness component and Next
  proxy/selection routes with fixture Identity/Accounting upstreams and an HttpOnly test
  session. They are not live-IdP/full-deployment certification. Real owner authority is
  separately exercised by the API suites above.
- Dedicated `/simplify` and `/security-review` tools were unavailable. Both reviews were
  manual and test-backed, not independent external audits. No blocking local findings
  remain within this scope.

Existing dashboard/customer loaders remain fixtures pending the later business-page
workstream; this task adds context/read guards rather than replacing those sources with
live business APIs. Readiness itself uses the existing live service contracts. All fixture
services are loopback-only, terminate after their run and are absent from production routes.
No dependency, stylesheet, deployment, commit or publication was added. Concurrent
inventory/reporting changes were preserved.

Repeat browser checks from the root with existing frontend packages and Chrome installed:

```powershell
uv run --no-project --with playwright==1.56.0 python mfes/apps/console/tests/company-foundation-e2e/run.py
```

Decision: preserve local paths and compatible URLs, add only the minimum settings/readiness
surfaces for priorities 1-4, reuse owner APIs, and defer future business/action pages.

## Final sequential review — 2026-10-23

1. **Company isolation and context.** Rechecked verified company/year selection, atomic
   cookie writes, switch serialization and client state resets. Four regressions reproduced
   two remaining edge cases: optional context reads could throw, and a dirty editor could
   cancel navigation after cookies had already changed. Calendar reads now require
   `period.read`; unavailable list/calendar reads leave an explicit unavailable state.
   Next authentication and step-up redirects are rethrown. Existing editor unload guards
   now also block company/year changes before any selection request. Saving or leaving
   the editor releases the block. Browser checks prove blocked switches preserve cookies.
2. **Scope separation.** Rechecked active tenant grants against the owner's inclusive
   validity windows. Company/department/missing grants cannot grant organisation controls.
   Company creation and new-company books bootstrap require tenant authority. Company
   settings, organisation notifications and global platform references retain their own
   surfaces. No additional scope defect found.
3. **Permission navigation.** Rechecked the single rail/search resolver, direct-page read
   gates, absent-company handling and Audit query scope. Removed a Platform history link
   for notification-only administrators because that page requires a separate permission.
   Platform entry and page now share their permission list; corrected stale resolver docs.
4. **Company readiness.** Rechecked company/year ownership, cancelled responses, read-only
   API calls, per-card retries and denied/missing/error states. Additional checks confirm
   sparse/redacted books fields remain unknown and another year's result cannot display
   satisfied prerequisites. No readiness implementation defect found.

Focused final-review checks: **84 passed**. Console TypeScript passed. Chrome passed
unsaved-editor protection, A/B permission refresh, financial-year selection, draft reset,
denied selection preserving cookies and tenant/limited-read presentation. Document and
content-pane widths passed at 390px in light, dark and ledger themes. The new light mobile
screenshot was inspected. Artifacts:
`.tools/company-foundation-browser-76755b5dcab04a858cc33858f3e5183c`.

Final full Console run: **917 passed**, zero failures/skips; **131 reported suites passed**.
Affected owner APIs: **21 Identity checks passed**, **11 Accounting fiscal/readiness checks
passed**. Whitespace checks passed. Desktop and mobile screenshots were inspected.
All four final-review items are complete with no blocking findings within the implemented
scope. Browser upstreams remain fixtures; the deployment and business-loader limitations
above still apply. No commit or publication was performed for this review request.
