# Account opening review implementation

User approved the six-phase review plan on 2026-10-29.

1. Guard native opening posting preparation and commit against closed later books.
2. Pin worksheet edit baselines and distinguish new/replacement/resume selection.
3. Align period readiness, reconciliation and field/command permissions.
4. Complete native prepared-intent cancellation, reversal and replacement recovery.
5. Finish document validation, owner handoffs and large-opening progress.
6. Verify the lifecycle, MySQL behavior, contracts, UI and correctness/security rules.

Use existing Accounting batches, journals, permissions and immutable evidence. Add
regressions before fixes. Preserve concurrent work and local paths. No commit,
publication, live financial data changes or admission activation is authorized.

## Evidence

All six phases are implemented and verified within the limits below.

- Added failing regressions before period, conflict, document-permission, native
  recovery, immutable-revision and missing bank-page fixes. The legacy opening
  posting path reproduced the same later-closed-book gap and is covered by the
  shared native posting guard.
- The five initial period/reconciliation regressions passed after the guard fix.
- Console account-opening suite: **97 passed in 9 files**, including explicit
  predecessor-linked replacement, initial-registration conflict/reload, native
  field denial and exact correction retries. A bank-page test initially expected
  a shorter accessible back-link name; its assertion now matches the shared
  navigation control's accessible name.
- Focused recovery lifecycle/security/abort follow-up: **3 passed** on SQLite.
- Final capture-metadata integration checks: **3 passed**, proving finance
  management can capture and prepare without journal-post authority, while native
  posting is denied and native reference write-denies remain effective. The
  metadata/domain follow-up also passed **28 tests** before the integration case
  was added. Generic open-item CRUD metadata has no create fields; the opening
  metadata now exposes typed capture permissions under the existing native rules.
- Related Reports opening classification/YTD/unknown-age tests: **10 passed**.
- Migrated disposable MySQL suite: **51 passed**, including native company-opening
  concurrency, historical FX, YTD provenance, unknown-date on-account settlement,
  clearing chunks, partial posting/correction, permissions and immutable evidence.
  A second fresh-schema run of the final recovery changes: **3 passed**, including
  prepared-reversal cancellation and authority/field/company/tenant restrictions.
- The broad SQLite run had **50 passed** and one failed concurrent-create case:
  SQLite ignores the native company row lock and produced two integrity errors.
  The race is now explicitly MySQL-only, consistent with existing native-race
  tests; its classification check skips on SQLite, and the actual race passed in
  the native run. Production transaction handling was not weakened for SQLite.
- Final focused UI follow-up after the immutable-read typing correction:
  **29 passed in 3 files**; the final reversal confirmation/bank page follow-up
  also passed **6 tests**. Earlier Console TypeScript and final generated-client
  TypeScript checks passed. The last full Console recheck reports three type
  errors in concurrently edited `mfes/packages/ui/src/components/EntryGrid.tsx`
  (419, 435, 458): union-specific `index`/`key` properties are rejected by
  `Omit<Chase, 'before'>`. No account-opening file has a reported type error.
  That unrelated shared file was preserved; the full Console check is not green.
- Accounting OpenAPI and generated-client checks passed; **8 client transport
  tests** passed. Ruff passed for affected Python files and strict mypy passed for
  eight affected Accounting modules. Scoped whitespace validation passed.
- Live browser review could not connect because the Console server on 4320 is
  stopped. An isolated headless Edge harness then exercised the actual client
  components with fixture owner responses: save, draft preparation, native posting,
  reversal creation, reversal posting and predecessor-linked replacement entry.
  All **6 theme/viewport checks** (light/dark/ledger, 1440/390px) passed with no page
  errors or document overflow. The mobile recovery screenshot was inspected.
- Both MySQL runners migrated random schemas through existing Accounting head
  0222 and dropped them in `finally`. The loopback server started for verification
  was shut down; pre-existing schemas were preserved. Browser harness servers also
  shut down after each run. No live opening or admission state was changed.

## Review scope

The final security/correctness review covers company/tenant and field isolation,
private reads, immutable revision ownership, exact retries, current period checks,
native reversal dependencies, durable abort/confirmation and reporting continuity.
No new model, migration, permission key, event contract or dependency is needed.
OpenAPI and the generated Accounting client include the recovery read contract.

The `/simplify` and `/security-review` slash commands are unavailable in this
session. Their required review areas were checked manually against CLAUDE.md
sections 5 and 6. Findings from implementation review (immutable read/version
pairing, direct-selection loading order, cancellation without period authority,
prepared-reversal recovery, explicit reversal confirmation, company-keyed bank
state and the separation of capture metadata from generic CRUD/post authority)
were addressed. No
remaining findings were identified in the changed paths.

Native tests use real disposable MySQL transactions with existing Identity service
boundary test doubles. Browser writes use isolated fixture responses. No new live
authenticated financial workflow or full-repository coverage run is claimed.
Changes remain local; nothing was committed or published.
