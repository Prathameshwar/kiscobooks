# Company Default product type and group review

Previously the wizard created a General group, while Catalog's permanent company
source provisioner created neither a product type nor a product group. The updated
provisioner creates one type and one group initially named `Default`, code `DEFAULT`,
for active enrolled companies. New API-created companies and existing enrolled
companies missing these masters use the same authenticated source-refresh workflow.

Provisioning is asynchronous after Identity company creation. The normal worker
refresh catches up existing enrolled companies without a browser. A one-shot mode
can run only this pair's provisioning. The company policy lock prevents concurrent
duplicates; system outbox audit evidence commits atomically with each change.

A new pair also gets one published type revision and one root group edge: four
storage records, but exactly one type and one group. The initial BOTH baseline
permits NON_STOCK and NONE tracking with supported unit dimensions and optional
variants; it requires no brand/manufacturer/expiry. STOCK is permitted only when the
verified company snapshot enables inventory at provisioning. Later feature changes
use ordinary reviewed type publication; existing published policies and product
assignments are never changed automatically.

Existing General/custom records remain intact. Canonical DEFAULT codes survive
renames and take precedence; an existing named Default with another code is reused
when the canonical code is absent. Inactive, incompatible or unpublished existing
defaults require administrator review and are preserved.

The wizard now verifies the active pair and a published type revision through
bounded GET requests, without creating/publishing masters. Missing records leave
completed steps and the existing company retryable. The setup allowlist admits only
the fixed bounded Default queries and a bounded published-revision lookup. The
owning APIs retain their permission, field-policy, tenant/company and parent checks.
Native master lists omit company_id; the helper uses generated API types and the
authenticated company-scoped endpoint rather than requiring an invented field.

## Verification

| Check | Result | Ignored local evidence |
|---|---|---|
| Initial missing-default regression | Failed first: zero types/groups for both company configurations | Initial source-test output |
| Initial affected Catalog/source/unit/tax/warehouse suite | 39 passed, zero skips | `.test_artifacts/company-product-defaults-native.xml` (SQLite-backed, despite filename) |
| Final defaults/source/one-shot suite | 19 passed, zero skips | `.test_artifacts/company-product-defaults-worker-complete.xml` |
| Dedicated native MySQL concurrency and alternative-code reuse | 2 passed, zero skips | `.test_artifacts/company-product-defaults-mysql.xml` |
| Final wizard/bootstrap/setup-policy/readiness components | 156 passed, zero skips | `.test_artifacts/company-product-defaults-ui-verified.json` |
| Published-revision and actual list-contract regressions | Four revision failures and one list-contract failure reproduced before fixes | `.test_artifacts/company-product-defaults-revision-red.json`, `.test_artifacts/company-product-defaults-list-contract-red.json` |
| Ruff and strict mypy on both changed source modules | Passed | Local command output |
| Console TypeScript | Passed | `pnpm.cmd exec tsc --noEmit` |
| Live existing-company catch-up | Failed before company processing: Identity API offline | Private local worker log |
| New live company/wizard acceptance | NOT_RUN: Identity API offline | Follow-up below |

Catalog component/storage suites mock signed source transport at the existing test
boundary and use SQLite. Native MySQL runs separately on the validated dedicated
local server at port 13396 with generated disposable schemas, dropped after each
test. No manual SQL was applied to application company data. Counts overlap and
must not be added together as unique coverage. Local component passes are not live
UI E2E evidence.

An intermediate fixture incorrectly monkeypatched a read-only AsyncEngine method;
it now supplies a fake disposable engine, and both cleanup paths pass. An obsolete
General idempotency-key assertion was updated after removing the browser write.
Final green ledgers are distinct from these intermediate failures.

## Final review

Manual equivalents of `/simplify` and `/security-review` were performed because
these commands are unavailable in this session. CLAUDE.md sections 5 and 6 were
walked. Review found and fixed premature readiness for unpublished types and the
invented company_id list-field requirement. No remaining defect was found within
the implemented provisioner/readiness scope.

Guarded tenant sessions, explicit company scope and current verified Identity
context remain mandatory. Wrong tenant/company, inactive companies, replay,
customization preservation and native concurrent transactions are covered. Injected
audit failure rolls back all created rows/evidence; retry recovers. A failed default
transaction keeps the independently verified source lease and retries later.

The fixed starter data lives in Catalog seeds, validates through native schemas and
requirement rules, and accepts no caller-provided configuration. Provisioning grants
no user authoring/publication permissions. The one-shot command uses signed source
enrollment/snapshots, starts no broker consumer, and disposes its engine on success
and failure. The native test fixture accepts only the dedicated local server with
no selected database; identifiers are a fixed test prefix and generated UUID.
No public API/schema/event contract, migration, dependency, financial/tax execution,
release flag or invitation delivery was changed.

## Live existing-company execution pending

The local Identity API is offline following the VM shutdown. The attempted catch-up
failed at enrollment discovery with IdentitySourceUnavailableError, before any
company default transaction. This task's live catch-up has therefore not changed
existing company records. Companies outside Catalog's approved enrollment workflow
must enroll through that workflow first; catch-up does not bypass enrollment.

When services return, restart/redeploy the Catalog Identity source worker so it loads
the updated code. Its normal refresh applies the defaults. To run only product-pair
catch-up from the workspace root:

```powershell
apis/catalog/.venv/Scripts/python.exe -m catalog.tasks.source_worker --env-file start/win/env/catalog.env --once --product-defaults-only
```

After verified catch-up succeeds, inspect Product types and Product groups in each
existing QA company, and create one new company through the wizard. Record live
results separately. See [CSV](company-product-defaults-results-2026-10-30.csv) and
[reusable checks](testing/tenant-admin/README.md#company-default-product-masters).
