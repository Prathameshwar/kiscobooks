# Company management

Approved scope, 2026-10-23: complete permission-aware company management in three
phases: directory/navigation; metadata-driven view/edit with the existing creation
wizard; API/database consistency, tests and final review.

Company management remains tenant-isolated. Tenant grants cover companies in that
tenant; company grants cover their named company. Account classification, including
platform administrator, never substitutes for these permissions. Cross-tenant support
uses the existing audited impersonation mechanism. Creation requires tenant-level
`company.create`; viewing requires scoped `company.read`; editing requires scoped
`company.update` and field-level write access. The working-company chooser remains
available without company management permissions.

The existing company table, reference foreign keys, audit outbox and posting locks
remain authoritative. This work needs no new table or migration. A request-only
timestamp precondition protects edits against concurrent changes. Layout and field
permissions come from Identity's field-set endpoint.

Routes: `/companies/manage` (management directory), `/companies/new` (creation),
`/companies/{id}` (view), `/companies/{id}/edit` (edit). `/companies` retains the
working-company chooser. Navigation offers management through the administration
rail, organisation page and chooser when permitted. View/edit never switch the
working company as a side effect.

Review findings fixed:

- Detail responses omitted saved terms and declaration text. Both now round-trip.
- Inactive companies were writable despite read-only field metadata. Writes now
  reject suspended/closed companies; reads remain available for history.
- Concurrent edits could overwrite changes. The UI sends `expected_updated_at`,
  checked under the company row lock before mutation; stale writes return 409.
- Visibility redaction unnecessarily blocked a management list that did not filter
  visibility. Unfiltered lists now omit the field; filtering it still requires read.
- Creation omitted configured custom fields and trapped validation errors in the
  retry screen. Custom fields now render and validate, and failed creation can return
  to the details. Feature selection requires tenant-level `company.update`.
- Edit navigation confirms discard, context switches are blocked while dirty or
  saving, failed reference reads retain drafts, and successful saves reload metadata.
- A final browser pass caught omitted presentation fields erasing formatter defaults.
  View formatting now preserves defaults for sparse responses; a regression covers
  both dates and exact money when those settings are unavailable.

Dedicated `/simplify` and `/security-review` tools were unavailable. Manual reviews
covered CLAUDE.md sections 5 and 6: no role-name bypass, tenant-filtered sessions and
object checks remain in place, the proxy still allowlists paths/methods/queries,
server-managed data cannot be patched, money stays exact text/Decimal, audit remains
in the write transaction, posting locks remain owner-enforced, and no hard delete
was added. No unresolved blocking finding remains in the implemented scope.

Database verification: local MySQL Identity revision `0085`, all 61 company columns
match model types/nullability; Alembic check reports no upgrade operations. The
database was checked read-only and needed no alteration. OpenAPI and generated
Identity client match; API client version is `0.2.9`.

Browser verification uses production components and shared styles with fixture API
responses. Directory, view, edit and save passed at desktop and 390px mobile widths
in light/dark/ledger, with no horizontal overflow or browser errors. Desktop and
mobile screenshots were inspected. This is not live IdP certification. Repeat with
`node mfes/apps/console/tests/company-management-e2e/run.cjs` after installing the
existing local Playwright browser tooling. Ignored artifacts are under
`.tools/company-management/browser`.

Validation evidence:

- Full Console run with two workers: **962 passed**, zero failures; 133 reported
  suites passed. The initial unrestricted run hit widespread scheduling timeouts;
  the controlled rerun resolved them without changing unrelated application code.
- Final focused company management/wizard run: **35 passed**, including the last
  feature-permission and sparse-formatting regressions added after the full run began.
- Identity company/CRUD/customization/setup/immutability/scope suites: **126 passed**.
  Final management regressions, including visibility redaction: **10 passed**.
- Console, Auth and API-client TypeScript checks passed; API-client tests **8 passed**.
  Identity Ruff, strict mypy on affected modules, OpenAPI and client generation checks
  passed. No dependencies or shared stylesheet changes were needed.
- The previously running managed Identity API was restarted, is ready on port 8001,
  and serves the updated concurrency/custom-field contracts. Other services and the
  disabled VM adapter were left as found.

Decision log, 2026-10-23: reuse the company table and existing CRUD rather than add
parallel storage; retain explicit scoped authority for every account classification;
use request-only timestamp concurrency for backward-compatible API consumers;
allow create-only actors to fetch creation field metadata without granting existing
company reads. No commit or publication was requested or performed.
