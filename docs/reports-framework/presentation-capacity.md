# Presentation and capacity extension

Authorized on 2026-10-22: implement uninterrupted, then review. Existing local changes
and completed evidence are preserved. No production activation or publishing is requested.

## Phases

1. Retain view/execution choices; advertise registered compact and party-balance views,
   validate compatibility, and serve each calculation through its registered columns.
2. Add explicit BULK account-summary execution with bounded period units, immutable
   batches and verified checkpoint recovery. Add ZIP packages of bounded PDF/HTML parts
   with exact row ranges and hashes. Keep single-document safeguards and total budgets.
3. Synchronize API/client/console, run regression/native migration checks, and review
   permissions, exact arithmetic, resource bounds, checkpoint and artifact publication.

## Decisions

- Named compact views project the same calculation. Party-balance views of outstanding
  bills and advances use the existing exact aging rules and keep debt and credit separate.
  They cannot be used to export a detail run: their calculation requires a new run.
- BULK is opt-in for native account summaries. Standard paths retain existing bounds;
  bulk output is computed one period at a time against the same frozen source. Completed
  period checkpoints permit recovery into a new fenced attempt; partial periods replay.
- Large presentation exports use an explicit PACKAGE delivery. Each part remains bounded
  and independently rendered; publication exposes the complete ZIP and manifest together.
  No unbounded PDF, automatic truncation, cloud service or new dependency is introduced.
- Functional boundary/recovery tests are in scope. Historical production capacity remains
  unverified; the earlier exclusion of load/soak tests remains in effect.

## Verification and final review

- Initial four capability regressions failed before implementation. The first combined
  API/registry/export/execution/deadline gate passed 102 tests with one native-database skip.
- Native MySQL gate passed 48 tests, with schema/model/index parity and downgrade-to-base /
  upgrade-to-0035. Console presentation/download gate passed 37 tests; full console typing,
  client typing, eight transport tests, generated-client drift and asset checks passed.
- Manual simplify/security review (equivalents of the unavailable slash commands) checked
  current authority and field denies, tenant/company scope, idempotency, immutable result
  and artifact publication, exact sums, comparative currency labels, deadline/memory/disk
  bounds, checkpoint recovery and runtime identities. Review fixes retain comparative labels,
  fence checkpoint writes, validate period/count consistency, hash the new calculation rules,
  and check package scratch growth before assembling each part. No new dependency, public
  file access, user SQL/template or unsafe filesystem command was introduced.
- A period-splitting regression reproduced later opening entries being incorrectly moved
  out of turnover. Bulk units now retain the original current/comparative opening boundary;
  earlier opening entries cannot be counted twice when loading a later period's prefix.
  Materialized result plan identity also includes the retained view/execution options.
- A controlled-clock regression reproduced bulk setup losing its lease before the first
  period. The complete bulk operation is now supervised, covering context loading,
  validation and checkpoint replay as well as period calculation/publication. The regression
  advances past the original lease without a real long-running calculation or load test.
- Production activation, Linux validation and load/soak remain excluded. Bulk calculation
  currently extends ACCOUNT_SUMMARY only; other report families keep their declared bounds.
  Documents retain per-part limits and can reject very wide/long content. Packages resume by
  retrying the export; only calculation periods have resumable checkpoints.
- Full Reports suite: **402 passed, 6 skipped** in 1559.51 seconds. After final review fixes,
  affected statement/capacity/runtime/execution coverage checks passed **41 tests**; accumulated
  domain statement/branch coverage is **93.49%**, above the earlier 93.45% and 90% gate.
  Latest capacity/lease/runtime gate passed **29 tests** on SQLite and **29 tests** on MySQL;
  MySQL schema/model/index parity and complete downgrade/upgrade through `0035` passed.
  The full run preceded the final review fixes; the affected gates verify those final changes.
- Final Ruff check/format, strict mypy (**104 source files**), OpenAPI and asset checks passed.
  A fresh wheel was rebuilt and installed outside the checkout; worker imports, verified
  bundled assets, real PDF/HTML document parts and complete ZIP hashes/ranges passed.
  The disposable MySQL server launched for these checks was stopped after verification.
- Apply additive migrations `0034` and `0035` before deploying these changes. Refresh discovery
  for new definition versions. No production activation, commit or publishing was performed.
