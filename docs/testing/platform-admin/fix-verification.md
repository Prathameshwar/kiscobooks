# Platform administrator fixes and verification

Authorized after review of the 2026-10-29 findings CSV. Preserve that baseline and
record new evidence separately. No publishing or operator password change.

## Final result — 2026-10-29

Seven findings are fixed and verified: four application/native-flow bugs, two
test issues and the platform landing UX gap. Six entries remain open or partly
verified: cold-start environment behavior, SMTP configuration and the explicitly
listed live-coverage limits. See the updated
[findings CSV](../../platform-admin-findings-2026-10-29.csv); original observations
and baseline statuses are retained alongside fix/retest columns.

| Selected suite | Passed | Skipped |
|---|---:|---:|
| Identity | 235 | 2 |
| Console | 397 | 0 |
| Auth UI | 159 | 0 |
| Auth server, including native Redis case | 104 | 0 |
| Audit | 58 | 0 |
| Notification | 22 | 0 |
| **Total** | **975** | **2** |

No selected-suite failures remain. Both MySQL skips were covered separately by
six passing native executions, including both shared-schema orders. The dedicated
test MySQL server was started for those checks and stopped afterward.

[Automated retest ledger](automated-fix-results-2026-10-29.csv): **1,090 test
executions: 1,088 PASS, 2 SKIP**. This includes focused reruns and repeats of cases
in the selected suites; it is not a unique-test count. Native RBAC and PowerShell
deployment checks are recorded separately below.

[Live retest ledger](live-fix-results-2026-10-29.csv): the two final runs contain
**18 PASS results, no failures and no browser page errors**. All investigation
runs remain in the ledger (**52 PASS and 6 intermediate FAIL records**), with
latest-case and replacement-check results. Failures include the native permission
gate, a harness message mismatch, the blank completion bug, a transient session
page error and the old timing-sensitive pricing-page check.

## Phases

1. Repair recovery subject resolution, supported account eligibility and native
   object-permission handoff together. Preserve existing identity subjects,
   restricted credentials, audit intent, MFA and one-use provider tokens.
2. Apply consistent name validation, correct tracing assertions and isolate
   native outbox assertions. Send company-less platform operators to the existing
   permission-gated administration page.
3. Run regression suites, native checks and disposable-account live recovery;
   manually review security and simplification, and update findings with evidence.
   Configuration and unexecuted workflows remain open, not assumed fixed.

## Baseline

The seven acceptance tests were rerun before application changes: **2 passed,
5 failed**, reproducing PA-B001, PA-B002 and all three PA-B003 cases.
Evidence: `.test_artifacts/platform-admin-fixes/red.xml`.

## Changes

- PA-B001/B002: preserve stored OIDC subjects, use a bounded native lookup and
  verify the exact subject/email before recovery. Reject incomplete/ambiguous
  responses and unsupported subjects. Permit both supported application account
  paths; platform-created accounts must carry a valid provisioning marker.
- Deploy the native recovery flow and a trusted event-policy permission handoff
  for newly provisioned accounts; reconcile existing accounts through the same
  policy. Native testing exposed an additional Authentik POST permission gate:
  target-object `add_user` is required alongside view/reset. No global create,
  profile-change or delete permission is granted. The native read-only regression
  failed before this correction and passed afterward (3 checks).
- PA-B003: reuse one name/text validator across create/edit/access contracts,
  reject DEL and other existing forbidden controls, preserve valid Unicode.
- PA-T001/T002: verify required authentication/proof headers while permitting
  tracing, and scope native outbox assertions to the test tenant. Native runner
  checks isolated modules and both shared-schema orders (6 passing executions).
- PA-U001: the root page sends company-less platform operators to administration.
  Selected-company overviews and tenant onboarding are preserved. Remove the
  platform page's circular overview link when no company is selected.
- PA-B004 (discovered during retest): the native recovery completion stage had
  an empty static value, so it displayed only Continue. Move its confirmation
  copy into the static prompt value; a new regression failed before the change.
  This matches Authentik's [static prompt contract](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/prompt/).

## Verification and review notes

- Focused final API/adapter/acceptance run: 50 passed; recovery adapter coverage
  **91.75%**, including branches, exceeding the configured 90% threshold.
  Fifteen additional malformed-config/provider-error/secret-link/marker cases
  passed separately. This is affected-module coverage, not repository-wide coverage.
- Native expression policies/completion contract: 22 passed. Native permission checks: 3 passed.
  Windows deployment checks: 3 passed. Landing/navigation regression: 20 passed.
- Python strict mypy passed seven changed source files; affected Ruff checks and
  Console TypeScript checks passed. No API shape, model, migration, event payload,
  permission catalogue or shared-library version changed.
- The first two live recovery attempts still failed with a native HTTP 403.
  Provider logs and the native permission regression exposed the additional POST
  gate; these failures remain in the retest evidence. A later native run issued
  the link and signed in the new administrator but the browser assertion expected
  the wrong mismatch message. The screenshot shows native mismatch rejection;
  the selector was corrected to accept the actual wording.
- A later browser run exposed PA-B004's blank completion stage. Its failing
  regression and original screenshot are retained. The reusable write harness
  now calls the same settled read module as the read-only harness, removing the
  duplicate timing-sensitive page/theme sweep. The live ledger preserves every
  intermediate failure and gives the latest result for the same case ID.
- Simplification/security review performed manually because `/simplify` and
  `/security-review` commands are not available in this session. Reviewed current
  actor authority, target tenant/assignment/revision checks, exact subject/email
  binding, no privileged-account recovery, scoped provider grants, audit intent,
  no retry of secret issuance, link validation, no credential persistence and UI
  permission boundaries. The native POST gate and circular navigation were found
  and corrected during this review. No financial execution or tenant isolation
  mechanism was changed.
  Native source inspection also confirms that Authentik's existing
  `reset_user_password` permission covers its direct `set_password` action.
  The application recovery route exposes only provider-owned recovery links or
  email, never that direct setter; protect the object-scoped credential accordingly.

## Native results

Final native recovery verification passed on a newly provisioned disposable
administrator: initial sign-in, mismatch and same-password refusal, visible
completion confirmation, new-password sign-in, old-password refusal and rejection
of a used recovery link. Evidence:
`.test_artifacts/platform-admin-fixes/live-verified/live-results.json` and
`live-verified/disposable-recovery-complete.png`.

The separate final read-only run passed anonymous proxy refusal, ten live read
contracts, settled metadata/pricing/states/history, tenant search, all twelve
notification destinations, twelve mobile/theme combinations and the operator's
password-change handoff page. Actual operator password change was not performed.

Five disposable QA tenant/provider accounts were created during investigation
and retesting. Tenant lifecycle checks left them suspended, backup assignments
revoked and QA pricing offerings deleted. Resource IDs remain in the ignored
`qa-inventory.json`; no credentials or recovery URLs were saved. Intermediate
failed runs remain evidence, not silently replaced by the final successful run.

## Repeat targeted checks

Use the README commands for selected suites and native MySQL. Native expression
tests can run locally with:

```powershell
& apis/identity/.venv/Scripts/python.exe -m pytest start/win/registration/tests/test_administrator_recovery_policy.py -q
```

`start/win/registration/tests/test_administrator_recovery_rbac.py` runs inside
the configured Authentik `ak shell` after a QA account has been provisioned. It
checks native permissions without changing accounts or issuing tokens.

For the live fix workflow set `QA_MUTATE=1`, `QA_WORKFLOWS_ONLY=1`,
`QA_CORE_ONLY=1` and `QA_RECOVERY_COMPLETE=1`, together with environment-only
operator credentials. Use a fresh `QA_OUTPUT` folder. `QA_CORE_ONLY` omits the
separate page/theme sweep; run `QA_LIVE_READS=1` without `QA_MUTATE` for that.
The browser harness creates and later suspends only its own QA tenant.

The collection scripts support explicit JUnit reports (`collect_results.py
--reports ...`) and preserve all live failures by default. `--legacy-baseline`
is only for reproducing the original report's superseded observation handling.
