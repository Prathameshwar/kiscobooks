# Regional defaults verification — 2026-10-20

Implemented country/currency/timezone/language selectors in platform tenant
create/edit, self-service onboarding and first-run setup using existing shared
Select styling. Choices come from Identity tables through the existing gated
tenant-options, onboarding/status and setup/checks APIs. No new public endpoint.

Identity migrations 0072/0073 create language/timezone with one DDL per revision
and inverse downgrades. The existing installation command seeds both in its
default transaction. Local installation is at 0073: 184 active languages and
598 active timezones. Existing tenant and company values were preserved.

Validation evidence:

- Identity setup, onboarding, platform, regional and own-tenant suites: 38 passed;
  final expanded regional suite: 7 passed, including selected language persistence.
- Console tenant suite: 13 passed; shell suite: 16 passed.
- Auth onboarding: 14 passed; first-run setup: 12 passed;
  server suite: 52 passed, 1 existing opt-in Redis integration test skipped.
- Auth and Console production builds and TypeScript checks passed.
- Ruff and strict mypy passed for affected application paths; OpenAPI/client regenerated.
- Native laptop MySQL: full migration, downgrade through 0066, upgrade to 0073,
  provisioning/replay, active reference options, tenant isolation and lifecycle passed.
- Browser against disposable MySQL/API: edit selections (UTC/Hindi), create selections
  (Europe/London/Hindi), database-populated option counts, invitation result, mobile
  and stored-theme hydration passed. Disposable processes, schema and token removed.

Review: access gates, same-origin BFF requests, bounded lists and transactional
audit remain intact. Unknown/inactive references are rejected before writes;
unavailable options block save and offer retry. Older encrypted setup drafts may
omit locale and retain the API default of English. Strengthened language selection
uses ISO codes without claiming translated UI support. No unresolved findings.
