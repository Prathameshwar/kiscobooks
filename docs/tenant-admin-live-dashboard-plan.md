# Tenant admin #14: live company overview

The current overview and customer search build sample data. Replace them with
scoped owner reads, preserving exact decimal strings and company display settings.

1. Define one Reports read contract over a verified immutable source cut and an
   explicit covered posting-date range. Return source identity/freshness, currency,
   supported totals and bounded series. Apply the existing financial-report and
   object/field authority rules. Unknown history or unsupported source families
   must be visible as unavailable, rather than invented zero balances. Reports
   remains the read owner; no new service, datastore or direct application DB writes.
2. Add failing scope, readiness, decimal/reconciliation and bounded-query tests;
   implement the aggregate over native report source views. Regenerate OpenAPI and
   the versioned client. Use verified zero-effect QA sources initially; populated
   invoice/money acceptance retains the separate C1/C2 activation evidence.
3. Wire request-scoped overview loading and native Accounting customer lookup.
   Remove sample customers, figures, risk and compliance entries. Preserve the
   shared formatting, keyboard controls, recovery states and source-date notices.
   A current customer absent from the frozen source requires a fresh snapshot.
4. Exercise all three QA company profiles; verify empty, unavailable, retry,
   changed-company/year/customer and permitted-source behavior. Review security,
   simplify the changed paths, fix findings and update reusable evidence/TODO.

This plan refines the already authorized High-complexity sequence. It does not
activate financial execution or select new statutory/rendering policies.

## First supported contract

Use verified native daily-ledger and as-of open-item projections for cash/bank,
net customer/supplier balances and posted income/expense activity. Select the
current company and retained fiscal year explicitly. Default the activity range
to the later of year start and retained coverage; report both dates and identify
incomplete earlier history. Explicit dates before retained coverage are refused.
Do not call these income figures invoicing, and do not invent risk/compliance
scores or stock/invoice statistics. Source timestamp and identity remain visible.
Queries return at most one row per account/day plus a bounded daily series; they
aggregate in SQL rather than materializing transaction histories in HTTP.

The customer control uses Accounting's actual customer-party lookup and opens the
native customer ledger. Company totals remain clearly company-wide. Invoice and
populated collection features continue with the selected owner/release work.

## Extended contract (2026-11-01)

The presentation was redesigned in [business-overview-redesign-plan.md](business-overview-redesign-plan.md)
and the Reports read gained additive fields, still one scoped read over the same verified cut:
`position` (closing cash plus bank per day), `receivables` / `payables` (gross, advances, net, overdue,
six due-date buckets as of the period end, and the five largest balances), `top_expenses` and
`other_expenses`. Every breakdown reconciles exactly to `totals`; the console re-verifies that and
refuses a response that does not. `overdue` is gross of advances, so the page words it as "overdue
bills". Authority is unchanged: every contributing read permission is demanded, so a caller who may
not read party names gets a 403 for the whole overview rather than masked rows.

