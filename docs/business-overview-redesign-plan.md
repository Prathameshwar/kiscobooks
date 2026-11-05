# Business overview redesign — plan

Status: **implemented 2026-11-01** (see the live checklist in [business-overview-todo.md](business-overview-todo.md) and the deviations in §10). The text below is the plan as agreed. Option A was chosen
on 2026-11-01: a professional, restrained, live-data overview that keeps the earlier design's
strengths (KPI band, charts, ranked lists) and removes its invented numbers.

Supersedes the presentation (not the data rules) of
[tenant-admin-live-dashboard-plan.md](tenant-admin-live-dashboard-plan.md). Everything that plan
decided about sources, coverage and "unavailable is not zero" still holds.

## 1. Why the current page fails

| Problem | Cause in code |
|---|---|
| Looks like a form, not a dashboard | Seven `StatTile`s in `janso-form-grid`; no icon, tone, emphasis or trend |
| Explanation outweighs the numbers | Two paragraphs + a notice before the first figure, a second notice after |
| No picture of anything | Time series is a 20-row table of mostly `0.0000` |
| No way to ask a question | No period control, although the endpoint accepts `date_from`/`date_to` |
| Unhelpful when nothing is posted | Zero tiles + zero table instead of saying what to do next |
| Dead end when no source is ready | A warning `Notice` with a retry button |
| Flashes on every change | `useServiceRead` sets `data: null` on each new path |

## 2. Principles

1. **Answer four questions in five seconds:** how much cash do I have, who owes me, whom do I
   owe, am I making money this period.
2. **Only real figures.** Every number traces to a verified Reports source. Unavailable is shown as
   unavailable, never as zero. No sample data in application code — fixtures live in tests only.
3. **Restraint.** Four KPIs, four cards, no tabs. A block earns its place by being actionable.
4. **Reuse before inventing.** `@janso/ui` components and tokens; new reusable pieces go to
   `@janso/ui`, not the app (CLAUDE.md §4). No new colour tokens (chart palette is validated,
   design-system decision 13).
5. **Money is a string end to end.** Client sums use `lib/fixed-decimal.ts` (BigInt), never `number`.

## 3. Page anatomy

```
PageHeader   Business overview          Acme Retail · FY 2026–27                 [INR]
Toolbar      [ Year to date ▾ ]  ⓘ Ledger history starts 1 Oct          As of 1 Nov, 09:14  ⟳
─────────────────────────────────────────────────────────────────────────────────────────────
KPI band     ┌ Cash and bank ━━┐ ┌ Receivables ────┐ ┌ Payables ───────┐ ┌ Net result ─────┐
(4, one      │ ₹ 4,86,200      │ │ ₹ 3,12,000      │ │ ₹ 1,45,500      │ │ ▲ ₹ 92,400      │
 emphasised) │ Cash · Bank     │ │ ⚠ ₹ 48,000 over │ │ ⚠ ₹ 12,000 over │ │ Income · Expense│
│ ~~~sparkline│ │                 │ │                 │ │ ~~~sparkline    │
─────────────────────────────────────────────────────────────────────────────────────────────
Row 2        ┌ Income and expenses ──────────────── P&L → ┐ ┌ Receivables ageing  [Rec|Pay] ┐
(2fr / 1fr)  │  ▮▯ ▮▯ ▮▯ ▮▯ ▮▯ ▮▯ ▮▯ ▮▯  grouped bars     │ │ ₹ 48,000 overdue of ₹ 3.12 L │
             │  ■ Income  ■ Expenses   (weekly)           │ │ Not due        ▰▰▰▰▰▰▱  70%  │
             └────────────────────────────────────────────┘ │ 1–30 days      ▰▰▱▱▱▱▱  18%  │
                                                            │ 31–60 …  61–90 …  90+ …       │
                                                            └───────────────────────────────┘
Row 3        ┌ Who owes you          [Customers|Suppliers] ┐ ┌ Where money went ───── P&L → ┐
(1fr / 1fr)  │ 1 Meridian Wholesale  ₹ 1.2 L  ▰▰▰▰▱ ⚠ over │ │ 1 Rent             ₹ 24,000 ▰▰▰ │
             │ 2 …  (top 5)                                │ │ 2 Salaries …  (top 5 + other)│
             │ Find a customer ledger  [ search … ]        │ └──────────────────────────────┘
             └─────────────────────────────────────────────┘
```

Responsive (existing breakpoints): ≥1100px as drawn; 680–1100px KPI 2-up and cards stacked;
<680px KPI 1-up, toolbar wraps, chart height reduced. No horizontal page scroll at 375px.

### Block rules

- **Toolbar** — period `Select` (Year to date · This quarter · This month · Last 30 days), then a
  muted freshness line with refresh. Three short figure definitions and a report-source link use
  one collapsed "About these figures" `Disclosure`; only *unusual* conditions get a visible chip (history starts
  late). Presets are computed from the response's `date_to` (the company's own "today", never the
  browser clock), clamped to `max(year_start, coverage_start)`, and a clamped preset says so.
  The choice lives in the URL as `?period=` (allow-listed values only) so a link and a reload
  reproduce the view.
- **KPI band** — exactly one emphasised tile (Cash and bank). Tone is always paired with an icon or
  glyph. A tile with no source shows an em-dash, not `0`.
- **Income and expenses** — grouped bars (income = chart-1, expenses = chart-2), legend, title
  states the bucketing. Auto-bucket: ≤31 days daily, ≤120 weekly, else monthly (no control to
  maintain). Keeps the visually hidden table twin.
- **Receivables ageing** — a segmented toggle (Receivables | Payables); one summary sentence, then
  five bucket rows (`ListRow` + `Meter`): Not due, 1–30, 31–60, 61–90, 90+ days; advances shown
  as a separate negative line so the rows reconcile to the KPI.
- **Who owes you / whom you owe** — top five by outstanding, overdue badge, link to the party
  ledger; the existing customer-ledger search moves to the card footer, still gated on
  `accounting.party.read`.
- **Where money went** — top five expense ledgers for the period plus "Other", share meters.
- **Headings:** `h1` page; one visually hidden `h2` per band; card titles are `h3`
  (design-system §7 — no skipped level).

### States (each has a test)

| State | Treatment |
|---|---|
| Loading | Skeleton with the final layout's shape; `role="status"` |
| Refetch (period/refresh) | Previous figures stay and the toolbar says "Updating…" (a polite status for assistive tech; not dimmed, which would drop contrast) — no blank flash |
| No ready source (409) | "Prepare your figures" panel: one sentence + primary action to the existing source refresh in the report workspace (no raw error text) |
| Verified, nothing posted in period | KPIs still show verified balances; the chart card becomes an empty state with permission-gated next steps (opening balances, new voucher); list cards say "nothing outstanding" inline — not four big empty states |
| History starts late | Single dated history chip; period labels and ranges show the available dates |
| 403 no report access | Existing explanation, rendered as an `EmptyState` |
| 5xx / unverifiable payload | `ErrorState` + retry; wrong-company/year payload still refused |

## 4. Where each element's data comes from

| Element | Source | Available |
|---|---|---|
| Cash and bank, receivable, payable, income, expenses, net | `GET /v2/companies/{id}/overview` `totals` | now |
| Income/expenses chart, net sparkline | `series` (daily), bucketed client-side with `fixed-decimal` | now |
| Period selector | `date_from` / `date_to` already accepted (≤366 days, within year, ≥ coverage) | now |
| Cash-and-bank sparkline | closing cash+bank per day | **P3** (additive) |
| Ageing buckets, overdue, advances | `native_open_items.positions()` already computes due dates and balances | **P3** (additive) |
| Top parties by outstanding | same query grouped by account; names from the frozen account facts | **P3** (additive) |
| Top expense ledgers | `ReportDailyBalance` grouped by account, nature = EXPENSE, non-opening | **P3** (additive) |

### Explicitly not on the page (no source exists)

Invoiced/collected counts and top customers by sales, collections at risk, tax and compliance
coverage, stock value. They return only when their owner source lands (invoice/money activation
C1/C2, payment integrations Phase 7, stock reporting #15). The grid uses named areas so a card can
be added later without redesigning the page.

## 5. Phases

Each phase ends with its tests green and the repo working. Nothing is committed or published
unless asked; when asked, only this work's files are staged and `git publish` is used.

**P0 — Agree.** This plan; the three decisions in §8.

**P1 — Shared UI (`mfes/packages/ui`).**
`GroupedBarChart` (two or more series, slot colours only, hover titles, table twin, empty case) and
a small legend part; `styles/overview.css` for the page grid and the few page-level classes (tokens
only, no literals). Tests: geometry for negative/zero/single-series, a11y table, slot colours,
class-coverage and contrast tests stay green. Docs: §5.3 catalogue row, §4.2 page anatomy and a
decision-log entry in `design-system.md`. Load the `dataviz` skill before writing chart code.

**P2 — Overview page on existing data (`mfes/apps/console`).**
Split the 51-line `CompanyOverview.tsx` into a presentational view (props in, no fetching — also
what tests and screenshots render with fixtures) and a thin container; add `lib/overview-periods.ts`
(presets, clamping, bucketing) and a `useOverview` hook that retains prior data while refetching.
Delivers: toolbar, KPI band, activity chart, states, source disclosure, customer-ledger search.
First step: find out why the page forces `display: 'none'` plus an ISO code and keep that
behaviour only if it is deliberate. Tests: every state and branch, period math across year
boundaries and clamps, money in `en` and a non-`en`/Indian-grouping locale, permission-gated
lookup, stale company/year refusal, keyboard operation, a browser layout test at 375/768/1280.
The page is already clearly better here with no backend change.

**P3 — Reports additive contract (`apis/reports`) — needs your go-ahead.**
Extend `GET /overview` with new fields only (existing clients unaffected):
`position` (closing cash+bank per day), `receivables` / `payables`
(`gross`, `advances`, `net`, `overdue`, `buckets{current,days_1_30,days_31_60,days_61_90,days_over_90,unknown}`,
`parties[≤5]{party_id,name,outstanding,overdue}`), `top_expenses[≤5]{account_id,name,amount}` and
`other_expenses`. Aggregated in SQL over the frozen source, at most three extra grouped queries,
each with a `LIMIT`; no transaction history materialised in HTTP. Ageing is as of the period end.
Invariants asserted in tests **and** re-verified by the client: buckets − advances = net =
`totals.net_*`; Σ top + other = `totals.expenses`; last `position` = cash + bank; no float.
No model, migration, permission key, event or new service. Sync table: regenerate OpenAPI and
`clients/api-client/src/reports.d.ts`; extend `verifyOverview`. Party names follow the existing
party-ledger read authority; a denied read yields a masked label, tested.

**P4 — Remaining cards (console).** Ageing, people, expenses, overdue footnotes, cash sparkline,
all through the P2 view. Tests per card: populated, empty, toggle (radiogroup arrow keys), links
encoded, permission-gated pieces.

**P5 — Verification.** Live check on the three QA companies (update
`docs/testing/tenant-admin/verify-live-overview.cjs` for the new structure). Because live QA data is
zero-effect, populated visuals come from the fixture-driven view rendered in light, dark and
ledger at 375/768/1280/1920, with screenshots kept as evidence. Contrast and focus checked per
design-system §2.4.

**P6 — Review and close.** Walk CLAUDE.md §5 and §6; `/simplify`; `/security-review` (report
authority, tenant scoping and party names are in scope); mutation checks on the reconciliation
invariants; delete the unused `Dashboard.tsx`, `dashboard.test.tsx` and the stale `preview.html`;
update this doc, the live-dashboard plan's presentation notes and the decision logs. Final report
with real test numbers and anything not fixed.

Relative size: P1 small, P2 medium-large, P3 medium, P4 medium, P5 small, P6 small.

## 6. Test plan

**Backend (P3)** — per CLAUDE.md §7: happy path against the response schema; 401; 403 without
`report.read`; wrong-company object → 403; invalid/unknown query → 422; replay-safe GET with
`no-store`; returned types are `Decimal`-exact strings; two-tenant isolation for each new
aggregate; no ready source → 409 (not zero); closed-year and clamped-coverage ranges; advances and
unknown-due-date items; party-name read denial; statement count and `LIMIT` bounds. Runs on the
ordinary fixtures and on disposable native MySQL, as the existing four overview tests do.

**Frontend (P1, P2, P4)** — Vitest + RTL, mocked `api-client`: every conditional branch above; the
period selector and URL param; segmented toggles with arrow keys; chart a11y twin; loading, refetch,
409, empty, 403, 422, 500; wrong-company payload; non-`en` locale; permitted vs unpermitted
lookup; no horizontal overflow at 375px (browser test, same pattern as the existing
`*.browser.test.tsx`). Suites to run: `@janso/ui`, `console`, typecheck, `uv run pytest` for reports,
Ruff and mypy strict.

## 7. Security and correctness checklist (applies to every phase)

- No new permission key; endpoint stays deny-by-default on company-scoped `report.read`.
- Tenant filtering stays at session level — new queries use the existing native ORM source, not a
  bypass (the earlier slice's subquery was rejected for exactly this).
- No request-scoped data at module scope; fixtures never imported by app code.
- URL `period` is allow-listed; dates and ids are validated before they reach the proxy; links use
  `encodeURIComponent`.
- Money is never a JS number; display config (precision, rounding, grouping, date format) is read
  from the resolved config, never the browser locale.
- Reads emit no audit event; nothing here changes state.

## 8. Decisions I need from you

1. **Authorize P3** (additive fields on the Reports overview). Without it the page ships P1–P2 only:
   KPI band, activity chart and states, but no ageing, people or expense cards.
2. **Defaults I will use unless you change them:** default period Year to date; no tabs; "Where money
   went" shows expenses only; the "Prepare your figures" action links to the existing report-source
   refresh rather than starting a refresh inline (inline refresh is a later option).
3. **Old sample code.** `Dashboard.tsx`, its test and `preview.html` are removed in P6. The
   `/customers` page still imports sample customers from `lib/dashboard.ts`, so that file stays;
   migrating `/customers` to real parties is a separate follow-up, not part of this work.

## 9. Progress

- [x] Investigation and plan
- [x] P0 plan approved ("proceed what is best fit"), §8 defaults accepted, P3 authorized
- [x] P1 shared chart and styles
- [x] P2 page on existing data
- [x] P3 Reports contract
- [x] P4 remaining cards
- [x] P5 fixture-driven browser verification in three themes and four widths (the authenticated live run needs the QA stack and was not executed)
- [x] P6 review, cleanup, docs — independent review fixed and recorded, mutation checks, dead sample code removed; evidence in [business-overview-todo.md](business-overview-todo.md)

## 10. As built — deviations from the plan

- **No new stylesheet.** The legend and slot rules went into `chart.css` and the page rules into
  `data.css`, so there is no new import to wire and no new package export.
- **Customer lookup moved into the "Who owes you" card**; the interim "Jump to" card was dropped
  once the real cards existed. Its books links are reachable from the card actions and the rail.
- **Axis labels are short** (`05 Oct`, `Oct 2026`) through a new `formatAxisDate` formatter rather
  than the full configured date, which crowded the axis. The legend carries each series' total.
- **A phone draws the chart in a narrower coordinate space** (`width` prop chosen by a media
  query) so tick labels stay legible instead of shrinking with the card.
- **`.janso-chart` is its own clipping box.** The hidden table twin was widening the page on
  phones; this also fixes the latent case in `BarChart`.
- **The page keeps the previous figures while a new period loads** and states, from the data, the
  range it actually covers.
- **Client re-verification:** `verifyOverview` refuses a response whose breakdowns do not
  reconcile to its totals, or whose range is not the one requested.
- **Dead sample code removed:** see the todo's cleanup section.

### Copy simplification (2026-11-02)

The user requested shorter overview explanations. Replace the four paragraphs with
three labelled definitions: balance date/openings, activity dates/exclusions, and
net receivables/payables. Keep freshness in the existing toolbar and limited history
in its dated chip, without repeating them inside the disclosure. Remove explanations
of absent invoicing/stock/risk workflows from the page; their source boundaries remain
documented here. Calculations, sources, permissions and refresh behavior are unchanged.

Verification: **116 overview tests passed**; **6 expanded-disclosure browser checks
passed** at 1440px/390px in light/dark/ledger (screenshots inspected). Task-file
whitespace checks passed. Console typecheck reports unrelated errors in the separately
modified `purchase-api.ts` (optional components/dependencies) and `purchase-calculation.ts`
(duplicate `value`); those files were preserved. No blocking copy or layout finding
remained after manual review. Evidence: `.tools/overview-copy-*.log` and
`.test_artifacts/overview-copy-*.png`.
