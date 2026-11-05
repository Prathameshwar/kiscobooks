# Publication review — 2026-10-31

The user requested committing and publishing all current application changes through
the configured `git publish` mapping to `main:bll-pc/`. Local source paths stay intact.

The snapshot includes local authentication and provider-aware administration,
logs/activity navigation and event projection, KiscoBooks branding and its audited
installation seed, generated clients, migrations, scripts, documentation and tests.

## Corrections made before committing

- Fixed two overlong Python lines without changing their behavior or error text.
- Bumped the shared platform package to 0.44.3 for the local-auth tenant-filter
  exemptions and regenerated its lock and all eleven consumer locks offline.
- A forwarded-client throttle test depended on all requests landing in the same real
  clock minute. Pinning its limiter clock makes the intended window deterministic.
  It also verifies that another address gets its own budget and the original address
  can try again after the next window starts. Production throttling is unchanged.

## Validation

- Identity publication selection: 343 tests passed initially; the single minute-boundary
  test failure passes after the deterministic-clock correction.
- Auth server: 385 passed, 1 skipped. Auth UI: 289 passed, 3 opt-in browser cases skipped.
- Console publication selection: 158 passed. Shared platform convention/OIDC: 39 passed.
- Auth and Console TypeScript checks pass. Changed Python sources parse, credential
  pattern checks find nothing, and diff whitespace checks pass.
- Existing KiscoBooks and activity/logging browser/backend/native database evidence
  remains documented in the corresponding review and CSV files.

This is a source publication, not a production deployment. The local-auth delivery
tracker preserves the final full regression/mutation/report work still in progress
at the snapshot; it is not marked complete by this publication review.
Private environments, credentials, databases, tool installations and test artifacts
remain ignored and outside the commit.
