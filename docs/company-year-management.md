# Company and financial-year management

2026-10-23: user authorized the proposed phases and requested end-to-end fixes,
including correct kebab-menu links. Phases: (1) review/fix navigation and calendar
validation; (2) company-scoped year generation and period management UI; (3) API,
database, browser and regression verification with final security/simplification review.

Accounting remains the calendar owner. Company/year codes and start dates are unique
within the tenant/company; generation is idempotent and rejects overlapping years.
Dates/codes are derived from the company's fiscal anchor, never independently edited.
Periods control posting; there is no editable year status or year deletion.

Reads require scoped `period.read`; generation/open, close, reopen and terminal lock
retain their existing permissions and transactional audit/version/idempotency checks.
Platform role labels do not grant access to tenant books. Creation and period changes
must not silently change the working company/year selected in the shell.

Existing unrelated workspace changes are preserved. No publication is requested.
All three phases are implemented. Routes are `/companies/{companyId}/years`,
`/companies/{companyId}/years/new` and `/companies/{companyId}/years/{yearId}`.
Both company lists offer scoped **Manage years** links; directory view/edit and
year-detail destinations are ordinary links, preserving browser navigation and new tabs.

Review findings fixed:

- Menu navigation previously depended on command callbacks. Shared `MenuItem.href`
  now renders safe links; commands remain buttons. Disabled destinations omit `href`
  so auxiliary clicks cannot navigate around their disabled reason.
- Company chooser pagination discarded first-page metadata. The actual cursor and
  page size now survive server rendering; retries and search reset appropriately.
- Shell calendar reads requested an unsupported sort and ignored continuation pages.
  Bounded pagination now follows years/open periods, validates a selected year outside
  that window, and explicitly reports unavailable or limited results.
- Company creation/edit accepted impossible month/day combinations. API validation
  checks the combined anchor, including single-field edits; UI previews no longer
  conceal an invalid anchor. February 29 remains supported through existing fiscal rules.
- Suspended/closed companies could receive new addresses, licences, statutory IDs
  and tax registrations. These creates now share a scoped active-company guard under
  the company row lock; lifecycle changes acquire the same lock. Historical reads remain.
- Fresh-company books initialization missed its Accounting foundation. The existing
  bounded finance bootstrap now creates its required lock and starter chart (five heads,
  28 groups and 12 accounts), without granting chart/template CRUD. The wizard opens the period containing books start,
  rather than always opening period one or claiming closed books are open. Since 2026-11-03 it also opens every later
  period of that year ([company-setup](company-setup.md) decision log).
- Close/reopen/lock-only actors could not use transition field metadata. Writable
  hints now reflect these permissions; actual commands still enforce each transition.
- Added a read-only reconciliation review plus explicit reasoned confirmation for
  unused books. Existing server guards refuse posted/used books and stale reviews.
  Sparse metadata or an incomplete twelve-period calendar never enables status changes.

Manual security review covered CLAUDE.md sections 5 and 6: tenant/company object scope,
active grants, field redaction, narrow proxy paths, signed company facts, CSRF transport,
idempotency, optimistic versions, terminal lock confirmation and transactional audit.
No account-classification bypass, direct table CRUD or hard delete was introduced.
Manual simplification consolidated retry reads and reused existing shared layout,
formatting, tables, forms, dialogs and menu infrastructure. Dedicated `/simplify` and
`/security-review` tools were unavailable; these were manual, test-backed reviews.

Verification:

- Full Console: **988 passed**, zero failures; shared UI: **1,796 passed**, zero failures.
- Final focused financial-year/wizard/context regressions: **54 passed**.
- Identity company management/CRUD: **39 passed**; Accounting fiscal API/domain,
  reconciliation and new company-year checks: **36 passed**.
- Final inactive-company setup checks: **8 passed**, covering all four create paths
  for both suspended and closed companies while preserving historical reads.
  Final combined management/statutory/registration API rerun: **55 passed**.
  Shared menu's final disabled-link regression run: **35 passed**.
- Console, Auth and API-client TypeScript checks passed; API-client **8 tests passed**.
  Identity/Accounting OpenAPI and Accounting generated-client checks passed.
  Ruff and strict mypy checks passed on affected API modules.
- Browser checks exercise production components/shared CSS with fixture upstreams:
  six page modes, all three themes, desktop and 390px mobile, kebab navigation,
  company save and period open. No page errors or horizontal overflow; screenshots
  inspected. This does not certify live IdP or distributed posting integrations.
- Local MySQL Identity `0085`: all 61 company columns match; Alembic has no drift.
  Accounting fiscal tables match types/nullability, existing scoped unique keys are
  present, and duplicate year codes/start dates are absent. Accounting's pre-existing
  pending import-storage revisions `0157`–`0167` were reviewed and rehearsed in a
  disposable MySQL database, then applied after a local backup. Full Accounting
  Alembic check passes; existing fiscal row counts were preserved. No company/fiscal
  table migration was required by this feature.
- Managed Identity and Accounting are ready on ports 8001 and 8011. The disabled VM
  adapter and unrelated services were preserved. Backups/test artifacts are ignored
  under `.tools/company-management/`; no credentials were saved by this task.

Decision log, 2026-10-23: keep generated calendars and period lifecycle authoritative;
reuse existing commands rather than introduce editable year status/date/delete APIs.
Client packages advance to `@janso/ui` 0.1.17 and `@janso/api-client` 0.2.10.
This supplies company/year management and the unused-books recovery UI; it does not
claim the older distributed Identity/Accounting posting reservation work is complete.
No commit or publication was performed.
