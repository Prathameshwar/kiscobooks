# Account/party opening API delivery

Completed 2026-10-28 against [the authorized API plan](account-party-opening-api-plan.md).
See the [API reference](account-party-opening-api.md) for contracts, limits and recovery.
UI and release activation remain separate.

- [x] 1. Contract and policy audit, readiness and typed capabilities.
- [x] 2. Durable worksheet, immutable revisions and scoped indexed reads.
- [x] 3. Historical documents, on-account balances and base carrying values.
- [x] 4. General accounts and existing party, inventory and bank boundaries.
- [x] 5. Native posting handoff, aggregate completion, retry and correction.
- [x] 6. Coverage, imported YTD, ageing and annual continuity.
- [x] 7. Bounded imports, validation, history, resume and private exports.
- [x] 8. Migrations, models, contracts, clients and native verification.
- [x] Review 1: money, dates, security and recovery; findings fixed.
- [x] Review 2: workflows, compatibility and reporting; fixes verified.

## Confirmed policies

The user approved explicit unknown-history on-account balances, both
POST_CUTOVER_ONLY and YTD_SUMMARY reporting, and configured migration clearing
with mandatory zero reconciliation. All three paths are implemented and enabled
in typed capabilities.

Known documents retain their historical dates and remaining amounts. ON_ACCOUNT
records retain null document/due dates with explicit unknown-history provenance.
They settle normally and count toward credit exposure. Ageing and credit decisions
disclose unknown due history; automatic overdue charges require known dates.

Large declarations use bounded native journals and separately configured clearing.
Completion requires all journals posted and confirmed, agreement with declared GL
and outstanding documents, and zero clearing balance. YTD summaries reconcile to
nominal opening GL and never post earnings twice.

## Review 1: money, security and recovery

Manual review followed CLAUDE.md sections 5 and 6; the named slash commands were
not available as executable tools. Findings fixed:

- Capture checks native changed-field policies immediately. Export tickets recheck
  current scope and export rights, and private financial responses prohibit caching.
- Replacing preparation voids only unposted drafts and retains immutable evidence.
- Posting rejects account/party drift and disagreement with frozen native plans.
- Finalization checks financial/bill evidence, native confirmations and clearing.
- Correction fences include settlements, charges, stock claims and bank dependencies.
- Partial reversal closes remaining unposted plans without deleting financial facts.
- Import receipts explicitly disclose their declaration/draft effect and posting status.

## Review 2: compatibility and reporting

- Historical carrying values remain frozen across later display-precision changes.
  Matching cutover-day FX quotes are not falsely recorded as historical provenance.
- Reconciliation uses a shared company fence under READ COMMITTED isolation for
  consistent reads without changing setup generation or balances.
- Contributing fields, cross-company filters, replays and private downloads remain
  protected. Import staging checks authority before decoding archives.
- Captured entries expose their native chunk, journal and line posting link.
  Metadata links use the canonical existing finance field-set routes.
- Reports independently verifies YTD provenance against native journals before
  publishing a generation. Unknown dates have a separate ageing bucket.
- New immutable report-definition versions preserve completed run/export evidence.
  Earlier source-schema hashes remain compatible with reporting-contract 0.8.0.

## Verification

- Combined Accounting acceptance on disposable MySQL: **53 passed**.
- Combined Reports acceptance on disposable MySQL: **170 passed**.
- Approved-mode workflows: **4 passed**; targeted FX review: **4 passed**;
  final import-authorization and posting-lineage rerun: **2 passed**.
- Pure opening/import and ledger-domain checks: **51 passed**, **95.70%** branch-aware
  coverage across the two new opening-domain modules.
- Reports pure/reference/registry checks: **92 passed**.
- Strict mypy passed across 20 affected Accounting files, 12 affected Reports files
  and the shared contract. Targeted followups and Ruff passed.
- API client 0.2.40, Accounting/Reports generation checks, TypeScript checks and
  **8 transport tests** passed. OpenAPI, audit contracts, Identity field metadata,
  reporting contract and dependency locks are synchronized.
- Disposable Accounting upgrade through **0222**, downgrade to 0212, re-upgrade
  and full model parity passed. Reports head 0038 model parity passed.
- Local Accounting additive rollout through **0222** and full model parity passed.
- Identity, Accounting and Reports were refreshed, along with reports-worker,
  accounting-publisher and accounting-posting-delivery. Service readiness passed.
  The old Reports/Accounting processes were verified against this workspace's
  exact service-host command and stopped gracefully before launcher-managed restart.

Financial-flow tests use disposable MySQL databases and test doubles for external
Identity authority/confirmation boundaries. No real company opening was captured,
posted, reversed or finalized by this task. Live financial admission settings were
preserved; schema rollout does not authorize release activation.
