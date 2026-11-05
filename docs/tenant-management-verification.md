# Tenant management verification — 2026-10-20

Implemented the administration landing card and tenant directory, shared atomic
administrator/self-service provisioning, bounded BFFs, and post-login onboarding.
Theme hydration uses deterministic server/client initial state and restores browser
preferences after mounting. Registration layout follows the requested field rows.

Verified:

- Final Identity tenant/onboarding/platform/setup/revocation regression suites:
  32 passed, including directory search/cursor and reference-choice authorization.
- Complete Console suite: 441 passed; new server-page permission tests: 2 passed
  separately after the full run started. The first full run exposed a resettable
  media-query test stub and one load-sensitive customer timeout; the corrected
  full rerun passed with no unhandled errors.
- Complete Auth UI suite: 121 passed. Auth server suite: 44 passed,
  one native Redis integration prerequisite skipped. Shared theme: 30 passed,
  including actual server rendering and hydration regression.
- Auth and Console production builds passed, including new routes. TypeScript,
  Ruff and strict mypy checks passed for changed API modules.
- Native MySQL 9.6: fresh full migration, directory-index downgrade to `0066`, and
  upgrade to `0071`; create/replay, suspend/restore, prefix search and self-service
  isolation passed. Local Identity migrated to `0071` and restarted healthy.
- Headless Edge with a disposable native database and isolated signed test identity:
  landing card → tenant directory, search/sort, edit, suspension/restoration,
  creation/invitation handoff, mobile layout, and stored-theme hydration passed.
  This exercises UI/BFF/API/DB; it does not substitute for the personal operator's
  real Authentik credentials. Test credentials never changed production authority.

Manual final review against CLAUDE.md §§5–6 found and corrected: unconditional
login prompt; five-minute restriction on safe reads; self-service replay with
changed details; revocation enforcement on onboarding; invitation lookup relying
on an editable contact email; unbounded proxy body; and missing indexed directory
queries. No financial records or permission catalogue changes. Audit/outbox remain
transactional and tenant scope is explicitly switched only after platform authority.
`/simplify` and `/security-review` commands are unavailable in this session; the
equivalent manual reviews were performed. SMTP remains intentionally deferred.

Workspace suggestion and form-spacing follow-up (2026-10-20):

- Confirmed failing regressions before fixing automatic workspace IDs and the
  doubled form spacing. Tenant directory/page tests: 17 passed. Shared form,
  field, select, drawer and stepper tests: 52 passed. Auth UI: 125 passed;
  Auth server: 52 passed, one existing optional Redis integration skipped.
- Console and shared UI TypeScript checks passed. Headless Edge rendered the
  actual tenant drawer against isolated API fixtures: automatic suggestion,
  preserved manual ID, submitted custom ID, 16px field gaps, and no field overflow
  at 1440px and 390px in light/dark/ledger themes passed. This follow-up does not
  claim a new live API/database integration run.
- Manual simplification/security/invariant review found no remaining issues in
  these changes. Identity still enforces ID format, uniqueness and immutable IDs;
  the existing creation permission and idempotency handling are preserved.

Shared list-toolbar follow-up (2026-10-20): failing regressions confirmed before
the fix. Shared list/control suites: 190 passed; tenant/customer/audit list suites:
68 passed. Console and shared UI type checks passed. Headless Edge with isolated
API fixtures checked aligned search/dropdown/refresh controls, matching card and
table/pager gutters, responsive wrapping, filtering and refresh at 320, 390, 768,
1024 and 1440px across all three themes. Review corrected the stacked-table gutter
breakpoint; no remaining findings. Shared `@janso/ui` CSS/context provide the
layout, with no tenant-page stylesheet. API/database behavior was not changed.

Shared footer placement follow-up (2026-10-20): confirmed the failing shell
regression before the change. Shared shell/content-layout tests: 51 passed;
Console shell/tenant/error-page tests: 33 passed. Shared UI and Console type checks
passed. Headless Edge checked short pages, the one-tenant directory, long content,
and omitted footers at desktop/mobile sizes in all three themes using isolated API
fixtures. Short content fills the scrollport above the footer; long content scrolls
to it without overlap or document scrolling. Footer links remain focusable and the
contentinfo landmark is preserved. Manual final review found no remaining issues;
central shell CSS supplies the behavior across all AppShell pages.
