# Accounting finance execution

Authorized 2026-09-15: complete the approved nine-phase Accounting backend plan,
then perform two reviews and fix their findings. The user confirmed monthly periods;
special adjustment periods and 4-4-5 calendars are deferred. UI remains deferred.

- [x] AF1: Financial contract, ownership and behavior matrix.
- [x] AF2: Authoritative company context, monthly fiscal years/periods and posting guards.
- [x] AF3: Balanced journals, source identity, posting, reversal and balances.
- [x] AF4: Opening imports/previews, bill details, finalization and correction.
- [x] AF5: Terms, instalments, settlements, allocation/reversal, realized FX and ageing.
- [x] AF6: Credit limits, exposure, holds, reservations and separately approved overrides.
- [x] AF7: Dated overdue-charge policies and reproducible calculations.
- [x] AF8: Charge approval, signed tax evidence, posting, waiver and reversal.
- [x] AF9: Final full-suite coverage and reconciled delivery evidence.
- [x] Review 1: Financial correctness and simplicity; reproduced and fixed findings.
- [x] Review 2: Authorization, isolation, concurrency, replay and recovery; fixes verified.
- [x] Final verification against the unchanged application source.

Implementation and rollout behavior: [Accounting finance contract](accounting-finance-contract.md).
Baseline: Accounting 135 native tests, 95.68225190839695% overall coverage, domain
99-100%, migration head 0072. Final: 283 tests with passing native results, 96.37096774193549%
overall coverage, every domain module at 97.94-100%, migration head 0088. The overall
baseline and all domain floors are preserved without coverage exclusions.

## Review 1 fixes

Confirmed failing regressions before correcting:

- A voided reversal draft prevented its replacement. Live reversals now have a
  computed uniqueness key; voided drafts release that key.
- A finalized zero opening could not be corrected before trading. Versioned,
  reasoned reopening now enables a replacement batch under the dependency guard.
- Charge-policy close incorrectly excluded the final covered day. Effective end
  dates are inclusive while calculation intervals remain end-exclusive.
- Fixed fees could repeat across policy versions. Covered or waived fixed fees
  now count once per bill across versions.
- Credit checks accepted an account/currency mismatch.
- Credit reservations could be created for already posted source documents.

## Review 2 fixes

Confirmed failing regressions before correcting:

- Denied financial values could survive inside immutable JSON snapshots. Detail,
  replay and export now protect contributing fields and their copied snapshots.
- Opening and charge journals needed workflow-specific permissions on posting,
  replay and reversal, including current permissions on existing receipts.
- Input-only financial fields needed the same server-side write policy checks.
- A voided, never-reserved posting could be revived after company configuration
  changed. Identity now retains a service-owned abort intent atomically.
- Derived FX offsets and tax-account bindings needed related-account field
  authorization. Reversing original FX remains possible after retiring the offset.
- Maximum policy-close dates overflowed when checking inclusive coverage.
- Timezone was incorrectly treated as an immutable company setting; runtime
  controls now use the current signed timezone.
- Oversized foreign conversions returned HTTP 500 in credit, source and charge
  workflows. Native regressions reproduced all three; a common exact conversion
  function now rejects out-of-range or zero results as validation errors.
- Nested contract definitions needed resolution; raw beneficiary account numbers
  must remain unreadable in master field metadata.

Both manual passes covered the repository security and money invariants. The slash
commands `/simplify` and `/security-review` are unavailable in this environment;
these were code and regression reviews, not claims of tool execution.

## Verification evidence

- Accounting migrations 0073-0088 and Identity 0059 manually reviewed line by line:
  one atomic DDL per revision, scoped FKs, exact decimal scales, inline indexes and
  working downgrade/upgrade paths. Native MySQL head/model parity and round trips pass.
- Native Identity-to-Accounting bridge passes: signed gateway facts, openings,
  source/settlement/charge postings and delivered Identity confirmations. Identity
  0059 refuses unsafe downgrade with Accounting-owned reservations and permits safe downgrade.
- Every new financial table has two-tenant isolation coverage. Native competing
  allocation and credit reservation tests allow one effect and reject the conflicting request.
- Seven additional native operational/integrity scenarios pass: delivery retry and
  cleanup, failed-outbox closing, damaged-subledger detection, foreign override
  reservation/renewal/consumption, draft validation, numbering and FX authority.
- Full shared-platform suite: 868 passed at 98.24% coverage; posting and schema
  modules are 100%. Identity context, posting
  client and seed/role tests: 12 passed. Generated Accounting/Identity client checks,
  TypeScript type checking and Accounting transport test pass.
- Accounting Ruff passes; strict typing passes for 90 source/test/tool files.
- Final conversion correction: 12 native regression tests passed, with MySQL model
  parity and migration round trip. The real Identity/Accounting bridge also passed
  again on the corrected source.
- Final verification covered all 283 Accounting tests in 46 modules across four
  independent native databases against identical, hash-verified application source.
  The initial batches recorded 279 passes and four failures after 189-208 second
  delays. Three failed in setup and one in a final list read, with missing `items`
  in the response. Expired 60-second signed test contexts are a likely explanation,
  but those logs do not retain the response needed to prove the cause.
- Each of those four tests passed twice on native reruns with unchanged application
  code. The final four-test rerun also passed model parity and the complete migration
  round trip. There are no unresolved failing tests. This is combined batch/rerun
  evidence, not a claim that a single full-suite invocation passed without retries.
- Combined coverage is 96.37096774193549% (6,746/6,912 lines and 1,141/1,272
  branches); every domain module exceeds the 90% floor. The verifier confirms the
  complete module partition, all test outcomes, resolution of every initial failure
  and unchanged application hashes before combining the four batches and final
  rerun. Earlier interrupted/diagnostic runs are excluded from final coverage.
- Local evidence is retained under `.test_artifacts/accounting-finance-`: batch
  logs 1-4, `retry-native.txt`, `verified-coverage.json`,
  `identity-conversion-native.txt` and `platform-tests.txt`. Reconcile again with
  `.venv/Scripts/python.exe ../../.test_artifacts/verify_accounting_finance_coverage.py`
  from `apis/accounting`.

## Deferred and external work

Billing/Payments applications and Catalog's signed tax-evidence producer hookup are
external production integration gates. Accounting provides the source/settlement APIs,
versioned event contracts and signed evidence intake now. UI, special calendars,
annual closing/carry-forward, unrealized FX revaluation and cost centres are deferred.

No business database was used for verification. Existing Catalog/product custom-field
work is independent and preserved. Publishing/deployment are separate from this
implementation; the prior publication covered the earlier master/address work.
