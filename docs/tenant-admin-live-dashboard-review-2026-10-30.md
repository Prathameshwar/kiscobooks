# Tenant admin #14 implementation review

The company overview now reads Reports' latest verified immutable company source.
It displays cash/bank, net customer/supplier balances, posted income/expenses and
a bounded daily series. The customer control reads current Accounting parties and
opens their native record. Dates, currency and source freshness remain visible.

Four API tests pass both in the ordinary fixture suite and on disposable native
MySQL. They verify independently expected nonzero totals (cash 180, receivable 80,
income 200, expenses 40), exact decimal strings, no-store responses, tenant/company
isolation, field-read refusals and unavailable sources. Twenty-three affected
Console tests and TypeScript pass. OpenAPI and generated client checks pass.
Six live UI/API checks pass across retail, services and distribution: displayed
zero-effect totals agree with the actual sources, refresh returns the same scoped
view, and native customer search opens the correct record.

Current QA source coverage begins October 1, 2026, inside the selected financial
year; the UI identifies unavailable earlier history. These are snapshot dates,
not a claim that every earlier transaction is present. Source identity and UTC
timestamp allow readers to identify changes excluded by the frozen cut.

Manual simplification and security/correctness review checked complete-input
authority, signed current company context, tenant-filtered SQL, bounded result
size, decimal arithmetic, read-denies, fail-closed client validation and stale
company/year payload refusal. An initial aggregate subquery was rejected by the
shared tenant filter; the final query preserves the native ORM source instead
of bypassing that filter. No remaining defect was identified in this slice.
The named `/simplify` and `/security-review` commands are unavailable here.

Live populated money/invoice reconciliation still belongs to C1/C2 acceptance.
The overview does not fabricate invoice, stock, risk or compliance statistics.
No application database mutation or financial release activation was performed
for this read implementation.
