# Company configuration UI and API

Requested 24 October 2026: plan and implement company configuration end to end,
reusing the existing styles, layout and owner APIs. No implemented `comfix` concept
was found. The optional clarification received no answer, so this delivery treats it
as company configuration/features. Document numbering prefixes are a separate scope.

## Phases

1. Harden and verify Identity's existing feature APIs. Reject changes for inactive
   companies, protect reviewed changes with optional `expected_updated_at`, advance
   the company version for actual feature changes, and emit audit events only for
   actual enables/disables. Preserve scope checks, dependency closure, tax gates,
   first-use locks and pending-use disable guards. Export OpenAPI and regenerate the
   Identity client with its version/lock updates. These are request-only additions;
   existing models and migrations remain authoritative.
2. Implement a company configuration page and working-company settings entry.
   Reuse existing metadata-driven company viewing/editing for profile/defaults.
   Provide server-catalogued features with enabled/dependency/tax/lock explanations,
   explicit enable/disable review, required reason, pending/uncertain/conflict
   handling, refresh and draft guards. Add company kebab/profile/settings links and
   safe breadcrumbs/back navigation. Permissions follow active tenant/company
   grants; account labels confer no authority. Downstream books, registrations,
   product configuration and voucher execution retain their separate readiness.
3. Exercise API persistence/audit/scope/validation and UI/BFF contracts; run affected
   checks, type/build/generated-contract checks and desktop/mobile browser flows.
   Review security and correctness, fix findings, and record evidence and limits.

Enabling a feature is an Identity configuration change and does not assert that a
downstream voucher, provider or reporting workflow is ready. No live company flags
will be toggled during verification. Tests use isolated application databases and
fixture browser responses. Existing local edits and other running services are preserved.

## Findings before implementation

- Company profile/defaults already use field metadata, concurrency and posting locks.
- Settings currently exposes readiness/people/access but no configuration page.
- Feature enable/disable APIs exist; the browser boundary admits only enable.
- Feature writes currently omit inactive-company admission and reviewed-version
  checks; enabling an already-enabled feature emits an inaccurate extra audit event.
- Feature state/locks/dependencies are available through setup readiness and the
  server catalogue, so no parallel settings table or hardcoded feature list is needed.

## Delivery and validation

All three phases are implemented and reviewed locally.

### Entry points and behaviour

- Company settings offers **Company configuration** for the company currently open.
  `/settings/company` is also a working-company entry, with company selection when
  none is open and company creation only through an active tenant creation grant.
- Manage companies has **Configure company** in each readable company's kebab.
  Company details links to configuration. The canonical route is
  `/companies/{companyId}/configuration`; it does not switch the working company.
- Breadcrumbs, back links, related details/years and editing preserve validated
  internal return context, including directory filters and the settings origin.
  Readiness links apply only to the working company. Invalid identifiers are rejected
  before resolving business context. Related links respect their existing permissions.
- The existing metadata-driven editor continues to own company identity, regional,
  financial, presentation and document defaults, field validation and posting locks.
  Its save/cancel flow returns to the configuration page with refreshed values.
- **GST settings** follows **Edit company settings** for readable India GST companies.
  It opens `/companies/{companyId}/gst-settings`, which owns GST registrations and
  dated outward reporting profiles. Company configuration keeps defaults/features
  and performs no India GST history reads. The dedicated page preserves its
  configuration return and guards drafts, pending saves, refresh and report links.
  Non-GST configuration retains its existing tax-applicability view. This
  2026-11-02 navigation decision is documented in `company-gst-settings-page.md`.
- Features come from the server catalogue and setup snapshot. Search, status,
  dependencies, tax availability, first-use protection and disabled-action explanations
  reuse the shared table/search/kebab/dialog components and existing CSS.
- A feature change requires an explicit review and a printable reason of 1–200
  characters. The review identifies the company, feature, action and automatically
  enabled dependencies. Pending actions block double submission, navigation and company
  context changes. Conflicts, expired access, uncertain results and malformed successful
  responses freeze the review until an explicit read refresh; mutations are never replayed
  automatically. Reason validation stays editable and focused. An old enable reason
  cannot silently become the reason for disabling an already-applied uncertain change.
- Active scoped `company.read` admits viewing and `company.update` admits changes.
  Readers, suspended/closed companies and inconsistent feature snapshots get inspection
  or repair guidance. Platform/tenant/company account labels grant no permission by
  themselves; Identity independently resolves current endpoint and object grants.
- Partial, duplicated, unknown or invalid feature snapshots and mismatched company/version
  responses are rejected. Session expiry offers sign-in with the configuration return.
  Enabling a capability does not certify downstream readiness or activate money execution.

### API, database and client alignment

Identity's existing enable/disable APIs accept optional `expected_updated_at`, checked
under the company row lock. Inactive companies cannot change features. Actual changes
advance the company review version and updater and emit the existing audit event through
the same transaction's outbox. A repeated enable produces neither an invented change nor
an extra audit event. Profile edits based on an older feature configuration are rejected.
Existing dependency closure, tax gates, first-use and pending-use disable guards remain.

The optional request additions preserve existing wizard/script callers. The console sends
the displayed version and reason. The fixed company BFF now admits POST disable as well
as enable, retaining its method/service/path/query restrictions. OpenAPI and generated
Identity types are synchronized; the API client is **0.2.15** with lockfile updates. No
SQLAlchemy model or stored schema changed, so no migration was added. A read-only check of
the local Identity database reports **0085** for both migration and database head, **55**
model tables, no missing/extra tables and `alembic check` success. No live company flags
were changed during verification.

### Verification evidence

Evidence is under `.tools/company-configuration-review/` (ignored local artifacts).

- **143 API/domain tests pass** across configuration, companies, feature-domain rules,
  company management and setup review. These use the existing in-process application
  and isolated SQLite fixtures. Regression failures were recorded before the API fixes.
- **1 MySQL 9.6 integration test passes** against a separately initialized and migrated
  review database. Two concurrent feature changes using the same review version yield
  exactly one 200 and one 409, one actual flag change and one feature audit event. An old
  profile edit is rejected; an already-enabled replay preserves the version and event
  count. The owned temporary MySQL instance was shut down afterward.
- **1,393 console tests pass in 121 files**. After the mobile markup fix, the **44**
  configuration UI/page/navigation tests pass again. The earlier affected set passed
  **141** tests across configuration, company editing, policy and return navigation.
- Console coverage is **97.85% statements/lines, 85.27% branches and 80.62% functions**,
  improving the preceding **97.83%, 85.07%, 80.35%**. The coverage command still exits
  nonzero because the existing **90% global function** threshold is unmet. No threshold
  was lowered, and the feature component has full statement/function coverage.
- **57 browser checks pass** at **1440px and 390px** in light, dark and ledger themes:
  explicit enable/dependency review, validation, protected disable, reversible changes,
  response-loss recovery, profile editing/save/return, read-only access and mobile value
  alignment. Screenshots were inspected; no page errors or document overflow occurred.
  These use real console components/shared CSS with fixture BFF responses. Persistence,
  authorization, version locking and audit were checked independently in the API tests;
  this does not claim a live Authentik session or a production deployment.
- The isolated production build, console/auth/API-client type checks, **8 SDK tests**,
  OpenAPI/generated-client checks, Ruff and strict mypy pass. Generated build config is
  checked and restored to this turn's exact snapshots; the running console's `.next`
  remains intact. The launcher-managed Identity service was gracefully restarted
  after the read-only live check found its old contract still loaded. Its readiness
  check passes and its live OpenAPI now includes `expected_updated_at`. Other application
  services remain intact. Task-file whitespace validation passes;
  the unrestricted workspace check also reports pre-existing CRLF whitespace in
  `identity/api/login.py`, which this task did not change.

### Final review

Manual simplification and security/correctness review walked CLAUDE.md §§5–6. The named
`/simplify` and `/security-review` commands are unavailable in this session, so the review
was performed directly. No new dependency, permission key, storage mechanism or posting
behaviour was introduced. Scope checks, strict request validation, existing database
tenant filtering, same-transaction audit and server-side irreversibility remain enforced.

Findings fixed with regression evidence: inactive/stale feature admission; duplicate
enable audit; reason-validation focus; retained reason after an uncertain action changes
direction; expired-session navigation; settings creation inferred from a company/expired
grant; incomplete/invalid snapshots; and mobile feature/lock values split across the
shared table's label/value columns. No remaining configuration defect was found within
these checks. The existing global function-coverage gate remains a release limitation.
Changes are local and uncommitted; no publication or money/provider activation was performed.

## Company summary and tax sections (2026-11-02)

Company configuration groups business identity separately from regional/financial
defaults, uses readable tax labels, and places actions on their own rows to preserve
mobile heading space. The dedicated company GST settings page holds separate
registration and outward reporting history cards. Add actions open shared right-side
drawers with responsive fields, scrolling bodies and pinned Save/Cancel actions.
Drawer errors stay with the form; dirty drafts require discard confirmation and
pending writes block dismissal. Dated closure controls use disclosures. Pending
writes and unsaved tax drafts are included in page refresh/navigation protection.

Other tax defaults now have a read view of existing dated registration records with
bounded paging. A default framework is not proof of registration or exemption. The
shipped setup profiles remain India GST and UK VAT; no new country/tax choices were
added. VAT authoring on this page remains unavailable, and India state VAT remains a
separate planned extension. See the [layout review](company-configuration-layout-review.md)
for findings, regression evidence, screenshots and exact verification scope.
