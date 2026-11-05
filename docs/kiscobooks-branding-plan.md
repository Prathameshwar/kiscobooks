# KiscoBooks display branding

User decision (2026-10-30): display the product as **KiscoBooks**, with adjacent,
distinctly coloured Kisco and Books text. Display the publisher as **Khushiyan
Enterprise**. Preserve internal package names, CSS selectors, filenames, identifiers
and actual customer/company records.

## Phases

1. Update the shared accessible wordmark and logomark labels. Use existing semantic
   indigo theme ink (Kisco) and a dedicated green brand token (Books), keeping the name together.
2. Update visible web copy, metadata, preview branding and provider recovery messages.
   Keep favicon readiness checks aligned with their accessible labels.
3. Run shared/component and affected application tests, check desktop/mobile themes,
   and review scope, accessibility, security and simplification. Record the result here.

## Progress

- [x] Shared branding and accessibility.
- [x] Visible app, preview and recovery copy.
- [x] Regression tests and responsive/theme review.
- [x] Final review and governing design-system decision log.

Live VM/provider deployment is separate from source verification; no company records
or identity-provider identifiers will be rewritten for a display branding change.

## Verification and final review

- Shared UI: 382 tests pass (primitives, contrast, themes, rail, shell and wizard layout).
- Auth: 161 affected screen/flow tests and 45 provider tests pass.
- Console: 45 shell and voucher metadata tests pass. The branding regression test
  also verifies that the actual signed-in company name survives the publisher change.
- Windows launcher: 22 tests pass; registration and recovery deployment: 12 pass.
- Browser: 3 tests cover 36 combinations (auth, expanded/drawer rail and collapsed
  rail; light/dark/ledger; 1440/768/390/320px). Actual component DOM and shared styles
  render with the self-hosted Inter font. Both name parts stay adjacent, distinct,
  unclipped and within the viewport. Screenshots are in the ignored
  `.test_artifacts/kiscobooks-branding/` folder.
- UI, Auth and Console TypeScript checks pass. Changed SVGs parse with the correct
  accessible label; recovery preparation Python syntax and diff whitespace checks pass.
- Initial full-glow contrast regression reproduced 4.33:1 (light) and 4.42:1
  (ledger) with the reused success ink. Dedicated `--janso-wordmark-books` shades
  fix both cases; the final tests require at least 4.5:1, including maximum glow.
  Existing success/status colours are unaffected.
- Shared UI version is 0.1.42. Consumers still resolve `workspace:*` links; no package
  identifiers, dependency resolution or lockfile entries changed.
- Manual CLAUDE.md sections 5 and 6, simplification and security review: no remaining
  findings in this change. The slash-command review tools are unavailable in this
  environment. Changes are display copy/styles only; provider IDs, recovery policies,
  tenant scoping, stored records and business calculations retain their behaviour.
  Concurrent local-auth and audit/activity work is preserved.

Reusable browser command, from `mfes/apps/auth/` in PowerShell:

```powershell
$env:QA_BRANDING_BROWSER = '1'
.\node_modules\.bin\vitest.CMD run tests/branding-layout.browser.test.tsx --maxWorkers=1 --minWorkers=1
```

The browser fixture reviews rendered UI, not live sign-in or native provider delivery.
The stopped VM was not used. Existing deployed Authentik recovery/enrollment screens
receive the new copy when their updated blueprints are reapplied through the existing
deployment workflow. No direct database writes, commits or publication were performed.

That statement describes the initial display-only phase; the database synchronization
requested afterwards is recorded in the follow-up below.

## Database, model and script synchronization follow-up

Requested by the user after the display change:

1. Inspect the persisted platform installation, generic model/schema contract and
   all installation/setup/provider defaults. Preserve customer records and technical IDs.
2. Make new-install defaults and deployment synchronization reusable and idempotent.
   Use the existing audited administration API for the completed installation where
   available. Data seed changes belong in seeds, not historical DDL migrations.
3. Verify persistence, replay safety, custom-name preservation and unchanged bootstrap
   authority; run focused backend/script tests and record native synchronization evidence.

- [x] Persisted state and model/schema inspection.
- [x] Permanent default and script synchronization.
- [x] Existing installation synchronized and verified.
- [x] Tests and final review.

### Native database result

The follow-up used the supported deployment seed, because the running login-provider
configuration was incomplete. The standalone command applies only branding and
does not migrate the database or provision login accounts:

```powershell
start/win/sync-branding.bat -DryRun
start/win/sync-branding.bat
```

- Persisted `platform_installation.name`: JANSO -> KiscoBooks.
- Dry run left installation metadata, customer data and outbox rows unchanged.
- Apply created one `platform.details_updated` outbox event with system attribution,
  source Identity and a bounded name-changed marker. No human operator was fabricated.
- Replay changed no records and created no duplicate audit event.
- All protected installation/bootstrap fields and public URL stayed identical.
- All 16 tenants and 12 companies retained their names, identifiers and relationships.
- Native `name`/`public_url` lengths, nullability and defaults match the ORM model.
  Schema revision stays 0089; unrelated local-auth migrations were not applied.
- New installations seed KiscoBooks. Later deployment seeds update only exact legacy
  Janso names (case-insensitive, trimmed); custom platform names stay intact.
- Khushiyan Enterprise remains the publisher branding, not a customer's company record.

Native evidence is in the ignored `.test_artifacts/kiscobooks-native-db.json`.
Final combined verification: **57 tests pass**, covering seed/CLI behavior, first-run
setup, original completion replay, platform details, authorization and lifecycle.
Strict mypy, Ruff lint/format, launcher syntax and standalone seed entrypoint checks
also pass. An initial combined invocation exposed existing fixture-plugin discovery
errors; explicit setup/access plugin registration resolves those test-environment errors.

Reusable backend command, from `apis/identity/`:

```powershell
.venv/Scripts/python.exe -m pytest -p tests.test_platform_setup -p tests.test_platform_access tests/test_branding_seed.py tests/test_platform_setup.py tests/test_platform_details.py tests/test_platform_lifecycle_revision.py -q
```

Case-level results and native database checks are recorded in
[branding synchronization results](testing/tenant-admin/kiscobooks-branding-sync-results.csv).

Manual final simplification/security/correctness review (CLAUDE.md sections 5 and 6):
no remaining findings. The seed locks the existing singleton, changes only its owned
display name, and commits metadata and audit together. Error output excludes connection
details and credentials. Customer scopes, technical IDs, provider policies and monetary
data are unaffected. Generic models and API schemas already fit the stored data, so no
DDL or API/client regeneration is required. The script uses the existing Identity
virtualenv and private configuration without installing dependencies or changing paths.
Concurrent authentication work is preserved. Live provider deployment/sign-in remains
outside this database synchronization result.
