# Business overview redesign — live todo

Plan: [business-overview-redesign-plan.md](business-overview-redesign-plan.md). Decisions (2026-11-01):
P3 authorized ("proceed what is best fit"); §8 defaults accepted (YTD default, no tabs, expenses-only
"Where money went", refresh links to the report workspace). Nothing committed or published unless
asked. Other agents have unrelated uncommitted work in this tree — never stage or revert it.

## P1 — Shared UI (`mfes/packages/ui`)
- [x] `GroupedBarChart` + legend (slot colours, table twin, empty/negative/zero); shared `barPath`/`clamp` moved to `lib/chart-geometry`
- [x] Overview rules added to `data.css` / legend to `chart.css` instead of a new stylesheet (no new import wiring); tokens only
- [x] Export from `index.ts`; 15 tests; `design-system.md` §5.3, decision 87, dated section; ui version 0.1.47 → 0.1.48

## P2 — Overview page on existing data (`mfes/apps/console`)
- [x] Replaced by `useOverviewFormat`: config symbol when currencies match, ISO code otherwise (reason for the old forcing was not recorded; the guard keeps its safety)
- [x] `lib/overview-periods.ts` (presets, clamp, bucketing, fixed-decimal) — 33 unit tests
- [x] `lib/use-overview.ts` retains prior data while refetching; anchor read once for non-default presets
- [x] `OverviewView` + `CompanyOverview` container; `OverviewKpis`, `OverviewActivity`, `OverviewLookup`, `OverviewStates`
- [x] `?period=` URL param (allow-listed, `history.replaceState`)
- [~] Tests: states, locale, period, page done (27 + 33); 375px browser layout test still to add (P5)

## P3 — Reports additive contract (`apis/reports`)
- [x] Failing tests first (invariants, tenant isolation, 401/403/409/422, party-name denial, bounds)
- [x] position / receivables / payables / top_expenses / other_expenses
- [x] Resolve payable sign convention (see notes) — existing `net_payable` is correct, no bug
- [x] OpenAPI + `clients/api-client/src/reports.d.ts` regenerated; ruff + mypy

## P4 — Remaining cards (console)
- [x] Ageing card (+ toggle), people card (+ toggle, ledger search in the body), expenses card
- [x] KPI overdue footnotes (worded "overdue bills": overdue is gross of advances), cash sparkline, `verifyOverview` reconciles every breakdown
- [x] Tests per card (populated, empty, toggle, gating) + 12 verifier refusals

## P5 — Verification
- [x] Updated `docs/testing/tenant-admin/verify-live-overview.cjs` and `review-ui.cjs` for the new structure (live run needs the QA stack: not executed here)
- [x] Fixture-driven browser test, 3 scenarios × 4 widths (1440/1024/768/390) × 3 themes — passes, screenshots in `.test_artifacts/overview-*.png`; static `preview.html` generated from the real components
- [x] Contrast: no new colour tokens; legend/ink text on tokens, warn text paired with glyph + word. Focus: shared controls. Chart tick scale checked >0.7 on phones

## P6 — Review and cleanup
- [x] §5/§6 walk, simplify pass, independent security/correctness review (findings and dispositions below), mutation checks (25 front end, all killed after 3 survivors were fixed with tests; 13 backend, all killed)
- [x] Removed unreachable sample code: `Dashboard.tsx`, `Customers.tsx`, `lib/customer-search.ts`, `lib/dashboard.ts` and their 4 test files (`/customers` already redirects to the party directory), plus `.console-customer-filter` / `.console-tabpanel` CSS; `preview.html` regenerated
- [x] Docs and decision logs; plan §9 ticked; design-system decision 87 and dated section; live-dashboard plan notes; README preview note
- [x] Final report (real test numbers, anything unfixed)

## Notes / findings

### P3 notes (Reports overview contract)

New fields on `GET /v2/companies/{id}/overview` (additive; every amount is a scale-4 decimal string):
`position[{date, cash_and_bank}]` (same dates as `series`), `receivables` / `payables`
`{gross, advances, net, overdue, buckets{current, days_1_30, days_31_60, days_61_90, days_over_90, unknown}, parties[≤5]{party_id, name, outstanding, overdue}}`,
`top_expenses[≤5]{account_id, name, amount}`, `other_expenses`.

- **Sign convention (verified, no bug):** `DEBT` is the *bill* side for both roles (customer invoice, supplier
  bill) and `CREDIT` the unapplied/advance side — `controls()`' `positive` flag is the ledger orientation, a
  different thing. So `totals.net_payable` is already positive when the company owes suppliers; fixture data
  (bills 900 + 250, advances 130) gives `1020.0000`, and the source reconciles to the ledger.
  `receivables.net == totals.net_receivable` and `payables.net == totals.net_payable` by construction
  (the old receivable/payable query is replaced by the ageing query, so no extra statement).
- **Overdue is gross:** sum of the four overdue buckets of *bills*, before unapplied credit (same as the AGING
  report). A party or company can therefore show `overdue` larger than `outstanding` when it holds an advance
  (fixture: Customer 1 owes 650 net, 700 of it overdue). Word the UI as "overdue bills", or cap at outstanding.
- **Party names / masking:** not needed and not implemented. `authorize()` already demands *every* input
  permission including `accounting.party.read` and `accounting.account.read` and refuses any read-deny policy,
  so the whole overview is 403 for a caller who may not read names; tests assert a 403 with no names in the
  body for each denial. A masking branch would have been dead code. The name is the ledger account's name
  (as in the AGING report); `party_id` is the party's own id taken from the account row.
- **Query shape:** ageing is one grouped read over the as-of open items (shares `bucket_conditions()` with
  AGING), top parties are one `ORDER BY … LIMIT 5` read per role, top expenses one grouped read; position
  folds into the existing daily-series read plus an opening column in the cash/bank read. Aggregate
  statements: 6 before, 9 after (test pins ≤ baseline + 3). A window function was rejected — the session
  tenant guard refuses a statement whose columns clause has no ORM entity.
- **Tests:** `tests/test_company_overview_breakdowns.py` + `tests/overview_fixture.py` (expected values come from
  the journal specification and the reference AGING engine, never the code under test). Mutation checks (8):
  overdue includes current, opening effects counted as expenses, missing positive-net filters, payable sign,
  opening off by a day, ascending parties, top six — all killed (two needed a stronger fixture first).
- **Not run:** native MySQL execution (`tools/verify_mysql.py`) — no disposable server at 127.0.0.1:13396 and
  the open 3306 server was deliberately left alone. The `GROUP BY role` over a JSON path reuses the pattern
  `aged()` already ships.

### P6 review notes

Independent reviewer (read-only, fresh context) found no cross-tenant leak, authorization gap, float on
money or injectable output. Ten findings; dispositions:

| # | Finding | Disposition |
|---|---|---|
| 1 | "Where money went" could disagree with the Expenses tile when an expense ledger has a credit balance (negative `other_expenses`, row hidden, shares clamped) | Fixed: the row shows whenever non-zero, shares are of the positive rows, schema docs say it may be negative, backend and front-end tests added |
| 2 | Top parties grouped by ledger account, so one party with two ledgers split its balance and duplicated a React key | Fixed in Reports: grouped by `party_id`, named from the party fact; verifier now refuses duplicates |
| 3 | "This quarter" wrong for a fiscal year not starting on the 1st (and month-end overflow) | Fixed: latest quarter start not after today, month-end clamped; tests |
| 4 | Ageing bucket edges untested | Fixed: every boundary pinned in real SQL |
| 5 | Request cost: `positions()` aggregated several times; extra default read for a non-default first load | Not changed: bounded (series ≤ 367, top 5, role group 2), recorded here for capacity work |
| 6 | Verifier gaps (uniqueness, positivity, null rows threw a TypeError) | Fixed: all malformed payloads are the same 502 refusal |
| 7 | `choose()` dropped other query parameters and the hash; `initialPeriod` read only at mount; cached "today" across midnight | Fixed the first; the others are accepted (the page remounts per company/year) |
| 8 | Axis dates use fixed `dd MMM` / `MMM yyyy`, not the company format | Accepted, documented (a label for a bucket, short on purpose) |
| 9 | `overdue` is gross of advances; negative nets still labelled "owed by"; non-source 409s offered "refresh sources" | Fixed: "overdue bills" wording, "advances exceed bills" footnote, only source conflicts get the prepare-figures step |
| 10 | Dimming during refresh dropped contrast; Refresh was `disabled` while focused | Fixed: "Updating…" status instead of dimming, `aria-disabled` keeps focus |

### Evidence at close

- `@janso/ui`: 2302 tests, all passing on the final run after the two CRLF-sensitive style tests were repaired
  (my scripted edits had converted `data.css` to CRLF; normalised and recorded in memory).
- `@janso/console`: full suite 6262 tests; with the machine busy, 56 failed in 19 files. Re-run with limited
  concurrency, 16 of those files pass and **5 tests in 3 files still fail** — `product-price-setup`,
  `configuration-navigation-review`, `accounting-configuration-ui`. The same five fail identically on a
  clean extract of committed HEAD, so they are pre-existing and unrelated to this work.
- Reports: overview + open-items suites 30 passed; ruff, ruff format, mypy strict clean on the changed files;
  OpenAPI export check and TS client regenerated. Full reports suite (fork run, before the review fixes):
  797 passed, 6 failed, 6 skipped; the same six fail on HEAD (`test_money_reports`, `test_native_bank` x2,
  `test_report_navigation` x3).
- Not run: the authenticated live QA loop (`verify-live-overview.cjs`, needs the QA stack) and native MySQL
  execution of the new aggregates (no disposable server; the `GROUP BY role` over a JSON path reuses the
  pattern `aged()` already ships).
