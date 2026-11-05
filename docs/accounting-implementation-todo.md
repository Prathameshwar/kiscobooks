# Accounting masters implementation

Current planning reference (2026-09-14):
[master completion plan](accounting-masters-completion-plan.md), approved and implemented.
The [live completion todo](accounting-masters-todo.md) records current checks and both final
reviews. The phase notes below retain historical evidence from before this completion; their
unchecked feature boxes are superseded by the live todo. Publication remains separately authorized.

Approved scope: dedicated Accounting API; one account table for all ledger kinds;
shared party masters; 29 business tables; API and database only. Billing and Catalog
consumers, transaction posting, credit reservations, settlement, opening posting, and
financial-year closing are explicitly deferred by the user.

Revised 2026-09-13: administration screens are removed from scope. The chart of
accounts follows Tally Prime's group and ledger model. Generated OpenAPI and the
typed client stay in scope — they are API contract artifacts, not user interface.

## Status of the original phases

AM0, AM1r and AM2r are complete. The September 14 repairs passed 81 tests on native MySQL
at 94.92% coverage, with migration parity/round trips, Ruff and strict source mypy clean.
The later approved six-phase completion implements AM3r-AM6r master additions, typed export
rows and test/tool typing. Current verification and review evidence belongs in the live todo
and [completion review](accounting-masters-completion-review.md), rather than rewriting these
historical phase results. Publishing and deployment were not part of the local implementation.

- [x] AM0: Record schema, ownership, API, security, and delivery contracts.
- [x] AM1r: Foundation completion, generated contract, run script, native database run.
- [x] AM2r: Fix the failing import, seed and lifecycle defects; clear Ruff and mypy.
- [ ] AM3r: Tally Prime group parity — 28 predefined groups, behaviour flags, aliases.
- [ ] AM4r: Tally Prime ledger parity — inventory, rounding, ordering, duty type.
- [ ] AM5r: Verify address, registration and contact coverage against Tally's mailing model.
- [ ] AM6r: Contract artifacts, typed client, permission catalogue, export field denies.
- [ ] AM7r: Verification, simplification review, security review, docs, publication.

## AM1r: foundation completion

- [x] `apis/accounting/README.md`, mirroring `apis/catalog/README.md`.
- [x] `tools/export_openapi.py` and a committed `apis/accounting/openapi.json` —
  121 paths, 154 schemas.
- [x] `start/win/start-accounting.ps1`, mirroring `start-notification.ps1`. Port 8011;
  no port allocation is documented anywhere, so this took the next one after
  notification's 8010.
- [x] Run `tools/verify_mysql.py` on a loopback server: fresh upgrade to head,
  `compare_metadata` empty, downgrade to base. The 37 existing revisions have never
  run on MySQL, and autogenerate does not see generated columns, `VARCHAR` length,
  index renames or collation.
- [x] Close the service's own coverage gate. `pyproject.toml` sets
  `fail_under = 90` for the whole service, which is stricter than the repository floor
  of 90% on `domain/` alone, and the service sat at 84%. The gap was the endpoint matrix
  that §7 already mandates, absent for every resource no scenario test touches.

There was no `nginx/` directory when AM1r began, so Accounting's own deployment wiring is
the README and the start script only. During the phase a concurrent actor added an
uncommitted `start/win/` orchestration suite that includes `conf/bill.conf`, which routes
`/accounting/` to `127.0.0.1:8011` — the same port chosen here — and a `write-envs.ps1`
that supplies the encryption key. Those files are not Accounting's to edit; the ports
agree, and AM6r should confirm they still do rather than re-deriving them.

Two scope notes recorded rather than silently absorbed:

- `mypy` covers `src` only. Every test file in this service is unannotated, so the wider
  `mypy src tests tools` that catalog's README advertises reports 103 pre-existing errors
  across five files. Annotating the test tree is listed under AM7r, not smuggled in here.
- `dbs/accounting` is outside the Ruff scope: revisions carry generated DDL as one
  verbatim string per statement, and reflowing them is how a `VARCHAR` length or a
  collation changes unnoticed. `dbs/catalog` has the same 127 findings, so this is the
  repository's existing state, not an Accounting regression.

## AM2r: fix the failing paths

Write the failing test first for each defect, confirm it fails for the stated reason,
then fix. Starting suite: 3 failed, 19 passed, 81% coverage.

- [x] `POST /imports/preview` returned `invalid_record` for a party the test expected
  `POST /parties` to accept. **Not a defect.** A traceback showed
  `ValidationError: legal_name / Field required`, and the same body posted directly to
  `/parties` also answers 422. The import path does not diverge from the command path;
  the test payload omitted a required field. Corrected the payload.
- [x] Seed account code is `CASH_MAIN` under group `CASH`; two tests look up an account
  coded `CASH` and raise `StopIteration`. Fix the tests and change them to resolve
  seeded rows by `system_key`, so they stop coupling to template codes.
- [x] `POST /party-roles/{id}/deactivate` returns 200 where 409 is required. A role
  backing an active `PARTY` account must not retire — this is invariant 12, not a test
  expectation. `guard_retirement` walked `spec.references` only, and no resource declares
  a foreign key to `party_role`: `account.party_role`,
  `party_accounting_policy.role` and `party_credit_policy.role` all name the role *by
  value*. Added `guard_role_retirement`, which checks accounts and both role-scoped
  policies, with a regression test for each branch and for the must-still-succeed path.
- [x] mypy strict: `tasks/validation.py:100` (`Record` has no `account_id`) and
  `api/workflows.py:65`. The export page keeps `Page[dict[str, Any]]` rather than gaining
  a typed row model: `resource` is a path parameter spanning all 28 masters, so no single
  concrete item model can describe the page. Recorded in a comment at the route.
- [x] Ruff: 19 errors — 14 `E501` in `tests/test_workflows.py`, 4 in `models/masters.py`
  and `tasks/commands.py`, 1 `UP038` in `tasks/imports.py`. The four long strings are
  `CHECK` constraint bodies, split by implicit concatenation with byte-identical values so
  `compare_metadata` stays empty; confirmed by the native MySQL run.
- [x] Field policy raised `TypeError` — a **500** — instead of failing closed, when a
  policy carried a non-string value. `rules()` decides validity with `x not in
  frozenset(...)` and `uuid.UUID(x)`, and both raise on the wrong type. Found while
  writing the policy tests; a regression test asserts 403 and an error-envelope-only body
  for seven malformed shapes. Fixed by checking the shape is all strings first.

## AM3r: Tally Prime group parity

The seed has 25 groups; Tally Prime defines 28 — fifteen primary and thirteen sub.

- [ ] Add `BRANCH_DIVISIONS` (LIABILITY), `SUSPENSE` (LIABILITY) and `MISC_EXPENSES`
  (ASSET) as primaries; re-parent `RESERVES` under `CAPITAL`, matching Tally's
  Reserves & Surplus. Bump the template `VERSION` and update the install counts the
  tests assert.
- [ ] Keep the five heads. Tally's four natures map in and out by folding EQUITY into
  LIABILITY; hold that mapping in `domain/` beside the head rules, not in the seed.

`account_group` currently carries only code, name, head, parent, system key and status.
Every Tally group behaviour attribute is missing, and these are what let a chart of
accounts produce a correct Trading Account, Profit & Loss and Balance Sheet later. One
DDL statement per revision, so eleven revisions:

| Column | Tally attribute | Purpose |
|---|---|---|
| `is_primary` | the fifteen primary groups | primaries are never re-parented |
| `is_reserved` | predefined groups | never deleted, nature never changed |
| `affects_gross_profit` | direct/purchase/sales, stock-in-hand | trading versus P&L split |
| `is_revenue` | `IsRevenue` | revenue versus balance-sheet placement |
| `is_deemed_positive` | `IsDeemedPositive` | debit-positive sign convention |
| `sub_ledger_behaviour` | "behaves like a sub-ledger" | condensed or detailed reporting |
| `nett_balances` | "nett debit/credit balances" | net one side instead of both |
| `used_for_calculation` | "used for calculation" | taxes and discounts |
| `allocation_method` | purchase-invoice allocation | `NOT_APPLICABLE`/`BY_QTY`/`BY_VALUE` |
| `sort_order` | | report presentation order |

- [ ] New table `account_group_alias`; Tally groups carry aliases and only accounts do
  here. This takes the business tables from 28 to 29.
- [ ] `domain/rules.py`: extend `hierarchy()` so `nature`, `is_revenue` and
  `is_deemed_positive` inherit from the primary ancestor and cannot diverge; reject
  re-parenting or nature changes on reserved groups; allow `affects_gross_profit` only
  under an INCOME or EXPENSE primary, or on stock-in-hand.
- [ ] Schemas, `field-set`, and filter/sort allowlists per `api-conventions.md`.
- [ ] Tests: flag inheritance, reserved-group protection, updated install counts, and a
  cross-tenant isolation test for `account_group_alias`.

## AM4r: Tally Prime ledger parity

Five revisions, one statement each:

- [ ] `account.inventory_affected` — Tally "inventory values are affected".
- [ ] `account.rounding_method` and `account.rounding_limit` `DECIMAL(19,4)` — Tally
  duty-ledger rounding.
- [ ] `account.sort_order`.
- [ ] `account_tax_profile.duty_type` — GST, VAT, TDS, TCS, CESS, EXCISE. Classification
  only; the rate stays in the Catalog tax master.
- [ ] Extend `allowed_head()` for the new combinations and add an explicit kind against
  group-nature matrix test.

Deliberately not added: a per-account `bill_by_bill` or `credit_period_days`.
`party_accounting_policy.bill_wise` and `party_credit_policy` already own those with
dated intervals; duplicating them onto `account` breaks rule 4.12 and gives an invoice
two answers to one question.

## AM5r: address and contact coverage

Parties, addresses and contacts are already richer than Tally's flat mailing block, so
this phase verifies rather than builds.

- [ ] Confirm one default address per purpose is enforced.
- [ ] Confirm a `SHIPPING` address in another state resolves to that state's GSTIN
  through `party_registration_address`, and add the consistency test.
- [ ] Add `party_contact.fax`, `website` and `email_cc` only if the user asks; Tally
  carries them and nothing here needs them yet.

## AM6r: contract artifacts and permissions

- [x] Register Accounting OpenAPI in client generation, export `createAccountingClient`,
  and verify generated types and retry transport (2026-09-14).
- [x] Enforce current field-policy read denies in exports and history, including
  conditional native types, structural identity and protected changed-field names.
- [ ] Replace `Page[dict]` exports with individually typed export rows.
- [x] Document all 22 existing `accounting.*` permission keys and existing system-role
  grants in `docs/roles-permissions.md`. `seeds/roles` already delegates to the same
  Identity system-role catalogue; no duplicate seed or new grants were required.

Out of scope: `mfes/apps/console/` screens and any web or mobile work.

## AM7r: review and close

- [ ] `uv run pytest --cov` green, with the floors held. Met as of AM2r at 94.02% and both
  `domain/` modules at 100%; re-run after AM3r-AM6r add columns, seeds and routes.
- [ ] Ruff and mypy strict clean.
- [ ] Annotate the test tree so `mypy src tests tools` passes. Five files carry 103
  pre-existing errors; this is the last place the service is looser than catalog's README.
- [ ] Every new revision read line by line, with a working `downgrade` or a stated reason.
- [ ] `/simplify` and `/security-review`; report findings including "nothing".
- [ ] Update `accounting-design.md` — table count 28 to 29, Tally alignment, decision log.
- [ ] Commit the service, then `git publish --dry-run` and `git publish`. No longer
  untracked: a concurrent commit `23c7417` during the AM1r session picked up
  `apis/accounting/`, `dbs/accounting/`, `openapi.json` and `start-accounting.ps1`. The
  AM1r/AM2r edits after it, and `README.md`, are still uncommitted.

## Still deferred

Journals and voucher types, opening balance posting, financial-year closing, credit
reservation and live enforcement, tax computation, transaction-level bill-wise
allocation, cost categories and cost centres, and all Billing and Catalog consumers.

## Verification evidence

Record commands and actual results here as phases finish. Native database and broker
checks must be distinguished from SQLite/unit checks. Do not claim deferred consumers
or financial workflows are implemented.

- Pure domain rules: 13 tests passed (hierarchy, intervals, schedules, account types).
- Foundation API checks: 2 tests passed (authentication, setup replay, audit, groups).
- Master workflows: 4 tests passed, 3 failed — imports preview, mapping publish/export
  history, and role retirement. See AM2r.
- Whole suite before AM1r/AM2r on 2026-09-13: `3 failed, 19 passed`, 81% total coverage.
  Ruff 19 errors, mypy strict 2 errors.
- 37 one-statement revisions generated: 28 masters, 2 workflow evidence tables, 3 shared
  outbox/idempotency/message tables, 4 reference replicas.

After AM1r and AM2r, on 2026-09-13, from `apis/accounting`:

- `uv run pytest --cov` → **44 passed, 94.02% total coverage, exit 0**, 3m52s. The
  service's `fail_under = 90` gate now passes. `domain/rules.py` and
  `domain/reference.py` are both 100%; `api/masters.py` 60% → 99%, `tasks/reads.py`
  64% → 100%, `tasks/access.py` 77% → 100%, `api/workflows.py` → 100%.
- `uv run ruff check src tests tools` → **All checks passed**.
- `uv run ruff format --check src tests tools` → clean, 46 files.
- `uv run mypy src` → **no issues in 36 source files**.
- `uv run python tools/export_openapi.py` → `openapi.json`, 121 paths, 154 schemas.
- **Native MySQL, not SQLite**: `PYTHONPATH=. uv run python tools/verify_mysql.py` against
  a disposable loopback server on port 13396 → **passed on MySQL 9.6.0**. All 37 revisions
  upgrade on a fresh random `accounting_test_` schema, `compare_metadata` reported no
  model/migration drift, native setup + template install + list + concurrent idempotency
  passed, and downgrade-to-base then re-upgrade round-tripped. The tool created and
  dropped only its own schema. Docker is not installed on this machine.

Two coverage notes worth keeping:

- The 187-assertion endpoint matrix is written as seven whole-resource sweeps, not as
  `parametrize` over 28 resources. Parametrizing rebuilt the schema 196 times and took
  17m12s for the same 94.02%; sweeping takes 3m52s. Each sweep collects every failure and
  names the resource, so per-resource diagnostics survive. A suite nobody runs before
  pushing is not a backstop.
- `seeds/reference.py` is at 0%. It is a 12-line `__main__` entry point that requires a
  live database URL, so it is exercised by the native run above rather than by pytest.

## Workspace preservation

The workspace already contains unrelated Catalog, shared UI, and documentation edits.
Preserve them. Accounting changes must not implement Billing/Catalog consumers or
overwrite their concurrent work. Stage only Accounting files when publishing, through
the repository's `git publish` mapping.

## Review findings

The 2026-09-14 review of the current implementation is recorded in
[accounting-review-20260914.md](accounting-review-20260914.md). All 17 reproduced
findings and the gateway, publisher and generated-client gaps received repairs and
regression coverage. Additional final-review policy, metadata and environment-rerun
edge cases were reproduced and repaired. This does not mark the future AM3r-AM5r
Tally additions, typed export rows, test-tree annotation or publication complete.

### September 14 repair checklist

- [x] Consistent field policy across reads, writes, initialization, templates and history.
- [x] Preserve master classification, dependency eligibility and effective history.
- [x] Collision-safe template upgrade and bounded, backward-compatible import receipts.
- [x] Identity policy/layout authoring and current scoped subject resolution.
- [x] Authenticated gateway, scoped audit publisher and Accounting TypeScript client.
- [x] Native verifier binds migrations to its disposable schema, with optional full suite.
- [x] Final manual simplification/security review; named slash tools are unavailable
  in this session. Evidence and remaining limitations are in the linked report.
- [x] Final native MySQL suite: **81 passed**, **94.92% coverage**, all 37 migrations
  upgrade/downgrade/upgrade and model parity passed. Identity's targeted suite: **22 passed**;
  live RabbitMQ: **3 passed**; gateway/Identity bridge, generated clients, Ruff and strict
  source mypy passed. The broader Identity run has two existing Salesperson-role test
  expectation failures, documented in the review rather than hidden by the targeted result.
