# Profit and Loss loading failure — 2026-11-07

## Local fix and BTCL verification update

BTCL was checked read-only on `srv2111154`: its retained history begins **2026-11-06**, and a native calculation from that date through **2026-11-07** succeeds. April 1 through November 7 fails because April precedes coverage. The earlier evidence below concerns another observed company whose coverage begins November 7; do not apply that company's date to BTCL.

The user explicitly requested a valid From default before calculation. Automatic P&L opening now fills From with the later of the selected year start and source history start. BTCL therefore defaults to November 6. The page discloses the actual partial financial-year period; it does not imply full-year history. Users can explicitly choose an earlier year start when verified imported YTD coverage supports it.

Native and reference calculation now distinguish `InsufficientHistoryError` from snapshot corruption. Workers record `INSUFFICIENT_ACCOUNTING_HISTORY`, and the UI names the available history date and tells the user to correct From or comparison From. Manual history failures do not rebuild or retry the same unsupported range. Retained completed reports stay frozen.

Validation: actual React checks pass for a valid first automatic request, clear manual-date failure without rebuild/retry, and explicit imported-YTD full-year selection. Framework execution, profit views, real imported-YTD native/reference and registry suites: **87 passed**. Scoped Ruff and strict mypy pass. Console TypeScript passes. Standard Vitest remains blocked by Windows esbuild `spawn EPERM`; tests were added to the normal suite as well.

**VM status: deployed on 2026-11-07.** See [deployment verification](vm-latest-build-2026-11-07.md). BTCL's deployed P&L calculation succeeds from 2026-11-06; its overview and source-readiness endpoints return HTTP 200. Retained feed compatibility was corrected without rewriting snapshots or financial history. Earlier periods still require verified retained or imported history.

## Confirmed cause

The company observed in the failing live request has a READY accounting snapshot with `coverage_start=2026-11-07`. Profit and Loss automatically requests the selected fiscal year's start, `date_from=2026-04-01`, through `2026-11-07`.

That request precedes retained accounting history. Native calculation raises `ConflictError: requested history precedes retained owner coverage`. The worker classifies it as `REPORT_VERIFICATION_FAILED`, so the console shows “The accounting snapshot could not be verified. Retry the report.”

The snapshot is READY. Rebuilding it cannot add history before its coverage date. The console automatically rebuilds once and retries the same invalid period, producing a second blocked run rather than resolving the date problem.

## Live evidence

Read-only diagnosis on host `srv2111154`, authenticated as the saved profile's `root` user:

- Reports API and report/source workers are active.
- P&L definition and source reads returned HTTP 200; source and report admission returned HTTP 202.
- Run `01a1b443-dcaf-762f-b119-b7bf0f0d12e4` and its automatic retry `01a1b443-f777-7035-94c1-81f20a574364` are both BLOCKED with `REPORT_VERIFICATION_FAILED`.
- Latest run parameters: From `2026-04-01`, To `2026-11-07`.
- Its generation `01a1b443-ea1d-7162-a38a-e50acd1ccc3f` is READY, with coverage starting `2026-11-07`.
- Calling the deployed native calculation on the frozen run inputs reproduces the retained-history conflict.
- Calling the same deployed calculation with an in-memory input object whose From is `2026-11-07` succeeds, including P&L presentation, with six output rows. No job, source, accounting record or published report was changed by this calculation.

## Source defects

1. `mfes/apps/console/app/components/FinancialStatementWorkspace.tsx:68` initializes From to fiscal-year start. The loading path reads source coverage but does not handle a P&L start before that date; its coverage-date validation is specific to Balance Sheet.
2. `apis/reports/src/reports/queries/native_context.py:74` correctly rejects history before owner coverage unless the supported imported-YTD path applies.
3. `apis/reports/src/reports/tasks/framework_worker.py:317` turns this deterministic date/coverage conflict into the generic verification failure code.
4. `FinancialStatementWorkspace.tsx:143` treats that generic code as potentially repairable by rebuilding the source, then retries the same P&L start date.
5. `mfes/apps/console/app/lib/finance-source.ts` maps the final generic code to the snapshot-verification message, hiding the actionable date constraint.

## Immediate workaround

In Profit and Loss Filters, set From to **7 November 2026** or later and To to a date on or after From, then apply the filters. This company currently has no retained transaction history before that date. Full-year reporting would require the appropriate opening/YTD history to be supplied and verified.

## Recommended correction

- Make automatic opening handle available history explicitly. If using a shortened period, show the actual period and explain its start date; do not present a shortened report as full-year coverage.
- Validate manually selected current and comparison periods against supported coverage/YTD evidence before admitting a run.
- Return a specific insufficient-history failure rather than a snapshot-integrity failure.
- Do not rebuild/retry deterministic date-coverage failures. Keep rebuild recovery for failures that a fresh verified source can repair.
- Cover new-company fiscal-year defaults, comparison dates, retained runs and supported imported-YTD cases with meaningful regressions.

## Validation and status

Local P&L view and framework execution suites: **12 passed**. The Windows test launcher required a workspace temporary directory and a process-local directory-mode workaround because Python's private temporary-directory ACLs deny the sandbox token access. Application calculation behavior was not mocked.

Diagnosis is complete. No application fix, VM deployment, service restart or financial data change was made. Warehouse review remains saved separately in `docs/warehouse-config-stock-management-review-2026-11-07.md` with eleven findings and a follow-up checklist.
